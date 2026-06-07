"""
tb/tb_top_inloop_dma.py — in-loop, full-model co-sim of gelu_dma_top
(the DMA-incorporated path: mm2s_buffer + kernel + s2mm_buffer).

This is the same in-loop transformer experiment as tb_top_inloop.py, but one
level UP: instead of streaming FP32 operands straight into gelu_top over an
AXI4-Stream VIP, every GELU activation is offloaded through the full DMA path —

      host (fp64→fp32)
        → AXI4-MM write burst  → mm2s_buffer (input SRAM FIFO)
        → AXI4-Stream          → gelu_top kernel (fp32 GELU)
        → AXI4-Stream          → s2mm_buffer (output SRAM FIFO)
        → AXI4-MM read burst   → host (fp32→fp64)

So the data crosses the same AXI4-MM burst interface a real DMA engine would
drive (dma_in_* write channel, dma_out_* read channel), exercising the buffers,
the stream_enable gate, and per-burst framing — not just the kernel.

DUT: gelu_dma_top (rtl/DMA_memory/gelu_dma_top.sv) wrapping mm2s_buffer + gelu_top +
s2mm_buffer. In simulation the buffers use the behavioral openram_1k_wrap model
(no SRAM macro / SYNTHESIS define needed).

Buffer depth is 1024 words, so each GELU tensor is streamed in CHUNK-sized
DMA bursts (CHUNK ≤ 1024). The pure-software transformer.forward() output is
the reference; final logits and per-layer GELU accuracy are checked.

The DMA burst helpers (ReadOnly-phase handshake sampling) are adapted from
tb/wip/tb_gelu_dma_top.py; the model loop is adapted from tb/tb_top_inloop.py.
"""

import os
import sys
import time

import numpy as np
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ReadOnly
from cocotb.utils import get_sim_time
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
# M1 small config (matches tb_top_inloop.py)
# ---------------------------------------------------------------------------
VOCAB_SIZE = 64
SEQ_LEN    = 64
D_MODEL    = 64
N_HEADS    = 4
D_FF       = 256
N_LAYERS   = 2
BATCH_SIZE = 8
SEED       = 42

ARITH_OPS_PER_ELEM = 17
# DMA burst size in beats. Capped at 256 by AXI4: AWLEN/ARLEN are 8-bit, so a
# single burst is at most 256 beats (beats = AxLEN + 1). Also <= buffer depth (1024).
CHUNK              = 256
GELU_THRESHOLD     = 0.05

assert CHUNK <= 256,  "CHUNK exceeds the AXI4 max burst length (AxLEN is 8-bit)"
assert CHUNK <= 1024, "CHUNK must fit in the 1024-deep mm2s/s2mm buffers"


# ---------------------------------------------------------------------------
# DMA burst helpers — AXI4-MM write (dma_in_*) and read (dma_out_*)
# Handshake signals are sampled in the ReadOnly phase to avoid pre-NBA stale
# reads (see tb/wip/tb_gelu_dma_top.py for the detailed rationale).
# ---------------------------------------------------------------------------
async def init_dut(dut):
    dut.stream_enable.value   = 0
    dut.dma_in_awaddr.value   = 0
    dut.dma_in_awlen.value    = 0
    dut.dma_in_awvalid.value  = 0
    dut.dma_in_wdata.value    = 0
    dut.dma_in_wstrb.value    = 0xF
    dut.dma_in_wlast.value    = 0
    dut.dma_in_wvalid.value   = 0
    dut.dma_in_bready.value   = 0
    dut.dma_out_araddr.value  = 0
    dut.dma_out_arlen.value   = 0
    dut.dma_out_arvalid.value = 0
    dut.dma_out_rready.value  = 0


async def reset_dut(dut):
    dut.rst.value = 1
    await Timer(int(CLK_NS * 5), unit="ns")
    dut.rst.value = 0
    await Timer(int(CLK_NS * 2), unit="ns")
    await RisingEdge(dut.clk)


async def dma_write_burst(dut, data_words):
    """Burst-write a list of 32-bit words into the mm2s input buffer."""
    n = len(data_words)

    dut.dma_in_awaddr.value  = 0
    dut.dma_in_awlen.value   = n - 1
    dut.dma_in_awvalid.value = 1
    await ReadOnly()
    while not dut.dma_in_awready.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.dma_in_awvalid.value = 0

    for i, data in enumerate(data_words):
        dut.dma_in_wdata.value  = int(data)
        dut.dma_in_wstrb.value  = 0xF
        dut.dma_in_wlast.value  = 1 if i == n - 1 else 0
        dut.dma_in_wvalid.value = 1
        await ReadOnly()
        while not dut.dma_in_wready.value:
            await RisingEdge(dut.clk)
            await ReadOnly()
        await RisingEdge(dut.clk)
    dut.dma_in_wvalid.value = 0
    dut.dma_in_wlast.value  = 0

    dut.dma_in_bready.value = 1
    await ReadOnly()
    while not dut.dma_in_bvalid.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.dma_in_bready.value = 0


async def dma_read_burst(dut, n_beats):
    """Burst-read n_beats 32-bit words from the s2mm output buffer.

    Tolerant of slow-arriving beats: rvalid stalls mid-burst until the kernel
    produces the next result, so as long as stream_enable stays asserted the
    loop simply waits and drains all n_beats."""
    data_out = []

    dut.dma_out_araddr.value  = 0
    dut.dma_out_arlen.value   = n_beats - 1
    dut.dma_out_arvalid.value = 1
    await ReadOnly()
    while not dut.dma_out_arready.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.dma_out_arvalid.value = 0

    dut.dma_out_rready.value = 1
    while len(data_out) < n_beats:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if dut.dma_out_rvalid.value:
            data_out.append(int(dut.dma_out_rdata.value))
            last = bool(dut.dma_out_rlast.value)
            await RisingEdge(dut.clk)
            if last:
                break
        else:
            pass
    dut.dma_out_rready.value = 0
    return data_out


# ---------------------------------------------------------------------------
# hw_gelu_dma — offload one GELU tensor through the full DMA path.
#
# fp64 → fp32 (host), then per CHUNK: DMA-write the chunk into mm2s, assert
# stream_enable so it flows through the kernel into s2mm, DMA-read the chunk
# back, fp32 → fp64 (host). Accumulates element/byte/time stats into `acc`.
# ---------------------------------------------------------------------------
async def hw_gelu_dma(dut, x_fp64, acc):
    shape = x_fp64.shape
    flat  = np.asarray(x_fp64, dtype=np.float64).reshape(-1)
    N     = flat.size

    tc0 = time.perf_counter()
    x32 = flat.astype(np.float32)
    acc["conv_us"] += (time.perf_counter() - tc0) * 1e6

    y32 = np.empty(N, dtype=np.float32)

    for off in range(0, N, CHUNK):
        seg      = x32[off:off + CHUNK]
        in_words = seg.view(np.uint32).tolist()    # IEEE-754 FP32 bit patterns

        t0 = get_sim_time('ns')
        await dma_write_burst(dut, in_words)        # host → AXI-MM → mm2s
        dut.stream_enable.value = 1                 # mm2s → kernel → s2mm
        results = await dma_read_burst(dut, seg.size)  # s2mm → AXI-MM → host
        dut.stream_enable.value = 0
        t1 = get_sim_time('ns')

        out = np.array(results, dtype=np.uint32).view(np.float32)
        y32[off:off + seg.size] = out[:seg.size]

        acc["lat_ns"] += float(t1 - t0)
        acc["elems"]  += seg.size
        acc["bytes"]  += seg.size * 4 * 2
        acc["chunks"] += 1

    tc1 = time.perf_counter()
    y64 = y32.astype(np.float64)
    acc["conv_us"] += (time.perf_counter() - tc1) * 1e6

    return y64.reshape(shape)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_gelu_dma_inloop(dut):
    """Full-model in-loop co-sim: every GELU runs through the DMA + kernel path."""

    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    # --- enable kernel pipeline via AXI-Lite control register --------------
    axil = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)
    dut._log.info("AXI-Lite: writing pipeline_enable=1")
    await axil.write(0x00, b'\x01\x00\x00\x00')
    rb = await axil.read(0x00, 4)
    assert rb.data == b'\x01\x00\x00\x00', f"pipeline_enable readback failed: {rb.data}"

    # --- build the M1 model and the pure-software reference ----------------
    config = {"n_layers": N_LAYERS, "n_heads": N_HEADS}
    params = init_params(VOCAB_SIZE, SEQ_LEN, D_MODEL, N_HEADS, D_FF, N_LAYERS, seed=SEED)
    rng = np.random.default_rng(SEED)
    token_ids = rng.integers(0, VOCAB_SIZE, size=(BATCH_SIZE, SEQ_LEN))

    logits_ref, _ = forward(token_ids, params, config)

    acc = {"elems": 0, "lat_ns": 0.0, "bytes": 0, "chunks": 0, "conv_us": 0.0,
           "gelu_max_err": 0.0, "gelu_fail": 0}
    n_gelu = 0

    B, T = token_ids.shape
    x = params["tok_emb"][token_ids] + params["pos_emb"][:T, :]

    for l in range(N_LAYERS):
        p = f"l{l}"

        xn, _ = layer_norm_forward(x, params[f"{p}_ln1_g"], params[f"{p}_ln1_b"])
        attn_out, _ = mha_forward(
            xn,
            params[f"{p}_Wq"], params[f"{p}_Wk"], params[f"{p}_Wv"], params[f"{p}_Wo"],
            params[f"{p}_bq"], params[f"{p}_bk"], params[f"{p}_bv"], params[f"{p}_bo"],
            N_HEADS,
        )
        x = x + attn_out

        xn2, _ = layer_norm_forward(x, params[f"{p}_ln2_g"], params[f"{p}_ln2_b"])
        h = xn2 @ params[f"{p}_W1"] + params[f"{p}_b1"]    # (B, T, D_FF) fp64

        dut._log.info(f"Layer {l}: offloading GELU via DMA — {h.size} elements "
                      f"in {-(-h.size // CHUNK)} DMA burst(s) of <= {CHUNK}")
        h_act = await hw_gelu_dma(dut, h, acc)
        n_gelu += 1

        ref_act = gelu(h.astype(np.float32).astype(np.float64))
        err = np.abs(h_act - ref_act)
        acc["gelu_max_err"] = max(acc["gelu_max_err"], float(err.max()))
        acc["gelu_fail"]   += int((err > GELU_THRESHOLD).sum())

        ff_out = h_act @ params[f"{p}_W2"] + params[f"{p}_b2"]
        x = x + ff_out

    x_final, _ = layer_norm_forward(x, params["ln_f_g"], params["ln_f_b"])
    logits_hw = x_final @ params["W_out"] + params["b_out"]

    # --- loop-closure check ------------------------------------------------
    logit_err     = np.abs(logits_hw - logits_ref)
    logit_max_err = float(logit_err.max())
    logit_avg_err = float(logit_err.mean())
    same_argmax = int((logits_hw.argmax(axis=-1) == logits_ref.argmax(axis=-1)).sum())
    total_pos   = logits_ref.shape[0] * logits_ref.shape[1]

    # --- aggregate metrics (full DMA round-trip) ---------------------------
    lat_s        = acc["lat_ns"] * 1e-9
    elems        = acc["elems"]
    elem_per_s   = elems / lat_s
    cyc_per_elem = (acc["lat_ns"] / CLK_NS) / elems
    bw_total     = acc["bytes"] / lat_s / 1e6
    bw_dir       = (acc["bytes"] / 2) / lat_s / 1e6

    dut._log.info("\n=== Full-Model In-Loop GELU Co-Sim (DMA path) — Timing & Metrics ===")
    dut._log.info(f"  Model              : M1 transformer, {N_LAYERS} layers, "
                  f"B={BATCH_SIZE} T={SEQ_LEN} d_ff={D_FF} (seed={SEED})")
    dut._log.info(f"  Path               : AXI-MM DMA → mm2s → kernel → s2mm → AXI-MM DMA")
    dut._log.info(f"  GELU offloads      : {n_gelu} (one per layer FFN)")
    dut._log.info(f"  Elements streamed  : {elems}  in {acc['chunks']} DMA bursts of <= {CHUNK}")
    dut._log.info(f"  Clock (synth)      : {CLK_NS:.0f} ns  ({F_CLK_HZ/1e6:.2f} MHz)")
    dut._log.info("  --- MEASURED (cycle-accurate Icarus, full DMA round-trip) ---")
    dut._log.info(f"  DMA round-trip time: {acc['lat_ns']:.0f} ns "
                  f"(~{acc['lat_ns']/CLK_NS:.0f} cycles incl. write+compute+read)")
    dut._log.info(f"  Throughput         : {elem_per_s/1e6:.2f} M elem/s  "
                  f"({cyc_per_elem:.3f} cycles/elem)")
    dut._log.info(f"  AXI bandwidth/dir  : {bw_dir:.1f} MB/s (in, and out)")
    dut._log.info(f"  AXI bandwidth total: {bw_total:.1f} MB/s (in+out)")
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
        assert False, "In-loop full-model DMA simulation failed kernel accuracy threshold."
