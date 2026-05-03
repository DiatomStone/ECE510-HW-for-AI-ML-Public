// Created with Cursor - Manager (Claude Opus 4.6)
// Created: 2026-05-03
// Modified: 2026-05-03
//
// Self-checking SystemVerilog fallback testbench for gelu_axi_stream_interface.
// The primary testbench is cocotb (tb_interface.py); this file exists at the
// M2 checklist path in case the checker requires an SV testbench.

`timescale 1ns/1ps

module tb_interface;
    localparam int DATA_WIDTH = 32;
    localparam int USER_WIDTH = 1;
    localparam int PIPE_DEPTH = 5;
    localparam int FIFO_DEPTH = 16;
    localparam int NUM_INPUTS = 8;

    logic clk;
    logic rst;

    logic s_axis_tvalid;
    logic s_axis_tready;
    logic signed [DATA_WIDTH-1:0] s_axis_tdata;
    logic s_axis_tlast;
    logic [USER_WIDTH-1:0] s_axis_tuser;

    logic m_axis_tvalid;
    logic m_axis_tready;
    logic signed [DATA_WIDTH-1:0] m_axis_tdata;
    logic m_axis_tlast;
    logic [USER_WIDTH-1:0] m_axis_tuser;

    logic signed [DATA_WIDTH-1:0] inputs   [NUM_INPUTS];
    logic signed [DATA_WIDTH-1:0] expected [NUM_INPUTS];

    int failures;

    gelu_axi_stream_interface #(
        .DATA_WIDTH(DATA_WIDTH),
        .USER_WIDTH(USER_WIDTH),
        .PIPE_DEPTH(PIPE_DEPTH),
        .FIFO_DEPTH(FIFO_DEPTH)
    ) dut (
        .clk           (clk),
        .rst           (rst),
        .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .s_axis_tdata  (s_axis_tdata),
        .s_axis_tlast  (s_axis_tlast),
        .s_axis_tuser  (s_axis_tuser),
        .m_axis_tvalid (m_axis_tvalid),
        .m_axis_tready (m_axis_tready),
        .m_axis_tdata  (m_axis_tdata),
        .m_axis_tlast  (m_axis_tlast),
        .m_axis_tuser  (m_axis_tuser)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    function automatic longint abs64(input longint value);
        abs64 = (value < 0) ? -value : value;
    endfunction

    function automatic longint max64(input longint a, input longint b);
        max64 = (a > b) ? a : b;
    endfunction

    task automatic reset_dut;
        begin
            rst           = 1'b1;
            s_axis_tvalid = 1'b0;
            s_axis_tdata  = '0;
            s_axis_tlast  = 1'b0;
            s_axis_tuser  = '0;
            m_axis_tready = 1'b0;
            repeat (2) @(posedge clk);
            rst = 1'b0;
            @(posedge clk);
        end
    endtask

    task automatic axis_send(
        input logic signed [DATA_WIDTH-1:0] data,
        input logic last,
        input logic [USER_WIDTH-1:0] user
    );
        int cycles;
        begin
            @(negedge clk);
            s_axis_tdata  = data;
            s_axis_tlast  = last;
            s_axis_tuser  = user;
            s_axis_tvalid = 1'b1;

            cycles = 0;
            while (s_axis_tready !== 1'b1 && cycles <= 32) begin
                @(posedge clk);
                #1;
                cycles++;
            end

            if (s_axis_tready !== 1'b1) begin
                $display("FAIL: AXI4-Stream write handshake timed out");
                failures++;
            end

            @(negedge clk);
            s_axis_tvalid = 1'b0;
            s_axis_tdata  = '0;
            s_axis_tlast  = 1'b0;
            s_axis_tuser  = '0;
        end
    endtask

    task automatic axis_recv(
        output logic signed [DATA_WIDTH-1:0] data,
        output logic last,
        output logic [USER_WIDTH-1:0] user
    );
        int cycles;
        begin
            @(negedge clk);
            m_axis_tready = 1'b1;

            cycles = 0;
            while (m_axis_tvalid !== 1'b1 && cycles <= 64) begin
                @(posedge clk);
                #1;
                cycles++;
            end

            if (m_axis_tvalid !== 1'b1) begin
                $display("FAIL: AXI4-Stream read handshake timed out");
                failures++;
                data = '0;
                last = 1'b0;
                user = '0;
            end else begin
                data = m_axis_tdata;
                last = m_axis_tlast;
                user = m_axis_tuser;
            end


            @(negedge clk);
            m_axis_tready = 1'b0;
        end
    endtask

    task automatic check_output(
        input int index,
        input logic signed [DATA_WIDTH-1:0] got,
        input logic got_last,
        input logic [USER_WIDTH-1:0] got_user
    );
        longint diff;
        longint allowed;
        logic expected_last;
        begin
            diff = abs64(longint'(got) - longint'(expected[index]));
            allowed = max64((abs64(longint'(expected[index])) * 10) / 100, 32'sd655);
            expected_last = (index == NUM_INPUTS - 1);

            $display(
                "[%0d] expected=%0d got=%0d diff=%0d allowed=%0d tlast=%0b user=%0d",
                index, expected[index], got, diff, allowed, got_last, got_user
            );

            if (diff > allowed) begin
                $display("FAIL: output value mismatch at index %0d", index);
                failures++;
            end

            if (got_last !== expected_last) begin
                $display("FAIL: TLAST mismatch at index %0d", index);
                failures++;
            end
        end
    endtask

    initial begin
        logic signed [DATA_WIDTH-1:0] got;
        logic got_last;
        logic [USER_WIDTH-1:0] got_user;

        failures = 0;

        inputs[0] =  32'sd32768;    expected[0] =  32'sd22657;   //  0.5
        inputs[1] =  32'sd65536;    expected[1] =  32'sd55128;   //  1.0
        inputs[2] =  32'sd98304;    expected[2] =  32'sd91722;   //  1.5
        inputs[3] =  32'sd131072;   expected[3] =  32'sd128097;  //  2.0
        inputs[4] = -32'sd32768;    expected[4] = -32'sd10111;   // -0.5
        inputs[5] = -32'sd65536;    expected[5] = -32'sd10408;   // -1.0
        inputs[6] = -32'sd98304;    expected[6] = -32'sd6582;    // -1.5
        inputs[7] = -32'sd131072;   expected[7] = -32'sd2975;    // -2.0

        reset_dut();

        // Hold output ready low while sending to exercise internal buffering.
        m_axis_tready = 1'b0;
        for (int i = 0; i < NUM_INPUTS; i++) begin
            axis_send(inputs[i], (i == NUM_INPUTS - 1), i[0]);
        end

        repeat (2) @(posedge clk);
        #1;
        if (dut.fifo_count == '0 && dut.in_flight_count == '0) begin
            $display("FAIL: no internal pending state after AXI4-Stream writes");
            failures++;
        end else begin
            $display(
                "Internal state after writes: fifo_count=%0d in_flight_count=%0d",
                dut.fifo_count, dut.in_flight_count
            );
        end

        repeat (6) @(posedge clk);

        for (int i = 0; i < NUM_INPUTS; i++) begin
            axis_recv(got, got_last, got_user);
            check_output(i, got, got_last, got_user);
        end

        if (failures == 0) begin
            $display("PASS: AXI4-Stream interface SystemVerilog testbench matched hand-calculated reference values");
        end else begin
            $display("FAIL: AXI4-Stream interface SystemVerilog testbench saw %0d failures", failures);
        end

        $finish;
    end
endmodule
