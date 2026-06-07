"""
tb/tb_top_inloop.py — in-loop, timed co-simulation of gelu_top.

Unlike tb_top.py (which replays pre-baked vectors from gen_vectors.py), this
testbench runs the M1 transformer forward pass *live* and, at the GELU point
inside the FFN, hands the activation tensor to the hardware over the AXI path:

      software forward pass  (fp64)
         │   h = xn2 @ W1 + b1                     (FFN pre-activation, fp64)
         │
         ▼   fp64 → fp32         ┌──── hw_gelu() ────────────────────────┐
      h32 = h.astype(fp32) ─────►│  AXI-Stream → gelu_top → AXI-Stream   │
                                 │  (one FP32 per beat, drained live)    │
      h_act = y.astype(fp64) ◄───│  fp32 result ── fp32 → fp64           │
         │                       └───────────────────────────────────────┘
         ▼
      out = h_act @ W2 + b2      (forward pass continues, fp64)

The GELU round-trip is timed at the synthesized clock period (22 ns / 45.45 MHz)
so the reported throughput and effective AXI bandwidth reflect real silicon, not
the testbench's convenience clock. Numbers here are MEASURED (cycle-accurate
Icarus simulation), with a synthesis-based projected peak printed alongside as a
cross-check.

Scope note (see interface.sv): gelu_top is a pure AXI-Stream kernel with no
addressable on-chip memory — only a 16-deep output FIFO with backpressure. It
cannot absorb a large block transfer; it processes a continuously-drained
stream. This run uses one representative 256-element token row (the M1-defended
FFN kernel width: d_ff=256, batch=0, token=0), which fits the stream comfortably.
"""

import os
import sys
import time

import numpy as np
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb.utils import get_sim_time
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

# Make the M1 software model importable (silence @profile if line_profiler absent)
import builtins
builtins.profile = lambda f: f
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'orginal_software'))
from transformer import (                                   # noqa: E402
    init_params, layer_norm_forward, mha_forward, gelu,
)

# ---------------------------------------------------------------------------
# Synthesized timing — report metrics at the clock that closed timing in M3.
# ---------------------------------------------------------------------------
CLK_NS   = 22.0                  # synthesized clock period (OpenLane 2, sky130A)
F_CLK_HZ = 1.0 / (CLK_NS * 1e-9) # 45.45 MHz

# ---------------------------------------------------------------------------
# M1 small config (matches gen_vectors.py / sw_baseline.md)
# ---------------------------------------------------------------------------
VOCAB_SIZE = 64
SEQ_LEN    = 64
D_MODEL    = 64
N_HEADS    = 4
D_FF       = 256        # ← kernel width defended in M1
N_LAYERS   = 2
BATCH_SIZE = 8
SEED       = 42

ARITH_OPS_PER_ELEM = 17   # from core_kernel/int_op_count.md (1 MUL, no DIV)


# ---------------------------------------------------------------------------
# Software: produce the FFN layer-0 pre-activation tensor h (fp64), the data
# that reaches the GELU point. Mirrors gen_vectors.py but keeps the full tensor.
# ---------------------------------------------------------------------------
def ffn_pre_activation():
    params = init_params(VOCAB_SIZE, SEQ_LEN, D_MODEL, N_HEADS, D_FF, N_LAYERS, seed=SEED)
    rng = np.random.default_rng(SEED)
    token_ids = rng.integers(0, VOCAB_SIZE, size=(BATCH_SIZE, SEQ_LEN))

    x = params["tok_emb"][token_ids] + params["pos_emb"][:SEQ_LEN, :]
    xn, _ = layer_norm_forward(x, params["l0_ln1_g"], params["l0_ln1_b"])
    attn_out, _ = mha_forward(
        xn,
        params["l0_Wq"], params["l0_Wk"], params["l0_Wv"], params["l0_Wo"],
        params["l0_bq"], params["l0_bk"], params["l0_bv"], params["l0_bo"],
        N_HEADS,
    )
    x = x + attn_out
    xn2, _ = layer_norm_forward(x, params["l0_ln2_g"], params["l0_ln2_b"])
    h = xn2 @ params["l0_W1"] + params["l0_b1"]   # (B, T, D_FF), fp64
    return h


# ---------------------------------------------------------------------------
# hw_gelu — offload one GELU activation tensor to gelu_top over AXI-Stream.
#
# Performs the fp64→fp32 cast (host), streams the FP32 values through the DUT,
# receives the FP32 results, casts fp32→fp64 (host), and returns the fp64
# result so the software forward pass can continue. Returns (y_fp64, metrics).
#
# The stream round-trip is timed in simulation ns and converted to the
# synthesized 22 ns clock domain for the reported throughput / bandwidth.
# ---------------------------------------------------------------------------
async def hw_gelu(dut, axis_source, axis_sink, x_fp64):
    shape = x_fp64.shape
    flat  = np.asarray(x_fp64).reshape(-1)
    N     = flat.size

    # --- software fp64 → fp32 (counted as host-side conversion overhead) ---
    t_c0    = time.perf_counter()
    x32     = flat.astype(np.float32)
    t_c1    = time.perf_counter()
    payload = x32.tobytes()                       # little-endian FP32, one per beat

    # --- stream through the hardware, timed in sim-ns ----------------------
    t0       = get_sim_time('ns')
    recv_co  = cocotb.start_soon(axis_sink.recv())   # arm sink before driving input
    await axis_source.write(payload)                 # memory → AXI-Stream → DUT
    frame    = await recv_co                          # DUT → AXI-Stream → memory
    t1       = get_sim_time('ns')
    latency_ns = float(t1 - t0)

    out_bytes = bytes(frame.tdata)
    y32 = np.frombuffer(out_bytes, dtype=np.float32).copy()

    # --- software fp32 → fp64 (counted as host-side conversion overhead) ---
    t_c2 = time.perf_counter()
    y64  = y32.astype(np.float64)
    t_c3 = time.perf_counter()

    # --- metrics -----------------------------------------------------------
    cycles      = latency_ns / CLK_NS
    latency_s   = latency_ns * 1e-9
    bytes_in    = N * 4
    bytes_out   = len(out_bytes)
    metrics = {
        "N":            N,
        "latency_ns":   latency_ns,
        "cycles":       cycles,
        "elem_per_s":   N / latency_s,
        "results_per_s": len(y32) / latency_s,
        "bw_in_MBps":   bytes_in  / latency_s / 1e6,
        "bw_out_MBps":  bytes_out / latency_s / 1e6,
        "bw_total_MBps": (bytes_in + bytes_out) / latency_s / 1e6,
        "sw_fp64_to_fp32_us": (t_c1 - t_c0) * 1e6,
        "sw_fp32_to_fp64_us": (t_c3 - t_c2) * 1e6,
    }
    return y64.reshape(shape), metrics


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_gelu_top_inloop(dut):
    """In-loop timed co-simulation: software forward pass offloads GELU to HW."""

    # --- clock at the synthesized period, reset ----------------------------
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    dut.rst.value = 1
    await Timer(int(CLK_NS * 5), unit="ns")
    dut.rst.value = 0
    await Timer(int(CLK_NS * 5), unit="ns")
    await RisingEdge(dut.clk)

    # --- AXI VIPs ----------------------------------------------------------
    axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)
    axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
    axis_sink   = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

    # --- enable the pipeline via AXI-Lite control register -----------------
    dut._log.info("AXI-Lite: writing pipeline_enable=1")
    await axil_master.write(0x00, b'\x01\x00\x00\x00')
    rb = await axil_master.read(0x00, 4)
    assert rb.data == b'\x01\x00\x00\x00', f"AXI-Lite readback failed: {rb.data}"

    # --- software forward pass up to the GELU point ------------------------
    h_full = ffn_pre_activation()              # (B, T, D_FF) fp64
    h_row  = h_full[0, 0, :]                    # batch=0, token=0 → (256,) fp64
    N      = h_row.size

    dut._log.info(f"In-loop GELU offload: streaming one {N}-element token row "
                  f"(M1 FFN layer-0, batch=0, token=0)")

    # --- offload GELU to hardware (the in-loop step) -----------------------
    y_hw, m = await hw_gelu(dut, axis_source, axis_sink, h_row)

    # --- independent software reference (fp64 GELU on the same fp32 input) --
    # Match what the hardware actually sees: GELU of the fp32-quantised input.
    ref = gelu(h_row.astype(np.float32).astype(np.float64))

    err       = np.abs(y_hw - ref)
    avg_err   = float(err.mean())
    max_err   = float(err.max())
    worst_idx = int(err.argmax())
    fail_cnt  = int((err > 0.05).sum())

    # --- projected peak (synthesis cross-check, LABELED as projected) ------
    proj_elem_per_s = F_CLK_HZ * 1.0                     # 1 result / cycle
    proj_ops_per_s  = F_CLK_HZ * ARITH_OPS_PER_ELEM      # useful int-arith ops/cycle

    dut._log.info("\n=== In-Loop GELU Co-Simulation — Timing & Metrics ===")
    dut._log.info(f"  Kernel             : M1 FFN layer-0, batch=0, token=0 (d_ff={N})")
    dut._log.info(f"  Clock (synth)      : {CLK_NS:.0f} ns  ({F_CLK_HZ/1e6:.2f} MHz)")
    dut._log.info("  --- MEASURED (cycle-accurate Icarus) ---")
    dut._log.info(f"  Round-trip latency : {m['latency_ns']:.1f} ns  (~{m['cycles']:.0f} cycles for {N} elems)")
    dut._log.info(f"  Throughput         : {m['elem_per_s']/1e6:.2f} M elem/s  "
                  f"({m['cycles']/N:.2f} cycles/elem)")
    dut._log.info(f"  AXI bandwidth  in  : {m['bw_in_MBps']:.1f} MB/s")
    dut._log.info(f"  AXI bandwidth  out : {m['bw_out_MBps']:.1f} MB/s")
    dut._log.info(f"  AXI bandwidth total: {m['bw_total_MBps']:.1f} MB/s (in+out)")
    dut._log.info("  --- PROJECTED PEAK (synthesis × ops/cycle) ---")
    dut._log.info(f"  Peak throughput    : {proj_elem_per_s/1e6:.2f} M elem/s  (1 result/cycle @ {CLK_NS:.0f} ns)")
    dut._log.info(f"  Peak int-arith     : {proj_ops_per_s/1e6:.1f} M op/s  ({ARITH_OPS_PER_ELEM} ops/elem)")
    dut._log.info("  --- HOST-SIDE CONVERSION (informational, not kernel time) ---")
    dut._log.info(f"  fp64 → fp32 cast   : {m['sw_fp64_to_fp32_us']:.2f} us (host)")
    dut._log.info(f"  fp32 → fp64 cast   : {m['sw_fp32_to_fp64_us']:.2f} us (host)")
    dut._log.info("  --- ACCURACY vs fp64 software GELU ---")
    dut._log.info(f"  Avg error          : {avg_err:f}")
    dut._log.info(f"  Max error          : {max_err:f}  (index {worst_idx})")
    dut._log.info(f"  Failures           : {fail_cnt} / {N}  (threshold 0.05)")
    dut._log.info("=====================================================\n")

    if fail_cnt == 0:
        print("PASS")
        dut._log.info("PASS")
    else:
        print(f"FAIL: {fail_cnt} outputs exceeded error threshold 0.05")
        assert False, "In-loop simulation failed accuracy threshold."
