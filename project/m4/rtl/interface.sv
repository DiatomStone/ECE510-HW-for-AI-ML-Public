// =========================================================================
// Module:  gelu_axi_stream_interface
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Wide / parallel revision of gelu_axi_stream_interface.  Instead of a
//   single gelu_fp32 datapath processing one FP32 operand per AXI-Stream
//   beat, this version instantiates NUM_LANES (default 32) gelu_fp32
//   pipelines and packs NUM_LANES operands into every beat.  The AXI-Stream
//   data buses are widened to NUM_LANES*DATA_WIDTH bits:
//
//       lane i operand  =  s_axis_tdata[(i+1)*DATA_WIDTH-1 : i*DATA_WIDTH]
//       lane i result   =  m_axis_tdata[(i+1)*DATA_WIDTH-1 : i*DATA_WIDTH]
//
//   All NUM_LANES pipelines are fed by the SAME valid/ready handshake and
//   share identical latency, so they advance in perfect lockstep (SIMD
//   style).  This keeps the backpressure accounting and output FIFO scalar:
//   one beat in == NUM_LANES operands in, one beat out == NUM_LANES results
//   out.  Aggregate throughput is NUM_LANES results per cycle once full.
//
//   AXI-Lite slave (s_axil_*) exposes two registers:
//     0x00  [0]    pipeline_enable  - gates input acceptance; default 0 (off)
//     0x04  [31:0] num_lanes        - read-only; reports NUM_LANES (ID/CSR)
//
// Pipeline (per lane):
//   fp32_to_q16 (4) -> compute_core (4) -> q16_to_fp32 (4)
//   Total latency: PIPE_DEPTH = 12 clock cycles.
//
// Backpressure:
//   gelu_fp32 has no stall input.  s_axis_tready is deasserted when
//   (in_flight_count + fifo_count) >= FIFO_DEPTH so the output FIFO never
//   overflows.  FIFO_DEPTH must be >= PIPE_DEPTH.  Counters track BEATS,
//   each beat carrying NUM_LANES operands.
//
// Transaction Format:
//   Each input beat : NUM_LANES IEEE-754 FP32 operands packed lane-major.
//   Each output beat: NUM_LANES IEEE-754 FP32 GELU results packed lane-major.
//   TLAST and TUSER are per-beat sideband, delayed to match core latency.
//
// Ports (deltas from v1 in brackets):
//   clk             - input,  1                 : System clock
//   rst             - input,  1                 : Synchronous active-high reset
//   s_axil_*        - AXI4-Lite control slave   : (unchanged, +0x04 read reg)
//   s_axis_tdata    - input,  NUM_LANES*DW       : [WIDE] packed FP32 operands
//   s_axis_tvalid   - input,  1                 : Input stream data valid
//   s_axis_tready   - output, 1                 : Input stream ready (backpressure)
//   s_axis_tlast    - input,  1                 : Input stream end-of-packet marker
//   s_axis_tuser    - input,  USER_WIDTH         : Input stream sideband metadata
//   m_axis_tdata    - output, NUM_LANES*DW       : [WIDE] packed FP32 results
//   m_axis_tvalid   - output, 1                 : Output stream data valid
//   m_axis_tready   - input,  1                 : Output stream ready (backpressure)
//   m_axis_tlast    - output, 1                 : Output stream end-of-packet marker
//   m_axis_tuser    - output, USER_WIDTH         : Output stream sideband metadata
// =========================================================================

// Lane count: default 32 (x32). Override with -DGELU_NUM_LANES=8 (Icarus) or
// VERILOG_DEFINES (OpenLane) to build the x8 variant — one parameterized source.
`ifndef GELU_NUM_LANES
  `define GELU_NUM_LANES 32
`endif

module gelu_axi_stream_interface #(
    parameter int DATA_WIDTH = 32,   // per-lane operand width (FP32)
    parameter int NUM_LANES  = `GELU_NUM_LANES,   // parallel gelu_fp32 pipelines
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

    // --- AXI4-Stream Slave (packed FP32 input) -------------------------
    input  logic [NUM_LANES*DATA_WIDTH-1:0] s_axis_tdata,
    input  logic                            s_axis_tvalid,
    output logic                            s_axis_tready,
    input  logic                            s_axis_tlast,
    input  logic [USER_WIDTH-1:0]           s_axis_tuser,

    // --- AXI4-Stream Master (packed FP32 output) -----------------------
    output logic [NUM_LANES*DATA_WIDTH-1:0] m_axis_tdata,
    output logic                            m_axis_tvalid,
    input  logic                            m_axis_tready,
    output logic                            m_axis_tlast,
    output logic [USER_WIDTH-1:0]           m_axis_tuser
);

    // Aggregate (packed) bus width across all lanes.
    localparam int BUS_WIDTH = NUM_LANES * DATA_WIDTH;

    // Single counter width wide enough for fifo_count + in_flight_count.
    // Counters track beats, not individual operands.
    localparam int CNT_W    = $clog2(FIFO_DEPTH + PIPE_DEPTH + 1) + 1;
    localparam int PTR_W    = $clog2(FIFO_DEPTH);
    localparam int FIFO_CAP = FIFO_DEPTH;

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
    //   0x00 -> pipeline_enable, 0x04 -> NUM_LANES (read-only identity reg)
    //   Two-cycle handshake (AXI spec §A3.3.2).
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
                case (s_axil_araddr)
                    32'h00:  s_axil_rdata <= {31'b0, pipeline_enable};
                    32'h04:  s_axil_rdata <= 32'(NUM_LANES);
                    default: s_axil_rdata <= 32'b0;
                endcase
            end else if (s_axil_rvalid && s_axil_rready) begin
                s_axil_rvalid <= 1'b0;
            end
        end
    end

    // ----------------------------------------------------------------
    // Backpressure counters (in beats; one beat == NUM_LANES operands)
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
    // NUM_LANES parallel gelu_fp32 cores (SIMD lockstep)
    //   Every lane is driven by the same axis_in_fire, so all valid_out
    //   strobes are identical.  Lane 0's valid_out is the representative
    //   used for FIFO/counter bookkeeping.
    // ----------------------------------------------------------------
    logic [NUM_LANES-1:0]  core_valid_out;
    logic [BUS_WIDTH-1:0]  core_data_out;
    logic                  core_fire;        // one beat of results produced

    genvar gi;
    generate
        for (gi = 0; gi < NUM_LANES; gi++) begin : g_lane
            gelu_fp32 u_gelu_fp32 (
                .clk       (clk),
                .rst       (rst),
                .valid_in  (axis_in_fire),
                .data_in   (s_axis_tdata [gi*DATA_WIDTH +: DATA_WIDTH]),
                .valid_out (core_valid_out[gi]),
                .data_out  (core_data_out [gi*DATA_WIDTH +: DATA_WIDTH])
            );
        end
    endgenerate

    // All lanes share latency; lane 0 represents the beat-level valid.
    assign core_fire = core_valid_out[0];

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
    // Output FIFO (stores one wide BUS_WIDTH beat per slot)
    // ----------------------------------------------------------------
    logic [BUS_WIDTH-1:0]  fifo_data  [FIFO_DEPTH];
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
            if (core_fire) begin
                fifo_data[fifo_wr_ptr]  <= core_data_out;
                fifo_tlast[fifo_wr_ptr] <= meta_tlast_pipe[PIPE_DEPTH-1];
                fifo_tuser[fifo_wr_ptr] <= meta_tuser_pipe[PIPE_DEPTH-1];
                fifo_wr_ptr             <= fifo_wr_ptr + 1'b1;
            end

            if (axis_out_fire)
                fifo_rd_ptr <= fifo_rd_ptr + 1'b1;

            case ({core_fire, axis_out_fire})
                2'b10:   fifo_count <= fifo_count + 1'b1;
                2'b01:   fifo_count <= fifo_count - 1'b1;
                default: fifo_count <= fifo_count;
            endcase

            case ({axis_in_fire, core_fire})
                2'b10:   in_flight_count <= in_flight_count + 1'b1;
                2'b01:   in_flight_count <= in_flight_count - 1'b1;
                default: in_flight_count <= in_flight_count;
            endcase
        end
    end

endmodule
