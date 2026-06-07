// =========================================================================
// Module:  gelu_dma_top_x32
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   32-lane / wide revision of gelu_dma_top. Connects the macro-free wide DMA
//   buffers to the parallel kernel:
//     mm2s_buffer_x32 — DMA AXI4-MM write -> wide FIFO -> AXI-Stream -> kernel
//     gelu_top_x32    — 32 parallel gelu_fp32 pipelines (1024-bit AXI-Stream)
//     s2mm_buffer_x32 — AXI-Stream <- kernel -> wide FIFO -> DMA AXI4-MM read
//
//   The whole datapath is DATA_W = NUM_LANES*32 = 1024 bits wide: every AXI
//   beat (both the AXI4-MM DMA side and the internal AXI-Stream) carries
//   NUM_LANES = 32 packed IEEE-754 FP32 operands, lane i at bits [i*32 +: 32].
//
//   Buffers are sized DEPTH = 256 beats — one max-length AXI4 burst (AxLEN is
//   8-bit) — sufficient for the serial DMA-write -> stream -> DMA-read test
//   pattern. They are inferred register-array FIFOs (no SRAM macro / blackbox).
//
//   Control:
//     AXI4-Lite on gelu_top_x32 gates the kernel (pipeline_enable, 0x00).
//     stream_enable on mm2s_buffer_x32 gates streaming into the kernel.
//
// Hierarchy:
//   gelu_dma_top_x32
//     ├── mm2s_buffer_x32   (AXI4-MM write + wide FIFO + AXI-Stream master)
//     ├── gelu_top_x32      (32 parallel gelu_fp32 pipelines)
//     └── s2mm_buffer_x32   (AXI-Stream slave + wide FIFO + AXI4-MM read)
// =========================================================================

// Lane count: default 32 (x32). Override with -DGELU_NUM_LANES=8 (Icarus) or
// VERILOG_DEFINES (OpenLane) to build the x8 variant — one parameterized source.
`ifndef GELU_NUM_LANES
  `define GELU_NUM_LANES 32
`endif

module gelu_dma_top_x32 #(
    parameter int NUM_LANES = `GELU_NUM_LANES,    // parallel pipelines
    parameter int DATA_W    = NUM_LANES * 32,     // packed bus width
    parameter int DEPTH     = 256                 // buffer depth in beats (1 AXI burst)
)(
    input  logic                clk,
    input  logic                rst,
    input  logic                stream_enable,

    // AXI4-Lite — kernel pipeline_enable control
    input  logic [31:0]         s_axil_awaddr,
    input  logic                s_axil_awvalid,
    output logic                s_axil_awready,
    input  logic [31:0]         s_axil_wdata,
    input  logic [3:0]          s_axil_wstrb,
    input  logic                s_axil_wvalid,
    output logic                s_axil_wready,
    output logic [1:0]          s_axil_bresp,
    output logic                s_axil_bvalid,
    input  logic                s_axil_bready,
    input  logic [31:0]         s_axil_araddr,
    input  logic                s_axil_arvalid,
    output logic                s_axil_arready,
    output logic [31:0]         s_axil_rdata,
    output logic [1:0]          s_axil_rresp,
    output logic                s_axil_rvalid,
    input  logic                s_axil_rready,

    // AXI4-MM write slave — DMA fills input buffer (wide)
    input  logic [31:0]         dma_in_awaddr,
    input  logic [7:0]          dma_in_awlen,
    input  logic                dma_in_awvalid,
    output logic                dma_in_awready,
    input  logic [DATA_W-1:0]   dma_in_wdata,
    input  logic [DATA_W/8-1:0] dma_in_wstrb,
    input  logic                dma_in_wlast,
    input  logic                dma_in_wvalid,
    output logic                dma_in_wready,
    output logic [1:0]          dma_in_bresp,
    output logic                dma_in_bvalid,
    input  logic                dma_in_bready,

    // AXI4-MM read slave — DMA drains output buffer (wide)
    input  logic [31:0]         dma_out_araddr,
    input  logic [7:0]          dma_out_arlen,
    input  logic                dma_out_arvalid,
    output logic                dma_out_arready,
    output logic [DATA_W-1:0]   dma_out_rdata,
    output logic [1:0]          dma_out_rresp,
    output logic                dma_out_rvalid,
    input  logic                dma_out_rready,
    output logic                dma_out_rlast
);

    // Internal AXI-Stream: mm2s_buffer_x32 -> gelu_top_x32
    logic [DATA_W-1:0] axis_in_tdata;
    logic              axis_in_tvalid;
    logic              axis_in_tready;
    logic              axis_in_tlast;

    // Internal AXI-Stream: gelu_top_x32 -> s2mm_buffer_x32
    logic [DATA_W-1:0] axis_out_tdata;
    logic              axis_out_tvalid;
    logic              axis_out_tready;
    logic              axis_out_tlast;
    logic              axis_out_tuser;

    // ----------------------------------------------------------------
    // Input buffer: DMA write bursts -> wide FIFO -> stream to kernel
    // ----------------------------------------------------------------
    mm2s_buffer_x32 #(
        .DATA_W (DATA_W),
        .DEPTH  (DEPTH)
    ) u_mm2s (
        .clk            (clk),
        .rst            (rst),
        .s_axi_awaddr   (dma_in_awaddr),
        .s_axi_awlen    (dma_in_awlen),
        .s_axi_awvalid  (dma_in_awvalid),
        .s_axi_awready  (dma_in_awready),
        .s_axi_wdata    (dma_in_wdata),
        .s_axi_wstrb    (dma_in_wstrb),
        .s_axi_wlast    (dma_in_wlast),
        .s_axi_wvalid   (dma_in_wvalid),
        .s_axi_wready   (dma_in_wready),
        .s_axi_bresp    (dma_in_bresp),
        .s_axi_bvalid   (dma_in_bvalid),
        .s_axi_bready   (dma_in_bready),
        .m_axis_tdata   (axis_in_tdata),
        .m_axis_tvalid  (axis_in_tvalid),
        .m_axis_tready  (axis_in_tready),
        .m_axis_tlast   (axis_in_tlast),
        .stream_enable  (stream_enable)
    );

    // ----------------------------------------------------------------
    // 32-lane GELU kernel
    // ----------------------------------------------------------------
    gelu_top_x32 #(
        .NUM_LANES (NUM_LANES)
    ) u_gelu (
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
        .s_axis_tdata   (axis_in_tdata),
        .s_axis_tvalid  (axis_in_tvalid),
        .s_axis_tready  (axis_in_tready),
        .s_axis_tlast   (axis_in_tlast),
        .s_axis_tuser   (1'b0),
        .m_axis_tdata   (axis_out_tdata),
        .m_axis_tvalid  (axis_out_tvalid),
        .m_axis_tready  (axis_out_tready),
        .m_axis_tlast   (axis_out_tlast),
        .m_axis_tuser   (axis_out_tuser)
    );

    // ----------------------------------------------------------------
    // Output buffer: stream from kernel -> wide FIFO -> DMA read bursts
    // ----------------------------------------------------------------
    s2mm_buffer_x32 #(
        .DATA_W (DATA_W),
        .DEPTH  (DEPTH)
    ) u_s2mm (
        .clk            (clk),
        .rst            (rst),
        .s_axis_tdata   (axis_out_tdata),
        .s_axis_tvalid  (axis_out_tvalid),
        .s_axis_tready  (axis_out_tready),
        .s_axis_tlast   (axis_out_tlast),
        .m_axi_araddr   (dma_out_araddr),
        .m_axi_arlen    (dma_out_arlen),
        .m_axi_arvalid  (dma_out_arvalid),
        .m_axi_arready  (dma_out_arready),
        .m_axi_rdata    (dma_out_rdata),
        .m_axi_rresp    (dma_out_rresp),
        .m_axi_rvalid   (dma_out_rvalid),
        .m_axi_rready   (dma_out_rready),
        .m_axi_rlast    (dma_out_rlast)
    );

endmodule
