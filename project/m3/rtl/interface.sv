// =========================================================================
// Module:  gelu_axi_stream_interface
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   AXI4-Stream + AXI4-Lite interface wrapper for the gelu_fp32 pipeline.
//   Accepts IEEE-754 FP32 operands over an AXI-Stream slave port, applies
//   GELU via the gelu_fp32 chain (fp32_to_q16 -> compute_core -> q16_to_fp32),
//   and returns FP32 results over an AXI-Stream master port.
//
//   AXI-Lite slave (s_axil_*) exposes one control register:
//     0x00  [0] pipeline_enable  -  gates input acceptance; default 0 (off)
//
// Pipeline:
//   fp32_to_q16 (4 stages) -> compute_core (4 stages) -> q16_to_fp32 (4 stages)
//   Total latency: PIPE_DEPTH = 12 clock cycles.
//   Full throughput: one result per cycle once the pipeline is full.
//
// Backpressure:
//   gelu_fp32 has no stall input.  s_axis_tready is deasserted when
//   (in_flight_count + fifo_count) >= FIFO_DEPTH, guaranteeing the output
//   FIFO never overflows.  FIFO_DEPTH must be >= PIPE_DEPTH.
//
// Transaction Format:
//   Each input beat: one IEEE-754 FP32 operand in s_axis_tdata[31:0].
//   Each output beat: one IEEE-754 FP32 GELU result in m_axis_tdata[31:0].
//   TLAST and TUSER are propagated through the pipeline with matching delay.
//
// Ports:
//   clk             - input,  1   : System clock
//   rst             - input,  1   : Synchronous active-high reset
//   s_axil_awaddr   - input,  32  : AXI-Lite write address (register offset)
//   s_axil_awvalid  - input,  1   : AXI-Lite write address valid
//   s_axil_awready  - output, 1   : AXI-Lite write address ready
//   s_axil_wdata    - input,  32  : AXI-Lite write data
//   s_axil_wstrb    - input,  4   : AXI-Lite write byte strobes
//   s_axil_wvalid   - input,  1   : AXI-Lite write data valid
//   s_axil_wready   - output, 1   : AXI-Lite write data ready
//   s_axil_bresp    - output, 2   : AXI-Lite write response (00 = OKAY)
//   s_axil_bvalid   - output, 1   : AXI-Lite write response valid
//   s_axil_bready   - input,  1   : AXI-Lite write response ready
//   s_axil_araddr   - input,  32  : AXI-Lite read address (register offset)
//   s_axil_arvalid  - input,  1   : AXI-Lite read address valid
//   s_axil_arready  - output, 1   : AXI-Lite read address ready
//   s_axil_rdata    - output, 32  : AXI-Lite read data
//   s_axil_rresp    - output, 2   : AXI-Lite read response (00 = OKAY)
//   s_axil_rvalid   - output, 1   : AXI-Lite read data valid
//   s_axil_rready   - input,  1   : AXI-Lite read data ready
//   s_axis_tdata    - input,  32  : Input stream IEEE-754 FP32 operand
//   s_axis_tvalid   - input,  1   : Input stream data valid
//   s_axis_tready   - output, 1   : Input stream ready (deasserted under backpressure)
//   s_axis_tlast    - input,  1   : Input stream end-of-packet marker
//   s_axis_tuser    - input,  1   : Input stream sideband metadata
//   m_axis_tdata    - output, 32  : Output stream IEEE-754 FP32 GELU result
//   m_axis_tvalid   - output, 1   : Output stream data valid
//   m_axis_tready   - input,  1   : Output stream ready (backpressure from downstream)
//   m_axis_tlast    - output, 1   : Output stream end-of-packet marker (pipeline-delayed)
//   m_axis_tuser    - output, 1   : Output stream sideband metadata (pipeline-delayed)
// =========================================================================

module gelu_axi_stream_interface #(
    parameter int DATA_WIDTH = 32,
    parameter int USER_WIDTH = 1,
    parameter int PIPE_DEPTH = 12,
    parameter int FIFO_DEPTH = 16
)(
    input  logic clk,
    input  logic rst,

    // --- AXI4-Lite Slave (control) ------------------------------------
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

    // --- AXI4-Stream Slave (FP32 input) --------------------------------
    input  logic [DATA_WIDTH-1:0] s_axis_tdata,
    input  logic                  s_axis_tvalid,
    output logic                  s_axis_tready,
    input  logic                  s_axis_tlast,
    input  logic [USER_WIDTH-1:0] s_axis_tuser,

    // --- AXI4-Stream Master (FP32 output) ------------------------------
    output logic [DATA_WIDTH-1:0] m_axis_tdata,
    output logic                  m_axis_tvalid,
    input  logic                  m_axis_tready,
    output logic                  m_axis_tlast,
    output logic [USER_WIDTH-1:0] m_axis_tuser
);

    // Use a single counter width wide enough for fifo_count + in_flight_count.
    localparam int CNT_W      = $clog2(FIFO_DEPTH + PIPE_DEPTH + 1) + 1;
    localparam int PTR_W      = $clog2(FIFO_DEPTH);
    localparam int FIFO_CAP   = FIFO_DEPTH;

    // ----------------------------------------------------------------
    // AXI4-Lite: write channel
    //   Register map:  0x00[0] = pipeline_enable
    //
    //   Two-cycle handshake (AXI spec §A3.3.1):
    //     Cycle 1 – slave asserts awready/wready after seeing awvalid+wvalid
    //     Cycle 2 – slave asserts bvalid and writes register after the
    //               combined AW+W handshake completes; awready/wready deasserted
    // ----------------------------------------------------------------
    logic pipeline_enable;

    always_ff @(posedge clk) begin
        if (rst) begin
            s_axil_awready  <= 1'b0;
            s_axil_wready   <= 1'b0;
            s_axil_bvalid   <= 1'b0;
            s_axil_bresp    <= 2'b00;
            pipeline_enable <= 1'b0;
        end else begin
            // Cycle 1: assert READY once both address and data are valid
            if (s_axil_awvalid && s_axil_wvalid && !s_axil_awready && !s_axil_bvalid) begin
                s_axil_awready <= 1'b1;
                s_axil_wready  <= 1'b1;
            end else begin
                s_axil_awready <= 1'b0;
                s_axil_wready  <= 1'b0;
            end

            // Cycle 2: handshake complete — write register and assert BVALID
            if (s_axil_awready && s_axil_wready && s_axil_awvalid && s_axil_wvalid) begin
                s_axil_bvalid <= 1'b1;
                s_axil_bresp  <= 2'b00;
                if (s_axil_awaddr == 32'h00 && s_axil_wstrb[0])
                    pipeline_enable <= s_axil_wdata[0];
            end else if (s_axil_bvalid && s_axil_bready) begin
                s_axil_bvalid <= 1'b0;
            end
        end
    end

    // AXI4-Lite: read channel
    //   Two-cycle handshake (AXI spec §A3.3.2):
    //     Cycle 1 – slave asserts arready after seeing arvalid
    //     Cycle 2 – slave asserts rvalid+rdata after the AR handshake completes
    always_ff @(posedge clk) begin
        if (rst) begin
            s_axil_arready <= 1'b0;
            s_axil_rvalid  <= 1'b0;
            s_axil_rdata   <= 32'b0;
            s_axil_rresp   <= 2'b00;
        end else begin
            // Cycle 1: assert ARREADY
            if (s_axil_arvalid && !s_axil_arready && !s_axil_rvalid) begin
                s_axil_arready <= 1'b1;
            end else begin
                s_axil_arready <= 1'b0;
            end

            // Cycle 2: handshake complete — return read data
            if (s_axil_arready && s_axil_arvalid) begin
                s_axil_rvalid <= 1'b1;
                s_axil_rresp  <= 2'b00;
                s_axil_rdata  <= (s_axil_araddr == 32'h00)
                                 ? {31'b0, pipeline_enable}
                                 : 32'b0;
            end else if (s_axil_rvalid && s_axil_rready) begin
                s_axil_rvalid <= 1'b0;
            end
        end
    end

    // ----------------------------------------------------------------
    // Backpressure counters
    // ----------------------------------------------------------------
    logic [CNT_W-1:0] fifo_count;
    logic [CNT_W-1:0] in_flight_count;
    logic [CNT_W-1:0] pending_count;

    assign pending_count = fifo_count + in_flight_count;
    assign s_axis_tready = pipeline_enable && (pending_count < CNT_W'(FIFO_CAP));

    logic axis_in_fire;
    logic axis_out_fire;
    assign axis_in_fire  = s_axis_tvalid && s_axis_tready;
    assign axis_out_fire = m_axis_tvalid && m_axis_tready;

    // ----------------------------------------------------------------
    // gelu_fp32 core
    // ----------------------------------------------------------------
    logic        core_valid_out;
    logic [31:0] core_data_out;

    gelu_fp32 u_gelu_fp32 (
        .clk       (clk),
        .rst       (rst),
        .valid_in  (axis_in_fire),
        .data_in   (s_axis_tdata),
        .valid_out (core_valid_out),
        .data_out  (core_data_out)
    );

    // ----------------------------------------------------------------
    // Metadata pipeline: delay TLAST/TUSER to match core latency
    // ----------------------------------------------------------------
    logic [PIPE_DEPTH-1:0] meta_tlast_pipe;
    logic [USER_WIDTH-1:0] meta_tuser_pipe [PIPE_DEPTH];

    always_ff @(posedge clk) begin
        if (rst) begin
            meta_tlast_pipe <= '0;
            for (int i = 0; i < PIPE_DEPTH; i++)
                meta_tuser_pipe[i] <= '0;
        end else begin
            meta_tlast_pipe    <= {meta_tlast_pipe[PIPE_DEPTH-2:0],
                                   axis_in_fire ? s_axis_tlast : 1'b0};
            meta_tuser_pipe[0] <= axis_in_fire ? s_axis_tuser : '0;
            for (int i = 1; i < PIPE_DEPTH; i++)
                meta_tuser_pipe[i] <= meta_tuser_pipe[i-1];
        end
    end

    // ----------------------------------------------------------------
    // Output FIFO
    // ----------------------------------------------------------------
    logic [DATA_WIDTH-1:0] fifo_data  [FIFO_DEPTH];
    logic                  fifo_tlast [FIFO_DEPTH];
    logic [USER_WIDTH-1:0] fifo_tuser [FIFO_DEPTH];
    logic [PTR_W-1:0]      fifo_wr_ptr;
    logic [PTR_W-1:0]      fifo_rd_ptr;

    assign m_axis_tvalid = (fifo_count != '0);
    assign m_axis_tdata  = fifo_data[fifo_rd_ptr];
    assign m_axis_tlast  = fifo_tlast[fifo_rd_ptr];
    assign m_axis_tuser  = fifo_tuser[fifo_rd_ptr];

    always_ff @(posedge clk) begin
        if (rst) begin
            fifo_wr_ptr     <= '0;
            fifo_rd_ptr     <= '0;
            fifo_count      <= '0;
            in_flight_count <= '0;
        end else begin
            if (core_valid_out) begin
                fifo_data[fifo_wr_ptr]  <= core_data_out;
                fifo_tlast[fifo_wr_ptr] <= meta_tlast_pipe[PIPE_DEPTH-1];
                fifo_tuser[fifo_wr_ptr] <= meta_tuser_pipe[PIPE_DEPTH-1];
                fifo_wr_ptr             <= fifo_wr_ptr + 1'b1;
            end

            if (axis_out_fire)
                fifo_rd_ptr <= fifo_rd_ptr + 1'b1;

            case ({core_valid_out, axis_out_fire})
                2'b10:   fifo_count <= fifo_count + 1'b1;
                2'b01:   fifo_count <= fifo_count - 1'b1;
                default: fifo_count <= fifo_count;
            endcase

            case ({axis_in_fire, core_valid_out})
                2'b10:   in_flight_count <= in_flight_count + 1'b1;
                2'b01:   in_flight_count <= in_flight_count - 1'b1;
                default: in_flight_count <= in_flight_count;
            endcase
        end
    end

endmodule
