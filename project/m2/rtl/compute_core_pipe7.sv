module compute_core #(
    parameter integer WIDTH = 32,
    parameter integer FRAC_BITS = 16
)(
    input  logic              clk,
    input  logic              rst_n,
    input  logic [WIDTH-1:0]  x_in,
    input  logic              valid_in,
    output logic [WIDTH-1:0]  gelu_out,
    output logic              valid_out
);

    // --- Constants (Q16.16 format) ---[cite: 9]
    localparam logic signed [WIDTH-1:0] CONST_C1 = 32'h0000_CC42; // ~0.7978
    localparam logic signed [WIDTH-1:0] CONST_C2 = 32'h0000_0922; // ~0.0356
    localparam logic [WIDTH-1:0] TANH_SAT = 32'h0001_0000; // 1.0 in Q16.16

    // --- Pipeline Register Declarations ---[cite: 9, 10]
    logic signed [WIDTH-1:0] s1_v1, s1_v2, s1_v3, s1_v4;
    logic signed [WIDTH-1:0] s2_v5, s2_v3, s2_v4;
    logic signed [WIDTH-1:0] s3_v6, s3_v4;
    logic signed [WIDTH-1:0] s4_v6, s4_v4, s4_abs, s4_m, s4_b;
    logic signed            s4_sign;
    logic signed [WIDTH-1:0] s5_pwl, s5_pos_pwl, s5_v4;
    logic signed [WIDTH-1:0] s6_v7, s6_v4;
    logic signed [7:1]       v_pipe;

    // --- S1: Parallel Multiplications ---[cite: 9]
    always_ff @(posedge clk) begin
        if (valid_in) begin
            s1_v1 <= (64'(x_in) * x_in) >>> FRAC_BITS;
            s1_v2 <= (64'(CONST_C2) * x_in) >>> FRAC_BITS;
            s1_v3 <= (64'(CONST_C1) * x_in) >>> FRAC_BITS;
            s1_v4 <= x_in >>> 1; // 0.5x
        end
        v_pipe[1] <= valid_in && rst_n;
    end

    // --- S2: x^3 Term ---[cite: 9]
    always_ff @(posedge clk) begin
        if (v_pipe[1]) begin
            s2_v5 <= (64'(s1_v1) * s1_v2) >>> FRAC_BITS;
            s2_v3 <= s1_v3;
            s2_v4 <= s1_v4;
        end
        v_pipe[2] <= v_pipe[1] && rst_n;
    end

    // --- S3: Polynomial Sum ---[cite: 9]
    always_ff @(posedge clk) begin
        if (v_pipe[2]) begin
            s3_v6 <= s2_v5 + s2_v3;
            s3_v4 <= s2_v4;
        end
        v_pipe[3] <= v_pipe[2] && rst_n;
    end

    // --- S4: Sign/Abs/Clip & LUT Fetch ---[cite: 3, 9]
    always_ff @(posedge clk) begin
        if (v_pipe[3]) begin
            s4_v6   <= s3_v6;
            s4_v4   <= s3_v4;
            s4_sign <= s3_v6[WIDTH-1];
            s4_abs  <= s3_v6[WIDTH-1] ? -s3_v6 : s3_v6;
            
            // Placeholder for LUT Logic: Select m, b based on s4_abs
            // Example saturation logic:
            if (s4_abs >= (3 << FRAC_BITS)) begin
                s4_m <= 0;
                s4_b <= TANH_SAT;
            end else begin
                s4_m <= 32'h0000_8000; // Example slope
                s4_b <= 32'h0000_4000; // Example base
            end
        end
        v_pipe[4] <= v_pipe[3] && rst_n;
    end

    // --- S5: PWL Tanh & Sign Application ---[cite: 3, 9]
    always_ff @(posedge clk) begin
        if (v_pipe[4]) begin
            s5_pos_pwl <= ((64'(s4_m) * s4_abs) >>> FRAC_BITS) + s4_b;
            s5_v4      <= s4_v4;
            s5_pwl     <= s4_sign ? -s5_pos_pwl : s5_pos_pwl;
        end
        v_pipe[5] <= v_pipe[4] && rst_n;
    end

    // --- S6: Shift Range (1 + tanh) ---[cite: 9]
    always_ff @(posedge clk) begin
        if (v_pipe[5]) begin
            s6_v7 <= TANH_SAT + s5_pwl;
            s6_v4 <= s5_v4;
        end
        v_pipe[6] <= v_pipe[5] && rst_n;
    end

    // --- S7: Final Multiply ---[cite: 9]
    always_ff @(posedge clk) begin
        if (v_pipe[6]) begin
            gelu_out <= (64'(s6_v7) * s6_v4) >>> FRAC_BITS;
        end
        v_pipe[7] <= v_pipe[6] && rst_n;
    end

    assign valid_out = v_pipe[7];

endmodule
