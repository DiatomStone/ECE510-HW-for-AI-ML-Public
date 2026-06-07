"""
tb_q16_to_fp32.py — cocotb testbench for q16_to_fp32

4-stage pipelined Q16.16 → IEEE 754 FP32 converter.
  - Round-to-Nearest-Even (RNE)
  - Correct sign handling via two's complement magnitude extraction

Makefile target:  make opt=convout
"""

import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles


# ---------------------------------------------------------------------------
# Q16.16 constants
# ---------------------------------------------------------------------------
Q16_SCALE = 1 << 16       # 65536
Q16_MAX   =  0x7FFF_FFFF  # +32767.99998...
Q16_MIN   = -0x8000_0000  # -32768.0  (two's complement)

PIPE_DEPTH = 4             # both converters are 4-stage


# ---------------------------------------------------------------------------
# Format conversion helpers
# ---------------------------------------------------------------------------

def float_to_q16(f: float) -> int:
    """Convert a Python float to a signed Q16.16 integer (32-bit two's complement)."""
    raw = round(f * Q16_SCALE)
    raw = max(Q16_MIN, min(Q16_MAX, raw))
    return raw & 0xFFFF_FFFF


def q16_to_float(bits: int) -> float:
    """Convert an unsigned 32-bit Q16.16 bus value back to a Python float."""
    signed = bits if bits < 0x8000_0000 else bits - 0x1_0000_0000
    return signed / Q16_SCALE


def fp32_to_bits(f: float) -> int:
    """Pack a Python float as IEEE-754 single-precision bits (uint32)."""
    return struct.unpack(">I", struct.pack(">f", f))[0]


def bits_to_fp32(bits: int) -> float:
    """Unpack IEEE-754 single-precision bits to a Python float."""
    return struct.unpack(">f", struct.pack(">I", bits & 0xFFFF_FFFF))[0]


# ---------------------------------------------------------------------------
# Pipeline driver / collector
# ---------------------------------------------------------------------------

async def reset_dut(dut):
    """Apply synchronous reset for a few cycles."""
    dut.rst.value      = 1
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def drive_and_collect(dut, inputs: list, extra_drain: int = PIPE_DEPTH + 2):
    """
    Drive a list of 32-bit input values back-to-back (valid_in=1 every cycle),
    drain the pipeline, and return a list of data_out values captured on every
    cycle where valid_out == 1.

    Parameters
    ----------
    inputs      : list of uint32 bus values
    extra_drain : additional idle cycles after the last input
    """
    outputs = []

    async def collector():
        while True:
            await RisingEdge(dut.clk)
            if int(dut.valid_out.value) == 1:
                outputs.append(int(dut.data_out.value))

    task = cocotb.start_soon(collector())

    for val in inputs:
        await RisingEdge(dut.clk)
        dut.valid_in.value = 1
        dut.data_in.value  = val

    await RisingEdge(dut.clk)
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    await ClockCycles(dut.clk, extra_drain)

    task.kill()
    return outputs

# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_reset(dut):
    """After reset, valid_out and data_out must both be 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value      = 1
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await RisingEdge(dut.clk)  # one full registered cycle after reset release
    assert int(dut.valid_out.value) == 0, "valid_out should be 0 after reset"
    assert int(dut.data_out.value)  == 0, "data_out should be 0 after reset"


# ---------------------------------------------------------------------------
# Zero
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_zero(dut):
    """0x0000_0000 → FP32 should be +0.0 (0x0000_0000)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x0000_0000])
    assert len(outputs) == 1
    assert outputs[0] == 0x0000_0000, f"Expected +0.0, got {outputs[0]:#010x}"


# ---------------------------------------------------------------------------
# Exact unity values
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_one(dut):
    """Q16.16 0x0001_0000 = 1.0; FP32 result must be exactly 1.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x0001_0000])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got == 1.0, \
        f"q16_to_fp32(0x0001_0000) expected 1.0, got {got} ({outputs[0]:#010x})"


@cocotb.test()
async def test_neg_one(dut):
    """Q16.16 0xFFFF_0000 = -1.0; FP32 result must be exactly -1.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0xFFFF_0000])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got == -1.0, \
        f"q16_to_fp32(0xFFFF_0000) expected -1.0, got {got} ({outputs[0]:#010x})"


# ---------------------------------------------------------------------------
# Positive integers
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_positive_integers(dut):
    """Exact positive integers: 1.0, 2.0, 4.0, 256.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [1.0, 2.0, 4.0, 256.0]
    outputs = await drive_and_collect(dut, [float_to_q16(v) for v in test_vals])

    assert len(outputs) == len(test_vals)
    for v, raw in zip(test_vals, outputs):
        got = bits_to_fp32(raw)
        assert abs(got - v) < 1e-5, \
            f"q16_to_fp32({v}): expected {v}, got {got} ({raw:#010x})"


# ---------------------------------------------------------------------------
# Negative integers
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_negative_integers(dut):
    """Negative integers: -1.0, -2.0, -32768.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [-1.0, -2.0, -32768.0]
    outputs = await drive_and_collect(dut, [float_to_q16(v) for v in test_vals])

    assert len(outputs) == len(test_vals)
    for v, raw in zip(test_vals, outputs):
        got = bits_to_fp32(raw)
        assert abs(got - v) < 1e-4, \
            f"q16_to_fp32({v}): expected {v}, got {got} ({raw:#010x})"


# ---------------------------------------------------------------------------
# Fractional values
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_fractional_values(dut):
    """Fractional Q16.16 values — allow 2 LSB tolerance (~3e-5)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [0.5, 0.25, 0.125, -0.5, 3.14159, -2.71828]
    outputs = await drive_and_collect(dut, [float_to_q16(v) for v in test_vals])

    assert len(outputs) == len(test_vals)
    for v, raw in zip(test_vals, outputs):
        got = bits_to_fp32(raw)
        assert abs(got - v) < 4e-5, \
            f"q16_to_fp32({v}): expected {v}, got {got} ({raw:#010x})"


# ---------------------------------------------------------------------------
# Boundary values
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_max_positive(dut):
    """0x7FFF_FFFF = +32767.99998...; FP32 result must be positive and near 32768."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x7FFF_FFFF])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got > 0 and abs(got - 32768.0) < 1.0, \
        f"q16_to_fp32(Q16_MAX) expected ~32768, got {got}"


@cocotb.test()
async def test_min_negative(dut):
    """0x8000_0000 = -32768.0 exactly; FP32 result must be -32768.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x8000_0000])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got == -32768.0, \
        f"q16_to_fp32(0x8000_0000) expected -32768.0, got {got} ({outputs[0]:#010x})"


# ---------------------------------------------------------------------------
# Sign bit correctness
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_sign_bit_positive(dut):
    """All positive Q16.16 inputs must produce FP32 with sign bit = 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    pos_vals = [0x0000_0001, 0x0000_8000, 0x0001_0000, 0x7FFF_FFFF]
    outputs = await drive_and_collect(dut, pos_vals)

    assert len(outputs) == len(pos_vals)
    for q, raw in zip(pos_vals, outputs):
        assert (raw >> 31) == 0, \
            f"Positive Q16.16 {q:#010x} produced negative FP32 {raw:#010x}"


# ---------------------------------------------------------------------------
# RNE rounding
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_rne_consecutive_lsb(dut):
    """
    Two consecutive Q16.16 LSBs must produce ordered, positive FP32 outputs.
    Verifies RNE does not collapse adjacent values to the same result.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # raw Q16.16 counts: 1 LSB and 2 LSBs
    outputs = await drive_and_collect(dut, [1, 2])

    assert len(outputs) == 2
    f0 = bits_to_fp32(outputs[0])
    f1 = bits_to_fp32(outputs[1])
    assert f0 > 0 and f1 > f0, \
        f"Consecutive Q16.16 values should produce ordered positive FP32: {f0}, {f1}"


# ---------------------------------------------------------------------------
# Pipeline checks
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_pipeline_latency(dut):
    """valid_out must appear exactly PIPE_DEPTH cycles after valid_in."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    await RisingEdge(dut.clk)
    dut.valid_in.value = 1
    dut.data_in.value  = float_to_q16(1.0)
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    for cycle in range(1, PIPE_DEPTH + 5):
        await RisingEdge(dut.clk)
        if int(dut.valid_out.value) == 1:
            assert cycle == PIPE_DEPTH, \
                f"valid_out appeared at cycle {cycle}, expected {PIPE_DEPTH}"
            return

    raise AssertionError("valid_out never asserted within expected window")


@cocotb.test()
async def test_pipeline_throughput(dut):
    """N back-to-back valid inputs must produce exactly N valid outputs."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    N = 16
    vals = [float_to_q16(float(i) * 0.25) for i in range(N)]
    outputs = await drive_and_collect(dut, vals)

    assert len(outputs) == N, \
        f"Expected {N} outputs (full throughput), got {len(outputs)}"
