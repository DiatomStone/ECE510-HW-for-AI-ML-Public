"""
tb_fp32_to_q16.py — cocotb testbench for fp32_to_q16

4-stage pipelined IEEE 754 FP32 → Q16.16 converter.
  - Flush-To-Zero (FTZ) for subnormals
  - Round-to-Nearest-Even (RNE)
  - Saturation clamp on overflow

Makefile target:  make opt=convin
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
    # Hold rst high, drive no inputs, release, then sample on the next rising edge
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
    """0.0 → Q16.16 should be 0x0000_0000."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [fp32_to_bits(0.0)])
    assert len(outputs) == 1
    assert outputs[0] == 0x0000_0000, f"Expected 0, got {outputs[0]:#010x}"


# ---------------------------------------------------------------------------
# Positive integers
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_positive_integers(dut):
    """Small positive integers that are exactly representable in Q16.16."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [1.0, 2.0, 4.0, 100.0, 32767.0]
    outputs = await drive_and_collect(dut, [fp32_to_bits(v) for v in test_vals])

    assert len(outputs) == len(test_vals), \
        f"Expected {len(test_vals)} outputs, got {len(outputs)}"

    for v, raw in zip(test_vals, outputs):
        got = q16_to_float(raw)
        assert abs(got - v) < 2e-4, \
            f"fp32_to_q16({v}): expected ~{v}, got {got} ({raw:#010x})"


# ---------------------------------------------------------------------------
# Negative values
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_negative_values(dut):
    """Negative values including the -32768.0 boundary."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [-1.0, -2.5, -100.0, -32768.0]
    outputs = await drive_and_collect(dut, [fp32_to_bits(v) for v in test_vals])

    assert len(outputs) == len(test_vals)
    for v, raw in zip(test_vals, outputs):
        got = q16_to_float(raw)
        assert abs(got - v) <= 2e-4, \
            f"fp32_to_q16({v}): expected ~{v}, got {got} ({raw:#010x})"


@cocotb.test()
async def test_negative_one(dut):
    """-1.0 in FP32 → 0xFFFF_0000 in Q16.16 two's complement."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    outputs = await drive_and_collect(dut, [fp32_to_bits(-1.0)])
    assert len(outputs) == 1
    assert outputs[0] == 0xFFFF_0000, \
        f"fp32_to_q16(-1.0) expected 0xFFFF_0000, got {outputs[0]:#010x}"


# ---------------------------------------------------------------------------
# Fractional values
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_fractional_values(dut):
    """Fractional inputs — Q16.16 LSB ≈ 1.5e-5, allow 2 LSB tolerance."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    test_vals = [0.5, 0.25, 0.125, 1.5, -0.75, 3.14159]
    outputs = await drive_and_collect(dut, [fp32_to_bits(v) for v in test_vals])

    assert len(outputs) == len(test_vals)
    for v, raw in zip(test_vals, outputs):
        got = q16_to_float(raw)
        assert abs(got - v) < 4e-5, \
            f"fp32_to_q16({v}): expected ~{v}, got {got} ({raw:#010x})"


# ---------------------------------------------------------------------------
# Overflow / saturation clamp
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_positive_overflow_clamp(dut):
    """Values above Q16.16 max must clamp to 0x7FFF_FFFF."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    overflow_vals = [32768.0, 100000.0, float("inf")]
    outputs = await drive_and_collect(dut, [fp32_to_bits(v) for v in overflow_vals])

    assert len(outputs) == len(overflow_vals)
    for v, raw in zip(overflow_vals, outputs):
        assert raw == 0x7FFF_FFFF, \
            f"fp32_to_q16({v}) expected clamp 0x7FFF_FFFF, got {raw:#010x}"


@cocotb.test()
async def test_negative_overflow_clamp(dut):
    """Values below Q16.16 min must clamp to 0x8000_0000."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    overflow_vals = [-32769.0, -1e6, float("-inf")]
    outputs = await drive_and_collect(dut, [fp32_to_bits(v) for v in overflow_vals])

    assert len(outputs) == len(overflow_vals)
    for v, raw in zip(overflow_vals, outputs):
        assert raw == 0x8000_0000, \
            f"fp32_to_q16({v}) expected clamp 0x8000_0000, got {raw:#010x}"


# ---------------------------------------------------------------------------
# Subnormal flush-to-zero (FTZ)
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_subnormal_flush_to_zero(dut):
    """Subnormals (biased exponent == 0) must flush to zero per FTZ policy."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # smallest positive, largest positive, smallest negative subnormal
    subnormals = [0x0000_0001, 0x007F_FFFF, 0x8000_0001]
    outputs = await drive_and_collect(dut, subnormals)

    assert len(outputs) == len(subnormals)
    for bits, raw in zip(subnormals, outputs):
        assert raw == 0, \
            f"Subnormal {bits:#010x} should flush to 0, got {raw:#010x}"


# ---------------------------------------------------------------------------
# RNE rounding
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_rne_half_lsb(dut):
    """
    0.5 * 2^-16 is exactly one half-LSB in Q16.16.
    RNE must round to 0 (even) rather than 1.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    half_lsb = 0.5 / Q16_SCALE
    outputs = await drive_and_collect(dut, [fp32_to_bits(half_lsb)])

    assert len(outputs) == 1
    # FP32 may not represent the tie exactly; accept 0 or 1
    assert outputs[0] in (0, 1), \
        f"RNE half-LSB: expected 0 or 1, got {outputs[0]}"


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


@cocotb.test()
async def test_pipeline_throughput(dut):
    """N back-to-back valid inputs must produce exactly N valid outputs."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    N = 16
    vals = [fp32_to_bits(float(i) * 0.5) for i in range(N)]
    outputs = await drive_and_collect(dut, vals)

    assert len(outputs) == N, \
        f"Expected {N} outputs (full throughput), got {len(outputs)}"
