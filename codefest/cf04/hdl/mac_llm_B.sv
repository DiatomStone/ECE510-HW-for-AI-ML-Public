module mac (
    input  logic              clk,
    input  logic              rst,
    input  logic signed [7:0] a,
    input  logic signed [7:0] b,
    output logic signed [31:0] out
);

    // Sequential logic for the accumulator
    // Uses synchronous active-high reset as requested
    always_ff @(posedge clk) begin
        if (rst) begin
            out <= 32'sd0;
        end else begin
            // The multiplication of two 8-bit signed numbers results 
            // in a 15-bit signed result, which is then sign-extended 
            // to 32 bits and added to the current accumulator value.
            out <= out + (a * b);
        end
    end

endmodule
