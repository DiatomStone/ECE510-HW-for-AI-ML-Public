// =========================================================================
// tb_top.sv — co-simulation testbench for gelu_top
// Project  : GELU Activation Kernel — ECE 410/510, M3
//
// Description:
//   Black-box testbench: drives gelu_top exclusively through its AXI-Lite
//   and AXI-Stream ports — no access to internal signals.  Matches the
//   protocol a real PCIe/DMA host would use.
//
// Test kernel:
//   M1 small-config transformer (d_ff=256, seq=64, batch=8, seed=42).
//   Input vector: FFN layer-0 pre-activation h = xn2 @ W1 + b1,
//   batch=0, token=0 — 256 float32 elements.  This is the dominant GELU
//   kernel identified in M1 profiling (21.4 % of total runtime).
//
// Reference:
//   Expected outputs are pre-computed in float64 from the same float32
//   inputs using the exact GELU formula (see tb/gen_vectors.py).
//   They are NOT derived from a prior DUT run.
//
// Waveform:
//   VCD dumped to sim/cosim_run.vcd.  Three annotated regions:
//     Region 1 (0 – ~80 ns)   : AXI-Lite pipeline_enable write + readback
//     Region 2 (~80 – ~2640 ns): AXI-Stream input beats (host → DUT)
//     Region 3 (~2640 – end)  : AXI-Stream output beats (DUT → host)
//
// Pass criterion:
//   All 256 outputs within 0.05 of the float64 reference (same threshold
//   as the accuracy sweep in tb_axis_interface.py).
// =========================================================================

`timescale 1ns/1ps

module tb_top;

    // -----------------------------------------------------------------------
    // Clock and reset
    // -----------------------------------------------------------------------
    logic clk = 0;
    logic rst = 1;
    always #5 clk = ~clk;          // 100 MHz

    // -----------------------------------------------------------------------
    // AXI-Lite signals
    // -----------------------------------------------------------------------
    logic [31:0] s_axil_awaddr  = 0;
    logic        s_axil_awvalid = 0;
    logic        s_axil_awready;
    logic [31:0] s_axil_wdata   = 0;
    logic [3:0]  s_axil_wstrb   = 0;
    logic        s_axil_wvalid  = 0;
    logic        s_axil_wready;
    logic [1:0]  s_axil_bresp;
    logic        s_axil_bvalid;
    logic        s_axil_bready  = 0;
    logic [31:0] s_axil_araddr  = 0;
    logic        s_axil_arvalid = 0;
    logic        s_axil_arready;
    logic [31:0] s_axil_rdata;
    logic [1:0]  s_axil_rresp;
    logic        s_axil_rvalid;
    logic        s_axil_rready  = 0;

    // -----------------------------------------------------------------------
    // AXI-Stream signals
    // -----------------------------------------------------------------------
    logic [31:0] s_axis_tdata  = 0;
    logic        s_axis_tvalid = 0;
    logic        s_axis_tready;
    logic        s_axis_tlast  = 0;
    logic        s_axis_tuser  = 0;
    logic [31:0] m_axis_tdata;
    logic        m_axis_tvalid;
    logic        m_axis_tready = 0;
    logic        m_axis_tlast;
    logic        m_axis_tuser;

    // -----------------------------------------------------------------------
    // DUT: gelu_top (drives only top-level AXI ports)
    // -----------------------------------------------------------------------
    gelu_top dut (
        .clk            (clk),
        .rst            (rst),
        .s_axil_awaddr  (s_axil_awaddr),
        .s_axil_awvalid (s_axil_awvalid),
        .s_axil_awready (s_axil_awready),
        .s_axil_wdata   (s_axil_wdata),
        .s_axil_wstrb   (s_axil_wstrb),
        .s_axil_wvalid  (s_axil_wvalid),
        .s_axil_wready  (s_axil_wready),
        .s_axil_bresp   (s_axil_bresp),
        .s_axil_bvalid  (s_axil_bvalid),
        .s_axil_bready  (s_axil_bready),
        .s_axil_araddr  (s_axil_araddr),
        .s_axil_arvalid (s_axil_arvalid),
        .s_axil_arready (s_axil_arready),
        .s_axil_rdata   (s_axil_rdata),
        .s_axil_rresp   (s_axil_rresp),
        .s_axil_rvalid  (s_axil_rvalid),
        .s_axil_rready  (s_axil_rready),
        .s_axis_tdata   (s_axis_tdata),
        .s_axis_tvalid  (s_axis_tvalid),
        .s_axis_tready  (s_axis_tready),
        .s_axis_tlast   (s_axis_tlast),
        .s_axis_tuser   (s_axis_tuser),
        .m_axis_tdata   (m_axis_tdata),
        .m_axis_tvalid  (m_axis_tvalid),
        .m_axis_tready  (m_axis_tready),
        .m_axis_tlast   (m_axis_tlast),
        .m_axis_tuser   (m_axis_tuser)
    );

    // -----------------------------------------------------------------------
    // VCD dump — three annotated regions visible in GTKWave:
    //   Region 1: AXI-Lite control (write + readback of pipeline_enable)
    //   Region 2: AXI-Stream input beats   (s_axis_* active)
    //   Region 3: AXI-Stream output beats  (m_axis_tvalid rising)
    // -----------------------------------------------------------------------
    initial begin
        $dumpfile("sim/cosim_run.vcd");
        $dumpvars(0, tb_top);
    end

    // -----------------------------------------------------------------------
    // fp32_to_real: decode IEEE-754 single → SV real (via double encoding)
    // Normal numbers only; subnormals (exp=0) returned as 0.0.
    // -----------------------------------------------------------------------
    function automatic real fp32_to_real(input logic [31:0] f32);
        logic [63:0] d64;
        logic [10:0] exp11;
        logic [7:0]  exp8;
        exp8 = f32[30:23];
        if (exp8 == 8'hFF)
            d64 = {f32[31], 11'h7FF, 52'h0};          // inf / NaN proxy
        else if (exp8 == 8'h00)
            d64 = 64'h0;                               // zero / subnormal → 0
        else begin
            exp11 = {3'b0, exp8} + 11'd896;            // rebias 127 → 1023
            d64   = {f32[31], exp11, f32[22:0], 29'h0};
        end
        return $bitstoreal(d64);
    endfunction

    // -----------------------------------------------------------------------
    // Test vector storage (256 = d_ff from M1 small config)
    // -----------------------------------------------------------------------
    localparam int N = 256;
    logic [31:0] in_vec  [N];
    logic [31:0] exp_vec [N];
    logic [31:0] got_vec [N];

    // -----------------------------------------------------------------------
    // Output capture: always block fires at the same posedge as the RTL,
    // reads m_axis_tdata in the active region (pre-NBA) — guaranteed to get
    // fifo_data[rd_ptr] before rd_ptr advances.
    // -----------------------------------------------------------------------
    logic        cap_active = 0;
    integer      recv_count = 0;

    always @(posedge clk) begin
        if (cap_active && m_axis_tvalid && m_axis_tready) begin
            got_vec[recv_count] = m_axis_tdata;   // blocking: pre-NBA read
            recv_count          = recv_count + 1;
        end
    end

    // -----------------------------------------------------------------------
    // AXI-Lite write task (2-cycle decoupled handshake per spec §A3.3.1)
    //   Cycle 1: RTL asserts awready/wready
    //   Cycle 2: master holds awvalid; RTL completes handshake, writes reg, asserts bvalid
    //   Cycle 3: RTL clears bvalid (bready already 1)
    // -----------------------------------------------------------------------
    task automatic axil_write(input logic [31:0] addr, data);
        s_axil_awaddr  = addr;
        s_axil_wdata   = data;
        s_axil_wstrb   = 4'hF;
        s_axil_awvalid = 1;
        s_axil_wvalid  = 1;
        s_axil_bready  = 1;
        @(posedge clk); while (!s_axil_awready) @(posedge clk);
        s_axil_awvalid = 0;
        s_axil_wvalid  = 0;
        @(posedge clk); while (!s_axil_bvalid)  @(posedge clk);
        s_axil_bready  = 0;
        @(posedge clk);
    endtask

    // -----------------------------------------------------------------------
    // AXI-Lite read task (2-cycle decoupled handshake per spec §A3.3.2)
    // -----------------------------------------------------------------------
    task automatic axil_read(input logic [31:0] addr, output logic [31:0] data);
        s_axil_araddr  = addr;
        s_axil_arvalid = 1;
        s_axil_rready  = 1;
        @(posedge clk); while (!s_axil_arready) @(posedge clk);
        s_axil_arvalid = 0;
        @(posedge clk); while (!s_axil_rvalid)  @(posedge clk);
        data           = s_axil_rdata;
        s_axil_rready  = 0;
        @(posedge clk);
    endtask

    // -----------------------------------------------------------------------
    // Main test
    // -----------------------------------------------------------------------
    integer fail_count;
    real    max_err, avg_err, err_r;
    integer worst_idx;
    logic [31:0] readback;

    initial begin
        $readmemh("tb/gelu_in.hex",  in_vec);
        $readmemh("tb/gelu_exp.hex", exp_vec);

        // ── Reset ──────────────────────────────────────────────────────────
        repeat (5) @(posedge clk);
        rst = 0;
        @(posedge clk);

        // ── Region 1: AXI-Lite write pipeline_enable=1, then readback ─────
        $display("[%0t ns] Region 1: AXI-Lite control transaction", $time);
        axil_write(32'h0, 32'h1);

        axil_read(32'h0, readback);
        if (readback !== 32'h1) begin
            $display("FAIL: pipeline_enable readback expected 1, got %0d", readback);
            $finish;
        end
        $display("[%0t ns] pipeline_enable=1 verified", $time);

        // ── Regions 2 & 3: send beats, always block captures results ─────
        // m_axis_tready=1 throughout: FIFO drains immediately, no overflow.
        // The cap_active always block (above) collects received beats into
        // got_vec[] pre-NBA at the same posedge as the RTL — guaranteed
        // correct read ordering.
        m_axis_tready = 1;
        cap_active    = 1;
        $display("[%0t ns] Region 2: streaming %0d FP32 beats into DUT", $time, N);

        // ── Sender (host → DUT) ───────────────────────────────────────────
        for (int i = 0; i < N; i++) begin
            s_axis_tdata  = in_vec[i];
            s_axis_tvalid = 1;
            s_axis_tlast  = (i == N-1) ? 1'b1 : 1'b0;
            s_axis_tuser  = 0;
            @(posedge clk); while (!s_axis_tready) @(posedge clk);
        end
        s_axis_tvalid = 0;
        s_axis_tlast  = 0;

        // ── Wait for all N results (always block drives recv_count) ───────
        wait (recv_count == N);
        cap_active    = 0;
        m_axis_tready = 0;
        $display("[%0t ns] Region 3: all %0d output beats received", $time, N);

        // ── Compare against independent software reference ─────────────────
        fail_count = 0;
        max_err    = 0.0;
        avg_err    = 0.0;
        worst_idx  = 0;

        for (int i = 0; i < N; i++) begin
            real got_r, exp_r;
            got_r = fp32_to_real(got_vec[i]);
            exp_r = fp32_to_real(exp_vec[i]);
            err_r = got_r - exp_r;
            if (err_r < 0.0) err_r = -err_r;
            avg_err += err_r;
            if (err_r > max_err) begin
                max_err   = err_r;
                worst_idx = i;
            end
            if (err_r > 0.05) fail_count++;
        end
        avg_err /= real'(N);

        $display("");
        $display("=== GELU Co-Simulation Results ===");
        $display("  Kernel    : M1 small-config FFN layer-0, batch=0, token=0");
        $display("  N         : %0d  (d_ff=256, seed=42)", N);
        $display("  Avg error : %f", avg_err);
        $display("  Max error : %f  (index %0d)", max_err, worst_idx);
        $display("  Input[%0d] : 0x%08h  (%f)", worst_idx, in_vec[worst_idx],
                 fp32_to_real(in_vec[worst_idx]));
        $display("  Got[%0d]   : 0x%08h  (%f)", worst_idx, got_vec[worst_idx],
                 fp32_to_real(got_vec[worst_idx]));
        $display("  Exp[%0d]   : 0x%08h  (%f)", worst_idx, exp_vec[worst_idx],
                 fp32_to_real(exp_vec[worst_idx]));
        $display("  Failures  : %0d / %0d  (threshold 0.05)", fail_count, N);
        $display("==================================");
        $display("");

        if (fail_count == 0)
            $display("PASS");
        else
            $display("FAIL: %0d outputs exceeded error threshold 0.05", fail_count);

        $finish;
    end

endmodule
