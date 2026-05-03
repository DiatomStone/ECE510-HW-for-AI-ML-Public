// =========================================================================
// Module:  gelu_axi_stream_interface
// Project: GELU Activation Kernel - ECE 410/510, M2
// Author:  Created with Cursor - Manager (Claude Opus 4.6)
// Created: 2026-05-03
// Modified: 2026-05-03
//
// Description:
//   AXI4-Stream data interface for the GELU compute core. This module is the
//   FPGA-side streaming block intended to connect to vendor PCIe + DMA IP.
//   The PCIe endpoint and DMA engine are assumed external IP blocks; their
//   streaming data path connects to this module using AXI4-Stream.
//
// Protocol:
//   AXI4-Stream, 32-bit TDATA, optional TLAST/TUSER metadata propagation.
//   A transfer occurs only when TVALID and TREADY are both asserted on the
//   same rising clock edge. The input and output channels both honor the
//   TVALID/TREADY contract.
//
// Transaction Format:
//   Each input beat is one signed Q16.16 GELU operand in s_axis_tdata.
//   Each output beat is one signed Q16.16 GELU result in m_axis_tdata.
//   TLAST marks the final beat of a DMA packet and is delayed to match the
//   corresponding output. TUSER is forwarded with the same delay.
//
// Clock Domain:
//   Single clock domain (clk). All sequential logic on posedge clk.
//
// Reset:
//   Synchronous, active-high (rst). Clears stream control, metadata pipeline,
//   FIFO pointers, and counters.
//
// Backpressure:
//   compute_core has fixed latency and no stall input. This wrapper tracks
//   in-flight operations and buffers completed outputs in a small FIFO, then
//   deasserts s_axis_tready before the pending output capacity is exhausted.
//
// Ports:
//   clk           - input,  1-bit                  : System clock
//   rst           - input,  1-bit                  : Synchronous active-high reset
//   s_axis_tvalid - input,  1-bit                  : Input stream data valid
//   s_axis_tready - output, 1-bit                  : Input stream ready
//   s_axis_tdata  - input,  [DATA_WIDTH-1:0] signed: Input operand, Q16.16
//   s_axis_tlast  - input,  1-bit                  : Input packet end marker
//   s_axis_tuser  - input,  [USER_WIDTH-1:0]       : Input sideband metadata
//   m_axis_tvalid - output, 1-bit                  : Output stream data valid
//   m_axis_tready - input,  1-bit                  : Output stream ready
//   m_axis_tdata  - output, [DATA_WIDTH-1:0] signed: GELU result, Q16.16
//   m_axis_tlast  - output, 1-bit                  : Output packet end marker
//   m_axis_tuser  - output, [USER_WIDTH-1:0]       : Output sideband metadata
// =========================================================================

module gelu_axi_stream_interface #(
    parameter int DATA_WIDTH = 32,
    parameter int USER_WIDTH = 1,
    parameter int PIPE_DEPTH = 5,
    parameter int FIFO_DEPTH = 16
)(
    input  logic                         clk,
    input  logic                         rst,

    input  logic                         s_axis_tvalid,
    output logic                         s_axis_tready,
    input  logic signed [DATA_WIDTH-1:0] s_axis_tdata,
    input  logic                         s_axis_tlast,
    input  logic        [USER_WIDTH-1:0] s_axis_tuser,

    output logic                         m_axis_tvalid,
    input  logic                         m_axis_tready,
    output logic signed [DATA_WIDTH-1:0] m_axis_tdata,
    output logic                         m_axis_tlast,
    output logic        [USER_WIDTH-1:0] m_axis_tuser
);

    localparam int FIFO_COUNT_WIDTH = $clog2(FIFO_DEPTH + 1);
    localparam int FIFO_PTR_WIDTH   = $clog2(FIFO_DEPTH);
    localparam logic [FIFO_COUNT_WIDTH:0] FIFO_CAPACITY = FIFO_DEPTH;

    logic axis_in_fire;
    logic axis_out_fire;

    logic core_valid_out;
    logic signed [DATA_WIDTH-1:0] core_out;

    logic [PIPE_DEPTH-1:0] meta_valid_pipe;
    logic [PIPE_DEPTH-1:0] meta_tlast_pipe;
    logic [USER_WIDTH-1:0] meta_tuser_pipe [PIPE_DEPTH];

    logic signed [DATA_WIDTH-1:0] fifo_data  [FIFO_DEPTH];
    logic                         fifo_tlast [FIFO_DEPTH];
    logic        [USER_WIDTH-1:0] fifo_tuser [FIFO_DEPTH];

    logic [FIFO_PTR_WIDTH-1:0] fifo_wr_ptr;
    logic [FIFO_PTR_WIDTH-1:0] fifo_rd_ptr;
    logic [FIFO_COUNT_WIDTH-1:0] fifo_count;
    logic [FIFO_COUNT_WIDTH-1:0] in_flight_count;
    logic [FIFO_COUNT_WIDTH:0] pending_count;

    assign pending_count = fifo_count + in_flight_count;
    assign s_axis_tready = (pending_count < FIFO_CAPACITY);

    assign axis_in_fire  = s_axis_tvalid && s_axis_tready;
    assign axis_out_fire = m_axis_tvalid && m_axis_tready;

    assign m_axis_tvalid = (fifo_count != '0);
    assign m_axis_tdata  = fifo_data[fifo_rd_ptr];
    assign m_axis_tlast  = fifo_tlast[fifo_rd_ptr];
    assign m_axis_tuser  = fifo_tuser[fifo_rd_ptr];

    compute_core #(
        .DATA_WIDTH(DATA_WIDTH),
        .FRAC_BITS(16),
        .PIPE_DEPTH(PIPE_DEPTH)
    ) u_compute_core (
        .clk       (clk),
        .rst       (rst),
        .valid_in  (axis_in_fire),
        .x         (s_axis_tdata),
        .valid_out (core_valid_out),
        .out       (core_out)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            meta_valid_pipe <= '0;
            meta_tlast_pipe <= '0;
            for (int i = 0; i < PIPE_DEPTH; i++) begin
                meta_tuser_pipe[i] <= '0;
            end
        end else begin
            meta_valid_pipe <= {meta_valid_pipe[PIPE_DEPTH-2:0], axis_in_fire};
            meta_tlast_pipe <= {meta_tlast_pipe[PIPE_DEPTH-2:0], axis_in_fire ? s_axis_tlast : 1'b0};
            meta_tuser_pipe[0] <= axis_in_fire ? s_axis_tuser : '0;
            for (int i = 1; i < PIPE_DEPTH; i++) begin
                meta_tuser_pipe[i] <= meta_tuser_pipe[i-1];
            end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            fifo_wr_ptr     <= '0;
            fifo_rd_ptr     <= '0;
            fifo_count      <= '0;
            in_flight_count <= '0;
        end else begin
            if (core_valid_out) begin
                fifo_data[fifo_wr_ptr]  <= core_out;
                fifo_tlast[fifo_wr_ptr] <= meta_tlast_pipe[PIPE_DEPTH-1];
                fifo_tuser[fifo_wr_ptr] <= meta_tuser_pipe[PIPE_DEPTH-1];
                fifo_wr_ptr             <= fifo_wr_ptr + 1'b1;
            end

            if (axis_out_fire) begin
                fifo_rd_ptr <= fifo_rd_ptr + 1'b1;
            end

            case ({core_valid_out, axis_out_fire})
                2'b10: fifo_count <= fifo_count + 1'b1;
                2'b01: fifo_count <= fifo_count - 1'b1;
                default: fifo_count <= fifo_count;
            endcase

            case ({axis_in_fire, core_valid_out})
                2'b10: in_flight_count <= in_flight_count + 1'b1;
                2'b01: in_flight_count <= in_flight_count - 1'b1;
                default: in_flight_count <= in_flight_count;
            endcase
        end
    end

endmodule
