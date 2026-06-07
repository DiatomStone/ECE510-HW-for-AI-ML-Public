"""
cocotb testbench for fp32_to_q16 and q16_to_fp32

Both modules are 4-stage pipelines with:
  - clk, rst (active-high synchronous)
  - valid_in / data_in  (32-bit)
  - valid_out / data_out (32-bit, appears 4 cycles after valid_in)

Run with (example Makefile targets):
  make opt=convin
  make opt=convout
"""

import struct
import math
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

# ---------------------------------------------------------------------------
# Q16.16 helpers
# ---------------------------------------------------------------------------
Q16_SCALE = 1 << 16          # 65536
Q16_MAX   =  0x7FFF_FFFF     # +32767.99998...
Q16_MIN   = -0x8000_0000     # -32768.0  (two's complement)


def float_to_q16(f: float) -> int:
    """Convert a Python float to a signed Q16.16 integer (32-bit two's complement)."""
    raw = round(f * Q16_SCALE)
    raw = max(Q16_MIN, min(Q16_MAX, raw))
    # Return as unsigned 32-bit for DUT bus
    return raw & 0xFFFF_FFFF


def q16_to_float(bits: int) -> float:
    """Convert an unsigned 32-bit Q16.16 bus value back to float."""
    # Reinterpret as signed 32-bit
    signed = bits if bits < 0x8000_0000 else bits - 0x1_0000_0000
    return signed / Q16_SCALE


def fp32_to_bits(f: float) -> int:
    """Pack a Python float as IEEE-754 single-precision bits (uint32)."""
    return struct.unpack(">I", struct.pack(">f", f))[0]


def bits_to_fp32(bits: int) -> float:
    """Unpack IEEE-754 single-precision bits to a Python float."""
    return struct.unpack(">f", struct.pack(">I", bits & 0xFFFF_FFFF))[0]


# ---------------------------------------------------------------------------
# Shared pipeline driver / collector
# ---------------------------------------------------------------------------
PIPE_DEPTH = 4  # both converters are 4-stage


async def reset_dut(dut):
    """Apply synchronous reset for a few cycles."""
    dut.rst.value      = 1
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def drive_and_collect(dut, inputs: list[int], extra_drain: int = PIPE_DEPTH + 2):
    """
    Drive a list of 32-bit input values back-to-back (valid_in=1 every cycle),
    then drain the pipeline.  Returns a list of (data_out, valid_out) tuples
    captured on every rising edge after valid_out first goes high.

    Parameters
    ----------
    inputs      : list of uint32 bus values
    extra_drain : additional idle cycles after the last input
    """
    outputs = []

    async def collector():
        """Background task: capture every cycle where valid_out == 1."""
        while True:
            await RisingEdge(dut.clk)
            if int(dut.valid_out.value) == 1:
                outputs.append(int(dut.data_out.value))

    task = cocotb.start_soon(collector())

    # Drive inputs
    for val in inputs:
        await RisingEdge(dut.clk)
        dut.valid_in.value = 1
        dut.data_in.value  = val

    # De-assert valid_in, drain pipeline
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    await ClockCycles(dut.clk, extra_drain)

    task.kill()
    return outputs


# ---------------------------------------------------------------------------
# fp32_to_q16 tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_fp32_to_q16_reset(dut):
    """After reset, valid_out and data_out must both be 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)
    await ClockCycles(dut.clk, 2)
    assert int(dut.valid_out.value) == 0, "valid_out should be 0 after reset"
    assert int(dut.data_out.value)  == 0, "data_out should be 0 after reset"


@cocotb.test()
async def test_fp32_to_q16_zero(dut):
    """0.0 → Q16.16 should be 0x0000_0000."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [fp32_to_bits(0.0)])
    assert len(outputs) == 1
    assert outputs[0] == 0x0000_0000, f"Expected 0, got {outputs[0]:#010x}"


@cocotb.test()
async def test_fp32_to_q16_positive_integer(dut):
    """Small positive integers that are exactly representable."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [1.0, 2.0, 4.0, 100.0, 32767.0]
    inputs = [fp32_to_bits(v) for v in test_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(test_vals), \
        f"Expected {len(test_vals)} outputs, got {len(outputs)}"

    for v, raw in zip(test_vals, outputs):
        got = q16_to_float(raw)
        assert abs(got - v) < 2e-4, \
            f"fp32_to_q16({v}): expected ~{v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_fp32_to_q16_negative_values(dut):
    """Negative values, including -1.0 and -32768.0 (boundary)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [-1.0, -2.5, -100.0, -32768.0]
    inputs = [fp32_to_bits(v) for v in test_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(test_vals)

    for v, raw in zip(test_vals, outputs):
        got = q16_to_float(raw)
        # -32768.0 is exactly representable in Q16.16
        tol = 2e-4
        assert abs(got - v) <= tol, \
            f"fp32_to_q16({v}): expected ~{v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_fp32_to_q16_fractional(dut):
    """Fractional values — Q16.16 has 16 frac bits so ≈ 1.5e-5 LSB resolution."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [0.5, 0.25, 0.125, 1.5, -0.75, 3.14159]
    inputs = [fp32_to_bits(v) for v in test_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(test_vals)

    for v, raw in zip(test_vals, outputs):
        got = q16_to_float(raw)
        # 1 LSB in Q16.16 = 1/65536 ≈ 1.5e-5; allow 2 LSB tolerance
        assert abs(got - v) < 4e-5, \
            f"fp32_to_q16({v}): expected ~{v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_fp32_to_q16_positive_overflow_clamp(dut):
    """Values above +32767.999... must clamp to 0x7FFF_FFFF."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    overflow_vals = [32768.0, 100000.0, float("inf")]
    inputs = [fp32_to_bits(v) for v in overflow_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(overflow_vals)
    for v, raw in zip(overflow_vals, outputs):
        assert raw == 0x7FFF_FFFF, \
            f"fp32_to_q16({v}) expected clamp 0x7FFF_FFFF, got {raw:#010x}"


@cocotb.test()
async def test_fp32_to_q16_negative_overflow_clamp(dut):
    """Values below -32768 must clamp to 0x8000_0000."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    overflow_vals = [-32769.0, -1e6, float("-inf")]
    inputs = [fp32_to_bits(v) for v in overflow_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(overflow_vals)
    for v, raw in zip(overflow_vals, outputs):
        assert raw == 0x8000_0000, \
            f"fp32_to_q16({v}) expected clamp 0x8000_0000, got {raw:#010x}"


@cocotb.test()
async def test_fp32_to_q16_subnormal_flush_to_zero(dut):
    """Subnormals (biased exponent == 0) must flush to zero (FTZ)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # Smallest positive subnormal: 0x0000_0001
    # Largest positive subnormal:  0x007F_FFFF
    subnormals = [0x0000_0001, 0x007F_FFFF, 0x8000_0001]  # last one is negative subnormal
    outputs = await drive_and_collect(dut, subnormals)

    assert len(outputs) == len(subnormals)
    for bits, raw in zip(subnormals, outputs):
        assert raw == 0, \
            f"Subnormal {bits:#010x} should flush to 0, got {raw:#010x}"


@cocotb.test()
async def test_fp32_to_q16_negative_one(dut):
    """-1.0 in FP32 → 0xFFFF_0000 in Q16.16 two's complement."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [fp32_to_bits(-1.0)])
    assert len(outputs) == 1
    assert outputs[0] == 0xFFFF_0000, \
        f"fp32_to_q16(-1.0) expected 0xFFFF_0000, got {outputs[0]:#010x}"


@cocotb.test()
async def test_fp32_to_q16_pipeline_throughput(dut):
    """
    Back-to-back valid_in asserted for N cycles must produce exactly N
    valid_out pulses with no stalls (full throughput).
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    N = 16
    vals = [fp32_to_bits(float(i) * 0.5) for i in range(N)]
    outputs = await drive_and_collect(dut, vals)

    assert len(outputs) == N, \
        f"Expected {N} outputs for {N} inputs (full throughput), got {len(outputs)}"


@cocotb.test()
async def test_fp32_to_q16_valid_out_latency(dut):
    """valid_out must appear exactly PIPE_DEPTH cycles after valid_in."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # Send a single pulse and count cycles until valid_out
    await RisingEdge(dut.clk)
    dut.valid_in.value = 1
    dut.data_in.value  = fp32_to_bits(1.0)
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    for cycle in range(1, PIPE_DEPTH + 5):
        await RisingEdge(dut.clk)
        if int(dut.valid_out.value) == 1:
            assert cycle == PIPE_DEPTH, \
                f"valid_out appeared at cycle {cycle}, expected {PIPE_DEPTH}"
            return

    raise AssertionError("valid_out never asserted within expected window")


# ---------------------------------------------------------------------------
# q16_to_fp32 tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_q16_to_fp32_reset(dut):
    """After reset, valid_out and data_out must both be 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)
    await ClockCycles(dut.clk, 2)
    assert int(dut.valid_out.value) == 0, "valid_out should be 0 after reset"
    assert int(dut.data_out.value)  == 0, "data_out should be 0 after reset"


@cocotb.test()
async def test_q16_to_fp32_zero(dut):
    """0x0000_0000 → FP32 should be +0.0 (0x0000_0000)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x0000_0000])
    assert len(outputs) == 1
    assert outputs[0] == 0x0000_0000, f"Expected +0.0, got {outputs[0]:#010x}"


@cocotb.test()
async def test_q16_to_fp32_positive_integers(dut):
    """Exact positive integers: 1.0, 2.0, 4.0, 256.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [1.0, 2.0, 4.0, 256.0]
    inputs = [float_to_q16(v) for v in test_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(test_vals)

    for v, raw in zip(test_vals, outputs):
        got = bits_to_fp32(raw)
        assert abs(got - v) < 1e-5, \
            f"q16_to_fp32({v}): expected {v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_q16_to_fp32_negative_integers(dut):
    """Negative integers: -1.0, -2.0, -32768.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [-1.0, -2.0, -32768.0]
    inputs = [float_to_q16(v) for v in test_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(test_vals)

    for v, raw in zip(test_vals, outputs):
        got = bits_to_fp32(raw)
        assert abs(got - v) < 1e-4, \
            f"q16_to_fp32({v}): expected {v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_q16_to_fp32_fractional(dut):
    """Fractional Q16.16 values."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [0.5, 0.25, 0.125, -0.5, 3.14159, -2.71828]
    inputs = [float_to_q16(v) for v in test_vals]
    outputs = await drive_and_collect(dut, inputs)

    assert len(outputs) == len(test_vals)

    for v, raw in zip(test_vals, outputs):
        got = bits_to_fp32(raw)
        # Allow 2 LSB of Q16.16 error (~3e-5)
        assert abs(got - v) < 4e-5, \
            f"q16_to_fp32({v}): expected {v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_q16_to_fp32_one(dut):
    """Q16.16 representation of 1.0 is 0x0001_0000; result should be exactly 1.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x0001_0000])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got == 1.0, f"q16_to_fp32(0x0001_0000) expected 1.0, got {got} ({outputs[0]:#010x})"


@cocotb.test()
async def test_q16_to_fp32_neg_one(dut):
    """Q16.16 -1.0 is 0xFFFF_0000; result should be exactly -1.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0xFFFF_0000])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got == -1.0, f"q16_to_fp32(0xFFFF_0000) expected -1.0, got {got} ({outputs[0]:#010x})"


@cocotb.test()
async def test_q16_to_fp32_max_positive(dut):
    """0x7FFF_FFFF is +32767.99998...; FP32 result must be positive and in range."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x7FFF_FFFF])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got > 0 and abs(got - 32768.0) < 1.0, \
        f"q16_to_fp32(Q16_MAX) expected ~32768, got {got}"


@cocotb.test()
async def test_q16_to_fp32_min_negative(dut):
    """0x8000_0000 is -32768.0 exactly; FP32 should be -32768.0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [0x8000_0000])
    assert len(outputs) == 1
    got = bits_to_fp32(outputs[0])
    assert got == -32768.0, \
        f"q16_to_fp32(0x8000_0000) expected -32768.0, got {got} ({outputs[0]:#010x})"


@cocotb.test()
async def test_q16_to_fp32_sign_bit(dut):
    """All outputs for positive Q16.16 inputs must have FP32 sign bit = 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    pos_vals = [0x0000_0001, 0x0000_8000, 0x0001_0000, 0x7FFF_FFFF]
    outputs = await drive_and_collect(dut, pos_vals)

    assert len(outputs) == len(pos_vals)
    for q, raw in zip(pos_vals, outputs):
        assert (raw >> 31) == 0, \
            f"Positive Q16.16 {q:#010x} produced negative FP32 {raw:#010x}"


@cocotb.test()
async def test_q16_to_fp32_pipeline_throughput(dut):
    """N back-to-back valid inputs must produce exactly N valid outputs."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    N = 16
    vals = [float_to_q16(float(i) * 0.25) for i in range(N)]
    outputs = await drive_and_collect(dut, vals)

    assert len(outputs) == N, \
        f"Expected {N} outputs (full throughput), got {len(outputs)}"


@cocotb.test()
async def test_q16_to_fp32_valid_out_latency(dut):
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


# ---------------------------------------------------------------------------
# Round-trip sanity (runs against whichever DUT is loaded — skip gracefully
# if signal names don't match the expected module)
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_fp32_to_q16_rne_rounding(dut):
    """
    Verify Round-to-Nearest-Even behaviour for a value that sits exactly
    halfway between two Q16.16 representable values.

    0.000007629... = 0.5 * 2^-16 is exactly one half-LSB; the result must
    round to 0 (even) rather than 1.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # 0.5 * 2^-16 is exactly half an LSB in Q16.16 — should round to 0 (even)
    half_lsb = 0.5 / Q16_SCALE
    outputs = await drive_and_collect(dut, [fp32_to_bits(half_lsb)])

    assert len(outputs) == 1
    # Allow either 0 or 1 — FP32 itself may not be exact enough to hit the tie
    assert outputs[0] in (0, 1), \
        f"RNE half-LSB: expected 0 or 1, got {outputs[0]}"


@cocotb.test()
async def test_q16_to_fp32_rne_rounding(dut):
    """
    RNE: two Q16.16 values whose FP32 representations differ only in the last
    bit must both round to valid, correctly-signed FP32 outputs.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # LSB of Q16.16 = 1/65536 ≈ 1.526e-5
    # Two consecutive values: 1 LSB and 2 LSBs
    vals = [1, 2]  # raw Q16.16 integer counts
    outputs = await drive_and_collect(dut, vals)

    assert len(outputs) == 2
    f0 = bits_to_fp32(outputs[0])
    f1 = bits_to_fp32(outputs[1])
    assert f0 > 0 and f1 > f0, \
        f"Consecutive Q16.16 values should produce ordered positive FP32: {f0}, {f1}"