// =========================================================================
// Module:  compute_core (High-Accuracy 24-Segment Parallel PWL)
// Description:
//   Designed for 16-core instantiation. Uses non-uniform segmentation
//   to maximize accuracy in high-curvature regions of the GELU function.
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
    // STAGE 1: Parallel Identification (The Flash Decode) [cite: 132]
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s1_x;
    logic [23:0] s1_hits;

    always_ff @(posedge clk) begin
        s1_x <= x; // [cite: 133]
        // Non-uniform boundaries: High density (0.25 steps) near the center [cite: 136, 137]
        s1_hits[0]  <= (x < -32'sd196608);                          // x < -3.0
        s1_hits[1]  <= (x >= -32'sd196608 && x < -32'sd163840);    // [-3.0, -2.5)
        s1_hits[2]  <= (x >= -32'sd163840 && x < -32'sd131072);    // [-2.5, -2.0)
        s1_hits[3]  <= (x >= -32'sd131072 && x < -32'sd98304);     // [-2.0, -1.5)
        s1_hits[4]  <= (x >= -32'sd98304  && x < -32'sd81920);     // [-1.5, -1.25)
        s1_hits[5]  <= (x >= -32'sd81920  && x < -32'sd65536);     // [-1.25, -1.0)
        s1_hits[6]  <= (x >= -32'sd65536  && x < -32'sd49152);     // [-1.0, -0.75)
        s1_hits[7]  <= (x >= -32'sd49152  && x < -32'sd32768);     // [-0.75, -0.5)
        s1_hits[8]  <= (x >= -32'sd32768  && x < -32'sd16384);     // [-0.5, -0.25)
        s1_hits[9]  <= (x >= -32'sd16384  && x <  32'sd0);         // [-0.25, 0.0)
        s1_hits[10] <= (x >=  32'sd0      && x <  32'sd16384);     // [0.0, 0.25)
        s1_hits[11] <= (x >=  32'sd16384  && x <  32'sd32768);     // [0.25, 0.5)
        s1_hits[12] <= (x >=  32'sd32768  && x <  32'sd49152);     // [0.5, 0.75)
        s1_hits[13] <= (x >=  32'sd49152  && x <  32'sd65536);     // [0.75, 1.0)
        s1_hits[14] <= (x >=  32'sd65536  && x <  32'sd81920);     // [1.0, 1.25)
        s1_hits[15] <= (x >=  32'sd81920  && x <  32'sd98304);     // [1.25, 1.5)
        s1_hits[16] <= (x >=  32'sd98304  && x <  32'sd131072);    // [1.5, 2.0)
        s1_hits[17] <= (x >=  32'sd131072 && x <  32'sd163840);    // [2.0, 2.5)
        s1_hits[18] <= (x >=  32'sd163840 && x <  32'sd196608);    // [2.5, 3.0)
        s1_hits[19] <= (x >=  32'sd196608);                         // x >= 3.0 [cite: 140]
    end

    // -------------------------------------------------------------------------
    // STAGE 2: One-Hot Select & Offset [cite: 142]
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s2_m, s2_b, s2_dx;
    logic signed [DATA_WIDTH-1:0] comb_m, comb_b, comb_t;

    always_comb begin
        // default: linear pass-through x >= 3.0
        comb_m = 32'sd65536; comb_b = 32'sd0; comb_t = 32'sd0; // [cite: 143, 144]
        
        unique case (1'b1) // [cite: 145, 159]
            s1_hits[0]:  begin comb_m = 32'sd0;      comb_b =  32'sd0;      comb_t =  32'sd0;      end // x < -3.0   : clamp 0
            s1_hits[1]:  begin comb_m = -32'sd2369;  comb_b = -32'sd1314;   comb_t = -32'sd196608; end // [-3.0,-2.5)
            s1_hits[2]:  begin comb_m = -32'sd4025;  comb_b = -32'sd2499;   comb_t = -32'sd163840; end // [-2.5,-2.0)
            s1_hits[3]:  begin comb_m = -32'sd5883;  comb_b = -32'sd4511;   comb_t = -32'sd131072; end // [-2.0,-1.5)
            s1_hits[4]:  begin comb_m = -32'sd6455;  comb_b = -32'sd7452;   comb_t = -32'sd98304;  end // [-1.5,-1.25)
            s1_hits[5]:  begin comb_m = -32'sd5366;  comb_b = -32'sd9066;   comb_t = -32'sd81920;  end // [-1.25,-1.0)
            s1_hits[6]:  begin comb_m = -32'sd2142;  comb_b = -32'sd10408;  comb_t = -32'sd65536;  end // [-1.0,-0.75)
            s1_hits[7]:  begin comb_m =  32'sd4072;  comb_b = -32'sd10943;  comb_t = -32'sd49152;  end // [-0.75,-0.5)
            s1_hits[8]:  begin comb_m =  32'sd13664; comb_b = -32'sd9925;   comb_t = -32'sd32768;  end // [-0.5,-0.25)
            s1_hits[9]:  begin comb_m =  32'sd26037; comb_b = -32'sd6509;   comb_t = -32'sd16384;  end // [-0.25,0.0)
            s1_hits[10]: begin comb_m =  32'sd39499; comb_b =  32'sd0;      comb_t =  32'sd0;      end // [0.0,0.25)
            s1_hits[11]: begin comb_m =  32'sd51872; comb_b =  32'sd9875;   comb_t =  32'sd16384;  end // [0.25,0.5)
            s1_hits[12]: begin comb_m =  32'sd61464; comb_b =  32'sd22843;  comb_t =  32'sd32768;  end // [0.5,0.75)
            s1_hits[13]: begin comb_m =  32'sd67678; comb_b =  32'sd38209;  comb_t =  32'sd49152;  end // [0.75,1.0)
            s1_hits[14]: begin comb_m =  32'sd70902; comb_b =  32'sd55128;  comb_t =  32'sd65536;  end // [1.0,1.25)
            s1_hits[15]: begin comb_m =  32'sd71991; comb_b =  32'sd72854;  comb_t =  32'sd81920;  end // [1.25,1.5)
            s1_hits[16]: begin comb_m =  32'sd71419; comb_b =  32'sd90852;  comb_t =  32'sd98304;  end // [1.5,2.0)
            s1_hits[17]: begin comb_m =  32'sd69561; comb_b =  32'sd126561; comb_t =  32'sd131072; end // [2.0,2.5)
            s1_hits[18]: begin comb_m =  32'sd67905; comb_b =  32'sd161341; comb_t =  32'sd163840; end // [2.5,3.0)
            s1_hits[19]: begin comb_m =  32'sd65536; comb_b =  32'sd0;      comb_t =  32'sd0;      end // x >= 3.0  : linear
            default:     begin comb_m =  32'sd65536; comb_b =  32'sd0;      comb_t =  32'sd0;      end
        endcase
    end

    always_ff @(posedge clk) begin
        s2_m  <= comb_m;
        s2_b  <= comb_b; // [cite: 161]
        s2_dx <= s1_x - comb_t; // [cite: 162]
    end

    // -------------------------------------------------------------------------
    // STAGE 3: Mult & Saturate 
    // -------------------------------------------------------------------------
    logic [PIPE_DEPTH-2:0] v_pipe;
    always_ff @(posedge clk) begin
        if (rst) v_pipe <= '0; // [cite: 130]
        else     v_pipe <= {v_pipe[0], valid_in}; // [cite: 131]
    end

    logic signed [63:0] s3_full;
    assign s3_full = ($signed(64'(s2_m)) * $signed(64'(s2_dx))) >>> FRAC_BITS; // 

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0; // [cite: 165]
            out       <= 0; // [cite: 166]
        end else begin
            valid_out <= v_pipe[1]; // [cite: 166]
            // Saturation logic for 32-bit Q16.16 [cite: 167]
            if ((s3_full + s2_b) > 64'sd2147483647) 
                out <= 32'sd2147483647;
            else if ((s3_full + s2_b) < -64'sd2147483648) // [cite: 168]
                out <= -32'sd2147483648;
            else
                out <= s3_full[31:0] + s2_b; // [cite: 169]
        end
    end

endmodule
