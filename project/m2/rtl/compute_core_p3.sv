// =========================================================================
// Module:  compute_core (Pipelined GELU - Parallel PWL)
// Description:
//   3-stage pipelined GELU activation function using a 16-segment 
//   parallel Piecewise-Linear (PWL) approximation.
// Data Format: 32-bit signed fixed point, Q16.16
// =========================================================================

module compute_core #(
    parameter int DATA_WIDTH = 32,
    parameter int FRAC_BITS  = 16,
    parameter int PIPE_DEPTH = 3
)(
    input  logic                        clk,
    input  logic                        rst,
    input  logic                        valid_in,
    input  logic signed [DATA_WIDTH-1:0] x,
    output logic                        valid_out,
    output logic signed [DATA_WIDTH-1:0] out
);

    // -------------------------------------------------------------------------
    // Threshold Constants (Q16.16) - Every 0.5 steps from -3.5 to 3.5
    // -------------------------------------------------------------------------
    localparam signed [DATA_WIDTH-1:0] T_N35 = -32'sd229376; // -3.5
    localparam signed [DATA_WIDTH-1:0] T_N30 = -32'sd196608; // -3.0
    localparam signed [DATA_WIDTH-1:0] T_N25 = -32'sd163840; // -2.5
    localparam signed [DATA_WIDTH-1:0] T_N20 = -32'sd131072; // -2.0
    localparam signed [DATA_WIDTH-1:0] T_N15 = -32'sd98304;  // -1.5
    localparam signed [DATA_WIDTH-1:0] T_N10 = -32'sd65536;  // -1.0
    localparam signed [DATA_WIDTH-1:0] T_N05 = -32'sd32768;  // -0.5
    localparam signed [DATA_WIDTH-1:0] T_000 =  32'sd0;      //  0.0
    localparam signed [DATA_WIDTH-1:0] T_P05 =  32'sd32768;  //  0.5
    localparam signed [DATA_WIDTH-1:0] T_P10 =  32'sd65536;  //  1.0
    localparam signed [DATA_WIDTH-1:0] T_P15 =  32'sd98304;  //  1.5
    localparam signed [DATA_WIDTH-1:0] T_P20 =  32'sd131072; //  2.0
    localparam signed [DATA_WIDTH-1:0] T_P25 =  32'sd163840; //  2.5
    localparam signed [DATA_WIDTH-1:0] T_P30 =  32'sd196608; //  3.0
    localparam signed [DATA_WIDTH-1:0] T_P35 =  32'sd229376; //  3.5

    // -------------------------------------------------------------------------
    // Valid Shift Register
    // -------------------------------------------------------------------------
    logic [PIPE_DEPTH-2:0] valid_pipe;
    always_ff @(posedge clk) begin
        if (rst) valid_pipe <= '0;
        else     valid_pipe <= {valid_pipe[PIPE_DEPTH-3:0], valid_in};
    end

    // =========================================================================
    // STAGE 1: Parallel Comparison (The "Flash" Stage)
    // =========================================================================
    logic signed [DATA_WIDTH-1:0] s1_x;
    logic [15:0] s1_region_hit; 

    always_ff @(posedge clk) begin
        s1_x <= x; // Latch input
        
        // Parallel comparators - evaluates in a single cycle
        s1_region_hit[0]  <= (x < T_N30);
        s1_region_hit[1]  <= (x >= T_N30 && x < T_N25);
        s1_region_hit[2]  <= (x >= T_N25 && x < T_N20);
        s1_region_hit[3]  <= (x >= T_N20 && x < T_N15);
        s1_region_hit[4]  <= (x >= T_N15 && x < T_N10);
        s1_region_hit[5]  <= (x >= T_N10 && x < T_N05);
        s1_region_hit[6]  <= (x >= T_N05 && x < T_000);
        s1_region_hit[7]  <= (x >= T_000 && x < T_P05);
        s1_region_hit[8]  <= (x >= T_P05 && x < T_P10);
        s1_region_hit[9]  <= (x >= T_P10 && x < T_P15);
        s1_region_hit[10] <= (x >= T_P15 && x < T_P20);
        s1_region_hit[11] <= (x >= T_P20 && x < T_P25);
        s1_region_hit[12] <= (x >= T_P25 && x < T_P30);
        s1_region_hit[13] <= (x >= T_P30 && x < T_P35);
        s1_region_hit[14] <= (x >= T_P35);
    end

    // =========================================================================
    // STAGE 2: One-Hot Selection & Subtraction
    // =========================================================================
    logic signed [DATA_WIDTH-1:0] s2_slope;
    logic signed [DATA_WIDTH-1:0] s2_base;
    logic signed [DATA_WIDTH-1:0] s2_dx;

    logic signed [DATA_WIDTH-1:0] comb_slope, comb_base, comb_thresh;

    always_comb begin
        // Default to linear pass-through (x >= 3.5 roughly equals x)
        comb_slope  = 32'sd65536; 
        comb_base   = 32'sd0;
        comb_thresh = 32'sd0;

        // 'unique case' forces parallel MUX synthesis rather than a priority chain
        unique case (1'b1)
            s1_region_hit[0]:  begin comb_slope = 32'sd0;     comb_base = 32'sd0;      comb_thresh = 32'sd0;   end // < -3.0 (Zero)
            s1_region_hit[1]:  begin comb_slope = 32'sd200;   comb_base = -32'sd262;   comb_thresh = T_N30;    end // [-3.0, -2.5)
            s1_region_hit[2]:  begin comb_slope = 32'sd1966;  comb_base = -32'sd983;   comb_thresh = T_N25;    end // [-2.5, -2.0)
            s1_region_hit[3]:  begin comb_slope = 32'sd3604;  comb_base = -32'sd2949;  comb_thresh = T_N20;    end // [-2.0, -1.5)
            s1_region_hit[4]:  begin comb_slope = 32'sd3801;  comb_base = -32'sd6553;  comb_thresh = T_N15;    end // [-1.5, -1.0)
            s1_region_hit[5]:  begin comb_slope = 32'sd262;   comb_base = -32'sd10354; comb_thresh = T_N10;    end // [-1.0, -0.5)
            s1_region_hit[6]:  begin comb_slope = 32'sd10092; comb_base = -32'sd10092; comb_thresh = T_N05;    end // [-0.5, 0.0)
            s1_region_hit[7]:  begin comb_slope = 32'sd22609; comb_base = 32'sd0;      comb_thresh = T_000;    end // [0.0, 0.5)
            s1_region_hit[8]:  begin comb_slope = 32'sd32505; comb_base = 32'sd22609;  comb_thresh = T_P05;    end // [0.5, 1.0)
            s1_region_hit[9]:  begin comb_slope = 32'sd36569; comb_base = 32'sd55115;  comb_thresh = T_P10;    end // [1.0, 1.5)
            s1_region_hit[10]: begin comb_slope = 32'sd36372; comb_base = 32'sd91684;  comb_thresh = T_P15;    end // [1.5, 2.0)
            s1_region_hit[11]: begin comb_slope = 32'sd34734; comb_base = 32'sd128057; comb_thresh = T_P20;    end // [2.0, 2.5)
            s1_region_hit[12]: begin comb_slope = 32'sd33423; comb_base = 32'sd162791; comb_thresh = T_P25;    end // [2.5, 3.0)
            s1_region_hit[13]: begin comb_slope = 32'sd33030; comb_base = 32'sd196214; comb_thresh = T_P30;    end // [3.0, 3.5)
            s1_region_hit[14]: begin comb_slope = 32'sd65536; comb_base = 32'sd0;      comb_thresh = 32'sd0;   end // >= 3.5 (Linear y=x)
            default:           begin comb_slope = 32'sd65536; comb_base = 32'sd0;      comb_thresh = 32'sd0;   end 
        endcase
    end

    always_ff @(posedge clk) begin
        s2_slope <= comb_slope;
        s2_base  <= comb_base;
        // Subtractor pulled out of the branches to save logic area
        if (s1_region_hit[14] || s1_region_hit[0]) begin
            s2_dx <= s1_x; // Pass raw X for tails
        end else begin
            s2_dx <= s1_x - comb_thresh;
        end
    end

    // =========================================================================
    // STAGE 3: Compute & Saturate
    // =========================================================================
    logic signed [63:0] s3_mult_full;

    // Single DSP multiplier used here
    assign s3_mult_full = ($signed(64'(s2_slope)) * $signed(64'(s2_dx))) >>> FRAC_BITS;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0;
            out       <= '0;
        end else begin
            valid_out <= valid_pipe[PIPE_DEPTH-2];
            
            // Saturation logic
            if ((s3_mult_full + s2_base) > 64'sd2147483647)
                out <= 32'sd2147483647;
            else if ((s3_mult_full + s2_base) < -64'sd2147483648)
                out <= -32'sd2147483648;
            else
                out <= s3_mult_full[31:0] + s2_base;
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
