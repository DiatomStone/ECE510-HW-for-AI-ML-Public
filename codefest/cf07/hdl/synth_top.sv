// =========================================================================
// Module:  synth_top (High-Accuracy 24-Segment Parallel PWL)
// Description:
//   Designed for 16-core instantiation. Uses non-uniform segmentation
//   to maximize accuracy in high-curvature regions of the GELU function.
// =========================================================================

module synth_top #(
    parameter int DATA_WIDTH = 32,
    parameter int FRAC_BITS  = 16,
    parameter int PIPE_DEPTH = 4
)(
    input  logic                        clk,
    input  logic                        rst,
    input  logic                        valid_in,
    input  logic signed [DATA_WIDTH-1:0] x,
    output logic                        valid_out,
    output logic signed [DATA_WIDTH-1:0] out
);

    // -------------------------------------------------------------------------
    // STAGE 1: Boundary Decode
    // Registers the input and decodes which PWL segment contains x.
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s1_x;
    logic [23:0] s1_hits;

    always_ff @(posedge clk) begin
        s1_x <= x;
        // Non-uniform boundaries: high density near the high-curvature center.
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
        s1_hits[19] <= (x >=  32'sd196608);                         // x >= 3.0
    end

    // -------------------------------------------------------------------------
    // STAGE 2: Coefficient And Offset Select
    // Converts the one-hot segment hit into slope, intercept, and segment base.
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s2_m, s2_b, s2_dx;
    logic signed [DATA_WIDTH-1:0] comb_m, comb_b, comb_t;

    always_comb begin
        // default: linear pass-through x >= 3.0
        comb_m = 32'sd65536; comb_b = 32'sd0; comb_t = 32'sd0;
        
        unique case (1'b1)
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
        s2_b  <= comb_b;
        s2_dx <= s1_x - comb_t;
    end

    // -------------------------------------------------------------------------
    // STAGE 3: Multiply
    // Computes the raw product m * dx and carries b forward.
    // -------------------------------------------------------------------------
    logic [PIPE_DEPTH-2:0] v_pipe;
    always_ff @(posedge clk) begin
        if (rst) v_pipe <= '0;
        else     v_pipe <= {v_pipe[PIPE_DEPTH-3:0], valid_in};
    end

    logic signed [63:0] s3_mult;
    logic signed [DATA_WIDTH-1:0] s3_b;

    always_ff @(posedge clk) begin
        if (rst) begin
            s3_mult <= 64'sh0;
            s3_b    <= 32'sh0;
        end else begin
            s3_mult <= s2_m * s2_dx;
            s3_b    <= s2_b;
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 4: Add, Saturate, And Output
    // Adds the intercept, clamps to signed 32-bit Q16.16, and asserts valid_out.
    // -------------------------------------------------------------------------
    logic signed [63:0] s4_sum;

    assign s4_sum = (s3_mult >>> FRAC_BITS) + s3_b;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0;
            out       <= 0;
        end else begin
            valid_out <= v_pipe[PIPE_DEPTH-2];
            // A value fits in signed 32 bits when bits [63:31] are sign extension.
            if ((s4_sum[63:31] == 33'b0) || (s4_sum[63:31] == 33'h1_FFFF_FFFF))
                out <= s4_sum[31:0];
            else if (s4_sum[63])
                out <= 32'sh8000_0000;  //-32768.0
            else
                out <= 32'sh7FFF_FFFF;  //+32767.999984 
        end
    end

endmodule
