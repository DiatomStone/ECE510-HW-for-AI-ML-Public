module mac (
    input  logic        clk,
    input  logic        rst,
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [31:0] out
);

    logic signed [15:0] product;

    always_ff @(posedge clk) begin
        if (rst) begin
            out <= 32'sd0;
        end else begin
            product = a * b;
            out <= out + 32'(product);
        end
    end
    // Add this for VCD generation
initial begin
    $dumpfile("dump.vcd"); // Name of the file to be created
    $dumpvars(0, mac);     // 0 means dump all signals in 'mac' and below
end

endmodule
