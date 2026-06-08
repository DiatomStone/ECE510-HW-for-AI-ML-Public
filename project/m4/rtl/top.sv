// =========================================================================
// Module:  gelu_top
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Parallel revision of gelu_top. Wraps gelu_axi_stream_interface, which
//   instantiates NUM_LANES (=32) gelu_fp32 pipelines and processes NUM_LANES
//   packed FP32 operands per AXI-Stream beat (SIMD lockstep).
//
//   Hierarchy:
//     gelu_top
//       └── gelu_axi_stream_interface   (AXI protocol + FIFO + 32 lanes)
//             └── gelu_fp32  × NUM_LANES    (FP32 end-to-end datapath, 12 cyc)
//                   ├── fp32_to_q16
//                   ├── compute_core
//                   └── q16_to_fp32
//
//   Only difference vs gelu_top: the AXI4-Stream data buses are widened to
//   NUM_LANES*DATA_WIDTH bits.  s_axis_tdata[ (i+1)*32-1 : i*32 ] is lane i's
//   FP32 operand; m_axis_tdata is the matching packed result.  AXI4-Lite
//   control and all sideband signals are unchanged.
//
// Clock Domain: single clock (clk), all logic on posedge clk.
// Reset:        synchronous, active-high (rst).
// =========================================================================

// Lane count: default 32 (x32). Override with -DGELU_NUM_LANES=8 (Icarus) or
// VERILOG_DEFINES (OpenLane) to build the x8 variant — one parameterized source.
`ifndef GELU_NUM_LANES
  `define GELU_NUM_LANES 32
`endif

module gelu_top #(
    parameter int DATA_WIDTH = 32,   // per-lane FP32 width
    parameter int NUM_LANES  = `GELU_NUM_LANES,   // parallel gelu_fp32 pipelines
    parameter int USER_WIDTH = 1,
    parameter int PIPE_DEPTH = 12,
    parameter int FIFO_DEPTH = 16
)(
    input  logic clk,
    input  logic rst,

    // AXI4-Lite Slave (control)
    input  logic [31:0] s_axil_awaddr,
    input  logic        s_axil_awvalid,
    output logic        s_axil_awready,
    input  logic [31:0] s_axil_wdata,
    input  logic [3:0]  s_axil_wstrb,
    input  logic        s_axil_wvalid,
    output logic        s_axil_wready,
    output logic [1:0]  s_axil_bresp,
    output logic        s_axil_bvalid,
    input  logic        s_axil_bready,
    input  logic [31:0] s_axil_araddr,
    input  logic        s_axil_arvalid,
    output logic        s_axil_arready,
    output logic [31:0] s_axil_rdata,
    output logic [1:0]  s_axil_rresp,
    output logic        s_axil_rvalid,
    input  logic        s_axil_rready,

    // AXI4-Stream Slave (packed FP32 input — NUM_LANES operands per beat)
    input  logic [NUM_LANES*DATA_WIDTH-1:0] s_axis_tdata,
    input  logic                            s_axis_tvalid,
    output logic                            s_axis_tready,
    input  logic                            s_axis_tlast,
    input  logic [USER_WIDTH-1:0]           s_axis_tuser,

    // AXI4-Stream Master (packed FP32 output — NUM_LANES results per beat)
    output logic [NUM_LANES*DATA_WIDTH-1:0] m_axis_tdata,
    output logic                            m_axis_tvalid,
    input  logic                            m_axis_tready,
    output logic                            m_axis_tlast,
    output logic [USER_WIDTH-1:0]           m_axis_tuser
);

    gelu_axi_stream_interface #(
        .DATA_WIDTH (DATA_WIDTH),
        .NUM_LANES  (NUM_LANES),
        .USER_WIDTH (USER_WIDTH),
        .PIPE_DEPTH (PIPE_DEPTH),
        .FIFO_DEPTH (FIFO_DEPTH)
    ) u_interface (
        .clk            (clk),
        .rst            (rst),

        .s_axil_awaddr  (s_axil_awaddr),
        .s_axil_awvalid (s_axil_awvalid),
        .s_axil_awready (s_axil_awready),
        .s_axil_wdata   (s_axil_wdata),
        .s_axil_wstrb   (s_axil_wstrb),
        .s_axil_wvalid  (s_axil_wvalid),
        .s_axil_wready  (s_axil_wready),
        .s_axil_bresp   (s_axil_bresp),
        .s_axil_bvalid  (s_axil_bvalid),
        .s_axil_bready  (s_axil_bready),
        .s_axil_araddr  (s_axil_araddr),
        .s_axil_arvalid (s_axil_arvalid),
        .s_axil_arready (s_axil_arready),
        .s_axil_rdata   (s_axil_rdata),
        .s_axil_rresp   (s_axil_rresp),
        .s_axil_rvalid  (s_axil_rvalid),
        .s_axil_rready  (s_axil_rready),

        .s_axis_tdata   (s_axis_tdata),
        .s_axis_tvalid  (s_axis_tvalid),
        .s_axis_tready  (s_axis_tready),
        .s_axis_tlast   (s_axis_tlast),
        .s_axis_tuser   (s_axis_tuser),

        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tready  (m_axis_tready),
        .m_axis_tlast   (m_axis_tlast),
        .m_axis_tuser   (m_axis_tuser)
    );

endmodule
