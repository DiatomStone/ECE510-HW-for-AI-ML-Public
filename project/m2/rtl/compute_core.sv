// =========================================================================
// Module:  compute_core
// Project: GELU Activation Kernel — ECE 410/510, M2
// Author:  Created with Cursor — Manager (Claude Opus 4.6)
// Created: 2026-05-03
// Modified: 2026-05-03
//
// Description:
//   Pipelined GELU activation function in synthesizable SystemVerilog.
//   Implements GELU(x) = 0.5 * x * (1 + tanh(c1*x + c2*x^3))
//   using a 10-segment piecewise-linear (PWL) tanh approximation.
//
// Data Format:
//   32-bit signed fixed point, Q16.16 (1 sign, 15 integer, 16 fractional)
//
// Clock Domain:
//   Single clock domain (clk). All sequential logic on posedge clk.
//
// Reset:
//   Synchronous, active-high (rst). Clears valid pipeline and output.
//   Datapath registers are not reset (values gated by valid).
//
// Pipeline:
//   5 stages, 5-cycle latency. Accepts one input per clock when valid_in
//   is asserted. Fully pipelined — no stalls or backpressure.
//
// Port Descriptions:
//   clk       — input,  1-bit        : System clock
//   rst       — input,  1-bit        : Synchronous active-high reset
//   valid_in  — input,  1-bit        : Input data valid strobe
//   x         — input,  [31:0] signed: Input operand in Q16.16
//   valid_out — output, 1-bit        : Output data valid strobe
//   out       — output, [31:0] signed: GELU(x) result in Q16.16
// =========================================================================

module compute_core #(
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
    // -------------------------------------------------------------------------
    localparam signed [DATA_WIDTH-1:0] CONST_1 = 32'sd52261;  // sqrt(2/pi)
    localparam signed [DATA_WIDTH-1:0] CONST_2 = 32'sd2337;   // CONST_1 * 0.044715
    localparam signed [DATA_WIDTH-1:0] ONE     = 32'sd65536;  // 1.0 in Q16.16

    // -------------------------------------------------------------------------
    // Pipeline valid shift register
    // -------------------------------------------------------------------------
    // valid_pipe tracks stages 1 to (PIPE_DEPTH-1). The final stage is valid_out.
    logic [PIPE_DEPTH-2:0] valid_pipe;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_pipe <= '0;
        end else begin
            valid_pipe <= {valid_pipe[PIPE_DEPTH-3:0], valid_in};
        end
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 1:
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s1_var1, s1_var2, s1_var3, s1_var4;

    // No reset on datapath to save area. Values only matter when valid_pipe[0] is high.
    always_ff @(posedge clk) begin
        s1_var1 <= ($signed(64'(x)) * $signed(64'(x))) >>> FRAC_BITS;
        s1_var2 <= ($signed(64'(CONST_2)) * $signed(64'(x))) >>> FRAC_BITS;
        s1_var3 <= ($signed(64'(CONST_1)) * $signed(64'(x))) >>> FRAC_BITS;
        s1_var4 <= x >>> 1;
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 2:
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s2_var5;
    logic signed [DATA_WIDTH-1:0] s2_var3, s2_var4;

    always_ff @(posedge clk) begin
        s2_var5 <= ($signed(64'(s1_var1)) * $signed(64'(s1_var2))) >>> FRAC_BITS;
        s2_var3 <= s1_var3;
        s2_var4 <= s1_var4;
    end

    // -------------------------------------------------------------------------
    // Pipeline Slot 3:
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s3_var6;
    logic signed [DATA_WIDTH-1:0] s3_var4;

    always_ff @(posedge clk) begin
        s3_var6 <= s2_var5 + s2_var3;
        s3_var4 <= s2_var4;
    end

    // PWL Tanh — 10-segment approximation with endpoint-to-endpoint slopes
    // Thresholds (Q16.16)
    localparam signed [DATA_WIDTH-1:0] TANH_SAT    = 32'sd65536;   // 1.0
    localparam signed [DATA_WIDTH-1:0] THRESH_4    = 32'sd262144;  // 4.0
    localparam signed [DATA_WIDTH-1:0] THRESH_3    = 32'sd196608;  // 3.0
    localparam signed [DATA_WIDTH-1:0] THRESH_2    = 32'sd131072;  // 2.0
    localparam signed [DATA_WIDTH-1:0] THRESH_175  = 32'sd114688;  // 1.75
    localparam signed [DATA_WIDTH-1:0] THRESH_15   = 32'sd98304;   // 1.5
    localparam signed [DATA_WIDTH-1:0] THRESH_125  = 32'sd81920;   // 1.25
    localparam signed [DATA_WIDTH-1:0] THRESH_1    = 32'sd65536;   // 1.0
    localparam signed [DATA_WIDTH-1:0] THRESH_075  = 32'sd49152;   // 0.75
    localparam signed [DATA_WIDTH-1:0] THRESH_05   = 32'sd32768;   // 0.5
    // Bases — tanh(threshold) in Q16.16
    localparam signed [DATA_WIDTH-1:0] BASE_3      = 32'sd65212;   // tanh(3.0)
    localparam signed [DATA_WIDTH-1:0] BASE_2      = 32'sd63179;   // tanh(2.0)
    localparam signed [DATA_WIDTH-1:0] BASE_175    = 32'sd61694;   // tanh(1.75)
    localparam signed [DATA_WIDTH-1:0] BASE_15     = 32'sd59320;   // tanh(1.5)
    localparam signed [DATA_WIDTH-1:0] BASE_125    = 32'sd55593;   // tanh(1.25)
    localparam signed [DATA_WIDTH-1:0] BASE_1      = 32'sd49912;   // tanh(1.0)
    localparam signed [DATA_WIDTH-1:0] BASE_075    = 32'sd41625;   // tanh(0.75)
    localparam signed [DATA_WIDTH-1:0] BASE_05     = 32'sd30285;   // tanh(0.5)
    // Slopes — (tanh(upper) - tanh(lower)) / (upper - lower) in Q16.16
    localparam signed [DATA_WIDTH-1:0] SLOPE_3_4   = 32'sd280;     // [3.0, 4.0)
    localparam signed [DATA_WIDTH-1:0] SLOPE_2_3   = 32'sd2033;    // [2.0, 3.0)
    localparam signed [DATA_WIDTH-1:0] SLOPE_175_2 = 32'sd5938;    // [1.75, 2.0)
    localparam signed [DATA_WIDTH-1:0] SLOPE_15_175= 32'sd9497;    // [1.5, 1.75)
    localparam signed [DATA_WIDTH-1:0] SLOPE_125_15= 32'sd14907;   // [1.25, 1.5)
    localparam signed [DATA_WIDTH-1:0] SLOPE_1_125 = 32'sd22725;   // [1.0, 1.25)
    localparam signed [DATA_WIDTH-1:0] SLOPE_075_1 = 32'sd33147;   // [0.75, 1.0)
    localparam signed [DATA_WIDTH-1:0] SLOPE_05_075= 32'sd45359;   // [0.5, 0.75)
    localparam signed [DATA_WIDTH-1:0] SLOPE_LIN   = 32'sd65536;   // [0, 0.5) tanh≈x   

    // -------------------------------------------------------------------------
    // Pipeline Slot 4: Combinational PWL + Registered Stage
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] next_pwl; 
    logic signed [DATA_WIDTH-1:0] s4_var7, s4_var4;
    logic signed [DATA_WIDTH-1:0] abs_var6;
    logic                         sign_var6;

    assign abs_var6  = (s3_var6 < 0) ? -s3_var6 : s3_var6;
    assign sign_var6 = s3_var6[DATA_WIDTH-1];

    always_comb begin
        if (abs_var6 >= THRESH_4)
            next_pwl = sign_var6 ? -TANH_SAT : TANH_SAT;
        else if (abs_var6 >= THRESH_3) begin
            next_pwl = (64'(SLOPE_3_4) * (abs_var6 - THRESH_3)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_3 + next_pwl) : (BASE_3 + next_pwl);
        end else if (abs_var6 >= THRESH_2) begin
            next_pwl = (64'(SLOPE_2_3) * (abs_var6 - THRESH_2)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_2 + next_pwl) : (BASE_2 + next_pwl);
        end else if (abs_var6 >= THRESH_175) begin
            next_pwl = (64'(SLOPE_175_2) * (abs_var6 - THRESH_175)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_175 + next_pwl) : (BASE_175 + next_pwl);
        end else if (abs_var6 >= THRESH_15) begin
            next_pwl = (64'(SLOPE_15_175) * (abs_var6 - THRESH_15)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_15 + next_pwl) : (BASE_15 + next_pwl);
        end else if (abs_var6 >= THRESH_125) begin
            next_pwl = (64'(SLOPE_125_15) * (abs_var6 - THRESH_125)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_125 + next_pwl) : (BASE_125 + next_pwl);
        end else if (abs_var6 >= THRESH_1) begin
            next_pwl = (64'(SLOPE_1_125) * (abs_var6 - THRESH_1)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_1 + next_pwl) : (BASE_1 + next_pwl);
        end else if (abs_var6 >= THRESH_075) begin
            next_pwl = (64'(SLOPE_075_1) * (abs_var6 - THRESH_075)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_075 + next_pwl) : (BASE_075 + next_pwl);
        end else if (abs_var6 >= THRESH_05) begin
            next_pwl = (64'(SLOPE_05_075) * (abs_var6 - THRESH_05)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_05 + next_pwl) : (BASE_05 + next_pwl);
        end else begin
            next_pwl = (64'(SLOPE_LIN) * s3_var6) >>> FRAC_BITS;
        end
    end

    always_ff @(posedge clk) begin
        s4_var7 <= ONE + next_pwl;  
        s4_var4 <= s3_var4;
    end
    // -------------------------------------------------------------------------
    // Pipeline Slot 5: Output with Saturation
    // -------------------------------------------------------------------------
    logic signed [63:0] out_full;
    assign out_full = ($signed(64'(s4_var7)) * $signed(64'(s4_var4))) >>> FRAC_BITS;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0;
            out       <= '0;
        end else begin
            valid_out <= valid_pipe[PIPE_DEPTH-2]; // Synced strictly with final data
            
            // Saturation limit clamping
            if (out_full > 64'sd2147483647)
                out <= 32'sd2147483647;
            else if (out_full < -64'sd2147483648)
                out <= -32'sd2147483648;
            else
                out <= out_full[31:0];
        end
    end
    
    // -------------------------------------------------------------------------
    // Simulation hooks
    // -------------------------------------------------------------------------
    initial begin
        $dumpfile("dump.vcd"); 
        $dumpvars(0, compute_core);     
    end

endmodule
