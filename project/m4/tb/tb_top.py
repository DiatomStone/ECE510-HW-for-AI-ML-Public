"""
tb/tb_top.py — in-loop, timed co-sim of gelu_top (parameterized SIMD pipelines).

The full-model in-loop benchmark tb. It runs the M1 transformer forward pass and
offloads EVERY GELU to the hardware. The DUT is gelu_top, which packs NUM_LANES
(default 32; build at 8 or 1 via GELU_NUM_LANES) IEEE-754 FP32 operands into every
AXI-Stream beat and feeds NUM_LANES gelu_fp32 pipelines in lockstep
(see rtl/interface.sv). Lane count is read from the GELU_NUM_LANES env var.

Why the data path barely changes: cocotbext-axi is a *byte-stream* model. It
segments the payload bytes into beats of (TDATA_WIDTH/8) bytes automatically,
so widening m/s_axis_tdata from 32 to 1024 bits just means 128 bytes (= 32
FP32) move per beat instead of 4 bytes (= 1 FP32). The host still hands the
exact same little-endian FP32 byte buffer to axis_source.write() and gets the
same byte buffer back from the sink. The kernel result is identical; only the
*timing* differs — ~32× fewer beats, so ~32× higher element throughput.

What this testbench adds over the v1 version:
  * NUM_LANES is asserted against the actual DUT bus width at runtime.
  * Last-beat padding is handled: a chunk whose element count is not a multiple
    of NUM_LANES gets zero-padded to a whole beat by cocotbext-axi, so the
    returned frame may carry up to (NUM_LANES-1) extra trailing elements; we
    slice the read-back to the exact chunk size.
  * Throughput metrics and the projected synthesis peak are scaled by NUM_LANES
    (the kernel now retires NUM_LANES results per cycle).

Timing is reported at the synthesized clock period (22 ns / 45.45 MHz).
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
# Parallelization — must match gelu_top NUM_LANES parameter.
# Env-driven so x8 and x32 share this tb (Makefile x8 sets GELU_NUM_LANES=8);
# verified against the real DUT bus width in the test below. Default 32 = x32.
# ---------------------------------------------------------------------------
NUM_LANES = int(os.environ.get("GELU_NUM_LANES", "32"))

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
CHUNK              = 16384   # max elements per AXI-Stream frame (multiple of NUM_LANES)
GELU_THRESHOLD     = 0.05    # per-element accuracy contract for the kernel

assert CHUNK % NUM_LANES == 0, "CHUNK must be a whole number of NUM_LANES-wide beats"


# ---------------------------------------------------------------------------
# hw_gelu — offload one GELU activation tensor to gelu_top over AXI-Stream.
#
# fp64 → fp32 (host), stream through the DUT in CHUNK-sized TLAST frames,
# fp32 → fp64 (host). With a NUM_LANES-wide bus, cocotbext-axi packs NUM_LANES
# FP32 operands per beat automatically; the byte payload is unchanged. The
# read-back is sliced to the exact element count in case the final beat of a
# chunk was zero-padded.
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
        payload = seg.tobytes()                       # little-endian FP32, NUM_LANES/beat

        t0      = get_sim_time('ns')
        recv_co = cocotb.start_soon(axis_sink.recv())  # arm sink before driving input
        await axis_source.write(payload)               # mem → AXI-Stream → DUT
        frame   = await recv_co                        # DUT → AXI-Stream → mem
        t1      = get_sim_time('ns')

        out = np.frombuffer(bytes(frame.tdata), dtype=np.float32)
        n   = seg.size                                 # slice off any padded lanes
        y32[off:off + n] = out[:n]

        acc["lat_ns"] += float(t1 - t0)
        acc["elems"]  += seg.size
        acc["bytes"]  += seg.size * 4 * 2              # in + out
        acc["chunks"] += 1
        acc["beats"]  += -(-seg.size // NUM_LANES)     # ceil-div: beats per chunk

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
    """Full-model in-loop co-sim on the 32-lane DUT: every GELU runs on HW."""

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

    # --- confirm the DUT really is NUM_LANES wide --------------------------
    bus_lanes = len(dut.s_axis_tdata) // 32
    assert bus_lanes == NUM_LANES, (
        f"DUT s_axis_tdata is {len(dut.s_axis_tdata)} bits = {bus_lanes} FP32 lanes, "
        f"but NUM_LANES={NUM_LANES}. Rebuild with gelu_top / matching NUM_LANES.")
    dut._log.info(f"DUT parallelization confirmed: {bus_lanes} lanes "
                  f"({len(dut.s_axis_tdata)}-bit AXI-Stream, {NUM_LANES} FP32/beat)")

    # --- enable the pipeline via AXI-Lite control register -----------------
    dut._log.info("AXI-Lite: writing pipeline_enable=1")
    await axil_master.write(0x00, b'\x01\x00\x00\x00')
    rb = await axil_master.read(0x00, 4)
    assert rb.data == b'\x01\x00\x00\x00', f"AXI-Lite readback failed: {rb.data}"

    # read-only identity register: lane count (interface reg 0x04)
    rl = await axil_master.read(0x04, 4)
    hw_lanes = int.from_bytes(rl.data, "little")
    assert hw_lanes == NUM_LANES, f"NUM_LANES CSR reports {hw_lanes}, expected {NUM_LANES}"

    # --- build the M1 model and the pure-software reference ----------------
    config = {"n_layers": N_LAYERS, "n_heads": N_HEADS}
    params = init_params(VOCAB_SIZE, SEQ_LEN, D_MODEL, N_HEADS, D_FF, N_LAYERS, seed=SEED)
    rng = np.random.default_rng(SEED)
    token_ids = rng.integers(0, VOCAB_SIZE, size=(BATCH_SIZE, SEQ_LEN))

    logits_ref, _ = forward(token_ids, params, config)     # all-software reference

    # --- in-loop forward: same structure as transformer.forward(), GELU on HW
    acc = {"elems": 0, "lat_ns": 0.0, "bytes": 0, "chunks": 0, "beats": 0,
           "conv_us": 0.0, "gelu_max_err": 0.0, "gelu_fail": 0}
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
                      f"in {-(-h.size // CHUNK)} chunk(s) of <= {CHUNK} "
                      f"({-(-h.size // NUM_LANES)} beats @ {NUM_LANES} lanes)")
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
    cyc_per_beat = (acc["lat_ns"] / CLK_NS) / acc["beats"]
    bw_total     = acc["bytes"] / lat_s / 1e6
    bw_dir       = (acc["bytes"] / 2) / lat_s / 1e6

    # NUM_LANES results retired per cycle at full rate.
    proj_elem_per_s = F_CLK_HZ * NUM_LANES
    proj_ops_per_s  = F_CLK_HZ * ARITH_OPS_PER_ELEM * NUM_LANES

    dut._log.info("\n=== Full-Model In-Loop GELU Co-Sim (v2, parallel) — Timing & Metrics ===")
    dut._log.info(f"  Model              : M1 transformer, {N_LAYERS} layers, "
                  f"B={BATCH_SIZE} T={SEQ_LEN} d_ff={D_FF} (seed={SEED})")
    dut._log.info(f"  Parallelization    : {NUM_LANES} lanes "
                  f"({NUM_LANES*32}-bit AXI-Stream, {NUM_LANES} FP32/beat)")
    dut._log.info(f"  GELU offloads      : {n_gelu} (one per layer FFN)")
    dut._log.info(f"  Elements streamed  : {elems}  in {acc['chunks']} AXI frames "
                  f"({acc['beats']} beats)")
    dut._log.info(f"  Clock (synth)      : {CLK_NS:.0f} ns  ({F_CLK_HZ/1e6:.2f} MHz)")
    dut._log.info("  --- MEASURED (cycle-accurate Icarus) ---")
    dut._log.info(f"  HW streaming time  : {acc['lat_ns']:.0f} ns "
                  f"(~{acc['lat_ns']/CLK_NS:.0f} cycles)")
    dut._log.info(f"  Throughput         : {elem_per_s/1e6:.2f} M elem/s  "
                  f"({cyc_per_elem:.4f} cycles/elem, {cyc_per_beat:.3f} cycles/beat)")
    dut._log.info(f"  AXI bandwidth/dir  : {bw_dir:.1f} MB/s (in, and out)")
    dut._log.info(f"  AXI bandwidth total: {bw_total:.1f} MB/s (in+out)")
    dut._log.info("  --- PROJECTED PEAK (synthesis × lanes × ops/cycle) ---")
    dut._log.info(f"  Peak throughput    : {proj_elem_per_s/1e6:.2f} M elem/s  "
                  f"({NUM_LANES} results/cycle @ {CLK_NS:.0f} ns)")
    dut._log.info(f"  Peak int-arith     : {proj_ops_per_s/1e6:.1f} M op/s  "
                  f"({ARITH_OPS_PER_ELEM} ops/elem × {NUM_LANES} lanes)")
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
