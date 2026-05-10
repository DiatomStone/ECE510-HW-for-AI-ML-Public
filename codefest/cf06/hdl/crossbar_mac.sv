// Created with Cursor - Manager (GPT-5.5)
// Created: 2026-05-06
// Modified: 2026-05-10
//
// Module: crossbar_mac
//
// Description:
//   4x4 binary-weight crossbar multiply-accumulate block. Each output column
//   computes the signed sum of four 8-bit input lines multiplied by binary
//   weights encoded as +1 or -1.
//
// Operation:
//   out[j] = sum_i(weight[i][j] * in[i])
//
// Data format:
//   Inputs are signed 8-bit integers. Outputs are signed accumulators wide
//   enough to hold the sum of four signed 8-bit terms.
//
// Weight encoding:
//   weight_bit[i][j] = 1'b1 means +1
//   weight_bit[i][j] = 1'b0 means -1
//
// Ports:
//   clk          - input,  1-bit            : System clock
//   rst          - input,  1-bit            : Synchronous active-high reset
//   load_weights - input,  1-bit            : Load strobe for weight_in
//   weight_in    - input,  [15:0]           : Row-major 4x4 binary weights
//   in0-in3      - input,  signed [7:0]     : Input lines
//   out0-out3    - output, signed [10:0]    : Accumulator outputs

module crossbar_mac (
    input  logic              clk,
    input  logic              rst,
    input  logic              load_weights,
    input  logic [15:0]       weight_in,
    input  logic signed [7:0] in0,
    input  logic signed [7:0] in1,
    input  logic signed [7:0] in2,
    input  logic signed [7:0] in3,
    output logic signed [10:0] out0,
    output logic signed [10:0] out1,
    output logic signed [10:0] out2,
    output logic signed [10:0] out3
);

    logic weight_bit [4][4];
    logic signed [10:0] in_ext [4];
    logic signed [10:0] sum [4];

    assign in_ext[0] = {{3{in0[7]}}, in0};
    assign in_ext[1] = {{3{in1[7]}}, in1};
    assign in_ext[2] = {{3{in2[7]}}, in2};
    assign in_ext[3] = {{3{in3[7]}}, in3};

    always_comb begin
        for (int j = 0; j < 4; j++) begin
            sum[j] = '0;
            for (int i = 0; i < 4; i++) begin
                if (weight_bit[i][j]) begin
                    sum[j] += in_ext[i];
                end else begin
                    sum[j] -= in_ext[i];
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            for (int i = 0; i < 4; i++) begin
                for (int j = 0; j < 4; j++) begin
                    weight_bit[i][j] <= 1'b0;
                end
            end
            out0 <= '0;
            out1 <= '0;
            out2 <= '0;
            out3 <= '0;
        end else begin
            if (load_weights) begin
                for (int i = 0; i < 4; i++) begin
                    for (int j = 0; j < 4; j++) begin
                        weight_bit[i][j] <= weight_in[(i * 4) + j];
                    end
                end
            end
            out0 <= sum[0];
            out1 <= sum[1];
            out2 <= sum[2];
            out3 <= sum[3];
        end
    end

endmodule
