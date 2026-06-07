// =========================================================================
// Module:  mm2s_buffer
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Input DMA buffer. Accepts AXI4-MM write bursts from the DMA engine and
//   streams stored data out to the kernel over AXI4-Stream.
//
//   Backed by openram_1k_wrap (1024 x 32-bit): port 0 = DMA write,
//   port 1 = stream read (1-cycle registered read latency).
//
//   Read path: a per-burst length FIFO frames TLAST independently of the
//   write side, and a credit-gated prefetch FIFO absorbs the 1-cycle SRAM
//   read latency to sustain 1 word/cycle without dead cycles.
// =========================================================================

module mm2s_buffer (
    input  logic        clk,
    input  logic        rst,

    // AXI4-MM write slave (DMA -> buffer)
    input  logic [31:0] s_axi_awaddr,
    input  logic [7:0]  s_axi_awlen,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,
    input  logic [31:0] s_axi_wdata,
    input  logic [3:0]  s_axi_wstrb,
    input  logic        s_axi_wlast,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,
    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,

    // AXI4-Stream master (buffer -> kernel)
    output logic [31:0] m_axis_tdata,
    output logic        m_axis_tvalid,
    input  logic        m_axis_tready,
    output logic        m_axis_tlast,

    // Control
    input  logic        stream_enable
);

    localparam int DEPTH    = 256;   // inferred RAM depth (was 1024; shrunk so
    localparam int PTR_W    = 8;      // gelu_dma_top routes — DMA bursts are <=256)
    localparam int CNT_W    = 9;
    localparam int LF_DEPTH = 16;
    localparam int LF_PTR_W = 4;
    localparam int LF_CNT_W = 5;
    localparam int PF_DEPTH = 4;
    localparam int PF_PTR_W = 2;
    localparam int PF_CNT_W = 3;
    localparam int CR_W     = 3;   // holds 0..PF_DEPTH

    // ----------------------------------------------------------------
    // Data FIFO occupancy (SRAM is the storage array)
    // ----------------------------------------------------------------
    logic [PTR_W-1:0] wr_ptr, rd_ptr;
    logic [CNT_W-1:0] fifo_count;

    wire fifo_full  = (fifo_count == CNT_W'(DEPTH));
    wire fifo_empty = (fifo_count == '0);

    logic wr_fire;
    assign wr_fire = s_axi_wvalid && s_axi_wready;

    // ----------------------------------------------------------------
    // AXI4-MM write state machine
    // ----------------------------------------------------------------
    typedef enum logic [1:0] { IDLE, BURST, RESP } aw_state_t;
    aw_state_t aw_state;

    logic [7:0] beats_left;

    assign s_axi_awready = (aw_state == IDLE);
    assign s_axi_wready  = (aw_state == BURST) && !fifo_full;
    assign s_axi_bresp   = 2'b00;

    wire aw_fire = s_axi_awvalid && s_axi_awready;   // AW handshake

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
    // Length FIFO: push AWLEN on each AW handshake (BEFORE the burst's
    // data arrives), pop when the read side begins draining a new burst.
    // This decouples per-burst TLAST framing from the single write FSM.
    // ----------------------------------------------------------------
    logic [7:0]          lf_mem [0:LF_DEPTH-1];
    logic [LF_PTR_W-1:0] lf_wr, lf_rd;
    logic [LF_CNT_W-1:0] lf_count;

    wire       lf_empty = (lf_count == '0);
    wire [7:0] lf_head  = lf_mem[lf_rd];

    logic lf_push, lf_pop;
    assign lf_push = aw_fire;

    always_ff @(posedge clk) begin
        if (rst) begin
            lf_wr    <= '0;
            lf_rd    <= '0;
            lf_count <= '0;
        end else begin
            if (lf_push) begin
                lf_mem[lf_wr] <= s_axi_awlen;
                lf_wr <= lf_wr + 1'b1;
            end
            if (lf_pop)
                lf_rd <= lf_rd + 1'b1;
            case ({lf_push, lf_pop})
                2'b10:   lf_count <= lf_count + 1'b1;
                2'b01:   lf_count <= lf_count - 1'b1;
                default: lf_count <= lf_count;
            endcase
        end
    end

    // ----------------------------------------------------------------
    // Credit-gated read issue + prefetch FIFO
    //   A read issued this cycle lands on sram_rdata next cycle. Each
    //   issue consumes a credit (reserves a prefetch slot); each stream
    //   pop returns a credit. This removes the 50% dead-cycle and never
    //   overflows the prefetch FIFO.
    // ----------------------------------------------------------------
    logic [CR_W-1:0] credits;

    logic rd_issue;
    assign rd_issue = stream_enable && !fifo_empty && (credits != '0);

    logic [31:0] sram_rdata;   // SRAM port-1 read data (1-cycle latency)
    logic        rd_issue_d;   // read result valid this cycle
    logic        last_d;       // TLAST flag aligned to landing data

    // TLAST tracking on the read (issue) side
    logic [7:0] rd_beats_left;
    logic       rd_active;

    wire start_burst = rd_issue && !rd_active;
    assign lf_pop = start_burst;

    wire last_comb = start_burst ? (lf_head == 8'd0)
                                 : (rd_beats_left == 8'd1);

    always_ff @(posedge clk) begin
        if (rst) begin
            rd_beats_left <= '0;
            rd_active     <= 1'b0;
        end else if (rd_issue) begin
            if (!rd_active) begin
                rd_beats_left <= lf_head;
                rd_active     <= (lf_head != 8'd0);
            end else begin
                rd_beats_left <= rd_beats_left - 1'b1;
                if (rd_beats_left == 8'd1)
                    rd_active <= 1'b0;
            end
        end
    end

    // Pipeline issue + last flag one cycle to align with SRAM data landing
    always_ff @(posedge clk) begin
        if (rst) begin
            rd_issue_d <= 1'b0;
            last_d     <= 1'b0;
        end else begin
            rd_issue_d <= rd_issue;
            if (rd_issue)
                last_d <= last_comb;
        end
    end

    // Prefetch FIFO: stores {last, data}
    logic [32:0]         pf_mem [0:PF_DEPTH-1];
    logic [PF_PTR_W-1:0] pf_wr, pf_rd;
    logic [PF_CNT_W-1:0] pf_count;

    wire pf_empty = (pf_count == '0);

    wire pf_push = rd_issue_d;
    wire pf_pop  = m_axis_tvalid && m_axis_tready;

    always_ff @(posedge clk) begin
        if (rst) begin
            pf_wr    <= '0;
            pf_rd    <= '0;
            pf_count <= '0;
        end else begin
            if (pf_push) begin
                pf_mem[pf_wr] <= {last_d, sram_rdata};
                pf_wr <= pf_wr + 1'b1;
            end
            if (pf_pop)
                pf_rd <= pf_rd + 1'b1;
            case ({pf_push, pf_pop})
                2'b10:   pf_count <= pf_count + 1'b1;
                2'b01:   pf_count <= pf_count - 1'b1;
                default: pf_count <= pf_count;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst)
            credits <= CR_W'(PF_DEPTH);
        else begin
            case ({rd_issue, pf_pop})
                2'b10:   credits <= credits - 1'b1;
                2'b01:   credits <= credits + 1'b1;
                default: credits <= credits;
            endcase
        end
    end

    // AXI-Stream outputs driven from prefetch FIFO head (first-word fall-through)
    assign m_axis_tvalid = !pf_empty;
    assign m_axis_tdata  = pf_mem[pf_rd][31:0];
    assign m_axis_tlast  = pf_mem[pf_rd][32];

    // ----------------------------------------------------------------
    // Data FIFO pointer / count update
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
        .p0_en    (wr_fire),
        .p0_we    (1'b1),
        .p0_wmask (s_axi_wstrb),
        .p0_addr  (wr_ptr),
        .p0_din   (s_axi_wdata),
        .p0_dout  (),
        .p1_en    (rd_issue),
        .p1_addr  (rd_ptr),
        .p1_dout  (sram_rdata)
    );

endmodule
