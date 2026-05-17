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
PIPE_DEPTH = 3                 # Updated to match new parallel PWL RTL

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
    """Drive reset and clear inputs."""
    dut.rst.value = 1
    dut.valid_in.value = 0
    dut.x.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

async def flush_pipeline(dut):
    """Wait enough cycles to clear the pipeline."""
    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)

# -----------------------------------------------------------------------
# Test 1 — High-Density Sweep & Error Characterization
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_sweep_error(dut):
    """Sweep from -4.0 to 4.0 in 0.05 steps to calculate Max and Avg Error."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # 161 points creates exact 0.05 intervals [-4.00, -3.95, ... 3.95, 4.00]
    test_inputs = np.linspace(-4.0, 4.0, 161)
    
    total_error = 0.0
    max_error = 0.0
    worst_case_x = 0.0
    
    dut.valid_in.value = 1
    
    for i, x_float in enumerate(test_inputs):
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)
        
        # Once the pipeline is full, we can start reading the outputs
        if i >= PIPE_DEPTH:
            out_idx = i - PIPE_DEPTH
            out_x = test_inputs[out_idx]
            expected = gelu_ref(out_x)
            result = to_float(signed32(dut.out.value))
            
            err = abs(result - expected)
            total_error += err
            if err > max_error:
                max_error = err
                worst_case_x = out_x

    dut.valid_in.value = 0
    
    # Drain the remaining values in the pipeline
    for i in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        out_idx = len(test_inputs) - PIPE_DEPTH + i
        out_x = test_inputs[out_idx]
        expected = gelu_ref(out_x)
        result = to_float(signed32(dut.out.value))
        
        err = abs(result - expected)
        total_error += err
        if err > max_error:
            max_error = err
            worst_case_x = out_x

    avg_error = total_error / len(test_inputs)
    
    print("\n=== PWL Error Characterization ===")
    print(f"Points Tested : {len(test_inputs)}")
    print(f"Average Error : {avg_error:.6f}")
    print(f"Max Error     : {max_error:.6f} (Occurred at x = {worst_case_x:.2f})")
    print("==================================\n")

    # Hardware target check: Max error shouldn't exceed typical PWL bounds (~0.05)
    assert max_error < 0.08, f"Max error {max_error} is too high!"

# -----------------------------------------------------------------------
# Test 2 — Deep Edge Cases & Saturation
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_edge_cases(dut):
    """Test zero crossing and extreme tails to ensure no overflow."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    sat_inputs = [0.0, -0.01, 0.01, 10.0, -10.0, 50.0, -50.0, 100.0, -100.0]

    for x_float in sat_inputs:
        dut.valid_in.value = 1
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)
        
        dut.valid_in.value = 0
        await flush_pipeline(dut)

        expected = gelu_ref(x_float) if abs(x_float) < 10 else (x_float if x_float > 0 else 0)
        result = to_float(signed32(dut.out.value))
        
        print(f"Edge Case x={x_float:7.2f} | expected={expected:7.4f} | got={result:7.4f}")
        
        # High tolerance for massive numbers, we just care that it didn't wrap around
        assert abs(result - expected) < 0.1, \
            f"Edge case failed at x={x_float}: expected {expected}, got {result}"

# -----------------------------------------------------------------------
# Test 3 — Pipeline Valid Timing
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_valid_pipeline(dut):
    """valid_out should appear exactly PIPE_DEPTH cycles after valid_in."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Assert valid_in for exactly one cycle
    dut.valid_in.value = 1
    dut.x.value = to_fixed(1.0) & 0xFFFFFFFF
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    # valid_out should be low for (PIPE_DEPTH - 1) cycles
    for i in range(PIPE_DEPTH - 1):
        await RisingEdge(dut.clk)
        assert dut.valid_out.value == 0, \
            f"valid_out went high too early at cycle {i+1} (expected {PIPE_DEPTH})"

    # valid_out should go high exactly on cycle PIPE_DEPTH
    await RisingEdge(dut.clk)
    assert dut.valid_out.value == 1, f"valid_out failed to assert on cycle {PIPE_DEPTH}"
    print(f"Pipeline valid_out timing exactly {PIPE_DEPTH} cycles: PASS")

# -----------------------------------------------------------------------
# Test 4 — High-Stress Streaming
# -----------------------------------------------------------------------
@cocotb.test()
async def test_gelu_streaming(dut):
    """Stream 50 random values back-to-back with zero gaps."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    np.random.seed(42) # Deterministic random
    inputs = np.random.uniform(-3.5, 3.5, 50)
    outputs = []

    # Stream inputs continuously
    for x_float in inputs:
        dut.valid_in.value = 1
        dut.x.value = to_fixed(x_float) & 0xFFFFFFFF
        await RisingEdge(dut.clk)
        
        # Collect outputs if valid
        if dut.valid_out.value == 1:
            outputs.append(to_float(signed32(dut.out.value)))

    dut.valid_in.value = 0

    # Flush the rest of the pipeline
    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
        if dut.valid_out.value == 1:
            outputs.append(to_float(signed32(dut.out.value)))

    assert len(outputs) == len(inputs), \
        f"Dropped data: sent {len(inputs)}, received {len(outputs)}"
        
    print(f"Successfully streamed {len(inputs)} overlapping cycles.")