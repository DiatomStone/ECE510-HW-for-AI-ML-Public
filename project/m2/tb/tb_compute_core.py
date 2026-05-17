import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np

# -----------------------------------------------------------------------
# Constants and Reference Functions
# -----------------------------------------------------------------------
CONST_1 = 0.7978845608028654   # sqrt(2/pi)
CONST_2 = 0.03567740813630012  # CONST_1 * 0.044715
FRAC_BITS = 16
SCALE = 2 ** FRAC_BITS         # Q16.16 scale factor
PIPE_DEPTH = 4                 # 4-stage pipeline: boundary | coeff+dx | mult | add+sat

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
    val = int(val) & 0xFFFFFFFF
    if val >= (1 << 31):
        val -= (1 << 32)
    return val

async def reset_dut(dut):
    """Drive reset for 2 cycles and clear inputs."""
    dut.rst.value = 1
    dut.valid_in.value = 0
    dut.x.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

async def flush_pipeline(dut):
    """Clock PIPE_DEPTH extra cycles to drain remaining results."""
    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)

# -----------------------------------------------------------------------
# Test 1 — High-Density Sweep & Error Characterization
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_sweep_error(dut):
    """Sweep -4.0 to 4.0 in 0.05 steps; report Max and Avg Error."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # 161 points: exact 0.05 intervals [-4.00 .. 4.00]
    test_inputs = np.linspace(-4.0, 4.0, 161)

    total_error = 0.0
    max_error   = 0.0
    worst_x     = 0.0

    dut.valid_in.value = 1

    for i, x_float in enumerate(test_inputs):
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)

        # Output is valid PIPE_DEPTH cycles after the corresponding input
        if i >= PIPE_DEPTH:
            out_x    = test_inputs[i - PIPE_DEPTH]
            expected = gelu_ref(out_x)
            result   = to_float(signed32(dut.out.value))
            err      = abs(result - expected)
            total_error += err
            if err > max_error:
                max_error = err
                worst_x   = out_x

    dut.valid_in.value = 0

    # Drain the last PIPE_DEPTH results still in flight
    for i in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        out_idx  = len(test_inputs) - PIPE_DEPTH + i
        out_x    = test_inputs[out_idx]
        expected = gelu_ref(out_x)
        result   = to_float(signed32(dut.out.value))
        err      = abs(result - expected)
        total_error += err
        if err > max_error:
            max_error = err
            worst_x   = out_x

    avg_error = total_error / len(test_inputs)

    print("\n=== PWL Error Characterization (24-seg, 4-stage) ===")
    print(f"Points Tested : {len(test_inputs)}")
    print(f"Average Error : {avg_error:.6f}")
    print(f"Max Error     : {max_error:.6f}  (at x = {worst_x:.2f})")
    print("=====================================================\n")

    # 24-segment non-uniform PWL should comfortably stay under 0.05
    assert max_error < 0.05, f"Max error {max_error:.6f} exceeds 0.05 threshold!"

# -----------------------------------------------------------------------
# Test 2 — Saturation & Tail Clamping
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_edge_cases(dut):
    """
    Verify zero-crossing, saturation clamps, and extreme tails.
    Hardware clamps x < -3.0 to 0 and x >= 3.0 to linear (pass-through).
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Q16.16 input port is signed 32-bit: valid range ±32767.99998.
    # Any x where to_fixed(x) overflows 32-bit signed wraps at the port —
    # the stage-4 output saturator never sees it. x=40000 → 2.62B > 2.147B max,
    # wraps to a negative value, hits hits[0] clamp, outputs 0. Not a testable case.
    #
    # x < -3.0  → output clamped to 0       (m=0, b=0)
    # x >= 3.0  → linear passthrough        (m=1.0, b=0 — slope never amplifies)
    # Output saturator fires only if a future kernel produces amplified intermediates.
    # (input,  expected_output,  tolerance, description)
    cases = [
        ( 0.0,           0.0,              0.01, "zero"),
        (-0.01,          gelu_ref(-0.01),  0.02, "just below zero"),
        ( 0.01,          gelu_ref( 0.01),  0.02, "just above zero"),
        (-3.0,           gelu_ref(-3.0),   0.05, "exactly at negative clamp boundary"),
        (-3.5,           0.0,              0.05, "clamped negative tail (x < -3.0 → 0)"),
        (-10.0,          0.0,              0.05, "deep negative clamped to 0"),
        ( 3.0,           3.0,              0.05, "exactly at positive linear boundary"),
        ( 3.5,           3.5,              0.05, "linear positive tail passthrough"),
        ( 10.0,          10.0,             0.05, "deep positive passthrough"),
        ( 50.0,          50.0,             0.10, "large positive passthrough"),
        ( 32767.0,       32767.0,          0.10, "near positive input limit"),
        (-32767.0,       0.0,              0.10, "near negative input limit (clamped to 0)"),
    ]

    for x_float, expected, tol, desc in cases:
        dut.valid_in.value = 1
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)
        dut.valid_in.value = 0
        await flush_pipeline(dut)

        result = to_float(signed32(dut.out.value))
        err    = abs(result - expected)
        status = "PASS" if err < tol else "FAIL"
        print(f"[{status}] {desc:35s} x={x_float:8.2f} | exp={expected:10.4f} | got={result:10.4f} | err={err:.4f}")

        assert err < tol, \
            f"Edge case '{desc}' failed: x={x_float}, expected≈{expected:.4f}, got={result:.4f}"

# -----------------------------------------------------------------------
# Test 3 — Pipeline Valid Timing
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_valid_pipeline(dut):
    """valid_out must assert exactly PIPE_DEPTH cycles after valid_in."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Send a single valid pulse
    dut.valid_in.value = 1
    dut.x.value = to_fixed(1.0) & 0xFFFFFFFF
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    # valid_out must stay low for (PIPE_DEPTH - 1) cycles
    for i in range(PIPE_DEPTH - 1):
        await RisingEdge(dut.clk)
        assert dut.valid_out.value == 0, \
            f"valid_out went high too early at cycle {i+1} (expected cycle {PIPE_DEPTH})"

    # valid_out must go high on exactly cycle PIPE_DEPTH
    await RisingEdge(dut.clk)
    assert dut.valid_out.value == 1, \
        f"valid_out failed to assert on cycle {PIPE_DEPTH}"

    print(f"valid_out timing: exactly {PIPE_DEPTH} cycles — PASS")

# -----------------------------------------------------------------------
# Test 4 — High-Stress Streaming (no gaps)
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_streaming(dut):
    """Stream 100 random values back-to-back; verify no dropped samples."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    np.random.seed(42)
    inputs  = np.random.uniform(-3.5, 3.5, 100)
    outputs = []

    for x_float in inputs:
        dut.valid_in.value = 1
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)
        if dut.valid_out.value == 1:
            outputs.append(to_float(signed32(dut.out.value)))

    dut.valid_in.value = 0

    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        if dut.valid_out.value == 1:
            outputs.append(to_float(signed32(dut.out.value)))

    assert len(outputs) == len(inputs), \
        f"Sample count mismatch: sent {len(inputs)}, received {len(outputs)}"

    # Spot-check accuracy across the stream
    max_stream_err = 0.0
    for i, (x_float, result) in enumerate(zip(inputs, outputs)):
        expected = gelu_ref(x_float)
        err = abs(result - expected)
        if err > max_stream_err:
            max_stream_err = err

    print(f"Streamed {len(inputs)} samples — no drops. Max stream error: {max_stream_err:.6f}")
    assert max_stream_err < 0.05, \
        f"Streaming accuracy degraded: max error {max_stream_err:.6f}"

# -----------------------------------------------------------------------
# Test 5 — Segment Boundary Accuracy
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_segment_boundaries(dut):
    """
    Test values just inside each PWL segment boundary to catch
    off-by-one errors in the boundary decode logic.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # All segment boundaries from the RTL (in Q16.16: /65536 = float)
    boundaries = [-3.0, -2.5, -2.0, -1.5, -1.25, -1.0,
                  -0.75, -0.5, -0.25, 0.0,
                   0.25,  0.5,  0.75,  1.0,  1.25,  1.5, 2.0, 2.5, 3.0]

    epsilon = 1.0 / SCALE  # One LSB step above/below boundary

    test_points = []
    for b in boundaries:
        test_points.append(b - epsilon)  # just below
        test_points.append(b)            # exactly on
        test_points.append(b + epsilon)  # just above

    errors = []
    results_collected = []

    dut.valid_in.value = 1
    for i, x_float in enumerate(test_points):
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)
        if i >= PIPE_DEPTH:
            out_x    = test_points[i - PIPE_DEPTH]
            expected = gelu_ref(out_x)
            result   = to_float(signed32(dut.out.value))
            errors.append(abs(result - expected))
            results_collected.append((out_x, expected, result))

    dut.valid_in.value = 0
    for i in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        out_idx  = len(test_points) - PIPE_DEPTH + i
        out_x    = test_points[out_idx]
        expected = gelu_ref(out_x)
        result   = to_float(signed32(dut.out.value))
        errors.append(abs(result - expected))
        results_collected.append((out_x, expected, result))

    max_err = max(errors)
    print(f"\n=== Segment Boundary Check ({len(test_points)} points) ===")
    print(f"Max error at boundaries: {max_err:.6f}")
    for x_f, exp, got in results_collected:
        flag = " <-- WORST" if abs(got - exp) == max_err else ""
        print(f"  x={x_f:8.5f} | exp={exp:8.5f} | got={got:8.5f} | err={abs(got-exp):.6f}{flag}")

    assert max_err < 0.05, \
        f"Boundary accuracy failure: max error {max_err:.6f} at a segment edge"
