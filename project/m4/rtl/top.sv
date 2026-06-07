// =========================================================================
// Module:  gelu_top
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Top-level integration module. Instantiates gelu_axi_stream_interface,
//   which wraps gelu_fp32 (fp32_to_q16 -> compute_core -> q16_to_fp32).
//   All host communication flows through the AXI4-Stream data ports and
//   the AXI4-Lite control port. No direct access to internal sub-modules.
//
//   Hierarchy:
//     gelu_top
//       └── gelu_axi_stream_interface   (AXI protocol + FIFO + backpressure)
//             └── gelu_fp32             (FP32 end-to-end datapath, 12 cycles)
//                   ├── fp32_to_q16     (IEEE-754 -> Q16.16, 4 stages)
//                   ├── compute_core    (GELU PWL approximation, 4 stages)
//                   └── q16_to_fp32    (Q16.16 -> IEEE-754, 4 stages)
//
//   Glue logic: none. The interface module absorbs all handshake adaptation,
//   backpressure buffering, and metadata delay internally. The top level is
//   a direct port-to-port connection with no additional logic.
//
// Clock Domain:
//   Single clock domain (clk). All sequential logic on posedge clk.
//
// Reset:
//   Synchronous, active-high (rst).
//
// Ports:
//   clk             - input,  1                : System clock
//   rst             - input,  1                : Synchronous active-high reset
//   s_axil_awaddr   - input,  32               : AXI-Lite write address
//   s_axil_awvalid  - input,  1                : AXI-Lite write address valid
//   s_axil_awready  - output, 1                : AXI-Lite write address ready
//   s_axil_wdata    - input,  32               : AXI-Lite write data
//   s_axil_wstrb    - input,  4                : AXI-Lite write byte strobes
//   s_axil_wvalid   - input,  1                : AXI-Lite write data valid
//   s_axil_wready   - output, 1                : AXI-Lite write data ready
//   s_axil_bresp    - output, 2                : AXI-Lite write response
//   s_axil_bvalid   - output, 1                : AXI-Lite write response valid
//   s_axil_bready   - input,  1                : AXI-Lite write response ready
//   s_axil_araddr   - input,  32               : AXI-Lite read address
//   s_axil_arvalid  - input,  1                : AXI-Lite read address valid
//   s_axil_arready  - output, 1                : AXI-Lite read address ready
//   s_axil_rdata    - output, 32               : AXI-Lite read data
//   s_axil_rresp    - output, 2                : AXI-Lite read response
//   s_axil_rvalid   - output, 1                : AXI-Lite read data valid
//   s_axil_rready   - input,  1                : AXI-Lite read data ready
//   s_axis_tdata    - input,  32               : Input stream FP32 operand
//   s_axis_tvalid   - input,  1                : Input stream data valid
//   s_axis_tready   - output, 1                : Input stream ready (backpressure)
//   s_axis_tlast    - input,  1                : Input stream end-of-packet marker
//   s_axis_tuser    - input,  1                : Input stream sideband metadata
//   m_axis_tdata    - output, 32               : Output stream FP32 GELU result
//   m_axis_tvalid   - output, 1                : Output stream data valid
//   m_axis_tready   - input,  1                : Output stream ready (backpressure)
//   m_axis_tlast    - output, 1                : Output stream end-of-packet marker
//   m_axis_tuser    - output, 1                : Output stream sideband metadata
// =========================================================================

module gelu_top (
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

    // AXI4-Stream Slave (FP32 input)
    input  logic [31:0] s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,
    input  logic        s_axis_tuser,

    // AXI4-Stream Master (FP32 output)
    output logic [31:0] m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,
    output logic        m_axis_tuser
);

    gelu_axi_stream_interface #(
        .DATA_WIDTH (32),
        .USER_WIDTH (1),
        .PIPE_DEPTH (12),
        .FIFO_DEPTH (16)
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
