"""
tb/tb_top_inloop.py — in-loop, timed, full-model co-simulation of gelu_top.

This runs the M1 transformer forward pass and offloads EVERY GELU to the
hardware. It inlines transformer.py's own forward() structure (the same
sequence forward() executes) using transformer.py's real functions and
weights — layer_norm_forward, mha_forward, and the trained params — for the
whole model (all layers, final layer-norm, output projection). The only
substitution is the activation: where software does

      h_act = gelu(h)                         (transformer.ff_forward)

this testbench does, at every layer's FFN:

      h32   = h.astype(fp32)                  fp64 → fp32      (host)
      h_act = [ AXI-Stream → gelu_top → AXI-Stream ].astype(fp64)   fp32 → fp64
      ff    = h_act @ W2 + b2                 loop continues   (fp64)

so the hardware result flows back through W2, the residual, and into the next
layer — the loop is fully closed. The final logits are compared against the
pure-software transformer.forward() reference.

Why the forward() body is inlined instead of called directly: transformer.py's
forward()/ff_forward() are synchronous numpy, but driving gelu_top requires
awaiting clock edges inside a cocotb coroutine. You cannot await from inside a
synchronous function, so the forward path is reproduced here as a coroutine
that calls the real transformer.py building blocks and awaits hw_gelu at the
activation. transformer.py itself is unmodified.

Streaming model (see interface.sv): gelu_top is a pure AXI-Stream kernel with
no addressable on-chip memory — only a 16-deep output FIFO with backpressure.
It cannot absorb a large block transfer, so the full GELU tensor
(B·T·d_ff = 131,072 elements per layer) is streamed in chunks of CHUNK
elements, each a TLAST-framed AXI packet, drained live.

Timing is reported at the synthesized clock period (22 ns / 45.45 MHz) so the
throughput and effective AXI bandwidth reflect real silicon. MEASURED numbers
are cycle-accurate (Icarus); a synthesis-based projected peak is printed
alongside, clearly labeled.
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
    init_params, layer_norm_forward, mha_forward, gelu, forward,
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

ARITH_OPS_PER_ELEM = 17     # from core_kernel/int_op_count.md (1 MUL, no DIV)
CHUNK              = 16384   # max elements per AXI-Stream frame (stream-size budget)
GELU_THRESHOLD     = 0.05    # per-element accuracy contract for the kernel


# ---------------------------------------------------------------------------
# hw_gelu — offload one GELU activation tensor to gelu_top over AXI-Stream.
#
# fp64 → fp32 (host), stream through the DUT in CHUNK-sized TLAST frames,
# fp32 → fp64 (host). Accumulates streamed-element count, sim-time streaming
# latency, and bytes into `acc` so the caller can report aggregate throughput
# and bandwidth across every GELU call in the model.
# ---------------------------------------------------------------------------
async def hw_gelu(dut, axis_source, axis_sink, x_fp64, acc):
    shape = x_fp64.shape
    flat  = np.asarray(x_fp64, dtype=np.float64).reshape(-1)
    N     = flat.size

    # --- software fp64 → fp32 (host-side conversion) -----------------------
    tc0 = time.perf_counter()
    x32 = flat.astype(np.float32)
    acc["conv_us"] += (time.perf_counter() - tc0) * 1e6

    y32 = np.empty(N, dtype=np.float32)

    # --- stream in chunks, timing the hardware-busy window -----------------
    for off in range(0, N, CHUNK):
        seg     = x32[off:off + CHUNK]
        payload = seg.tobytes()                       # little-endian FP32, one/beat

        t0      = get_sim_time('ns')
        recv_co = cocotb.start_soon(axis_sink.recv())  # arm sink before driving input
        await axis_source.write(payload)               # mem → AXI-Stream → DUT
        frame   = await recv_co                        # DUT → AXI-Stream → mem
        t1      = get_sim_time('ns')

        out = np.frombuffer(bytes(frame.tdata), dtype=np.float32)
        y32[off:off + out.size] = out

        acc["lat_ns"] += float(t1 - t0)
        acc["elems"]  += seg.size
        acc["bytes"]  += seg.size * 4 * 2              # in + out
        acc["chunks"] += 1

    # --- software fp32 → fp64 (host-side conversion) -----------------------
    tc1 = time.perf_counter()
    y64 = y32.astype(np.float64)
    acc["conv_us"] += (time.perf_counter() - tc1) * 1e6

    return y64.reshape(shape)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_gelu_top_inloop(dut):
    """Full-model in-loop co-sim: every GELU in transformer.forward() runs on HW."""

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

    # --- build the M1 model and the pure-software reference ----------------
    config = {"n_layers": N_LAYERS, "n_heads": N_HEADS}
    params = init_params(VOCAB_SIZE, SEQ_LEN, D_MODEL, N_HEADS, D_FF, N_LAYERS, seed=SEED)
    rng = np.random.default_rng(SEED)
    token_ids = rng.integers(0, VOCAB_SIZE, size=(BATCH_SIZE, SEQ_LEN))

    logits_ref, _ = forward(token_ids, params, config)     # all-software reference

    # --- in-loop forward: same structure as transformer.forward(), GELU on HW
    acc = {"elems": 0, "lat_ns": 0.0, "bytes": 0, "chunks": 0, "conv_us": 0.0,
           "gelu_max_err": 0.0, "gelu_fail": 0}
    n_gelu = 0

    B, T = token_ids.shape
    x = params["tok_emb"][token_ids] + params["pos_emb"][:T, :]

    for l in range(N_LAYERS):
        p = f"l{l}"

        # pre-norm attention (real transformer.py functions)
        xn, _ = layer_norm_forward(x, params[f"{p}_ln1_g"], params[f"{p}_ln1_b"])
        attn_out, _ = mha_forward(
            xn,
            params[f"{p}_Wq"], params[f"{p}_Wk"], params[f"{p}_Wv"], params[f"{p}_Wo"],
            params[f"{p}_bq"], params[f"{p}_bk"], params[f"{p}_bv"], params[f"{p}_bo"],
            N_HEADS,
        )
        x = x + attn_out

        # pre-norm feed-forward — GELU offloaded to hardware
        xn2, _ = layer_norm_forward(x, params[f"{p}_ln2_g"], params[f"{p}_ln2_b"])
        h = xn2 @ params[f"{p}_W1"] + params[f"{p}_b1"]    # (B, T, D_FF) fp64

        dut._log.info(f"Layer {l}: offloading GELU — {h.size} elements "
                      f"in {-(-h.size // CHUNK)} chunk(s) of <= {CHUNK}")
        h_act = await hw_gelu(dut, axis_source, axis_sink, h, acc)
        n_gelu += 1

        # per-layer kernel accuracy vs fp64 GELU of the fp32-quantised input
        ref_act = gelu(h.astype(np.float32).astype(np.float64))
        err = np.abs(h_act - ref_act)
        acc["gelu_max_err"] = max(acc["gelu_max_err"], float(err.max()))
        acc["gelu_fail"]   += int((err > GELU_THRESHOLD).sum())

        ff_out = h_act @ params[f"{p}_W2"] + params[f"{p}_b2"]
        x = x + ff_out

    x_final, _ = layer_norm_forward(x, params["ln_f_g"], params["ln_f_b"])
    logits_hw = x_final @ params["W_out"] + params["b_out"]

    # --- end-to-end loop-closure check (informational) ---------------------
    logit_err     = np.abs(logits_hw - logits_ref)
    logit_max_err = float(logit_err.max())
    logit_avg_err = float(logit_err.mean())
    # argmax agreement: does HW-in-the-loop pick the same next token as software?
    same_argmax = int((logits_hw.argmax(axis=-1) == logits_ref.argmax(axis=-1)).sum())
    total_pos   = logits_ref.shape[0] * logits_ref.shape[1]

    # --- aggregate metrics -------------------------------------------------
    lat_s   = acc["lat_ns"] * 1e-9
    elems   = acc["elems"]
    elem_per_s   = elems / lat_s
    cyc_per_elem = (acc["lat_ns"] / CLK_NS) / elems
    bw_total     = acc["bytes"] / lat_s / 1e6
    bw_dir       = (acc["bytes"] / 2) / lat_s / 1e6

    proj_elem_per_s = F_CLK_HZ * 1.0
    proj_ops_per_s  = F_CLK_HZ * ARITH_OPS_PER_ELEM

    dut._log.info("\n=== Full-Model In-Loop GELU Co-Sim — Timing & Metrics ===")
    dut._log.info(f"  Model              : M1 transformer, {N_LAYERS} layers, "
                  f"B={BATCH_SIZE} T={SEQ_LEN} d_ff={D_FF} (seed={SEED})")
    dut._log.info(f"  GELU offloads      : {n_gelu} (one per layer FFN)")
    dut._log.info(f"  Elements streamed  : {elems}  in {acc['chunks']} AXI frames")
    dut._log.info(f"  Clock (synth)      : {CLK_NS:.0f} ns  ({F_CLK_HZ/1e6:.2f} MHz)")
    dut._log.info("  --- MEASURED (cycle-accurate Icarus) ---")
    dut._log.info(f"  HW streaming time  : {acc['lat_ns']:.0f} ns "
                  f"(~{acc['lat_ns']/CLK_NS:.0f} cycles)")
    dut._log.info(f"  Throughput         : {elem_per_s/1e6:.2f} M elem/s  "
                  f"({cyc_per_elem:.3f} cycles/elem)")
    dut._log.info(f"  AXI bandwidth/dir  : {bw_dir:.1f} MB/s (in, and out)")
    dut._log.info(f"  AXI bandwidth total: {bw_total:.1f} MB/s (in+out)")
    dut._log.info("  --- PROJECTED PEAK (synthesis × ops/cycle) ---")
    dut._log.info(f"  Peak throughput    : {proj_elem_per_s/1e6:.2f} M elem/s  (1 result/cycle @ {CLK_NS:.0f} ns)")
    dut._log.info(f"  Peak int-arith     : {proj_ops_per_s/1e6:.1f} M op/s  ({ARITH_OPS_PER_ELEM} ops/elem)")
    dut._log.info("  --- HOST-SIDE CONVERSION (informational, not kernel time) ---")
    dut._log.info(f"  fp64<->fp32 casts  : {acc['conv_us']:.1f} us total (host, both directions)")
    dut._log.info("  --- KERNEL ACCURACY (per-element, all layers) ---")
    dut._log.info(f"  GELU max error     : {acc['gelu_max_err']:f}")
    dut._log.info(f"  GELU failures      : {acc['gelu_fail']} / {elems}  (threshold {GELU_THRESHOLD})")
    dut._log.info("  --- LOOP CLOSURE: final logits vs all-software forward() ---")
    dut._log.info(f"  Logits avg / max   : {logit_avg_err:f} / {logit_max_err:f}")
    dut._log.info(f"  Next-token argmax  : {same_argmax}/{total_pos} positions match software")
    dut._log.info("=========================================================\n")

    if acc["gelu_fail"] == 0:
        print("PASS")
        dut._log.info("PASS")
    else:
        print(f"FAIL: {acc['gelu_fail']} GELU outputs exceeded error threshold {GELU_THRESHOLD}")
        assert False, "In-loop full-model simulation failed kernel accuracy threshold."
