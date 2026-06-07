// =========================================================================
// Module:  s2mm_buffer
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Output DMA buffer. Accepts AXI4-Stream results from the kernel and
//   makes them available for the DMA engine to read back over AXI4-MM.
//
//   Internally backed by openram_1k_wrap (1024 x 32-bit).
//     Port 0 (RW) : kernel write path  — advances wr_ptr each accepted beat
//     Port 1 (R)  : DMA read path      — advances rd_ptr each completed read
//
//   AXI4-MM read channel only (no AW/W). ARLEN encodes burst length
//   (AXI4 convention: beats = ARLEN + 1). ARSIZE assumed 4 bytes (32-bit).
//
//   Backpressure:
//     - s_axis_tready deasserted when FIFO full
//     - RVALID deasserted when FIFO empty
//
// Ports:
//   clk            - input,  1   : System clock
//   rst            - input,  1   : Synchronous active-high reset
//   s_axis_tdata   - input,  32  : Stream input data (from kernel)
//   s_axis_tvalid  - input,  1   : Stream input valid
//   s_axis_tready  - output, 1   : Stream input ready (backpressure to kernel)
//   s_axis_tlast   - input,  1   : Last beat of kernel packet
//   m_axi_araddr   - input,  32  : Read base address (word-aligned; [1:0] ignored)
//   m_axi_arlen    - input,  8   : Burst length minus 1 (AXI4)
//   m_axi_arvalid  - input,  1   : Read address valid
//   m_axi_arready  - output, 1   : Read address ready
//   m_axi_rdata    - output, 32  : Read data
//   m_axi_rresp    - output, 2   : Read response (00 = OKAY)
//   m_axi_rvalid   - output, 1   : Read data valid
//   m_axi_rready   - input,  1   : Read data ready
//   m_axi_rlast    - output, 1   : Last beat of read burst
// =========================================================================

module s2mm_buffer (
    input  logic        clk,
    input  logic        rst,

    // AXI4-Stream slave (kernel → buffer)
    input  logic [31:0] s_axis_tdata,
    input  logic        s_axis_tvalid,
    output logic        s_axis_tready,
    input  logic        s_axis_tlast,

    // AXI4-MM read slave (buffer → DMA)
    input  logic [31:0] m_axi_araddr,
    input  logic [7:0]  m_axi_arlen,
    input  logic        m_axi_arvalid,
    output logic        m_axi_arready,
    output logic [31:0] m_axi_rdata,
    output logic [1:0]  m_axi_rresp,
    output logic        m_axi_rvalid,
    input  logic        m_axi_rready,
    output logic        m_axi_rlast
);

    localparam int DEPTH = 256;   // inferred RAM depth (was 1024; shrunk so
    localparam int PTR_W = 8;      // gelu_dma_top routes — DMA bursts are <=256)
    localparam int CNT_W = 9;

    // ----------------------------------------------------------------
    // FIFO pointers and count
    // ----------------------------------------------------------------
    logic [PTR_W-1:0] wr_ptr, rd_ptr;
    logic [CNT_W-1:0] fifo_count;

    wire fifo_full  = (fifo_count == CNT_W'(DEPTH));
    wire fifo_empty = (fifo_count == '0);

    // ----------------------------------------------------------------
    // AXI4-Stream write path (kernel → SRAM port 0)
    // ----------------------------------------------------------------
    wire wr_fire = s_axis_tvalid && s_axis_tready;

    assign s_axis_tready = !fifo_full;

    // ----------------------------------------------------------------
    // AXI4-MM read state machine
    //   IDLE   : waiting for ARVALID
    //   BURST  : issuing RDATA beats
    // ----------------------------------------------------------------
    typedef enum logic { AR_IDLE, AR_BURST } ar_state_t;
    ar_state_t ar_state;

    logic [7:0] ar_beats_left;
    logic       rd_issue;       // pulse: issue read to SRAM port 1
    logic       rd_inflight;    // SRAM read issued, result arrives next cycle

    assign m_axi_arready = (ar_state == AR_IDLE);
    assign m_axi_rresp   = 2'b00;

    // Issue a read when in burst, FIFO has data, no beat in flight,
    // and downstream will accept (or no pending valid beat).
    assign rd_issue = (ar_state == AR_BURST) && !fifo_empty && !rd_inflight &&
                      (!m_axi_rvalid || m_axi_rready);

    always_ff @(posedge clk) begin
        if (rst) begin
            ar_state      <= AR_IDLE;
            ar_beats_left <= '0;
            rd_inflight   <= 1'b0;
            m_axi_rvalid  <= 1'b0;
            m_axi_rlast   <= 1'b0;
        end else begin
            // 1-cycle SRAM latency tracking
            rd_inflight <= rd_issue;

            // rvalid: set one cycle after rd_issue (data arrives from SRAM)
            if (rd_issue)
                m_axi_rvalid <= 1'b1;
            else if (m_axi_rvalid && m_axi_rready)
                m_axi_rvalid <= 1'b0;

            case (ar_state)
                AR_IDLE: begin
                    if (m_axi_arvalid) begin
                        ar_beats_left <= m_axi_arlen;
                        ar_state      <= AR_BURST;
                    end
                end

                AR_BURST: begin
                    if (rd_issue) begin
                        if (ar_beats_left == '0) begin
                            m_axi_rlast <= 1'b1;
                            ar_state    <= AR_IDLE;
                        end else begin
                            m_axi_rlast   <= 1'b0;
                            ar_beats_left <= ar_beats_left - 1'b1;
                        end
                    end else if (m_axi_rvalid && m_axi_rready) begin
                        m_axi_rlast <= 1'b0;
                    end
                end

                default: ar_state <= AR_IDLE;
            endcase
        end
    end

    // ----------------------------------------------------------------
    // FIFO pointer and count update
    // ----------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            wr_ptr     <= '0;
            rd_ptr     <= '0;
            fifo_count <= '0;
        end else begin
            if (wr_fire)
                wr_ptr <= wr_ptr + 1'b1;

            if (rd_issue)
                rd_ptr <= rd_ptr + 1'b1;

            case ({wr_fire, rd_issue})
                2'b10:   fifo_count <= fifo_count + 1'b1;
                2'b01:   fifo_count <= fifo_count - 1'b1;
                default: fifo_count <= fifo_count;
            endcase
        end
    end

    // ----------------------------------------------------------------
    // SRAM instance
    // ----------------------------------------------------------------
    openram_1k_wrap #(.DEPTH(DEPTH)) u_ram (
        .clk      (clk),
        // Port 0: kernel writes
        .p0_en    (wr_fire),
        .p0_we    (1'b1),
        .p0_wmask (4'hF),
        .p0_addr  (wr_ptr),
        .p0_din   (s_axis_tdata),
        .p0_dout  (),
        // Port 1: DMA reads
        .p1_en    (rd_issue),
        .p1_addr  (rd_ptr),
        .p1_dout  (m_axi_rdata)
    );

endmodule
