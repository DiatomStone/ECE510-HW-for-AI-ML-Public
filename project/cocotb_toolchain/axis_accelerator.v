`timescale 1ns / 1ps

module axis_accelerator (
    input wire clk,
    input wire rst,

    // AXI-Stream Input (From Memory Buffer)
    input  wire [31:0] s_axis_tdata,
    input  wire        s_axis_tvalid,
    output wire        s_axis_tready,
    input  wire        s_axis_tlast,

    // AXI-Stream Output (Back to Memory Buffer)
    output wire [31:0] m_axis_tdata,
    output wire        m_axis_tvalid,
    input  wire        m_axis_tready,
    output wire        m_axis_tlast
);

    // Perform the mathematical processing directly on the stream pipeline
    assign m_axis_tdata  = s_axis_tdata * 5;
    assign m_axis_tvalid = s_axis_tvalid;
    assign m_axis_tlast  = s_axis_tlast;
    
    // Pass backpressure signals across the channel straight through
    assign s_axis_tready = m_axis_tready;

endmodule

