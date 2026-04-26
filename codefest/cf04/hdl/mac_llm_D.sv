module mac (
    input  logic              clk,   // 1-bit clock
    input  logic              rst,   // 1-bit active-high synchronous reset
    input  logic signed [7:0] a,     // 8-bit signed input
    input  logic signed [7:0] b,     // 8-bit signed input
    output logic signed [31:0] out   // 32-bit signed accumulator
);

    // Sequential logic block for the multiply-accumulate operation
    always_ff @(posedge clk) begin
        if (rst) begin
            // Synchronous reset: clear the accumulator to 0
            out <= 32'sd0;
        end else begin
            // Multiply-Accumulate: out = out + (a * b)
            // SystemVerilog handles the sign extension from the 16-bit 
            // product (a*b) to the 32-bit accumulator automatically
            // because the operands and output are declared as signed.
            out <= out + (a * b);
        end
    end

endmodule


