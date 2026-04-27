// GELU Activation — Pipelined SystemVerilog Implementation
// Based on algebraic optimization:
//   GELU(x) = 0.5 * x * (1 + tanh(constant_1*x + constant_2*x^3))
//
// Constants (FP64 hex):
//   constant_1 = sqrt(2/pi)          = 0x3fe9884533d43651
//   constant_2 = constant_1 * 0.044715 = 0x3fa2444f2a4d8b4b
//
// Pipeline (5 slots, 1 cycle each):
//   Slot 1: var_1 = x*x
//           var_2 = constant_2 * x
//           var_3 = constant_1 * x
//           var_4 = x >> 1          (0.5 * x)
//   Slot 2: var_5 = var_1 * var_2   (constant_2 * x^3, since var_1=x^2, var_2=c2*x)
//   Slot 3: var_6 = var_5 + var_3   (constant_1*x + constant_2*x^3)
//   Slot 4: PWL   = tanh_pwl(var_6) (piecewise linear tanh approximation)
//           var_7 = 1 + PWL
//   Slot 5: out   = var_7 * var_4   (0.5 * x * (1 + tanh(...)))
//
// Data format: 32-bit fixed point, Q16.16 (1 sign, 15 integer, 16 fractional)
// Instantiate 16x in parallel for throughput.

module gelu #(
    parameter int DATA_WIDTH = 32,              // total bit width
    parameter int FRAC_BITS  = 16,              // fractional bits (Q16.16)
    parameter int PIPE_DEPTH = 5                // pipeline stages
)(
    input  logic                        clk,
    input  logic                        rst,
    input  logic                        valid_in,
    input  logic signed [DATA_WIDTH-1:0] x,
    output logic                        valid_out,
    output logic signed [DATA_WIDTH-1:0] out
);

    // -------------------------------------------------------------------------
    // Constants in Q16.16 fixed point
    // constant_1 = 0.79788456  -> round(0.79788456 * 2^16) = 52261
    // constant_2 = 0.03567741  -> round(0.03567741 * 2^16) = 2337
    // ONE        = 1.0         -> 1 << 16 = 65536
    // -------------------------------------------------------------------------
    localparam signed [DATA_WIDTH-1:0] CONST_1 = 32'sd52261;
    localparam signed [DATA_WIDTH-1:0] CONST_2 = 32'sd2337;
    localparam signed [DATA_WIDTH-1:0] ONE     = 32'sd65536;  // 1.0 in Q16.16

    // -------------------------------------------------------------------------
    // Pipeline valid shift register
    // -------------------------------------------------------------------------
    logic [PIPE_DEPTH-1:0] valid_pipe;

    always_ff @(posedge clk) begin
        if (rst)
            valid_pipe <= '0;
        else
            valid_pipe <= {valid_pipe[PIPE_DEPTH-2:0], valid_in};
    end

    assign valid_out = valid_pipe[PIPE_DEPTH-1];

    // -------------------------------------------------------------------------
    // Pipeline Slot 1:
    //   var_1 = x * x                (x^2, Q16.16: take upper 32 bits of 64-bit product)
    //   var_2 = constant_2 * x       (c2*x)
    //   var_3 = constant_1 * x       (c1*x)
    //   var_4 = x >>> 1              (0.5*x, arithmetic right shift)
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s1_var1, s1_var2, s1_var3, s1_var4;

    always_ff @(posedge clk) begin
        if (rst) begin
            s1_var1 <= '0;
            s1_var2 <= '0;
            s1_var3 <= '0;
            s1_var4 <= '0;
        end else begin
            // Q16.16 * Q16.16 -> Q32.32, take [47:16] for Q16.16 result
            s1_var1 <= (x * x) >>> FRAC_BITS;
            s1_var2 <= (CONST_2 * x) >>> FRAC_BITS;
            s1_var3 <= (CONST_1 * x) >>> FRAC_BITS;
            s1_var4 <= x >>> 1;
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 2:
    //   var_5 = var_1 * var_2   = x^2 * (c2*x) = c2*x^3
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s2_var5;
    logic signed [DATA_WIDTH-1:0] s2_var3, s2_var4;  // forwarded

    always_ff @(posedge clk) begin
        if (rst) begin
            s2_var5 <= '0;
            s2_var3 <= '0;
            s2_var4 <= '0;
        end else begin
            s2_var5 <= (s1_var1 * s1_var2) >>> FRAC_BITS;
            s2_var3 <= s1_var3;
            s2_var4 <= s1_var4;
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 3:
    //   var_6 = var_5 + var_3   = c2*x^3 + c1*x
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s3_var6;
    logic signed [DATA_WIDTH-1:0] s3_var4;  // forwarded

    always_ff @(posedge clk) begin
        if (rst) begin
            s3_var6 <= '0;
            s3_var4 <= '0;
        end else begin
            s3_var6 <= s2_var5 + s2_var3;
            s3_var4 <= s2_var4;
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 4:
    //   PWL   = tanh_piecewise_linear(var_6)
    //   var_7 = 1 + PWL
    //
    // Piecewise linear tanh approximation (Q16.16):
    //   |x| >= 4.0  -> tanh = sign(x) * 1.0
    //   |x| >= 2.0  -> tanh = sign(x) * (0.9051 + 0.0244*(|x|-2.0))  -- approx
    //   |x| >= 1.0  -> tanh = sign(x) * (0.7616 + 0.1435*(|x|-1.0))  -- approx
    //   |x| <  1.0  -> tanh = x * 0.9  -- linear region approximation
    //
    // All thresholds and slopes in Q16.16
    // -------------------------------------------------------------------------
    localparam signed [DATA_WIDTH-1:0] TANH_SAT   = 32'sd65536;   //  1.0
    localparam signed [DATA_WIDTH-1:0] THRESH_4   = 32'sd262144;  //  4.0
    localparam signed [DATA_WIDTH-1:0] THRESH_2   = 32'sd131072;  //  2.0
    localparam signed [DATA_WIDTH-1:0] THRESH_1   = 32'sd65536;   //  1.0
    localparam signed [DATA_WIDTH-1:0] SLOPE_LIN  = 32'sd58982;   //  0.9  * 2^16
    localparam signed [DATA_WIDTH-1:0] BASE_2     = 32'sd59330;   //  0.9051 * 2^16
    localparam signed [DATA_WIDTH-1:0] SLOPE_2    = 32'sd1600;    //  0.0244 * 2^16
    localparam signed [DATA_WIDTH-1:0] BASE_1     = 32'sd49933;   //  0.7616 * 2^16
    localparam signed [DATA_WIDTH-1:0] SLOPE_1    = 32'sd9408;    //  0.1435 * 2^16

    logic signed [DATA_WIDTH-1:0] s4_pwl, s4_var7;
    logic signed [DATA_WIDTH-1:0] s4_var4;  // forwarded
    logic signed [DATA_WIDTH-1:0] abs_var6;
    logic                         sign_var6;

    always_ff @(posedge clk) begin
        if (rst) begin
            s4_pwl  <= '0;
            s4_var7 <= '0;
            s4_var4 <= '0;
        end else begin
            abs_var6  = (s3_var6 < 0) ? -s3_var6 : s3_var6;
            sign_var6 = s3_var6[DATA_WIDTH-1];

            // Piecewise linear tanh
            if (abs_var6 >= THRESH_4)
                s4_pwl <= sign_var6 ? -TANH_SAT : TANH_SAT;
            else if (abs_var6 >= THRESH_2)
                s4_pwl <= sign_var6 ?
                    -(BASE_2 + ((SLOPE_2 * (abs_var6 - THRESH_2)) >>> FRAC_BITS)) :
                     (BASE_2 + ((SLOPE_2 * (abs_var6 - THRESH_2)) >>> FRAC_BITS));
            else if (abs_var6 >= THRESH_1)
                s4_pwl <= sign_var6 ?
                    -(BASE_1 + ((SLOPE_1 * (abs_var6 - THRESH_1)) >>> FRAC_BITS)) :
                     (BASE_1 + ((SLOPE_1 * (abs_var6 - THRESH_1)) >>> FRAC_BITS));
            else
                s4_pwl <= (SLOPE_LIN * s3_var6) >>> FRAC_BITS;

            s4_var7 <= ONE + s4_pwl;  // 1 + tanh(...)
            s4_var4 <= s3_var4;
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 5:
    //   output = var_7 * var_4 = (1 + tanh(...)) * (0.5 * x)
    // -------------------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst)
            out <= '0;
        else
            out <= (s4_var7 * s4_var4) >>> FRAC_BITS;
    end
    
    
    initial begin
	    $dumpfile("dump.vcd"); // Name of the file to be created
	    $dumpvars(0, gelu);     // 0 means dump all signals in 'mac' and below
    end

endmodule
