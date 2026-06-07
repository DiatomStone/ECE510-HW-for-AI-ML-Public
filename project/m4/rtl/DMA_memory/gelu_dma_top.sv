// =========================================================================
// Module:  gelu_dma_top
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Top-level integration with DMA buffers. Connects:
//     mm2s_buffer  — DMA AXI4-MM write → 1K SRAM → AXI-Stream → kernel
//     gelu_top     — AXI-Stream kernel (fp32 → Q16.16 GELU → fp32)
//     s2mm_buffer  — AXI-Stream ← kernel → 1K SRAM → DMA AXI4-MM read
//
//   Control:
//     AXI4-Lite on gelu_top gates the kernel pipeline (pipeline_enable).
//     stream_enable on mm2s_buffer gates stream output to the kernel.
//     Both should be asserted after DMA fills the input buffer.
//
// Hierarchy:
//   gelu_dma_top
//     ├── mm2s_buffer      (AXI4-MM slave write + SRAM + AXI-Stream master)
//     │     └── openram_1k_wrap
//     ├── gelu_top         (existing kernel wrapper, untouched)
//     │     └── gelu_axi_stream_interface
//     │           └── gelu_fp32
//     └── s2mm_buffer      (AXI-Stream slave + SRAM + AXI4-MM slave read)
//           └── openram_1k_wrap
//
// Ports:
//   clk               - input,  1   : System clock
//   rst               - input,  1   : Synchronous active-high reset
//   stream_enable     - input,  1   : Enable mm2s → kernel stream
//   -- AXI4-Lite (kernel control, pipeline_enable) --
//   s_axil_awaddr     - input,  32
//   s_axil_awvalid    - input,  1
//   s_axil_awready    - output, 1
//   s_axil_wdata      - input,  32
//   s_axil_wstrb      - input,  4
//   s_axil_wvalid     - input,  1
//   s_axil_wready     - output, 1
//   s_axil_bresp      - output, 2
//   s_axil_bvalid     - output, 1
//   s_axil_bready     - input,  1
//   s_axil_araddr     - input,  32
//   s_axil_arvalid    - input,  1
//   s_axil_arready    - output, 1
//   s_axil_rdata      - output, 32
//   s_axil_rresp      - output, 2
//   s_axil_rvalid     - output, 1
//   s_axil_rready     - input,  1
//   -- AXI4-MM write slave (DMA → input buffer) --
//   dma_in_awaddr     - input,  32
//   dma_in_awlen      - input,  8
//   dma_in_awvalid    - input,  1
//   dma_in_awready    - output, 1
//   dma_in_wdata      - input,  32
//   dma_in_wstrb      - input,  4
//   dma_in_wlast      - input,  1
//   dma_in_wvalid     - input,  1
//   dma_in_wready     - output, 1
//   dma_in_bresp      - output, 2
//   dma_in_bvalid     - output, 1
//   dma_in_bready     - input,  1
//   -- AXI4-MM read slave (DMA ← output buffer) --
//   dma_out_araddr    - input,  32
//   dma_out_arlen     - input,  8
//   dma_out_arvalid   - input,  1
//   dma_out_arready   - output, 1
//   dma_out_rdata     - output, 32
//   dma_out_rresp     - output, 2
//   dma_out_rvalid    - output, 1
//   dma_out_rready    - input,  1
//   dma_out_rlast     - output, 1
// =========================================================================

module gelu_dma_top (
    input  logic        clk,
    input  logic        rst,
    input  logic        stream_enable,

    // AXI4-Lite — kernel pipeline_enable control
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

    // AXI4-MM write slave — DMA fills input buffer
    input  logic [31:0] dma_in_awaddr,
    input  logic [7:0]  dma_in_awlen,
    input  logic        dma_in_awvalid,
    output logic        dma_in_awready,
    input  logic [31:0] dma_in_wdata,
    input  logic [3:0]  dma_in_wstrb,
    input  logic        dma_in_wlast,
    input  logic        dma_in_wvalid,
    output logic        dma_in_wready,
    output logic [1:0]  dma_in_bresp,
    output logic        dma_in_bvalid,
    input  logic        dma_in_bready,

    // AXI4-MM read slave — DMA drains output buffer
    input  logic [31:0] dma_out_araddr,
    input  logic [7:0]  dma_out_arlen,
    input  logic        dma_out_arvalid,
    output logic        dma_out_arready,
    output logic [31:0] dma_out_rdata,
    output logic [1:0]  dma_out_rresp,
    output logic        dma_out_rvalid,
    input  logic        dma_out_rready,
    output logic        dma_out_rlast
);

    // Internal AXI-Stream: mm2s_buffer → gelu_top
    logic [31:0] axis_in_tdata;
    logic        axis_in_tvalid;
    logic        axis_in_tready;
    logic        axis_in_tlast;

    // Internal AXI-Stream: gelu_top → s2mm_buffer
    logic [31:0] axis_out_tdata;
    logic        axis_out_tvalid;
    logic        axis_out_tready;
    logic        axis_out_tlast;
    logic        axis_out_tuser;

    // ----------------------------------------------------------------
    // Input buffer: DMA write bursts → SRAM → stream to kernel
    // ----------------------------------------------------------------
    mm2s_buffer u_mm2s (
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
    // GELU kernel (existing, untouched)
    // ----------------------------------------------------------------
    gelu_top u_gelu (
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
    // Output buffer: stream from kernel → SRAM → DMA read bursts
    // ----------------------------------------------------------------
    s2mm_buffer u_s2mm (
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
