module mac (
    input  logic        clk,
    input  logic        rst,
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [31:0] out
);

    // Combinational product: 8sx8s = 16-bit signed, zero-extended to 32-bit
    logic signed [15:0] product;
    assign product = a * b;

    always_ff @(posedge clk) begin
        if (rst) begin
            out <= 32'sd0;
        end else begin
            out <= out + 32'(product);
        end
    end

endmodule
