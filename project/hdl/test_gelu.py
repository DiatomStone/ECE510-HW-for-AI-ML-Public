import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np

# -----------------------------------------------------------------------
# Reference GELU in Python (matches the algebraic optimization)
# -----------------------------------------------------------------------
CONST_1 = 0.7978845608028654   # sqrt(2/pi)
CONST_2 = 0.03567740813630012  # CONST_1 * 0.044715
FRAC_BITS = 16
SCALE = 2 ** FRAC_BITS         # Q16.16 scale factor


def gelu_ref(x_float):
    """Reference GELU using the same algebraic form as the hardware."""
    return 0.5 * x_float * (1.0 + np.tanh(CONST_1 * x_float + CONST_2 * x_float ** 3))


def to_fixed(x_float):
    """Convert float to Q16.16 signed integer."""
    return int(round(x_float * SCALE))


def to_float(x_fixed):
    """Convert Q16.16 signed integer to float."""
    return x_fixed / SCALE


def signed32(val):
    """Interpret a 32-bit value as signed."""
    if val >= (1 << 31):
        val -= (1 << 32)
    return val


async def reset_dut(dut):
    dut.rst.value = 1
    dut.valid_in.value = 0
    dut.x.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0


# -----------------------------------------------------------------------
# Test 1 — basic known values
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_known_values(dut):
    """Check GELU output against reference for known inputs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    test_inputs = [0.0, 1.0, -1.0, 2.0, -2.0, 0.5, -0.5]
    tolerance = 0.05  # 5% tolerance for PWL approximation

    for x_float in test_inputs:
        x_fixed = to_fixed(x_float)
        expected = gelu_ref(x_float)

        dut.valid_in.value = 1
        dut.x.value = x_fixed & 0xFFFFFFFF  # mask to 32 bits for cocotb

        # Wait for pipeline to flush (5 stages)
        for _ in range(5):
            await RisingEdge(dut.clk)

        dut.valid_in.value = 0

        # Wait for valid_out
        await RisingEdge(dut.clk)

        raw = dut.out.value.to_signed()
        result = to_float(raw)

        print(f"x={x_float:6.2f} | expected={expected:.4f} | got={result:.4f} | valid_out={dut.valid_out.value}")

        if abs(expected) > 1e-6:
            err = abs(result - expected) / abs(expected)
            assert err < tolerance, \
                f"x={x_float}: expected {expected:.4f}, got {result:.4f}, rel_err={err:.4f}"
        else:
            assert abs(result - expected) < 0.01, \
                f"x={x_float}: expected {expected:.4f}, got {result:.4f}"


# -----------------------------------------------------------------------
# Test 2 — saturation region (|x| >= 4)
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_saturation(dut):
    """Large inputs should saturate tanh to ±1."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    sat_inputs = [5.0, 8.0, -5.0, -8.0]
    tolerance = 0.1

    for x_float in sat_inputs:
        x_fixed = to_fixed(x_float)
        expected = gelu_ref(x_float)

        dut.valid_in.value = 1
        dut.x.value = x_fixed & 0xFFFFFFFF

        for _ in range(5):
            await RisingEdge(dut.clk)

        dut.valid_in.value = 0
        await RisingEdge(dut.clk)

        raw = dut.out.value.to_signed()
        result = to_float(raw)

        print(f"x={x_float:6.2f} | expected={expected:.4f} | got={result:.4f}")

        err = abs(result - expected)
        assert err < tolerance, \
            f"x={x_float}: expected {expected:.4f}, got {result:.4f}, abs_err={err:.4f}"


# -----------------------------------------------------------------------
# Test 3 — valid signal propagates correctly through pipeline
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_valid_pipeline(dut):
    """valid_out should appear exactly PIPE_DEPTH cycles after valid_in."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    PIPE_DEPTH = 5

    # Assert valid_in for one cycle
    dut.valid_in.value = 1
    dut.x.value = to_fixed(1.0)
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    # valid_out should be low for PIPE_DEPTH-1 cycles
    for i in range(PIPE_DEPTH - 1):
        await RisingEdge(dut.clk)
        assert dut.valid_out.value == 0, \
            f"valid_out went high too early at cycle {i+1}"

    # valid_out should be high on cycle PIPE_DEPTH
    await RisingEdge(dut.clk)
    assert dut.valid_out.value == 1, "valid_out never went high"
    print("valid_out timing: PASS")


# -----------------------------------------------------------------------
# Test 4 — zero input
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_zero(dut):
    """GELU(0) should be 0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    dut.valid_in.value = 1
    dut.x.value = 0

    for _ in range(5):
        await RisingEdge(dut.clk)

    dut.valid_in.value = 0
    await RisingEdge(dut.clk)

    raw = dut.out.value.to_signed()
    result = to_float(raw)

    print(f"GELU(0) = {result} (expected 0.0)")
    assert abs(result) < 0.01, f"GELU(0) should be 0, got {result}"


# -----------------------------------------------------------------------
# Test 5 — streaming throughput (back to back inputs)
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_streaming(dut):
    """Send multiple values back to back and collect outputs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    PIPE_DEPTH = 5
    tolerance  = 0.05
    inputs     = [0.5, 1.0, 1.5, 2.0, -0.5, -1.0, -1.5, -2.0]
    outputs    = []

    # Drive all inputs back to back
    for x_float in inputs:
        dut.valid_in.value = 1
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)

    dut.valid_in.value = 0

    # Collect outputs — flush pipeline
    for _ in range(PIPE_DEPTH + len(inputs)):
        await RisingEdge(dut.clk)
        if dut.valid_out.value == 1:
            raw = dut.out.value.to_signed()
            outputs.append(to_float(raw))

    print(f"Collected {len(outputs)} outputs from {len(inputs)} inputs")

    for i, (x_float, result) in enumerate(zip(inputs, outputs)):
        expected = gelu_ref(x_float)
        print(f"  [{i}] x={x_float:6.2f} expected={expected:.4f} got={result:.4f}")
        if abs(expected) > 1e-6:
            err = abs(result - expected) / abs(expected)
            assert err < tolerance, \
                f"x={x_float}: expected {expected:.4f}, got {result:.4f}, rel_err={err:.4f}"
