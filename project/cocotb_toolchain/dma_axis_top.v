`timescale 1ns / 1ps

module dma_axis_top (
    input wire clk,
    input wire rst,

    // AXI-Lite Slave Interface
    input  wire [31:0] s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output reg         s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output reg         s_axi_wready,
    output reg  [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    
    input  wire [31:0] s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output reg         s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output reg  [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    // AXI-Stream Input Port (From Host PC)
    input  wire [31:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,

    // AXI-Stream Output Port (To Host PC)
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);

    // Configuration Gate Switch Control
    reg pipeline_enable;

    // --- AXI-Lite Command Handling ---
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            s_axi_awready   <= 0;
            s_axi_wready    <= 0;
            s_axi_bvalid    <= 0;
            s_axi_bresp     <= 0;
            pipeline_enable <= 0;
        end else begin
            if (s_axi_awvalid && s_axi_wvalid && !s_axi_bvalid) begin
                s_axi_awready <= 1;
                s_axi_wready  <= 1;
                s_axi_bvalid  <= 1;
                if (s_axi_awaddr == 32'h00) begin
                    pipeline_enable <= s_axi_wdata[0];
                end
            end else begin
                s_axi_awready <= 0;
                s_axi_wready  <= 0;
                if (s_axi_bvalid && s_axi_bready) s_axi_bvalid <= 0;
            end
        end
    end

    // Internal Interconnect Wires
    wire [31:0] to_acc_tdata;
    wire        to_acc_tvalid;
    wire        to_acc_tready;
    wire        to_acc_tlast;

    wire [31:0] from_acc_tdata;
    wire        from_acc_tvalid;
    wire        from_acc_tready;
    wire        from_acc_tlast;

    // -------------------------------------------------------------
    // INPUT BUFFER FIFO (Standard Circular Queue Implementation)
    // -------------------------------------------------------------
    reg [31:0] in_fifo_ram [0:15];
    reg [3:0]  in_wr_ptr = 0;
    reg [3:0]  in_rd_ptr = 0;
    reg [4:0]  in_count  = 0;

    assign s_axis_tready = (in_count < 16);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            in_wr_ptr <= 0;
            in_rd_ptr <= 0;
            in_count  <= 0;
        end else begin
            if (s_axis_tvalid && s_axis_tready) begin
                in_fifo_ram[in_wr_ptr] <= s_axis_tdata;
                in_wr_ptr <= in_wr_ptr + 1;
            end
            if (to_acc_tvalid && to_acc_tready) begin
                in_rd_ptr <= in_rd_ptr + 1;
            end
            
            case ({s_axis_tvalid && s_axis_tready, to_acc_tvalid && to_acc_tready})
                2'b10: in_count <= in_count + 1;
                2'b01: in_count <= in_count - 1;
                default: in_count <= in_count;
            endcase
        end
    end

    assign to_acc_tdata  = in_fifo_ram[in_rd_ptr];
    assign to_acc_tvalid = (in_count > 0) && pipeline_enable;
    assign to_acc_tlast  = (in_count == 1);

    // -------------------------------------------------------------
    // INSTANTIATION: Core Processing Node
    // -------------------------------------------------------------
    axis_accelerator u_accelerator (
        .clk           (clk),
        .rst           (rst),
        .s_axis_tdata  (to_acc_tdata),
        .s_axis_tvalid (to_acc_tvalid),
        .s_axis_tready (to_acc_tready),
        .s_axis_tlast  (to_acc_tlast),
        .m_axis_tdata  (from_acc_tdata),
        .m_axis_tvalid (from_acc_tvalid),
        .m_axis_tready (from_acc_tready),
        .m_axis_tlast  (from_acc_tlast)
    );

    // -------------------------------------------------------------
    // OUTPUT BUFFER FIFO (Standard Circular Queue Implementation)
    // -------------------------------------------------------------
    reg [31:0] out_fifo_ram [0:15];
    reg [3:0]  out_wr_ptr = 0;
    reg [3:0]  out_rd_ptr = 0;
    reg [4:0]  out_count  = 0;

    assign from_acc_tready = (out_count < 16);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            out_wr_ptr <= 0;
            out_rd_ptr <= 0;
            out_count  <= 0;
        end else begin
            if (from_acc_tvalid && from_acc_tready) begin
                out_fifo_ram[out_wr_ptr] <= from_acc_tdata;
                out_wr_ptr <= out_wr_ptr + 1;
            end
            if (m_axis_tvalid && m_axis_tready) begin
                out_rd_ptr <= out_rd_ptr + 1;
            end
            
            case ({from_acc_tvalid && from_acc_tready, m_axis_tvalid && m_axis_tready})
                2'b10: out_count <= out_count + 1;
                2'b01: out_count <= out_count - 1;
                default: out_count <= out_count;
            endcase
        end
    end

    assign m_axis_tdata  = out_fifo_ram[out_rd_ptr];
    assign m_axis_tvalid = (out_count > 0);
    assign m_axis_tlast  = (out_count == 1);

    // Tie off dummy read spaces safely
    always @(posedge clk or posedge rst) begin
        if (rst) begin s_axi_arready <= 0; s_axi_rvalid <= 0; s_axi_rdata <= 0; s_axi_rresp <= 0; end
        else if (s_axi_arvalid && !s_axi_rvalid) begin s_axi_arready <= 1; s_axi_rvalid <= 1; end
        else begin s_axi_arready <= 0; if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 0; end
    end

endmodule

