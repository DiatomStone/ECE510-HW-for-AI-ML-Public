// GELU Activation — Pipelined SystemVerilog Implementation
// Optimized for throughput, accurate PWL approximation, and saturation safety.
//
// Data format: 32-bit fixed point, Q16.16 (1 sign, 15 integer, 16 fractional)

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

// --- Place these at the top of the module or right before Slot 4 ---
    localparam signed [DATA_WIDTH-1:0] TANH_SAT   = 32'sd65536;   
    localparam signed [DATA_WIDTH-1:0] THRESH_4   = 32'sd262144;  
    localparam signed [DATA_WIDTH-1:0] THRESH_2   = 32'sd131072;  
    localparam signed [DATA_WIDTH-1:0] THRESH_1   = 32'sd65536;   
    localparam signed [DATA_WIDTH-1:0] THRESH_05  = 32'sd32768;   
    localparam signed [DATA_WIDTH-1:0] SLOPE_LIN  = 32'sd65536;   
    localparam signed [DATA_WIDTH-1:0] BASE_2     = 32'sd59330;   
    localparam signed [DATA_WIDTH-1:0] SLOPE_2    = 32'sd1600;    
    localparam signed [DATA_WIDTH-1:0] BASE_1     = 32'sd49933;   
    localparam signed [DATA_WIDTH-1:0] SLOPE_1    = 32'sd9408;    
    localparam signed [DATA_WIDTH-1:0] BASE_05    = 32'sd30284;   
    localparam signed [DATA_WIDTH-1:0] SLOPE_05   = 32'sd39256;   

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
        // High-precision Piecewise linear tanh
        if (abs_var6 >= THRESH_4)
            next_pwl = sign_var6 ? -TANH_SAT : TANH_SAT;
        else if (abs_var6 >= THRESH_2) begin
            // Calculate the segment offset first
            next_pwl = (64'(SLOPE_2) * (abs_var6 - THRESH_2)) >>> FRAC_BITS;
            // Add to base then apply sign
            next_pwl = sign_var6 ? -(BASE_2 + next_pwl) : (BASE_2 + next_pwl);
        end else if (abs_var6 >= THRESH_1) begin
            next_pwl = (64'(SLOPE_1) * (abs_var6 - THRESH_1)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_1 + next_pwl) : (BASE_1 + next_pwl);
        end else if (abs_var6 >= THRESH_05) begin
            next_pwl = (64'(SLOPE_05) * (abs_var6 - THRESH_05)) >>> FRAC_BITS;
            next_pwl = sign_var6 ? -(BASE_05 + next_pwl) : (BASE_05 + next_pwl);
        end else begin
            // Use the original signed value for the linear region to ensure a smooth zero-crossing
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
