// =========================================================================
// Module:  s2mm_buffer
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Wide, macro-free output DMA buffer for the 32-lane kernel. Accepts
//   DATA_W-wide AXI4-Stream results from the kernel (default 1024 bits = 32
//   FP32 lanes) and makes them available for the DMA engine to read back over
//   a DATA_W-wide AXI4-MM read channel.
//
//   Like mm2s_buffer, storage is an inferred register-array FIFO — pure
//   standard cells, no SRAM macro / blackbox / OpenLane MACROS config. Sized
//   SHALLOW (DEPTH beats); trading depth for width keeps the flop count flat
//   versus the original 32-bit × 1024-deep SRAM buffer while delivering a full
//   1024-bit beat per cycle.
//
//   The FIFO read is combinational (first-word fall-through), so the 1-cycle
//   SRAM read-latency tracking (rd_inflight) of the v1 buffer is gone: RDATA is
//   driven straight from the FIFO head and RVALID is just (in-burst & !empty).
//
//   RLAST is framed from ARLEN (AXI4: beats = ARLEN + 1), as in v1. araddr is
//   ignored (FIFO-ordered). Read response is always OKAY.
//
// Ports:
//   clk            - input,  1        : System clock
//   rst            - input,  1        : Synchronous active-high reset
//   s_axis_tdata   - input,  DATA_W   : Stream data from kernel (packed beat)
//   s_axis_tvalid  - input,  1        : Stream valid
//   s_axis_tready  - output, 1        : Stream ready (backpressure; deasserts full)
//   s_axis_tlast   - input,  1        : Last beat of kernel packet (unused; ARLEN frames)
//   m_axi_araddr   - input,  32       : Read address (ignored; FIFO-ordered)
//   m_axi_arlen    - input,  8        : Burst length minus 1 (AXI4)
//   m_axi_arvalid  - input,  1        : Read address valid
//   m_axi_arready  - output, 1        : Read address ready
//   m_axi_rdata    - output, DATA_W   : Read data (packed beat)
//   m_axi_rresp    - output, 2        : Read response (00 = OKAY)
//   m_axi_rvalid   - output, 1        : Read data valid
//   m_axi_rready   - input,  1        : Read data ready
//   m_axi_rlast    - output, 1        : Last beat of read burst
// =========================================================================

module s2mm_buffer #(
    parameter int DATA_W = 1024,                 // packed beat width (32 FP32 lanes)
    parameter int DEPTH  = 32                    // FIFO depth in beats
)(
    input  logic                clk,
    input  logic                rst,

    // AXI4-Stream slave (kernel -> buffer)
    input  logic [DATA_W-1:0]   s_axis_tdata,
    input  logic                s_axis_tvalid,
    output logic                s_axis_tready,
    input  logic                s_axis_tlast,

    // AXI4-MM read slave (buffer -> DMA)
    input  logic [31:0]         m_axi_araddr,
    input  logic [7:0]          m_axi_arlen,
    input  logic                m_axi_arvalid,
    output logic                m_axi_arready,
    output logic [DATA_W-1:0]   m_axi_rdata,
    output logic [1:0]          m_axi_rresp,
    output logic                m_axi_rvalid,
    input  logic                m_axi_rready,
    output logic                m_axi_rlast
);

    localparam int PTR_W = (DEPTH > 1) ? $clog2(DEPTH) : 1;
    localparam int CNT_W = $clog2(DEPTH + 1);

    // ----------------------------------------------------------------
    // Inferred register-array FIFO (combinational read)
    // ----------------------------------------------------------------
    logic [DATA_W-1:0] fifo_data [DEPTH];
    logic [PTR_W-1:0]  wr_ptr, rd_ptr;
    logic [CNT_W-1:0]  fifo_count;

    wire fifo_full  = (fifo_count == CNT_W'(DEPTH));
    wire fifo_empty = (fifo_count == '0);

    wire wr_fire = s_axis_tvalid && s_axis_tready;
    wire rd_fire = m_axi_rvalid && m_axi_rready;

    assign s_axis_tready = !fifo_full;

    // ----------------------------------------------------------------
    // AXI4-MM read state machine
    //   AR_IDLE  : waiting for ARVALID
    //   AR_BURST : presenting RDATA beats until ARLEN exhausted
    // ----------------------------------------------------------------
    typedef enum logic { AR_IDLE, AR_BURST } ar_state_t;
    ar_state_t  ar_state;
    logic [7:0] ar_beats_left;

    assign m_axi_arready = (ar_state == AR_IDLE);
    assign m_axi_rresp   = 2'b00;

    // First-word fall-through read: present FIFO head while in burst.
    assign m_axi_rvalid = (ar_state == AR_BURST) && !fifo_empty;
    assign m_axi_rdata  = fifo_data[rd_ptr];
    assign m_axi_rlast  = (ar_state == AR_BURST) && (ar_beats_left == '0) && !fifo_empty;

    always_ff @(posedge clk) begin
        if (rst) begin
            ar_state      <= AR_IDLE;
            ar_beats_left <= '0;
        end else begin
            case (ar_state)
                AR_IDLE: begin
                    if (m_axi_arvalid) begin
                        ar_beats_left <= m_axi_arlen;
                        ar_state      <= AR_BURST;
                    end
                end
                AR_BURST: begin
                    if (rd_fire) begin
                        if (ar_beats_left == '0)
                            ar_state <= AR_IDLE;     // RLAST beat consumed
                        else
                            ar_beats_left <= ar_beats_left - 1'b1;
                    end
                end
                default: ar_state <= AR_IDLE;
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
                fifo_data[wr_ptr] <= s_axis_tdata;
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

endmodule
