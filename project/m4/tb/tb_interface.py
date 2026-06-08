"""
tb_interface.py  —  AXI protocol testbench for gelu_axi_stream_interface
(parameterized SIMD: NUM_LANES gelu_fp32 pipelines).

Lane count is env-driven (GELU_NUM_LANES, default 32; the Makefile `interface_x8`
target builds the RTL at 8 and exports 8). The DUT has a NUM_LANES*32-bit
AXI-Stream: every beat packs NUM_LANES IEEE-754 FP32 operands, one per lane,
processed by NUM_LANES gelu_fp32 pipelines in lockstep (see rtl/interface.sv).
The AXI-Lite control path adds a read-only register 0x04 that reports NUM_LANES;
Test 1 asserts it equals the env value, so a mismatched RTL build is caught.

Lane packing (matches interface.sv): lane i occupies tdata[i*32 +: 32], so
lane 0 is the least-significant 32 bits of the NUM_LANES*32-bit word.

This drives the raw AXI ports directly (no cocotbext); the data plane is a
packed multi-lane word per beat.
"""

import os
import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Lane count is env-driven so x8 and x32 share this tb: the Makefile x8 target
# sets GELU_NUM_LANES=8 (and -DGELU_NUM_LANES=8 on the RTL). Default 32 = x32.
NUM_LANES  = int(os.environ.get("GELU_NUM_LANES", "32"))   # must match the DUT
PIPE_DEPTH = 12   # fp32_to_q16(4) + compute_core(4) + q16_to_fp32(4)
FIFO_DEPTH = 16   # output FIFO depth, in BEATS (each beat = NUM_LANES operands)

GELU_C1 = 0.7978845608028654
GELU_C2 = 0.03567740813630012


def gelu_ref(x: float) -> float:
    return 0.5 * x * (1.0 + np.tanh(GELU_C1 * x + GELU_C2 * x ** 3))

def fp32_to_bits(f: float) -> int:
    return struct.unpack(">I", struct.pack(">f", float(f)))[0]

def bits_to_fp32(b: int) -> float:
    return struct.unpack(">f", struct.pack(">I", int(b) & 0xFFFF_FFFF))[0]


# ---------------------------------------------------------------------------
# Lane pack / unpack — one beat carries NUM_LANES FP32 operands.
#   lane i  ->  bits [i*32 +: 32]   (lane 0 = LSB)
# ---------------------------------------------------------------------------
def pack_lanes(values) -> int:
    """Pack up to NUM_LANES floats into a single 1024-bit beat word.
    Fewer than NUM_LANES values are zero-padded in the high lanes."""
    assert len(values) <= NUM_LANES, f"beat holds at most {NUM_LANES} lanes"
    word = 0
    for i, v in enumerate(values):
        word |= (fp32_to_bits(v) & 0xFFFF_FFFF) << (i * 32)
    return word

def unpack_lanes(word: int) -> list:
    """Unpack a 1024-bit beat word into NUM_LANES floats (lane 0 = LSB)."""
    word = int(word)
    return [bits_to_fp32((word >> (i * 32)) & 0xFFFF_FFFF) for i in range(NUM_LANES)]

def chunk_beats(values, pad=0.0):
    """Split a flat list of values into NUM_LANES-wide beats, padding the last."""
    beats = []
    for off in range(0, len(values), NUM_LANES):
        seg = list(values[off:off + NUM_LANES])
        if len(seg) < NUM_LANES:
            seg = seg + [pad] * (NUM_LANES - len(seg))
        beats.append(seg)
    return beats


# ---------------------------------------------------------------------------
# Bus helpers
# ---------------------------------------------------------------------------
async def reset_dut(dut):
    dut.rst.value = 1
    # idle all AXI ports so there are no floating signals during reset
    for sig in ("s_axil_awaddr", "s_axil_wdata", "s_axil_wstrb",
                "s_axil_awvalid", "s_axil_wvalid", "s_axil_bready",
                "s_axil_araddr", "s_axil_arvalid", "s_axil_rready",
                "s_axis_tdata", "s_axis_tvalid", "s_axis_tlast",
                "s_axis_tuser", "m_axis_tready"):
        getattr(dut, sig).value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def axil_write(dut, addr: int, data: int):
    """
    AXI-Lite write — three-edge sequence matching the decoupled handshake:
      Edge 1 → RTL asserts awready/wready (master keeps awvalid/wvalid=1)
      Edge 2 → RTL sees ready+valid together, asserts bvalid, writes register;
               master deasserts awvalid/wvalid after this edge
      Edge 3 → RTL clears bvalid (bready was asserted); master deasserts bready
    """
    dut.s_axil_awaddr.value  = addr
    dut.s_axil_wdata.value   = data
    dut.s_axil_wstrb.value   = 0xF
    dut.s_axil_awvalid.value = 1
    dut.s_axil_wvalid.value  = 1
    dut.s_axil_bready.value  = 1
    await RisingEdge(dut.clk)      # edge 1: RTL asserts awready/wready
    await RisingEdge(dut.clk)      # edge 2: RTL completes handshake, bvalid←1
    dut.s_axil_awvalid.value = 0
    dut.s_axil_wvalid.value  = 0
    await RisingEdge(dut.clk)      # edge 3: RTL clears bvalid
    dut.s_axil_bready.value  = 0


async def axil_read(dut, addr: int) -> int:
    """
    AXI-Lite read — three-edge sequence matching the decoupled handshake:
      Edge 1 → RTL asserts arready (master keeps arvalid=1)
      Edge 2 → RTL sees arready+arvalid, asserts rvalid+rdata;
               master deasserts arvalid after this edge
      Edge 3 → rdata stable (edge-2 NBA committed); RTL clears rvalid;
               safe to sample rdata now (rdata holds after rvalid clears)
    """
    dut.s_axil_araddr.value  = addr
    dut.s_axil_arvalid.value = 1
    dut.s_axil_rready.value  = 1
    await RisingEdge(dut.clk)      # edge 1: RTL asserts arready
    await RisingEdge(dut.clk)      # edge 2: RTL asserts rvalid + rdata
    dut.s_axil_arvalid.value = 0
    await RisingEdge(dut.clk)      # edge 3: rdata stable; RTL clears rvalid
    data = int(dut.s_axil_rdata.value)
    dut.s_axil_rready.value  = 0
    return data


async def enable_pipeline(dut):
    await axil_write(dut, 0x00, 0x1)


async def axis_send(dut, values, tlast_on_last=True):
    """Send a flat list of FP32 floats, NUM_LANES per beat (last beat padded)."""
    beats = chunk_beats(values)
    n = len(beats)
    for i, beat in enumerate(beats):
        dut.s_axis_tdata.value  = pack_lanes(beat)
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tlast.value  = 1 if (tlast_on_last and i == n - 1) else 0
        dut.s_axis_tuser.value  = 0
        while not int(dut.s_axis_tready.value):
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value  = 0


async def axis_recv(dut, count: int) -> list:
    """Collect exactly `count` beats; each beat unpacked into NUM_LANES floats."""
    results = []
    dut.m_axis_tready.value = 1
    while len(results) < count:
        await RisingEdge(dut.clk)
        if int(dut.m_axis_tvalid.value):
            results.append({
                "lanes": unpack_lanes(int(dut.m_axis_tdata.value)),
                "tlast": int(dut.m_axis_tlast.value),
            })
    dut.m_axis_tready.value = 0
    return results


# ---------------------------------------------------------------------------
# Test 1 — AXI-Lite enable register + NUM_LANES identity register
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_axil_enable_readback(dut):
    """pipeline_enable read/write, plus the read-only NUM_LANES register (0x04)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    val = await axil_read(dut, 0x00)
    assert val == 0, f"Expected 0 after reset, got {val}"

    await axil_write(dut, 0x00, 0x1)
    val = await axil_read(dut, 0x00)
    assert val == 1, f"Expected 1 after enable write, got {val}"

    lanes = await axil_read(dut, 0x04)
    assert lanes == NUM_LANES, f"NUM_LANES register reports {lanes}, expected {NUM_LANES}"

    print(f"[PASS] AXI-Lite pipeline_enable write/readback; NUM_LANES reg = {lanes}")


# ---------------------------------------------------------------------------
# Test 2 — Pipeline gate: tready must be 0 when disabled, 1 when enabled
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pipeline_gate(dut):
    """s_axis_tready must stay low while pipeline_enable=0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.s_axis_tvalid.value = 1
    dut.s_axis_tdata.value  = pack_lanes([1.0] * NUM_LANES)
    dut.m_axis_tready.value = 1

    for _ in range(4):
        await RisingEdge(dut.clk)
        assert int(dut.s_axis_tready.value) == 0, \
            "s_axis_tready should be 0 while pipeline disabled"

    await enable_pipeline(dut)
    await RisingEdge(dut.clk)
    assert int(dut.s_axis_tready.value) == 1, \
        "s_axis_tready should be 1 after enabling pipeline"

    dut.s_axis_tvalid.value = 0
    dut.m_axis_tready.value = 0
    print("[PASS] pipeline gate: tready gated correctly by pipeline_enable")


# ---------------------------------------------------------------------------
# Test 3 — Single beat: NUM_LANES FP32 in → NUM_LANES GELU out in one cycle
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_single_beat(dut):
    """One packed beat of NUM_LANES distinct operands → NUM_LANES GELU results."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    xs = list(np.linspace(-3.5, 3.5, NUM_LANES))

    recv_task = cocotb.start_soon(axis_recv(dut, 1))
    await axis_send(dut, xs)
    lanes = (await recv_task)[0]["lanes"]

    max_err = 0.0
    for i, x in enumerate(xs):
        err = abs(lanes[i] - gelu_ref(x))
        max_err = max(max_err, err)
        assert err < 0.05, f"lane {i}: x={x:.3f} err={err:.5f} exceeds 0.05"
    print(f"[PASS] single beat: {NUM_LANES} lanes, max err {max_err:.5f}")


# ---------------------------------------------------------------------------
# Test 4 — TLAST propagation across a multi-beat packet
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tlast_propagation(dut):
    """TLAST on the last input beat must appear on the corresponding output beat."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    # 4 full beats = 4*NUM_LANES operands
    packet = list(np.linspace(-3.0, 3.0, 4 * NUM_LANES))
    n_beats = 4

    recv_task = cocotb.start_soon(axis_recv(dut, n_beats))
    await axis_send(dut, packet)
    beats = await recv_task

    for i, beat in enumerate(beats):
        exp_last = 1 if i == n_beats - 1 else 0
        ok = beat["tlast"] == exp_last
        print(f"  [{'PASS' if ok else 'FAIL'}] beat {i}: "
              f"lane0={beat['lanes'][0]:.4f}  tlast={beat['tlast']} (exp {exp_last})")
        assert ok, f"TLAST mismatch on beat {i}"

    print("[PASS] TLAST propagated correctly across multi-beat packet")


# ---------------------------------------------------------------------------
# Test 5 — Backpressure: tready deasserts at FIFO capacity (in beats), recovers
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_backpressure(dut):
    """Fill the output FIFO with tready=0; verify tready deasserts then recovers."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    dut.m_axis_tready.value = 0
    dut.s_axis_tdata.value  = pack_lanes([0.5] * NUM_LANES)
    dut.s_axis_tvalid.value = 1

    beats_sent = 0
    for _ in range(FIFO_DEPTH + PIPE_DEPTH + 4):
        if not int(dut.s_axis_tready.value):
            break
        await RisingEdge(dut.clk)
        beats_sent += 1

    dut.s_axis_tvalid.value = 0
    assert not int(dut.s_axis_tready.value), \
        "tready never deasserted — backpressure logic broken"
    print(f"  tready deasserted after {beats_sent} beats (FIFO_DEPTH={FIFO_DEPTH})")

    # Drain and verify recovery
    dut.m_axis_tready.value = 1
    recovered = False
    for _ in range(FIFO_DEPTH + PIPE_DEPTH + 4):
        await RisingEdge(dut.clk)
        if int(dut.s_axis_tready.value):
            recovered = True
            break
    dut.m_axis_tready.value = 0

    assert recovered, "tready did not recover after draining FIFO"
    print("[PASS] backpressure: tready deasserts at capacity, recovers on drain")


# ---------------------------------------------------------------------------
# Test 6 — Accuracy sweep across many lanes/beats, concurrent send and recv
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_accuracy_sweep(dut):
    """N FP32 inputs spread over multiple beats; all within 0.05 of gelu_ref."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    N      = 4 * NUM_LANES + 7   # 135 values → 5 beats, last beat padded
    inputs = list(np.linspace(-3.5, 3.5, N))
    n_beats = len(chunk_beats(inputs))

    # Concurrent: recv collects while send streams — avoids FIFO overflow
    recv_task = cocotb.start_soon(axis_recv(dut, n_beats))
    await axis_send(dut, inputs)
    beats = await recv_task

    # Flatten lane results back to a single ordered list, slice to N (drop padding)
    flat = [v for beat in beats for v in beat["lanes"]][:N]

    max_err, total_err, worst_x = 0.0, 0.0, 0.0
    for x, got in zip(inputs, flat):
        err = abs(got - gelu_ref(x))
        total_err += err
        if err > max_err:
            max_err, worst_x = err, x

    print(f"\n=== Accuracy Sweep ({N} pts over {n_beats} beats, -3.5 → 3.5) ===")
    print(f"  Lanes     : {NUM_LANES} ({NUM_LANES*32}-bit AXI-Stream)")
    print(f"  Avg error : {total_err/N:.6f}")
    print(f"  Max error : {max_err:.6f}  (x = {worst_x:.3f})")
    print("==========================================\n")
    assert max_err < 0.05, f"Max error {max_err:.6f} exceeds threshold"
    print("[PASS] accuracy sweep")
