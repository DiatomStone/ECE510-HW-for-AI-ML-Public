// =========================================================================
// Module:  mac  (Weight-Stationary MAC / Processing Element)
// Project: GELU Activation Kernel - ECE 410/510, M3 (systolic array add-on)
//
// Description:
//   Single processing element (PE) of a weight-stationary systolic array.
//   Holds one stationary weight and performs a Q16.16 multiply-accumulate:
//
//       psum_out = saturate( psum_in + (a_in * w_q) >> FRAC_BITS )
//
//   It also forwards the activation to its right neighbour (a_out) so that a
//   row of PEs streams one activation per cycle. The partial sum (psum_out)
//   is passed to the PE below so a column of PEs accumulates a dot product.
//
//   Fixed-point convention matches the rest of the project (compute_core):
//   signed Q16.16, full 64-bit product, arithmetic shift right by FRAC_BITS,
//   then saturate to signed DATA_WIDTH. Truncation (toward -inf), no rounding.
//
//   Latency: 1 cycle. a_out and psum_out are registered versions of the
//   inputs sampled on the previous rising edge.
//
// Parameters:
//   DATA_WIDTH - operand/result width (default 32, matches Q16.16)
//   FRAC_BITS  - fractional bit count for the Q format (default 16)
//
// Ports:
//   clk       - input,  1          : System clock
//   rst       - input,  1          : Synchronous active-high reset (clears w/regs)
//   load_w    - input,  1          : Capture w_in into the stationary weight reg
//   w_in      - input,  DATA_WIDTH : Signed Q16.16 weight to load
//   a_in      - input,  DATA_WIDTH : Signed Q16.16 activation from the left
//   psum_in   - input,  DATA_WIDTH : Signed Q16.16 partial sum from above
//   a_out     - output, DATA_WIDTH : Registered activation to the right
//   psum_out  - output, DATA_WIDTH : Registered partial sum to below
// =========================================================================

module mac #(
    parameter int DATA_WIDTH = 32,
    parameter int FRAC_BITS  = 16
)(
    input  logic                         clk,
    input  logic                         rst,
    input  logic                         load_w,
    input  logic signed [DATA_WIDTH-1:0] w_in,
    input  logic signed [DATA_WIDTH-1:0] a_in,
    input  logic signed [DATA_WIDTH-1:0] psum_in,
    output logic signed [DATA_WIDTH-1:0] a_out,
    output logic signed [DATA_WIDTH-1:0] psum_out
);

    // Stationary weight register.
    logic signed [DATA_WIDTH-1:0] w_q;

    // Full-width MAC. The 2*DATA_WIDTH LHS forces the product to be evaluated
    // at full width (same trick compute_core relies on), then >>> aligns the
    // Q32.32 product back to Q16.16 before adding the (sign-extended) psum_in.
    logic signed [2*DATA_WIDTH-1:0] prod;
    logic signed [2*DATA_WIDTH-1:0] sum_ext;

    assign prod    = a_in * w_q;
    assign sum_ext = (prod >>> FRAC_BITS) + psum_in;

    // A value fits in signed DATA_WIDTH when the top DATA_WIDTH+1 bits are all
    // sign (all 0 or all 1). Otherwise clamp to the signed min/max.
    logic [DATA_WIDTH:0] top_bits;
    logic                fits;
    assign top_bits = sum_ext[2*DATA_WIDTH-1 : DATA_WIDTH-1];
    assign fits     = (&top_bits) | (~|top_bits);

    always_ff @(posedge clk) begin
        if (rst) begin
            w_q      <= '0;
            a_out    <= '0;
            psum_out <= '0;
        end else begin
            if (load_w) w_q <= w_in;
            a_out <= a_in;
            if (fits)
                psum_out <= sum_ext[DATA_WIDTH-1:0];
            else if (sum_ext[2*DATA_WIDTH-1])
                psum_out <= {1'b1, {(DATA_WIDTH-1){1'b0}}};   // most negative
            else
                psum_out <= {1'b0, {(DATA_WIDTH-1){1'b1}}};   // most positive
        end
    end

endmodule
