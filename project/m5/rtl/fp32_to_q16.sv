// =========================================================================
// Module:  fp32_to_q16
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   4-stage pipelined IEEE-754 single-precision FP32 to Q16.16 converter.
//   Implements Round-to-Nearest-Even (RNE). Subnormal inputs are flushed to
//   zero (FTZ), consistent with AI hardware conventions. Values outside the
//   Q16.16 representable range [-32768, 32767.99998] are saturated.
//
//   Stage 1: Unpack IEEE-754 fields; detect subnormals.
//   Stage 2: Compute right-shift amount; detect overflow.
//   Stage 3: Barrel-shift 64-bit vector to retain sticky bits for RNE.
//   Stage 4: Apply RNE rounding, two's complement for negatives, saturate.
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
//   valid_in  - input,  1  : Asserted when data_in holds a valid FP32 value
//   data_in   - input,  32 : IEEE-754 single-precision input
//   valid_out - output, 1  : Asserted when data_out holds a valid Q16.16 value
//   data_out  - output, 32 : Signed Q16.16 fixed-point result
// =========================================================================

module fp32_to_q16 (
    input  logic         clk,
    input  logic         rst,
    
    // FP32 Inputs
    input  logic         valid_in,
    input  logic [31:0]  data_in,
    
    // Q16.16 Outputs
    output logic         valid_out,
    output logic [31:0]  data_out
);

    // -------------------------------------------------------------------------
    // STAGE 1: Unpack & Subnormal Flush
    // Extracts IEEE fields and treats subnormals (exponent == 0) as exact zero, 
    // which is standard for high-performance AI hardware.
    // -------------------------------------------------------------------------
    logic        s1_valid, s1_sign, s1_is_zero;
    logic [7:0]  s1_exp;
    logic [22:0] s1_mant;

    always_ff @(posedge clk) begin
        if (rst) begin
            s1_valid   <= 1'b0;
            s1_sign    <= 1'b0;
            s1_exp     <= 8'b0;
            s1_mant    <= 23'b0;
            s1_is_zero <= 1'b0;
        end else begin
            s1_valid   <= valid_in;
            s1_sign    <= data_in[31];
            s1_exp     <= data_in[30:23];
            s1_mant    <= data_in[22:0];
            s1_is_zero <= (data_in[30:23] == 8'd0);
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 2: Shift Calculation & Overflow Detection
    // -------------------------------------------------------------------------
    logic        s2_valid, s2_sign, s2_is_zero, s2_overflow;
    logic [31:0] s2_norm_mag;
    logic [5:0]  s2_shift;

    // Hoisted from always_ff for Icarus compatibility (no automatic locals)
    logic signed [8:0] raw_shift;
    logic [63:0]       shift_in;
    logic [63:0]       shift_out;

    always_ff @(posedge clk) begin
        if (rst) begin
            s2_valid    <= 1'b0;
            s2_overflow <= 1'b0;
        end else begin
            s2_valid   <= s1_valid;
            s2_sign    <= s1_sign;
            s2_is_zero <= s1_is_zero;
            
            // Reconstruct the 32-bit absolute magnitude with the implicit '1'
            s2_norm_mag <= {1'b1, s1_mant, 8'b0};
            
            // Calculate right-shift amount: 142 - Exponent
            // Using a 9-bit signed calculation to catch under/overflow cleanly
            raw_shift = 9'sd142 - {1'b0, s1_exp};
            
            // Overflow bounds: 
            // Max positive Q16.16 is ~32767.99 (Exp=141).
            // Max negative Q16.16 is -32768.0  (Exp=142, Mant=0).
            if ((s1_exp > 8'd142) || 
                (s1_exp == 8'd142 && (s1_sign == 1'b0 || s1_mant != 23'd0))) begin
                s2_overflow <= 1'b1;
                s2_shift    <= 6'd0; // Shift doesn't matter, will be saturated
            end else begin
                s2_overflow <= 1'b0;
                // Cap shift at 63 to handle heavy underflows gracefully (forces to 0)
                s2_shift    <= (raw_shift > 9'sd63) ? 6'd63 : raw_shift[5:0];
            end
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 3: Barrel Shifter
    // Shifts a 64-bit vector to retain all sticky bits for precise rounding.
    // -------------------------------------------------------------------------
    logic        s3_valid, s3_sign, s3_is_zero, s3_overflow;
    logic [31:0] s3_mag;
    logic [31:0] s3_frac;

    always_ff @(posedge clk) begin
        if (rst) begin
            s3_valid <= 1'b0;
        end else begin
            s3_valid    <= s2_valid;
            s3_sign     <= s2_sign;
            s3_is_zero  <= s2_is_zero;
            s3_overflow <= s2_overflow;
            
            // Perform 64-bit right shift. 
            // Top 32 bits become the Q16.16 integer/fraction absolute magnitude.
            // Bottom 32 bits catch the remainder for RNE.
            shift_in  = {s2_norm_mag, 32'b0};
            shift_out = shift_in >> s2_shift;
            
            s3_mag  <= shift_out[63:32];
            s3_frac <= shift_out[31:0];
        end
    end

    // -------------------------------------------------------------------------
    // STAGE 4: Rounding (RNE), Sign Application, & Assembly
    // -------------------------------------------------------------------------
    logic        round_bit;
    logic        sticky_bit;
    logic        round_up;
    logic [31:0] rounded_mag;
    logic [31:0] signed_val;

    // RNE Logic exactly mirroring the forward module
    assign round_bit  = s3_frac[31];
    assign sticky_bit = |s3_frac[30:0];
    assign round_up   = round_bit & (sticky_bit | s3_mag[0]);
    
    assign rounded_mag = s3_mag + round_up;
    
    // Apply Two's Complement for negative numbers
    assign signed_val = s3_sign ? (~rounded_mag + 1'b1) : rounded_mag;

    always_ff @(posedge clk) begin
        if (rst) begin
            valid_out <= 1'b0;
            data_out  <= 32'b0;
        end else begin
            valid_out <= s3_valid;
            
            if (s3_is_zero) begin
                data_out <= 32'b0;
            end else if (s3_overflow || (!s3_sign && rounded_mag[31])) begin
                // Clamping behavior: If overflow occurs, or if positive rounding 
                // pushes into the sign bit, clamp to max limits.
                data_out <= s3_sign ? 32'sh8000_0000 : 32'sh7FFF_FFFF;
            end else begin
                data_out <= signed_val;
            end
        end
    end

endmodule
