module mac (
    input  logic               clk,
    input  logic               rst,
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [31:0] out
);

    // Behavioral logic for the Multiply-Accumulate unit
    always_ff @(posedge clk) begin
        if (rst) begin
            out <= 32'sd0;
        end else begin
            // The multiplication of two 8-bit signed values results in a 
            // 15-bit signed value, which is then sign-extended and 
            // added to the 32-bit accumulator.
            out <= out + (a * b);
        end
    end

endmodule
