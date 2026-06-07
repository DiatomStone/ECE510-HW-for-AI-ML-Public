"""
tb_axis_interface.py  —  AXI protocol testbench for gelu_axi_stream_interface.

Drives only the AXI-Lite and AXI-Stream ports; no access to internal signals.

AXI-Lite handshake timing (after RTL fix for spec §A3.3.1/§A3.3.2):
  Write: edge1 → RTL asserts awready/wready
         edge2 → master still holds awvalid/wvalid; RTL completes handshake,
                 asserts bvalid, writes register; master deasserts awvalid/wvalid
         edge3 → RTL clears bvalid; master deasserts bready
  Read:  edge1 → RTL asserts arready
         edge2 → master still holds arvalid; RTL completes handshake, asserts
                 rvalid+rdata; master deasserts arvalid
         edge3 → rdata stable (edge2 NBA committed); RTL clears rvalid

Icarus/VPI note: RisingEdge fires before NBA commits, so a signal registered
at edge N is only safely readable after edge N+1.
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PIPE_DEPTH = 12   # fp32_to_q16(4) + compute_core(4) + q16_to_fp32(4)
FIFO_DEPTH = 16

GELU_C1 = 0.7978845608028654
GELU_C2 = 0.03567740813630012


def gelu_ref(x: float) -> float:
    return 0.5 * x * (1.0 + np.tanh(GELU_C1 * x + GELU_C2 * x ** 3))

def fp32_to_bits(f: float) -> int:
    return struct.unpack(">I", struct.pack(">f", float(f)))[0]

def bits_to_fp32(b: int) -> float:
    return struct.unpack(">f", struct.pack(">I", int(b) & 0xFFFF_FFFF))[0]


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
    """Send a list of FP32 floats over the AXI-Stream slave port."""
    n = len(values)
    for i, v in enumerate(values):
        dut.s_axis_tdata.value  = fp32_to_bits(v)
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tlast.value  = 1 if (tlast_on_last and i == n - 1) else 0
        dut.s_axis_tuser.value  = 0
        while not int(dut.s_axis_tready.value):
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value  = 0


async def axis_recv(dut, count: int) -> list:
    """Collect exactly count beats from the AXI-Stream master port."""
    results = []
    dut.m_axis_tready.value = 1
    while len(results) < count:
        await RisingEdge(dut.clk)
        if int(dut.m_axis_tvalid.value):
            results.append({
                "data":  bits_to_fp32(int(dut.m_axis_tdata.value)),
                "tlast": int(dut.m_axis_tlast.value),
            })
    dut.m_axis_tready.value = 0
    return results


# ---------------------------------------------------------------------------
# Test 1 — AXI-Lite enable register: write 1, read back 1
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_axil_enable_readback(dut):
    """pipeline_enable register must read back correctly after write."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    val = await axil_read(dut, 0x00)
    assert val == 0, f"Expected 0 after reset, got {val}"

    await axil_write(dut, 0x00, 0x1)
    val = await axil_read(dut, 0x00)
    assert val == 1, f"Expected 1 after enable write, got {val}"

    print("[PASS] AXI-Lite pipeline_enable write / readback")


# ---------------------------------------------------------------------------
# Test 2 — Pipeline gate: tready must be 0 when disabled, 1 when enabled
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pipeline_gate(dut):
    """s_axis_tready must stay low while pipeline_enable=0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.s_axis_tvalid.value = 1
    dut.s_axis_tdata.value  = fp32_to_bits(1.0)
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
# Test 3 — Single value: FP32 in → GELU out through the full AXI path
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_single_value(dut):
    """One FP32 operand must produce the correct GELU result at m_axis."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    x        = 1.0
    expected = gelu_ref(x)

    recv_task = cocotb.start_soon(axis_recv(dut, 1))
    await axis_send(dut, [x])
    result    = (await recv_task)[0]["data"]

    err = abs(result - expected)
    print(f"[{'PASS' if err < 0.05 else 'FAIL'}] "
          f"x={x}  expected={expected:.5f}  got={result:.5f}  err={err:.5f}")
    assert err < 0.05, f"Error {err:.5f} exceeds 0.05 threshold"


# ---------------------------------------------------------------------------
# Test 4 — TLAST propagation through 12-stage pipeline
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_tlast_propagation(dut):
    """TLAST on last input beat must appear on the corresponding output beat."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    packet = [0.5, 1.0, 1.5, 2.0]

    recv_task = cocotb.start_soon(axis_recv(dut, len(packet)))
    await axis_send(dut, packet)
    beats = await recv_task

    for i, beat in enumerate(beats):
        exp_last = 1 if i == len(packet) - 1 else 0
        ok = beat["tlast"] == exp_last
        print(f"  [{'PASS' if ok else 'FAIL'}] beat {i}: "
              f"data={beat['data']:.4f}  tlast={beat['tlast']} (exp {exp_last})")
        assert ok, f"TLAST mismatch on beat {i}"

    print("[PASS] TLAST propagated correctly through 12-stage pipeline")


# ---------------------------------------------------------------------------
# Test 5 — Backpressure: tready deasserts at FIFO capacity, recovers on drain
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_backpressure(dut):
    """Fill the output FIFO with tready=0; verify tready deasserts then recovers."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    dut.m_axis_tready.value = 0
    dut.s_axis_tdata.value  = fp32_to_bits(0.5)
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
# Test 6 — Accuracy sweep: 50 values, concurrent send and recv
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_accuracy_sweep(dut):
    """50 uniformly-spaced FP32 inputs; all outputs must be within 0.05 of gelu_ref."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)
    await enable_pipeline(dut)

    N      = 50
    inputs = list(np.linspace(-3.5, 3.5, N))

    # Concurrent: recv collects while send streams — avoids FIFO overflow
    recv_task = cocotb.start_soon(axis_recv(dut, N))
    await axis_send(dut, inputs)
    beats = await recv_task

    max_err, total_err, worst_x = 0.0, 0.0, 0.0
    for x, beat in zip(inputs, beats):
        err = abs(beat["data"] - gelu_ref(x))
        total_err += err
        if err > max_err:
            max_err, worst_x = err, x

    print(f"\n=== Accuracy Sweep ({N} pts, -3.5 → 3.5) ===")
    print(f"  Avg error : {total_err/N:.6f}")
    print(f"  Max error : {max_err:.6f}  (x = {worst_x:.3f})")
    print("==========================================\n")
    assert max_err < 0.05, f"Max error {max_err:.6f} exceeds threshold"
    print("[PASS] accuracy sweep")
