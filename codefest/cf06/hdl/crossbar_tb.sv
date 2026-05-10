// Created with Cursor - Manager (GPT-5.5)
// Created: 2026-05-06
// Modified: 2026-05-10
//
// Self-checking SystemVerilog testbench for crossbar_mac.

`timescale 1ns/1ps

module crossbar_tb;
    logic clk;
    logic rst;
    logic load_weights;
    logic [15:0] weight_in;

    logic signed [7:0] in0;
    logic signed [7:0] in1;
    logic signed [7:0] in2;
    logic signed [7:0] in3;

    logic signed [10:0] out0;
    logic signed [10:0] out1;
    logic signed [10:0] out2;
    logic signed [10:0] out3;

    int failures;

    crossbar_mac dut (
        .clk          (clk),
        .rst          (rst),
        .load_weights (load_weights),
        .weight_in    (weight_in),
        .in0          (in0),
        .in1          (in1),
        .in2          (in2),
        .in3          (in3),
        .out0         (out0),
        .out1         (out1),
        .out2         (out2),
        .out3         (out3)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task automatic reset_dut;
        begin
            rst = 1'b1;
            load_weights = 1'b0;
            weight_in = '0;
            in0 = '0;
            in1 = '0;
            in2 = '0;
            in3 = '0;
            repeat (2) @(posedge clk);
            rst = 1'b0;
            @(posedge clk);
        end
    endtask

    task automatic load_weight_matrix(input logic [15:0] weights);
        begin
            @(negedge clk);
            weight_in = weights;
            load_weights = 1'b1;

            @(posedge clk);

            @(negedge clk);
            load_weights = 1'b0;
            weight_in = '0;

            // Allow one clock with the newly loaded registered weights before checking outputs.
            @(posedge clk);
        end
    endtask

    task automatic check_vector(
        input string name,
        input logic signed [7:0] test_in0,
        input logic signed [7:0] test_in1,
        input logic signed [7:0] test_in2,
        input logic signed [7:0] test_in3,
        input logic signed [10:0] exp0,
        input logic signed [10:0] exp1,
        input logic signed [10:0] exp2,
        input logic signed [10:0] exp3
    );
        begin
            @(negedge clk);
            in0 = test_in0;
            in1 = test_in1;
            in2 = test_in2;
            in3 = test_in3;

            @(posedge clk);
            #1;

            $display(
                "%s inputs=(%0d,%0d,%0d,%0d) expected=(%0d,%0d,%0d,%0d) got=(%0d,%0d,%0d,%0d)",
                name, test_in0, test_in1, test_in2, test_in3,
                exp0, exp1, exp2, exp3, out0, out1, out2, out3
            );

            if (out0 !== exp0) begin
                $display("FAIL: %s out0 mismatch", name);
                failures++;
            end
            if (out1 !== exp1) begin
                $display("FAIL: %s out1 mismatch", name);
                failures++;
            end
            if (out2 !== exp2) begin
                $display("FAIL: %s out2 mismatch", name);
                failures++;
            end
            if (out3 !== exp3) begin
                $display("FAIL: %s out3 mismatch", name);
                failures++;
            end
        end
    endtask

    initial begin
        failures = 0;
        reset_dut();

        // Test matrix:
        //   [[ 1, -1,  1, -1],
        //    [ 1,  1, -1, -1],
        //    [-1,  1,  1, -1],
        //    [-1, -1, -1,  1]]
        //
        // weight_in is row-major with bit 1 = +1 and bit 0 = -1:
        //   row0 = 4'b0101, row1 = 4'b0011, row2 = 4'b0110, row3 = 4'b1000
        load_weight_matrix(16'h8635);

        // Input vector [10, 20, 30, 40].
        // Expected:
        //   out0 =  10 + 20 - 30 - 40 = -40
        //   out1 = -10 + 20 + 30 - 40 =   0
        //   out2 =  10 - 20 + 30 - 40 = -20
        //   out3 = -10 - 20 - 30 + 40 = -20
        check_vector("requested_matrix_vector", 8'sd10, 8'sd20, 8'sd30, 8'sd40,
                                                -11'sd40, 11'sd0, -11'sd20, -11'sd20);

        if (failures == 0) begin
            $display("PASS: crossbar_mac SystemVerilog testbench matched expected binary-weight sums");
        end else begin
            $display("FAIL: crossbar_mac SystemVerilog testbench saw %0d failures", failures);
        end

        $finish;
    end
endmodule
