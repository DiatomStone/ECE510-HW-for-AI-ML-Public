// =========================================================================
// Module:  synth_top (High-Accuracy 24-Segment Parallel PWL)
// Description:
//   Optimized for Sky130 ASIC flow. Implements a 5-stage pipeline with 
//   register replication to solve high-fanout timing violations.
// =========================================================================

module synth_top #(
    parameter int DATA_WIDTH = 32,
    parameter int FRAC_BITS  = 16,
    parameter int PIPE_DEPTH = 5
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
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] s1_x;
    logic [23:0] s1_hits;

    always_ff @(posedge clk) begin
        s1_x <= x;
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
    // STAGE 2: Coefficient Select & Replicated Registers
    // Replicated to reduce 254-way fanout on multiplier logic.
    // -------------------------------------------------------------------------
    logic signed [DATA_WIDTH-1:0] comb_m, comb_b, comb_t;
    
    // Register replication attributes for Sky130/OpenLane
    (* equivalent_register_removal = "no" *) logic signed [DATA_WIDTH-1:0] s2_m, s2_m_rep;
    (* equivalent_register_removal = "no" *) logic signed [DATA_WIDTH-1:0] s2_dx, s2_dx_rep;
    logic signed [DATA_WIDTH-1:0] s2_b;

    always_comb begin
        comb_m = 32'sd65536; comb_b = 32'sd0; comb_t = 32'sd0;
        unique case (1'b1)
            s1_hits[0]:  begin comb_m = 32'sd0;     comb_b = 32'sd0;      comb_t = 32'sd0;      end
            s1_hits[1]:  begin comb_m = -32'sd2369;  comb_b = -32'sd1314;   comb_t = -32'sd196608; end
            s1_hits[2]:  begin comb_m = -32'sd4025;  comb_b = -32'sd2499;   comb_t = -32'sd163840; end
            s1_hits[3]:  begin comb_m = -32'sd5883;  comb_b = -32'sd4511;   comb_t = -32'sd131072; end
            s1_hits[4]:  begin comb_m = -32'sd6455;  comb_b = -32'sd7452;   comb_t = -32'sd98304;  end
            s1_hits[5]:  begin comb_m = -32'sd5366;  comb_b = -32'sd9066;   comb_t = -32'sd81920;  end
            s1_hits[6]:  begin comb_m = -32'sd2142;  comb_b = -32'sd10408;  comb_t = -32'sd65536;  end
            s1_hits[7]:  begin comb_m = 32'sd4072;   comb_b = -32'sd10943;  comb_t = -32'sd49152;  end
            s1_hits[8]:  begin comb_m = 32'sd13664;  comb_b = -32'sd9925;   comb_t = -32'sd32768;  end
            s1_hits[9]:  begin comb_m = 32'sd26037;  comb_b = -32'sd6509;   comb_t = -32'sd16384;  end
            s1_hits[10]: begin comb_m = 32'sd39499;  comb_b = 32'sd0;      comb_t = 32'sd0;      end
            s1_hits[11]: begin comb_m = 32'sd51872;  comb_b = 32'sd9875;   comb_t = 32'sd16384;  end
            s1_hits[12]: begin comb_m = 32'sd61464;  comb_b = 32'sd22843;  comb_t = 32'sd32768;  end
            s1_hits[13]: begin comb_m = 32'sd67678;  comb_b = 32'sd38209;  comb_t = 32'sd49152;  end
            s1_hits[14]: begin comb_m = 32'sd70902;  comb_b = 32'sd55128;  comb_t = 32'sd65536;  end
            s1_hits[15]: begin comb_m = 32'sd71991;  comb_b = 32'sd72854;  comb_t = 32'sd81920;  end
            s1_hits[16]: begin comb_m = 32'sd71419;  comb_b = 32'sd90852;  comb_t = 32'sd98304;  end
            s1_hits[17]: begin comb_m = 32'sd69561;  comb_b = 32'sd126561; comb_t = 32'sd131072; end
            s1_hits[18]: begin comb_m = 32'sd67905;  comb_b = 32'sd161341; comb_t = 32'sd163840; end
            s1_hits[19]: begin comb_m = 32'sd65536;  comb_b = 32'sd0;      comb_t = 32'sd0;      end
            default:     begin comb_m = 32'sd65536;  comb_b = 32'sd0;      comb_t = 32'sd0;      end
        endcase
    end

    always_ff @(posedge clk) begin
        s2_m      <= comb_m;
        s2_m_rep  <= comb_m; // Clone for upper-limb math
        s2_dx     <= s1_x - comb_t;
        s2_dx_rep <= s1_x - comb_t; // Clone for upper-limb math
        s2_b      <= comb_b;
    end

    // -------------------------------------------------------------------------
    // STAGE 3: Partial Multiplier (Lower 16 bits)
    // -------------------------------------------------------------------------
    logic [PIPE_DEPTH-1:0] v_pipe;
    always_ff @(posedge clk) begin
        if (rst) v_pipe <= '0;
        else     v_pipe <= {v_pipe[PIPE_DEPTH-2:0], valid_in};
    end

    logic signed [63:0] s3_low_prod;
    logic signed [DATA_WIDTH-1:0] s3_m_hi, s3_dx_hi, s3_b;

    always_ff @(posedge clk) begin
        if (rst) begin
            s3_low_prod <= '0;
            s3_m_hi     <= '0;
            s3_dx_hi    <= '0;
            s3_b        <= '0;
        end else begin
            // Lower 16-bit multiplication (must be unsigned for split logic)
            s3_low_prod <= $signed({1'b0, s2_m[15:0]}) * s2_dx; 
            s3_m_hi     <= s2_m_rep;
            s3_dx_hi    <= s2_dx_rep;
            s3_b        <= s2_b;
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 4: Final Multiplier Accumulation
    // -------------------------------------------------------------------------
    logic signed [63:0] s4_mult_full;
    logic signed [DATA_WIDTH-1:0] s4_b;

    always_ff @(posedge clk) begin
        if (rst) begin
            s4_mult_full <= '0;
            s4_b         <= '0;
        end else begin
            // Add shifted upper-limb product to the lower-limb partial product
            s4_mult_full <= s3_low_prod + (64'(s3_m_hi[31:16] * s3_dx_hi) << 16);
            s4_b         <= s3_b;
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 5: Add, Saturate, and Output
    // -------------------------------------------------------------------------
    logic signed [63:0] s5_sum;
    assign s5_sum = (s4_mult_full >>> FRAC_BITS) + s4_b;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0;
            out       <= '0;
        end else begin
            valid_out <= v_pipe[PIPE_DEPTH-1];
            
            // Saturation logic for signed 32-bit Q16.16
            if ((s5_sum[63:31] == 33'b0) || (s5_sum[63:31] == 33'h1_FFFF_FFFF))
                out <= s5_sum[31:0];
            else if (s5_sum[63])
                out <= 32'sh8000_0000; // -32768.0
            else
                out <= 32'sh7FFF_FFFF; // +32767.999984 
        end
    end

endmodule
