"""
tb/tb_top_inloop_dma_x32.py — in-loop, full-model co-sim of gelu_dma_top_x32
(32 parallel lanes through the wide DMA path).

Same experiment as tb_top_inloop_dma.py, but the datapath is NUM_LANES=32 wide:
the AXI4-MM DMA channels and the internal AXI-Stream are DATA_W = 1024 bits, so
every beat packs 32 IEEE-754 FP32 operands (lane i at bits [i*32 +: 32]).

      host (fp64->fp32)
        -> AXI4-MM write burst (1024-bit) -> mm2s_buffer_x32 (wide FIFO)
        -> AXI4-Stream (1024-bit)          -> gelu_top_x32 (32 lanes)
        -> AXI4-Stream (1024-bit)          -> s2mm_buffer_x32 (wide FIFO)
        -> AXI4-MM read burst (1024-bit)  -> host (fp32->fp64)

DUT: gelu_dma_top_x32 (rtl/DMA_memory/gelu_dma_top_x32.sv) with DEPTH=256 buffers.

Burst sizing: each beat = NUM_LANES elements, AXI4 caps a burst at 256 beats,
so one burst = 256 * 32 = 8192 elements and the per-layer 131,072-element tensor
streams in 16 bursts/layer (32 total). Buffer DEPTH (256) holds one full burst.
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

import builtins
builtins.profile = lambda f: f
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'orginal_software'))
from transformer import (                                   # noqa: E402
    init_params, layer_norm_forward, mha_forward, gelu, forward,
)

# ---------------------------------------------------------------------------
CLK_NS   = 22.0
F_CLK_HZ = 1.0 / (CLK_NS * 1e-9)

# Env-driven so x8 and x32 share this tb (Makefile x8 sets GELU_NUM_LANES=8).
NUM_LANES  = int(os.environ.get("GELU_NUM_LANES", "32"))
BEAT_BYTES = NUM_LANES * 4          # bytes per beat (NUM_LANES * 4)

VOCAB_SIZE = 64
SEQ_LEN    = 64
D_MODEL    = 64
N_HEADS    = 4
D_FF       = 256
N_LAYERS   = 2
BATCH_SIZE = 8
SEED       = 42

ARITH_OPS_PER_ELEM = 17
# DMA burst size in BEATS. AXI4 AxLEN is 8-bit -> max 256 beats/burst, and the
# buffer DEPTH is 256, so one burst fills one buffer. 1 beat = NUM_LANES elems.
CHUNK_BEATS = 256
CHUNK_ELEMS = CHUNK_BEATS * NUM_LANES        # 8192 elements per burst
GELU_THRESHOLD = 0.05

assert CHUNK_BEATS <= 256, "AXI4 burst is capped at 256 beats (AxLEN is 8-bit)"


# ---------------------------------------------------------------------------
# DMA burst helpers (wide, 1024-bit beats)
# ---------------------------------------------------------------------------
async def init_dut(dut):
    dut.stream_enable.value   = 0
    dut.dma_in_awaddr.value   = 0
    dut.dma_in_awlen.value    = 0
    dut.dma_in_awvalid.value  = 0
    dut.dma_in_wdata.value    = 0
    dut.dma_in_wstrb.value    = (1 << BEAT_BYTES) - 1   # all byte lanes
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


async def dma_write_burst(dut, beat_words):
    """Burst-write a list of DATA_W-bit beat words into mm2s_buffer_x32."""
    n = len(beat_words)
    full_strb = (1 << BEAT_BYTES) - 1

    dut.dma_in_awaddr.value  = 0
    dut.dma_in_awlen.value   = n - 1
    dut.dma_in_awvalid.value = 1
    await ReadOnly()
    while not dut.dma_in_awready.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.dma_in_awvalid.value = 0

    for i, word in enumerate(beat_words):
        dut.dma_in_wdata.value  = int(word)
        dut.dma_in_wstrb.value  = full_strb
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
    """Burst-read n_beats DATA_W-bit beat words from s2mm_buffer_x32."""
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

    # s2mm_buffer_x32 has combinational first-word-fall-through rvalid (high every
    # cycle the FIFO is non-empty). With rready held high it pops ONE beat per
    # clock, so we must record exactly one beat per clock edge — sample in the
    # ReadOnly phase (before the edge), then advance one edge to pop it. Using
    # two edges per beat would over-pop the FIFO and deadlock the read.
    dut.dma_out_rready.value = 1
    while len(data_out) < n_beats:
        await ReadOnly()
        if dut.dma_out_rvalid.value:
            data_out.append(int(dut.dma_out_rdata.value))
            last = bool(dut.dma_out_rlast.value)
            await RisingEdge(dut.clk)          # this edge pops the sampled beat
            if last:
                break
        else:
            await RisingEdge(dut.clk)          # wait for data, no pop
    dut.dma_out_rready.value = 0
    return data_out


# ---------------------------------------------------------------------------
# Pack / unpack: a beat carries NUM_LANES FP32 (lane 0 = LSB). The natural
# little-endian byte order of a float32 row already places element 0 at the
# lowest address == LSB of the integer, so int.from_bytes(..,'little') packs it.
# ---------------------------------------------------------------------------
def pack_beats(x32):
    """x32: np.float32 array, length multiple of NUM_LANES -> list of beat ints."""
    rows = x32.reshape(-1, NUM_LANES)
    return [int.from_bytes(r.tobytes(), "little") for r in rows]

def unpack_beats(beat_words, n_elems):
    """list of beat ints -> np.float32 array of n_elems."""
    raw = b"".join(int(w).to_bytes(BEAT_BYTES, "little") for w in beat_words)
    return np.frombuffer(raw, dtype=np.float32)[:n_elems]


async def hw_gelu_dma(dut, x_fp64, acc):
    shape = x_fp64.shape
    flat  = np.asarray(x_fp64, dtype=np.float64).reshape(-1)
    N     = flat.size

    tc0 = time.perf_counter()
    x32 = flat.astype(np.float32)
    acc["conv_us"] += (time.perf_counter() - tc0) * 1e6

    y32 = np.empty(N, dtype=np.float32)

    for off in range(0, N, CHUNK_ELEMS):
        seg    = x32[off:off + CHUNK_ELEMS]
        nbeats = -(-seg.size // NUM_LANES)              # ceil-div to whole beats
        pad    = nbeats * NUM_LANES - seg.size
        if pad:
            seg = np.concatenate([seg, np.zeros(pad, dtype=np.float32)])
        beats = pack_beats(seg)

        t0 = get_sim_time('ns')
        await dma_write_burst(dut, beats)
        dut.stream_enable.value = 1
        out_beats = await dma_read_burst(dut, nbeats)
        dut.stream_enable.value = 0
        t1 = get_sim_time('ns')

        out = unpack_beats(out_beats, seg.size)
        y32[off:off + (seg.size - pad)] = out[:seg.size - pad]

        acc["lat_ns"] += float(t1 - t0)
        acc["elems"]  += seg.size - pad
        acc["bytes"]  += (seg.size - pad) * 4 * 2
        acc["beats"]  += nbeats
        acc["bursts"] += 1

    tc1 = time.perf_counter()
    y64 = y32.astype(np.float64)
    acc["conv_us"] += (time.perf_counter() - tc1) * 1e6

    return y64.reshape(shape)


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_gelu_dma_x32_inloop(dut):
    """Full-model in-loop co-sim: every GELU runs through the wide DMA + 32-lane kernel."""

    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    bus_lanes = len(dut.dma_in_wdata) // 32
    assert bus_lanes == NUM_LANES, (
        f"DUT dma_in_wdata is {len(dut.dma_in_wdata)} bits = {bus_lanes} lanes, "
        f"expected NUM_LANES={NUM_LANES}")
    dut._log.info(f"DUT width confirmed: {bus_lanes} lanes ({len(dut.dma_in_wdata)}-bit DMA bus)")

    axil = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)
    dut._log.info("AXI-Lite: writing pipeline_enable=1")
    await axil.write(0x00, b'\x01\x00\x00\x00')
    rb = await axil.read(0x00, 4)
    assert rb.data == b'\x01\x00\x00\x00', f"pipeline_enable readback failed: {rb.data}"

    config = {"n_layers": N_LAYERS, "n_heads": N_HEADS}
    params = init_params(VOCAB_SIZE, SEQ_LEN, D_MODEL, N_HEADS, D_FF, N_LAYERS, seed=SEED)
    rng = np.random.default_rng(SEED)
    token_ids = rng.integers(0, VOCAB_SIZE, size=(BATCH_SIZE, SEQ_LEN))

    logits_ref, _ = forward(token_ids, params, config)

    acc = {"elems": 0, "lat_ns": 0.0, "bytes": 0, "beats": 0, "bursts": 0,
           "conv_us": 0.0, "gelu_max_err": 0.0, "gelu_fail": 0}
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
        h = xn2 @ params[f"{p}_W1"] + params[f"{p}_b1"]

        dut._log.info(f"Layer {l}: offloading GELU via wide DMA — {h.size} elements "
                      f"in {-(-h.size // CHUNK_ELEMS)} burst(s) of <= {CHUNK_BEATS} beats "
                      f"({NUM_LANES} lanes)")
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

    logit_err     = np.abs(logits_hw - logits_ref)
    logit_max_err = float(logit_err.max())
    logit_avg_err = float(logit_err.mean())
    same_argmax = int((logits_hw.argmax(axis=-1) == logits_ref.argmax(axis=-1)).sum())
    total_pos   = logits_ref.shape[0] * logits_ref.shape[1]

    lat_s        = acc["lat_ns"] * 1e-9
    elems        = acc["elems"]
    elem_per_s   = elems / lat_s
    cyc_per_elem = (acc["lat_ns"] / CLK_NS) / elems
    cyc_per_beat = (acc["lat_ns"] / CLK_NS) / acc["beats"]
    bw_total     = acc["bytes"] / lat_s / 1e6
    bw_dir       = (acc["bytes"] / 2) / lat_s / 1e6

    dut._log.info("\n=== Full-Model In-Loop GELU Co-Sim (v2 wide DMA path) — Timing & Metrics ===")
    dut._log.info(f"  Model              : M1 transformer, {N_LAYERS} layers, "
                  f"B={BATCH_SIZE} T={SEQ_LEN} d_ff={D_FF} (seed={SEED})")
    dut._log.info(f"  Parallelization    : {NUM_LANES} lanes ({NUM_LANES*32}-bit DMA + AXI-Stream)")
    dut._log.info(f"  Path               : AXI-MM DMA → mm2s_x32 → kernel_x32 → s2mm_x32 → AXI-MM DMA")
    dut._log.info(f"  Elements streamed  : {elems}  in {acc['bursts']} DMA bursts ({acc['beats']} beats)")
    dut._log.info(f"  Clock (synth)      : {CLK_NS:.0f} ns  ({F_CLK_HZ/1e6:.2f} MHz)")
    dut._log.info("  --- MEASURED (cycle-accurate Icarus, full DMA round-trip) ---")
    dut._log.info(f"  DMA round-trip time: {acc['lat_ns']:.0f} ns "
                  f"(~{acc['lat_ns']/CLK_NS:.0f} cycles incl. write+compute+read)")
    dut._log.info(f"  Throughput         : {elem_per_s/1e6:.2f} M elem/s  "
                  f"({cyc_per_elem:.4f} cycles/elem, {cyc_per_beat:.3f} cycles/beat)")
    dut._log.info(f"  AXI bandwidth/dir  : {bw_dir:.1f} MB/s (in, and out)")
    dut._log.info(f"  AXI bandwidth total: {bw_total:.1f} MB/s (in+out)")
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
        assert False, "In-loop full-model wide-DMA simulation failed kernel accuracy threshold."
