// =========================================================================
// Module:  q16_to_fp32
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   4-stage pipelined Q16.16 to IEEE-754 single-precision FP32 converter.
//   Implements Round-to-Nearest-Even (RNE). Zero input produces a clean
//   IEEE-754 positive zero output.
//
//   Stage 1: Extract sign bit; compute absolute magnitude via two's complement.
//   Stage 2: Count leading zeros (CLZ) and compute biased exponent (142 - CLZ).
//   Stage 3: Left-shift magnitude to normalize (leading 1 at bit 31).
//   Stage 4: Apply RNE rounding; assemble sign, exponent, and mantissa fields.
//
// Clock Domain:
//   Single clock domain (clk). All sequential logic on posedge clk.
//
// Reset:
//   Synchronous, active-high (rst).
//
// Ports:
//   clk       - input,  1  : System clock
//   rst       - input,  1  : Synchronous active-high reset
//   valid_in  - input,  1  : Asserted when data_in holds a valid Q16.16 value
//   data_in   - input,  32 : Signed Q16.16 fixed-point input
//   valid_out - output, 1  : Asserted when data_out holds a valid FP32 result
//   data_out  - output, 32 : IEEE-754 single-precision result
// =========================================================================

module q16_to_fp32 (
    input  logic         clk,
    input  logic         rst,
    
    // Q16.16 Inputs (Interfaces with synth_top)
    input  logic         valid_in,
    input  logic [31:0]  data_in,
    
    // FP32 Outputs
    output logic         valid_out,
    output logic [31:0]  data_out
);

    // -------------------------------------------------------------------------
    // Function: clz32 (Count Leading Zeros)
    // Fast binary-search tree implementation for optimal synthesis.
    // -------------------------------------------------------------------------
    // Verilog-2001 style: non-ANSI port, reg locals, function-name return.
    // automatic is required because clz32 is called twice per always block.
    function automatic [4:0] clz32;
        input [31:0] val;
        reg [31:0] v;
        reg [4:0]  r;
        begin
            v = val; r = 5'd0;
            if (v[31:16] == 16'b0) begin r[4] = 1'b1; v = v << 16; end else r[4] = 1'b0;
            if (v[31:24] ==  8'b0) begin r[3] = 1'b1; v = v <<  8; end else r[3] = 1'b0;
            if (v[31:28] ==  4'b0) begin r[2] = 1'b1; v = v <<  4; end else r[2] = 1'b0;
            if (v[31:30] ==  2'b0) begin r[1] = 1'b1; v = v <<  2; end else r[1] = 1'b0;
            if (v[31]    ==  1'b0) begin r[0] = 1'b1;              end else r[0] = 1'b0;
            clz32 = r;
        end
    endfunction

    // -------------------------------------------------------------------------
    // STAGE 1: Sign Extraction & Absolute Magnitude
    // -------------------------------------------------------------------------
    logic        s1_valid, s1_sign, s1_is_zero;
    logic [31:0] s1_mag;

    always_ff @(posedge clk) begin
        if (rst) begin
            s1_valid   <= 1'b0;
            s1_sign    <= 1'b0;
            s1_mag     <= 32'b0;
            s1_is_zero <= 1'b0;
        end else begin
            s1_valid   <= valid_in;
            s1_sign    <= data_in[31];
            s1_is_zero <= (data_in == 32'b0);
            // Two's complement for negative numbers to get absolute magnitude
            s1_mag     <= data_in[31] ? (~data_in + 1'b1) : data_in;
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 2: Leading Zero Count & Biased Exponent
    // -------------------------------------------------------------------------
    logic        s2_valid, s2_sign, s2_is_zero;
    logic [31:0] s2_mag;
    logic [4:0]  s2_clz;
    logic [7:0]  s2_exp;

    always_ff @(posedge clk) begin
        if (rst) begin
            s2_valid   <= 1'b0;
            s2_is_zero <= 1'b0;
        end else begin
            s2_valid   <= s1_valid;
            s2_sign    <= s1_sign;
            s2_is_zero <= s1_is_zero;
            s2_mag     <= s1_mag;
            s2_clz     <= clz32(s1_mag);
            
            // Q16.16 Bias Calculation:
            // Base bias = 127. Q16.16 implicit point shifts this by 15.
            // Biased Exponent = 127 + 15 - CLZ = 142 - CLZ
            s2_exp     <= s1_is_zero ? 8'd0 : (8'd142 - clz32(s1_mag));
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 3: Mantissa Normalization Shift
    // -------------------------------------------------------------------------
    logic        s3_valid, s3_sign, s3_is_zero;
    logic [7:0]  s3_exp;
    logic [31:0] s3_norm_mag;

    always_ff @(posedge clk) begin
        if (rst) begin
            s3_valid   <= 1'b0;
            s3_is_zero <= 1'b0;
        end else begin
            s3_valid   <= s2_valid;
            s3_sign    <= s2_sign;
            s3_is_zero <= s2_is_zero;
            s3_exp     <= s2_exp;
            
            // Shift magnitude so the leading '1' sits exactly at bit 31
            s3_norm_mag <= s2_mag << s2_clz; 
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 4: Rounding (RNE) & Final Assembly
    // -------------------------------------------------------------------------
    logic        round_up;
    logic [23:0] rounded_mantissa; // 24 bits to catch carry-out

    // RNE Logic: 
    // Bit 7 is the tie-breaker bit (0.5). Bits [6:0] are sticky bits.
    // Bit 8 is the LSB of the final mantissa used to force rounding to even.
    assign round_up = s3_norm_mag[7] & (|s3_norm_mag[6:0] | s3_norm_mag[8]);
    
    // Add round bit to the extracted 23-bit mantissa space
    assign rounded_mantissa = {1'b0, s3_norm_mag[30:8]} + round_up;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0;
            data_out  <= 32'b0;
        end else begin
            valid_out <= s3_valid;
            
            if (s3_is_zero) begin
                data_out <= 32'b0; // Clean zero
            end else begin
                // Check if the mantissa cascaded and overflowed during rounding
                if (rounded_mantissa[23]) begin
                    data_out <= {s3_sign, s3_exp + 8'd1, 23'b0};
                end else begin
                    data_out <= {s3_sign, s3_exp, rounded_mantissa[22:0]};
                end
            end
        end
    end

endmodule
