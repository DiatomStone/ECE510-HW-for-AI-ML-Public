module mac (
    input  logic        clk,
    input  logic        rst,
    input  logic signed [7:0]  in_a,
    input  logic signed [7:0]  in_b,
    output  logic signed [7:0]  out_a,
    output  logic signed [7:0]  out_b,
    output  logic signed [32:0]  out
);

    logic signed [15:0] product;

    always_ff @(posedge clk) begin
        if (rst) begin
            out <= 32'sd0;
            out_a <= 8'sd0;
            out_b <= 8'sd0;
        end else begin
            product = a * b;
            out <= out + 32'(product);
            out_a <= in_a;
            out_b <= out_b;
        end
    end

endmodule
