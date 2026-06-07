// =========================================================================
// Module:  openram_1k_wrap
// Project: GELU Activation Kernel - ECE 410/510, M3
//
// Description:
//   Thin wrapper around sky130_sram_1rw1r_32_1024_8.
//   Exposes port 0 (read-write) and port 1 (read-only) with
//   straightforward active-high enable signals.
//
//   Both ports have 1-cycle registered output latency.
//
// Parameters:
//   DEPTH  - number of 32-bit words (default 1024). The DMA buffers override
//            this to 256 to keep the inferred (macro-free) RAM small enough to
//            place & route — a 256:1 read mux instead of 1024:1 — see synth
//            config_dma.json. The standalone unit tb keeps the 1024 default.
//   ADDR_W - word-address width (default clog2(DEPTH)).
//
// Ports — Port 0 (read-write):
//   clk          - input,  1      : System clock (shared both ports)
//   p0_en        - input,  1      : Port 0 chip enable (active high)
//   p0_we        - input,  1      : Write enable (1 = write, 0 = read)
//   p0_wmask     - input,  4      : Byte write mask (active high, write only)
//   p0_addr      - input,  ADDR_W : Word address
//   p0_din       - input,  32     : Write data
//   p0_dout      - output, 32     : Read data (valid 1 cycle after p0_en=1,p0_we=0)
//
// Ports — Port 1 (read-only):
//   p1_en        - input,  1      : Port 1 chip enable (active high)
//   p1_addr      - input,  ADDR_W : Word address
//   p1_dout      - output, 32     : Read data (valid 1 cycle after p1_en=1)
// =========================================================================

module openram_1k_wrap #(
    parameter int DEPTH  = 1024,
    parameter int ADDR_W = $clog2(DEPTH)
)(
    input  logic              clk,

    // Port 0 — read-write
    input  logic              p0_en,
    input  logic              p0_we,
    input  logic [3:0]        p0_wmask,
    input  logic [ADDR_W-1:0] p0_addr,
    input  logic [31:0]       p0_din,
    output logic [31:0]       p0_dout,

    // Port 1 — read-only
    input  logic              p1_en,
    input  logic [ADDR_W-1:0] p1_addr,
    output logic [31:0]       p1_dout
);

    // Inferred DEPTH x 32 dual-port memory (macro-free).
    // The sky130_sram_1rw1r_32_1024_8 macro views (gds/lef/lib) are not in the
    // repo, so synthesis builds this RAM from std cells (DFF-based) instead of
    // a hard macro. Same model is used for simulation (Icarus / cocotb).
    logic [31:0] mem [0:DEPTH-1];

    // Port 0: registered read-write
    always_ff @(posedge clk) begin
        if (p0_en) begin
            if (p0_we) begin
                if (p0_wmask[0]) mem[p0_addr][ 7: 0] <= p0_din[ 7: 0];
                if (p0_wmask[1]) mem[p0_addr][15: 8] <= p0_din[15: 8];
                if (p0_wmask[2]) mem[p0_addr][23:16] <= p0_din[23:16];
                if (p0_wmask[3]) mem[p0_addr][31:24] <= p0_din[31:24];
            end
            p0_dout <= mem[p0_addr];
        end
    end

    // Port 1: registered read-only
    always_ff @(posedge clk) begin
        if (p1_en)
            p1_dout <= mem[p1_addr];
    end

endmodule
