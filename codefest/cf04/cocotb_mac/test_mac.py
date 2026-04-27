import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

@cocotb.test()
async def test_mac_basic(dut):
    # Fix: 'units' renamed to 'unit' in cocotb 2.0+
    clock = Clock(dut.clk, 10, unit="ns") 
    cocotb.start_soon(clock.start())

    # Reset Sequence
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    
    # Drive inputs
    dut.a.value = 3
    dut.b.value = 4
    
    # The first 'always' block update happens on the NEXT edge
    # So we wait for the edge that captures the data...
    await RisingEdge(dut.clk)
    
    # ...then we check the results
    for expected in [12, 24, 36]:
        # We need a small delay (Timer) or ReadOnly to see the 
        # effect of the edge that just occurred
        await Timer(1, unit="ps") 
        # Fix: '.signed_integer' renamed to '.to_signed()'
        actual = dut.out.value.to_signed()
        assert actual == expected, f"Expected {expected}, got {actual}"
        
        # Wait for the next edge to trigger the next accumulation
        if expected != 36: # Avoid extra wait on the last iteration
            await RisingEdge(dut.clk)

    # Final Reset check
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ps") 
    assert dut.out.value.to_signed() == 0

@cocotb.test()
async def test_mac_overflow(dut):
    """Check behavior when the accumulator approaches 2^31 - 1."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # 1. Reset the system
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    # 2. Force the accumulator to a value near 2^31 - 1
    # Max signed 32-bit is 2147483647
    near_max = 2147483640 
    dut.out.value = near_max
    
    # 3. Drive inputs that will cause an overflow
    # 3 * 4 = 12. Accumulator should become 2147483652, 
    # which exceeds 2147483647.
    dut.a.value = 3
    dut.b.value = 4
    
    await RisingEdge(dut.clk)
    await Timer(10, unit="ns") # Let the non-blocking assignment settle

    actual = dut.out.value.to_signed()
    
    # Logic: 2147483647 + 1 wraps to -2147483648
    # So 2147483640 + 12 should wrap to -2147483644
    expected_wrap = -2147483644
    
    cocotb.log.info(f"Value after overflow: {actual}")
    
    if actual == expected_wrap:
        cocotb.log.info("Design behavior: WRAP")
    else:
        cocotb.log.info("Design behavior: SATURATE")

    # Final check for Part A-2 documentation
    assert actual == expected_wrap, f"Expected wrap to {expected_wrap}, but got {actual}"
