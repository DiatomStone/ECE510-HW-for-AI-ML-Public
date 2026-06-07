import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
import numpy as np

# -----------------------------------------------------------------------
# Constants and Reference Functions
# -----------------------------------------------------------------------
CONST_1    = 0.7978845608028654   # sqrt(2/pi)
CONST_2    = 0.03567740813630012  # CONST_1 * 0.044715
PIPE_DEPTH = 12                   # 3 x 4-stage pipeline: fp32_to_q16 | compute_core | q16_to_fp32

def gelu_ref(x_float):
    """Reference GELU using the same algebraic form as the hardware."""
    return 0.5 * x_float * (1.0 + np.tanh(CONST_1 * x_float + CONST_2 * x_float ** 3))

def fp32_to_bits(f: float) -> int:
    """Pack a Python float as IEEE-754 single-precision bits (uint32)."""
    return struct.unpack(">I", struct.pack(">f", f))[0]

def bits_to_fp32(bits: int) -> float:
    """Unpack IEEE-754 single-precision bits to a Python float."""
    return struct.unpack(">f", struct.pack(">I", int(bits) & 0xFFFF_FFFF))[0]

async def reset_dut(dut):
    """Drive reset for 5 cycles and clear inputs."""
    dut.rst.value      = 1
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst.value = 0

async def flush_pipeline(dut):
    """Clock PIPE_DEPTH extra cycles to drain remaining results."""
    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)

# -----------------------------------------------------------------------
# Test 1 — Reset
# -----------------------------------------------------------------------
@cocotb.test()
async def test_reset(dut):
    """After reset, valid_out and data_out must both be 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value      = 1
    dut.valid_in.value = 0
    dut.data_in.value  = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    assert int(dut.valid_out.value) == 0, "valid_out should be 0 after reset"
    assert int(dut.data_out.value)  == 0, "data_out should be 0 after reset"

# -----------------------------------------------------------------------
# Test 2 — High-Density Sweep & Error Characterization
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_sweep_error(dut):
    """Sweep -4.0 to 4.0 in 0.05 steps; report Max and Avg Error."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # 161 points: exact 0.05 intervals [-4.00 .. 4.00]
    test_inputs = np.linspace(-4.0, 4.0, 161)

    total_error = 0.0
    max_error   = 0.0
    worst_x     = 0.0

    dut.valid_in.value = 1

    for i, x_float in enumerate(test_inputs):
        dut.data_in.value = fp32_to_bits(x_float)
        await RisingEdge(dut.clk)

        # Output is valid PIPE_DEPTH cycles after the corresponding input
        if i >= PIPE_DEPTH:
            out_x    = test_inputs[i - PIPE_DEPTH]
            expected = gelu_ref(out_x)
            result   = bits_to_fp32(dut.data_out.value)
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
        result   = bits_to_fp32(dut.data_out.value)
        err      = abs(result - expected)
        total_error += err
        if err > max_error:
            max_error = err
            worst_x   = out_x

    avg_error = total_error / len(test_inputs)

    print("\n=== FP32 GELU Error Characterization (fp32 → PWL → fp32) ===")
    print(f"Points Tested : {len(test_inputs)}")
    print(f"Average Error : {avg_error:.6f}")
    print(f"Max Error     : {max_error:.6f}  (at x = {worst_x:.2f})")
    print("=============================================================\n")

    # 24-segment PWL + two FP32 conversions should stay under 0.05
    assert max_error < 0.05, f"Max error {max_error:.6f} exceeds 0.05 threshold!"

# -----------------------------------------------------------------------
# Test 3 — Edge Cases & Tail Clamping
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_edge_cases(dut):
    """
    Verify zero-crossing, saturation clamps, and extreme tails.
    compute_core clamps x < -3.0 to 0 and x >= 3.0 to linear passthrough.
    fp32_to_q16 clamps out-of-range FP32 before compute_core sees it.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # (input, expected_output, tolerance, description)
    cases = [
        ( 0.0,      0.0,              0.01, "zero"),
        (-0.01,     gelu_ref(-0.01),  0.02, "just below zero"),
        ( 0.01,     gelu_ref( 0.01),  0.02, "just above zero"),
        (-3.0,      gelu_ref(-3.0),   0.05, "exactly at negative clamp boundary"),
        (-3.5,      0.0,              0.05, "clamped negative tail (x < -3.0 → 0)"),
        (-10.0,     0.0,              0.05, "deep negative clamped to 0"),
        ( 3.0,      3.0,              0.05, "exactly at positive linear boundary"),
        ( 3.5,      3.5,              0.05, "linear positive tail passthrough"),
        ( 10.0,     10.0,             0.05, "deep positive passthrough"),
    ]

    for x_float, expected, tol, desc in cases:
        dut.valid_in.value = 1
        dut.data_in.value  = fp32_to_bits(x_float)
        await RisingEdge(dut.clk)
        dut.valid_in.value = 0
        await flush_pipeline(dut)

        result = bits_to_fp32(dut.data_out.value)
        err    = abs(result - expected)
        status = "PASS" if err < tol else "FAIL"
        print(f"[{status}] {desc:40s} x={x_float:8.2f} | exp={expected:10.4f} | got={result:10.4f} | err={err:.4f}")

        assert err < tol, \
            f"Edge case '{desc}' failed: x={x_float}, expected≈{expected:.4f}, got={result:.4f}"

# -----------------------------------------------------------------------
# Test 4 — Pipeline Valid Timing
# -----------------------------------------------------------------------
@cocotb.test()
async def test_valid_pipeline_timing(dut):
    """valid_out must assert exactly PIPE_DEPTH cycles after valid_in."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # Send a single valid pulse
    dut.valid_in.value = 1
    dut.data_in.value  = fp32_to_bits(1.0)
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    # valid_out must stay low for (PIPE_DEPTH - 1) cycles
    for i in range(PIPE_DEPTH - 1):
        await RisingEdge(dut.clk)
        assert int(dut.valid_out.value) == 0, \
            f"valid_out went high too early at cycle {i+1} (expected cycle {PIPE_DEPTH})"

    # valid_out must go high on exactly cycle PIPE_DEPTH
    await RisingEdge(dut.clk)
    assert int(dut.valid_out.value) == 1, \
        f"valid_out failed to assert on cycle {PIPE_DEPTH}"

    print(f"valid_out timing: exactly {PIPE_DEPTH} cycles — PASS")

# -----------------------------------------------------------------------
# Test 5 — High-Stress Streaming (no gaps)
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_streaming(dut):
    """Stream 100 random values back-to-back; verify no dropped samples."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    np.random.seed(42)
    inputs  = np.random.uniform(-3.5, 3.5, 100)
    outputs = []

    for x_float in inputs:
        dut.valid_in.value = 1
        dut.data_in.value  = fp32_to_bits(float(x_float))
        await RisingEdge(dut.clk)
        if int(dut.valid_out.value) == 1:
            outputs.append(bits_to_fp32(dut.data_out.value))

    dut.valid_in.value = 0

    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        if int(dut.valid_out.value) == 1:
            outputs.append(bits_to_fp32(dut.data_out.value))

    assert len(outputs) == len(inputs), \
        f"Sample count mismatch: sent {len(inputs)}, received {len(outputs)}"

    max_stream_err = 0.0
    for x_float, result in zip(inputs, outputs):
        expected = gelu_ref(x_float)
        err = abs(result - expected)
        if err > max_stream_err:
            max_stream_err = err

    print(f"Streamed {len(inputs)} samples — no drops. Max stream error: {max_stream_err:.6f}")
    assert max_stream_err < 0.05, \
        f"Streaming accuracy degraded: max error {max_stream_err:.6f}"

# -----------------------------------------------------------------------
# Test 6 — Segment Boundary Accuracy
# -----------------------------------------------------------------------
@cocotb.test()
async def test_segment_boundaries(dut):
    """
    Test values just inside each PWL segment boundary to catch
    off-by-one errors in the compute_core boundary decode logic.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # All segment boundaries from compute_core RTL
    boundaries = [-3.0, -2.5, -2.0, -1.5, -1.25, -1.0,
                  -0.75, -0.5, -0.25, 0.0,
                   0.25,  0.5,  0.75,  1.0,  1.25,  1.5, 2.0, 2.5, 3.0]

    epsilon = 1.0 / (2 ** 16)  # one Q16.16 LSB

    test_points = []
    for b in boundaries:
        test_points.append(b - epsilon)
        test_points.append(b)
        test_points.append(b + epsilon)

    errors            = []
    results_collected = []

    dut.valid_in.value = 1
    for i, x_float in enumerate(test_points):
        dut.data_in.value = fp32_to_bits(x_float)
        await RisingEdge(dut.clk)
        if i >= PIPE_DEPTH:
            out_x    = test_points[i - PIPE_DEPTH]
            expected = gelu_ref(out_x)
            result   = bits_to_fp32(dut.data_out.value)
            errors.append(abs(result - expected))
            results_collected.append((out_x, expected, result))

    dut.valid_in.value = 0
    for i in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        out_idx  = len(test_points) - PIPE_DEPTH + i
        out_x    = test_points[out_idx]
        expected = gelu_ref(out_x)
        result   = bits_to_fp32(dut.data_out.value)
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

# -----------------------------------------------------------------------
# Test 7 — FP32 Special Values
# -----------------------------------------------------------------------
@cocotb.test()
async def test_fp32_special_values(dut):
    """
    Verify behaviour for FP32 special inputs.
    +/-inf and large magnitudes are clamped by fp32_to_q16 before
    reaching compute_core, so output must be a finite clamped value.
    Zero and subnormals flush to zero through fp32_to_q16 FTZ.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await reset_dut(dut)

    # (raw FP32 bits or float, description, check_fn)
    cases = [
        (0.0,         "positive zero",    lambda r: r == 0.0),
        (-0.0,        "negative zero",    lambda r: r == 0.0),
        (0x00000001,  "smallest subnorm", lambda r: r == 0.0),   # FTZ → 0 → GELU(0) = 0
        (0x80000001,  "neg subnorm",      lambda r: r == 0.0),   # FTZ → 0 → GELU(0) = 0
        (1.0,         "one",              lambda r: abs(r - gelu_ref(1.0)) < 0.05),
        (-1.0,        "neg one",          lambda r: abs(r - gelu_ref(-1.0)) < 0.05),
    ]

    for val, desc, check in cases:
        # Accept raw int bits or float
        bits = val if isinstance(val, int) else fp32_to_bits(val)

        dut.valid_in.value = 1
        dut.data_in.value  = bits
        await RisingEdge(dut.clk)
        dut.valid_in.value = 0
        await flush_pipeline(dut)

        result = bits_to_fp32(dut.data_out.value)
        ok     = check(result)
        print(f"[{'PASS' if ok else 'FAIL'}] {desc:20s} → {result:.6f}")
        assert ok, f"Special value '{desc}' failed, got {result}"
