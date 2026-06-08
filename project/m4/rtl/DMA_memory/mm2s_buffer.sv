// =========================================================================
// Module:  mm2s_buffer
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Macro-free input DMA buffer for the (parameterized) kernel. Accepts AXI4-MM
//   write bursts from the DMA engine and streams stored beats out to the kernel
//   over a DATA_W = NUM_LANES*32-wide AXI4-Stream (NUM_LANES FP32 per beat).
//
//   Storage is an inferred register-array FIFO — pure standard cells, no SRAM
//   macro, no blackbox, no OpenLane MACROS config. It is sized SHALLOW (DEPTH
//   beats) rather than deep: a streaming feed-through kernel only needs enough
//   elastic buffering to cover DMA burst jitter and the 12-cycle pipeline
//   latency, not deep on-chip residency.
//
//   Trading depth for width keeps the flop count flat: the original 32-bit ×
//   1024-deep buffer was 32 Kbit; DATA_W=1024 × DEPTH=32 is also 32 Kbit, but
//   delivers a full 1024-bit beat every cycle.
//
//   Because the FIFO read is combinational (first-word fall-through, zero read
//   latency), the prefetch FIFO + credit logic and the separate length FIFO
//   used by the SRAM version are unnecessary: per-beat TLAST is stored next to
//   the data and pops out directly. AXI4-Stream framing = AXI4-MM WLAST.
//
//   addr is FIFO-ordered (awaddr is ignored, as in the v1 buffer). Partial
//   write strobes are not supported — the DMA is expected to write whole
//   DATA_W beats (wstrb all-ones); wstrb is accepted but not byte-masked.
//
// Ports:
//   clk            - input,  1        : System clock
//   rst            - input,  1        : Synchronous active-high reset
//   s_axi_awaddr   - input,  32       : Write address (ignored; FIFO-ordered)
//   s_axi_awlen    - input,  8        : Burst length minus 1 (AXI4)
//   s_axi_awvalid  - input,  1        : Write address valid
//   s_axi_awready  - output, 1        : Write address ready
//   s_axi_wdata    - input,  DATA_W   : Write data (one packed beat)
//   s_axi_wstrb    - input,  DATA_W/8 : Byte strobes (accepted, assumed all-1s)
//   s_axi_wlast    - input,  1        : Last beat of write burst -> TLAST
//   s_axi_wvalid   - input,  1        : Write data valid
//   s_axi_wready   - output, 1        : Write data ready (deasserts when full)
//   s_axi_bresp    - output, 2        : Write response (00 = OKAY)
//   s_axi_bvalid   - output, 1        : Write response valid
//   s_axi_bready   - input,  1        : Write response ready
//   m_axis_tdata   - output, DATA_W   : Stream data to kernel (packed beat)
//   m_axis_tvalid  - output, 1        : Stream valid (FIFO non-empty & enabled)
//   m_axis_tready  - input,  1        : Stream ready (backpressure from kernel)
//   m_axis_tlast   - output, 1        : Stream end-of-packet (stored WLAST)
//   stream_enable  - input,  1        : Gate output streaming
// =========================================================================

module mm2s_buffer #(
    parameter int DATA_W = 1024,                 // packed beat width (32 FP32 lanes)
    parameter int DEPTH  = 32                    // FIFO depth in beats
)(
    input  logic                clk,
    input  logic                rst,

    // AXI4-MM write slave (DMA -> buffer)
    input  logic [31:0]         s_axi_awaddr,
    input  logic [7:0]          s_axi_awlen,
    input  logic                s_axi_awvalid,
    output logic                s_axi_awready,
    input  logic [DATA_W-1:0]   s_axi_wdata,
    input  logic [DATA_W/8-1:0] s_axi_wstrb,
    input  logic                s_axi_wlast,
    input  logic                s_axi_wvalid,
    output logic                s_axi_wready,
    output logic [1:0]          s_axi_bresp,
    output logic                s_axi_bvalid,
    input  logic                s_axi_bready,

    // AXI4-Stream master (buffer -> kernel)
    output logic [DATA_W-1:0]   m_axis_tdata,
    output logic                m_axis_tvalid,
    input  logic                m_axis_tready,
    output logic                m_axis_tlast,

    // Control
    input  logic                stream_enable
);

    localparam int PTR_W = (DEPTH > 1) ? $clog2(DEPTH) : 1;
    localparam int CNT_W = $clog2(DEPTH + 1);

    // ----------------------------------------------------------------
    // Inferred register-array FIFO: stores {tlast, data} per beat.
    // Combinational (first-word fall-through) read — zero read latency.
    // ----------------------------------------------------------------
    logic [DATA_W-1:0] fifo_data [DEPTH];
    logic              fifo_last [DEPTH];
    logic [PTR_W-1:0]  wr_ptr, rd_ptr;
    logic [CNT_W-1:0]  fifo_count;

    wire fifo_full  = (fifo_count == CNT_W'(DEPTH));
    wire fifo_empty = (fifo_count == '0);

    wire wr_fire = s_axi_wvalid && s_axi_wready;
    wire rd_fire = m_axis_tvalid && m_axis_tready;

    // ----------------------------------------------------------------
    // AXI4-MM write state machine (AW -> data burst -> B response)
    // ----------------------------------------------------------------
    typedef enum logic [1:0] { IDLE, BURST, RESP } aw_state_t;
    aw_state_t  aw_state;
    logic [7:0] beats_left;

    assign s_axi_awready = (aw_state == IDLE);
    assign s_axi_wready  = (aw_state == BURST) && !fifo_full;
    assign s_axi_bresp   = 2'b00;

    wire aw_fire = s_axi_awvalid && s_axi_awready;

    always_ff @(posedge clk) begin
        if (rst) begin
            aw_state     <= IDLE;
            beats_left   <= '0;
            s_axi_bvalid <= 1'b0;
        end else begin
            case (aw_state)
                IDLE: begin
                    if (aw_fire) begin
                        beats_left <= s_axi_awlen;
                        aw_state   <= BURST;
                    end
                end
                BURST: begin
                    if (wr_fire) begin
                        if (s_axi_wlast || beats_left == '0) begin
                            aw_state     <= RESP;
                            s_axi_bvalid <= 1'b1;
                        end else begin
                            beats_left <= beats_left - 1'b1;
                        end
                    end
                end
                RESP: begin
                    if (s_axi_bvalid && s_axi_bready) begin
                        s_axi_bvalid <= 1'b0;
                        aw_state     <= IDLE;
                    end
                end
                default: aw_state <= IDLE;
            endcase
        end
    end

    // ----------------------------------------------------------------
    // FIFO write / read / occupancy
    // ----------------------------------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            wr_ptr     <= '0;
            rd_ptr     <= '0;
            fifo_count <= '0;
        end else begin
            if (wr_fire) begin
                fifo_data[wr_ptr] <= s_axi_wdata;
                fifo_last[wr_ptr] <= s_axi_wlast;
                wr_ptr <= (wr_ptr == PTR_W'(DEPTH-1)) ? '0 : wr_ptr + 1'b1;
            end
            if (rd_fire)
                rd_ptr <= (rd_ptr == PTR_W'(DEPTH-1)) ? '0 : rd_ptr + 1'b1;

            case ({wr_fire, rd_fire})
                2'b10:   fifo_count <= fifo_count + 1'b1;
                2'b01:   fifo_count <= fifo_count - 1'b1;
                default: fifo_count <= fifo_count;
            endcase
        end
    end

    // ----------------------------------------------------------------
    // AXI-Stream master outputs (first-word fall-through)
    // ----------------------------------------------------------------
    assign m_axis_tvalid = stream_enable && !fifo_empty;
    assign m_axis_tdata  = fifo_data[rd_ptr];
    assign m_axis_tlast  = fifo_last[rd_ptr];

endmodule
