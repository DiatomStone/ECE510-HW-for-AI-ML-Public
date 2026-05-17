// Created with Cursor — Agent (GPT-5.5)
// Created: 2026-05-16
// Modified: 2026-05-16
//
// Integration stimulus for gelu16_axi_top: hierarchical memory preload, AXI-lite, PASS/FAIL.

`timescale 1 ns / 1 ps

module tb_gelu16_axi_top;

    logic clk = 1'b0;
    logic rst = 1'b1;

    always #10 clk = ~clk;

    logic [31:0] axi_awaddr;
    logic        axi_awvalid;
    wire         axi_awready;

    logic [31:0] axi_wdata;
    logic [3:0]  axi_wstrb;
    logic        axi_wvalid;
    wire         axi_wready;

    wire [1:0] axi_bresp;
    wire       axi_bvalid;
    logic      axi_bready = 1'b1;

    logic [31:0] axi_araddr;
    logic        axi_arvalid;
    wire         axi_arready;

    wire [31:0] axi_rdata;
    wire [1:0]  axi_rresp;
    wire        axi_rvalid;
    logic       axi_rready = 1'b1;

    logic        s_axis_tvalid = 1'b0;
    wire         s_axis_tready;
    logic signed [31:0] s_axis_tdata = '0;
    logic        s_axis_tlast = 1'b0;
    logic [0:0]  s_axis_tuser = 1'b0;

    wire         m_axis_tvalid;
    logic        m_axis_tready = 1'b1;
    wire signed [31:0] m_axis_tdata;
    wire        m_axis_tlast;
    wire [0:0]  m_axis_tuser;

    localparam int TB_BANK_AW = $clog2(256);

    gelu16_axi_top #(
        .WORDS_PER_BANK (256)
    ) dut (
        .clk           (clk),
        .rst           (rst),
        .axi_awready   (axi_awready),
        .axi_awvalid   (axi_awvalid),
        .axi_awaddr    (axi_awaddr),
        .axi_wready    (axi_wready),
        .axi_wvalid    (axi_wvalid),
        .axi_wdata     (axi_wdata),
        .axi_wstrb     (axi_wstrb),
        .axi_bresp     (axi_bresp),
        .axi_bvalid    (axi_bvalid),
        .axi_bready    (axi_bready),
        .axi_arready   (axi_arready),
        .axi_arvalid   (axi_arvalid),
        .axi_araddr    (axi_araddr),
        .axi_rdata     (axi_rdata),
        .axi_rresp     (axi_rresp),
        .axi_rvalid    (axi_rvalid),
        .axi_rready    (axi_rready),
        .s_axis_tvalid (s_axis_tvalid),
        .s_axis_tready (s_axis_tready),
        .s_axis_tdata  (s_axis_tdata),
        .s_axis_tlast  (s_axis_tlast),
        .s_axis_tuser  (s_axis_tuser),
        .m_axis_tvalid (m_axis_tvalid),
        .m_axis_tready (m_axis_tready),
        .m_axis_tdata  (m_axis_tdata),
        .m_axis_tlast  (m_axis_tlast),
        .m_axis_tuser  (m_axis_tuser)
    );

    integer jj;
    integer poll_i;
    logic [31:0] rr;
    logic signed [31:0] y_ref;

    task automatic wait_clk;
        @(posedge clk);
    endtask

    task automatic write_lite(input logic [31:0] byte_addr, input logic [31:0] data);
        integer c;
        begin
            axi_awaddr   = byte_addr;
            axi_awvalid  = 1'b1;
            axi_wdata    = data;
            axi_wstrb    = 4'hF;
            axi_wvalid   = 1'b1;

            for (c = 0; c < 8192; c = c + 1) begin
                wait_clk();
                if (axi_awready && axi_wready && axi_wvalid && axi_awvalid)
                    c = 8192;
            end

            axi_awvalid = 1'b0;
            axi_wvalid  = 1'b0;

            for (c = 0; c < 8192; c = c + 1) begin
                wait_clk();
                if (axi_bvalid && axi_bready)
                    c = 8192;
            end
        end
    endtask

    task automatic read_lite(input logic [31:0] byte_addr, output logic [31:0] data);
        integer c;
        begin
            axi_araddr  = byte_addr;
            axi_arvalid = 1'b1;
            for (c = 0; c < 8192; c = c + 1) begin
                wait_clk();
                if (axi_arready && axi_arvalid)
                    c = 8192;
            end
            axi_arvalid = 1'b0;

            for (c = 0; c < 8192; c = c + 1) begin
                wait_clk();
                if (axi_rvalid && axi_rready) begin
                    data = axi_rdata;
                    c = 8192;
                end
            end
        end
    endtask

    task automatic mem_wr_logical(input logic [31:0] lg, input logic signed [31:0] dword);
        dut.mem_ff[lg[3:0]][lg[TB_BANK_AW+3:4]] = dword;
    endtask

    function automatic logic signed [31:0] mem_rd_logical(input logic [31:0] lg);
        mem_rd_logical = dut.mem_ff[lg[3:0]][lg[TB_BANK_AW+3:4]];
    endfunction

    initial begin
        axi_awvalid = 0;
        axi_wvalid = 0;
        axi_awaddr = '0;
        axi_wdata = '0;
        axi_wstrb = '0;
        axi_arvalid = 0;
        axi_araddr = '0;

        rst = 1'b1;
        repeat (8)
            wait_clk();
        rst = 1'b0;
        wait_clk();

        for (jj = 0; jj < 16; jj = jj + 1)
            mem_wr_logical(jj[31:0], 32'sd65536);

        write_lite(32'h08, 32'h0000_0000);
        write_lite(32'h0C, 32'd256);
        write_lite(32'h10, 32'd16);
        write_lite(32'h00, 32'h0000_0001);

        poll_i = 0;
        rr = 32'h0;
        while ((!rr[1]) && (poll_i < 100000)) begin
            wait_clk();
            read_lite(32'h04, rr);
            poll_i = poll_i + 1;
        end
        if (!rr[1])
            $fatal(1, "timeout polling status.done");

        y_ref = mem_rd_logical(32'd256);
        for (jj = 1; jj < 16; jj = jj + 1) begin
            if (mem_rd_logical(jj + 256) !== y_ref) begin
                $display("FAIL mismatch %0d", jj);
                $finish(2);
            end
        end
        $display("PASS");
        $finish(0);
    end

endmodule
