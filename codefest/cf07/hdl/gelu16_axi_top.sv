// Created with Cursor — Agent (GPT-5.5)
// Created: 2026-05-16
// Modified: 2026-05-16
// Modified by Manager (GPT-5.5); PIPE_DEPTH_CORE default aligned with synth_top
//
// 16 GELU lanes: AXI4-Lite CSRs, banked behavioral SRAM, optional AXI4 streams.

`timescale 1 ns / 1 ps

module gelu16_axi_top #(
    parameter int DATA_WIDTH        = 32,
    parameter int USER_WIDTH       = 1,
    parameter int ADDR_BYTE_WIDTH  = 32,
    parameter int WORDS_PER_BANK    = 256,
    parameter int NUM_LANES          = 16,
    parameter int PIPE_DEPTH_CORE   = 5
)(
    input  logic                        clk,
    input  logic                        rst,

    output logic                        axi_awready,
    input  logic                        axi_awvalid,
    input  logic [ADDR_BYTE_WIDTH-1:0] axi_awaddr,

    output logic                        axi_wready,
    input  logic                        axi_wvalid,
    input  logic [31:0]                 axi_wdata,
    input  logic [3:0]                  axi_wstrb,

    output logic [1:0]                  axi_bresp,
    output logic                        axi_bvalid,
    input  logic                        axi_bready,

    output logic                        axi_arready,
    input  logic                        axi_arvalid,
    input  logic [ADDR_BYTE_WIDTH-1:0] axi_araddr,

    output logic [31:0]                 axi_rdata,
    output logic [1:0]                  axi_rresp,
    output logic                        axi_rvalid,
    input  logic                        axi_rready,

    input  logic                        s_axis_tvalid,
    output logic                        s_axis_tready,
    input  logic signed [DATA_WIDTH-1:0]s_axis_tdata,
    input  logic                        s_axis_tlast,
    input  logic [USER_WIDTH-1:0]       s_axis_tuser,

    output logic                        m_axis_tvalid,
    input  logic                        m_axis_tready,
    output logic signed [DATA_WIDTH-1:0]m_axis_tdata,
    output logic                        m_axis_tlast,
    output logic [USER_WIDTH-1:0]       m_axis_tuser
);

    localparam int BANK_ADDR_W  = $clog2(WORDS_PER_BANK);
    localparam int WAIT_PIPE_CY = (PIPE_DEPTH_CORE > 1) ? (PIPE_DEPTH_CORE - 1) : 1;

    typedef logic signed [DATA_WIDTH-1:0] sdata_t;

    typedef enum logic [2:0] {
        ST_IDLE,
        ST_STREAM_RX,
        ST_ISSUE,
        ST_WAITPIPE,
        ST_STORE_MEM,
        ST_STREAM_TX,
        ST_DONE
    } st_t;

    st_t st_ff;

    logic [31:0] csr_ctl_ff;
    logic [31:0] csr_ibase_ff;
    logic [31:0] csr_obase_ff;
    logic [31:0] csr_elcnt_ff;
    logic        csr_busy_ff;
    logic        csr_done_ff;

    logic [31:0] job_total_ff;
    logic [31:0] job_ptr_ff;
    logic [31:0] snap_ib_ff;
    logic [31:0] snap_ob_ff;

    logic        cfg_stream_i_ff;
    logic        cfg_stream_o_ff;

    logic unsigned [4:0] lane_m1_ff;
    logic [7:0]          pipe_wait_ff;

    logic unsigned [4:0] srx_ix_ff;
    logic unsigned [4:0] stx_ix_ff;

    logic [NUM_LANES-1:0] v_in_ff;
    sdata_t              x_drv_ff[NUM_LANES];

    logic signed [DATA_WIDTH-1:0] y_out[NUM_LANES];
    logic                         y_hit[NUM_LANES];

    // mem[bank_id][row] holds dword whose logical index is (row << 4) | bank_id
    sdata_t mem_ff[NUM_LANES][WORDS_PER_BANK];

    sdata_t strm_buf[NUM_LANES];

    logic unsigned [31:0] iss_k_ext;
    logic [31:0]          iss_logical;
    logic unsigned [31:0] iss_bank;
    logic [31:0]           iss_row;

    logic unsigned [31:0] sto_w_ext;
    logic [31:0]          sto_logical;

    logic [NUM_LANES-1:0]     wr_pulse_ff;
    logic unsigned [3:0]       wr_bank_ff[NUM_LANES];
    logic [BANK_ADDR_W-1:0] wr_row_ff[NUM_LANES];
    sdata_t                  wr_wdata_ff[NUM_LANES];

    // -------------------------------------------------------------------------
    // AXI4-Lite write
    // -------------------------------------------------------------------------
    assign axi_awready = !(csr_busy_ff || (axi_bvalid && !axi_bready));
    assign axi_wready  = axi_awready;

    wire lite_wr_pulse =
        axi_awvalid &&
        axi_wvalid &&
        axi_awready &&
        axi_wready &&
        !csr_busy_ff;

    always_ff @(posedge clk) begin
        if (rst) begin
            axi_bvalid <= 1'b0;
            axi_bresp  <= 2'b00;
        end else begin
            if (axi_bready && axi_bvalid)
                axi_bvalid <= 1'b0;
            else if (lite_wr_pulse)
                axi_bvalid <= 1'b1;
        end
    end

    assign axi_arready = !axi_rvalid || axi_rready;

    wire [ADDR_BYTE_WIDTH-1:2] ar_word_ix = axi_araddr[ADDR_BYTE_WIDTH-1:2];

    always_ff @(posedge clk) begin
        if (rst) begin
            axi_rvalid <= 1'b0;
            axi_rdata  <= 32'h0;
            axi_rresp  <= 2'b00;
        end else begin
            if (axi_rready && axi_rvalid)
                axi_rvalid <= 1'b0;
            else if (axi_arvalid && axi_arready) begin
                axi_rvalid <= 1'b1;
                axi_rresp  <= 2'b00;
                unique case (ar_word_ix)
                    10'h000: begin
                        axi_rdata         <= csr_ctl_ff;
                        axi_rdata[0]      <= 1'b0; // start is pulse-only
                    end
                    10'h001: begin
                        axi_rdata            <= 32'h0;
                        axi_rdata[0]         <= csr_busy_ff;
                        axi_rdata[1]         <= csr_done_ff;
                    end
                    10'h002: axi_rdata <= csr_ibase_ff;
                    10'h003: axi_rdata <= csr_obase_ff;
                    10'h004: axi_rdata <= csr_elcnt_ff;
                    default: axi_rdata <= 32'hDEAD_BEEF;
                endcase
            end
        end
    end

    wire start_pulse = lite_wr_pulse &&
        (axi_awaddr[ADDR_BYTE_WIDTH-1:2] == 10'h000) &&
        axi_wstrb[0] && axi_wdata[0];

    wire clr_done_pulse = lite_wr_pulse &&
        (axi_awaddr[ADDR_BYTE_WIDTH-1:2] == 10'h000) &&
        axi_wstrb[1] && axi_wdata[1];

    function automatic logic [31:0] masked_wdata(logic [31:0] w, logic [3:0] s);
        masked_wdata = 32'h0;
        if (s[0]) masked_wdata[ 7: 0] = w[ 7: 0];
        if (s[1]) masked_wdata[15: 8] = w[15: 8];
        if (s[2]) masked_wdata[23:16] = w[23:16];
        if (s[3]) masked_wdata[31:24] = w[31:24];
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            csr_ctl_ff   <= 32'h0;
            csr_ibase_ff <= 32'h0;
            csr_obase_ff <= 32'h0;
            csr_elcnt_ff <= 32'h0;
            csr_done_ff  <= 1'b0;
        end else begin
            if (clr_done_pulse)
                csr_done_ff <= 1'b0;
            else if (st_ff == ST_DONE && csr_busy_ff)
                csr_done_ff <= 1'b1;

            if (lite_wr_pulse && !csr_busy_ff) begin
                unique case (axi_awaddr[ADDR_BYTE_WIDTH-1:2])
                    10'h000: begin
                        if (axi_wstrb[2])
                            csr_ctl_ff[2] <= axi_wdata[2];
                        if (axi_wstrb[3])
                            csr_ctl_ff[3] <= axi_wdata[3];
                    end
                    10'h002: begin
                        if (|axi_wstrb)
                            csr_ibase_ff <= masked_wdata(axi_wdata, axi_wstrb);
                    end
                    10'h003: begin
                        if (|axi_wstrb)
                            csr_obase_ff <= masked_wdata(axi_wdata, axi_wstrb);
                    end
                    10'h004: begin
                        if (|axi_wstrb)
                            csr_elcnt_ff <= masked_wdata(axi_wdata, axi_wstrb);
                    end
                    default: ;
                endcase
            end
        end
    end

    genvar gi;
    generate
        for (gi = 0; gi < NUM_LANES; gi++) begin : g_lane
            synth_top #(
                .DATA_WIDTH (DATA_WIDTH),
                .FRAC_BITS  (16),
                .PIPE_DEPTH (PIPE_DEPTH_CORE)
            ) u_lane (
                .clk       (clk),
                .rst       (rst),
                .valid_in  (v_in_ff[gi]),
                .x         (x_drv_ff[gi]),
                .valid_out (y_hit[gi]),
                .out       (y_out[gi])
            );
        end
    endgenerate

    // Remaining elements in this job
    logic [31:0] elems_left_c;
    always_comb begin
        elems_left_c = job_total_ff - job_ptr_ff;
    end

    function automatic logic unsigned [4:0] lanes_m1(input logic [31:0] left);
        if (left == 32'd0)
            lanes_m1 = 5'd0;
        else if (left >= 32'd16)
            lanes_m1 = 5'd15;
        else
            lanes_m1 = left[4:0] - 5'd1;
    endfunction

    // Memory write port
    integer bi, rj;
    always_ff @(posedge clk) begin
        if (rst) begin
            for (bi = 0; bi < NUM_LANES; bi = bi + 1) begin
                for (rj = 0; rj < WORDS_PER_BANK; rj = rj + 1)
                    mem_ff[bi][rj] <= sdata_t'(0);
            end
        end else begin
            for (bi = 0; bi < NUM_LANES; bi = bi + 1) begin
                if (wr_pulse_ff[bi])
                    mem_ff[wr_bank_ff[bi]][wr_row_ff[bi]] <= wr_wdata_ff[bi];
            end
        end
    end

    assign m_axis_tuser = USER_WIDTH'(0);

    assign s_axis_tready =
        (st_ff == ST_STREAM_RX) && (csr_busy_ff);

    integer   seq_k;
    integer   seq_w;
    logic [31:0] grp_width_word;
    logic [31:0] next_job_ptr;
    logic [31:0] strm_grp_w;
    logic [31:0] strm_next_ptr;

    always_ff @(posedge clk) begin
        if (rst) begin
            st_ff           <= ST_IDLE;
            csr_busy_ff     <= 1'b0;
            job_total_ff    <= 32'h0;
            job_ptr_ff      <= 32'h0;
            snap_ib_ff      <= 32'h0;
            snap_ob_ff      <= 32'h0;
            cfg_stream_i_ff <= 1'b0;
            cfg_stream_o_ff <= 1'b0;
            lane_m1_ff      <= 5'd0;
            pipe_wait_ff    <= WAIT_PIPE_CY[7:0];
            srx_ix_ff       <= 5'd0;
            stx_ix_ff       <= 5'd0;
            v_in_ff         <= '0;
            wr_pulse_ff     <= '0;
            m_axis_tvalid   <= 1'b0;
            m_axis_tdata    <= sdata_t'(0);
            m_axis_tlast    <= 1'b0;
        end else begin
            wr_pulse_ff <= '0;
            v_in_ff     <= '0;

            unique case (st_ff)
                ST_IDLE: begin
                    m_axis_tvalid <= 1'b0;
                    m_axis_tlast  <= 1'b0;
                    pipe_wait_ff  <= WAIT_PIPE_CY[7:0];
                    if (start_pulse) begin
                        csr_busy_ff     <= 1'b1;
                        job_total_ff    <= csr_elcnt_ff;
                        job_ptr_ff      <= 32'd0;
                        snap_ib_ff      <= csr_ibase_ff;
                        snap_ob_ff      <= csr_obase_ff;
                        cfg_stream_i_ff <= csr_ctl_ff[2];
                        cfg_stream_o_ff <= csr_ctl_ff[3];
                        srx_ix_ff       <= 5'd0;
                        stx_ix_ff       <= 5'd0;

                        lane_m1_ff <= lanes_m1(csr_elcnt_ff);

                        if (csr_elcnt_ff == 32'd0) begin
                            st_ff <= ST_DONE;
                        end else if (csr_ctl_ff[2])
                            st_ff <= ST_STREAM_RX;
                        else
                            st_ff <= ST_ISSUE;
                    end
                end

                ST_STREAM_RX: begin
                    lane_m1_ff <= lanes_m1(elems_left_c);
                    if (s_axis_tvalid && s_axis_tready) begin
                        strm_buf[srx_ix_ff] <= s_axis_tdata;
                        if (srx_ix_ff == lane_m1_ff) begin
                            st_ff <= ST_ISSUE;
                        end else begin
                            srx_ix_ff <= srx_ix_ff + 5'd1;
                        end
                    end
                end

                ST_ISSUE: begin
                    lane_m1_ff <= lanes_m1(elems_left_c);
                    pipe_wait_ff <= WAIT_PIPE_CY[7:0];

                    for (seq_k = 0; seq_k < NUM_LANES; seq_k = seq_k + 1) begin
                        iss_k_ext   = 32'(seq_k);
                        iss_logical = snap_ib_ff + job_ptr_ff + iss_k_ext;

                        if (iss_k_ext <= {27'd0, lane_m1_ff}) begin
                            iss_bank = iss_logical[3:0];
                            iss_row  = iss_logical >> 4;
                            if (cfg_stream_i_ff)
                                x_drv_ff[seq_k] <= strm_buf[seq_k];
                            else
                                x_drv_ff[seq_k] <= mem_ff[iss_bank[3:0]][iss_row[BANK_ADDR_W-1:0]];
                            v_in_ff[seq_k] <= 1'b1;
                        end else begin
                            v_in_ff[seq_k] <= 1'b0;
                        end
                    end

                    st_ff <= ST_WAITPIPE;
                end

                ST_WAITPIPE: begin
                    lane_m1_ff <= lane_m1_ff;
                    if (pipe_wait_ff == 8'd0) begin
                        if (cfg_stream_o_ff)
                            st_ff <= ST_STREAM_TX;
                        else
                            st_ff <= ST_STORE_MEM;
                    end else begin
                        pipe_wait_ff <= pipe_wait_ff - 8'd1;
                    end
                end

                ST_STORE_MEM: begin
                    for (seq_w = 0; seq_w < NUM_LANES; seq_w = seq_w + 1) begin
                        sto_w_ext = 32'(seq_w);
                        sto_logical = snap_ob_ff + job_ptr_ff + sto_w_ext;

                        if (sto_w_ext <= {27'd0, lane_m1_ff}) begin
                            wr_pulse_ff[seq_w]   <= 1'b1;
                            wr_bank_ff[seq_w]    <= sto_logical[3:0];
                            wr_row_ff[seq_w]     <= BANK_ADDR_W'(sto_logical >> 4);
                            wr_wdata_ff[seq_w]   <= y_out[seq_w];
                        end
                    end

                    grp_width_word = {27'd0, lane_m1_ff} + 32'd1;
                    next_job_ptr = job_ptr_ff + grp_width_word;

                    job_ptr_ff <= next_job_ptr;

                    if (next_job_ptr >= job_total_ff)
                        st_ff <= ST_DONE;
                    else begin
                        srx_ix_ff <= 5'd0;
                        lane_m1_ff <= lanes_m1(job_total_ff - next_job_ptr);

                        if (cfg_stream_i_ff)
                            st_ff <= ST_STREAM_RX;
                        else
                            st_ff <= ST_ISSUE;
                    end
                end

                ST_STREAM_TX: begin
                    lane_m1_ff <= lanes_m1(elems_left_c);

                    if (!m_axis_tvalid) begin
                        m_axis_tdata  <= y_out[stx_ix_ff];
                        m_axis_tlast  <= (stx_ix_ff == lane_m1_ff);
                        m_axis_tvalid <= 1'b1;
                    end else if (m_axis_tready) begin
                        if (stx_ix_ff == lane_m1_ff) begin
                            m_axis_tvalid <= 1'b0;

                            strm_grp_w   = {27'd0, lane_m1_ff} + 32'd1;
                            strm_next_ptr = job_ptr_ff + strm_grp_w;

                            job_ptr_ff <= strm_next_ptr;
                            stx_ix_ff  <= 5'd0;

                            if (strm_next_ptr >= job_total_ff)
                                st_ff <= ST_DONE;
                            else begin
                                srx_ix_ff  <= 5'd0;
                                lane_m1_ff <= lanes_m1(job_total_ff - strm_next_ptr);

                                if (cfg_stream_i_ff)
                                    st_ff <= ST_STREAM_RX;
                                else
                                    st_ff <= ST_ISSUE;
                            end
                        end else begin
                            stx_ix_ff     <= stx_ix_ff + 5'd1;
                            m_axis_tdata  <= y_out[stx_ix_ff + 5'd1];
                            m_axis_tlast  <= ((stx_ix_ff + 5'd1) == lane_m1_ff);
                            m_axis_tvalid <= 1'b1;
                        end
                    end
                end

                ST_DONE: begin
                    csr_busy_ff   <= 1'b0;
                    m_axis_tvalid <= 1'b0;
                    m_axis_tlast  <= 1'b0;
                    st_ff         <= ST_IDLE;
                end

                default: st_ff <= ST_IDLE;
            endcase
        end
    end

endmodule
