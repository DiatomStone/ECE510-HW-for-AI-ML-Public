module mac (
    input clk,
    input rst,
    input signed [7:0] a,
    input signed [7:0] b,
    output signed [31:0] out
);

    // Use always_ff for synchronous sequential logic (flip-flop behavior)
    always_ff @(posedge clk) begin
        if (rst) begin
            // Synchronous reset: set out to 0
            out <= 32'd0;
        end else begin
            // Accumulate: out = out + (a * b)
            // SystemVerilog handles the signed multiplication of a and b,
            // and the result is correctly widened and added to the 32-bit out.
            out <= out + (a * b);
        end
    end

endmodule



