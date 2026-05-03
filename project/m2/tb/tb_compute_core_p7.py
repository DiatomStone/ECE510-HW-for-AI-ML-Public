import cocotb
from cocotb.triggers import Timer, RisingEdge, FallingEdge
from cocotb.clock import Clock
import numpy as np

# --- Configuration Constants ---
PIPE_DEPTH = 7  # Matches system_diagram.png[cite: 9]
FRAC_BITS = 16  # Fractional bits used in compute_core.sv
TOLERANCE = 0.10 # 10% relative error tolerance[cite: 4]

def to_fixed(f, frac_bits):
    """Convert float to fixed-point integer."""
    return int(round(f * (1 << frac_bits)))

def from_fixed(val_handle, frac_bits):
    """Interpret cocotb handle as a signed float."""
    # Correctly call to_signed() on the cocotb value object[cite: 11]
    return float(val_handle.to_signed()) / (1 << frac_bits)

def reference_gelu(x):
    """Reference GELU implementation[cite: 9]."""
    c1 = 0.79788456
    c2 = 0.03567741
    tanh_in = c1 * x + c2 * (x**3)
    return 0.5 * x * (1.0 + np.tanh(tanh_in))

async def reset_dut(dut):
    dut.rst_n.value = 0
    await Timer(20, unit="ns") # Fixed: 'unit'[cite: 11, 13]
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

@cocotb.test()
async def test_gelu_7stage_pipeline(dut):
    """Verify 7-cycle latency with robust sampling."""
    cocotb.start_soon(Clock(dut.clk, 7.8, unit="ns").start()) # ~128 MHz[cite: 7]
    await reset_dut(dut)

    dut.valid_in.value = 1
    dut.x_in.value = to_fixed(1.0, FRAC_BITS)
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    # Wait for exactly 7 cycles[cite: 9]
    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)
    
    # Use FallingEdge to avoid race conditions[cite: 6, 11]
    await FallingEdge(dut.clk) 
    assert dut.valid_out.value == 1, "valid_out did not appear at cycle 7"
    dut._log.info("Pipeline latency: PASS")

@cocotb.test()
async def test_gelu_negative_accuracy(dut):
    """Verify accuracy for negative inputs (fixes the 43% error issue)."""
    cocotb.start_soon(Clock(dut.clk, 7.8, unit="ns").start())
    await reset_dut(dut)

    test_val = -1.5
    expected = reference_gelu(test_val) 
    
    dut.x_in.value = to_fixed(test_val, FRAC_BITS)
    dut.valid_in.value = 1
    await RisingEdge(dut.clk)
    dut.valid_in.value = 0

    for _ in range(PIPE_DEPTH):
        await RisingEdge(dut.clk)

    await FallingEdge(dut.clk)
    # Pass the handle directly to avoid AttributeError[cite: 13, 14]
    got = from_fixed(dut.gelu_out.value, FRAC_BITS)
    err = abs((got - expected) / expected) if expected != 0 else abs(got)

    dut._log.info(f"x={test_val} | expected={expected:.4f} | got={got:.4f} | err={err:.4f}")
    assert err < TOLERANCE, f"Accuracy failure at x={test_val}: err={err:.4f}"
