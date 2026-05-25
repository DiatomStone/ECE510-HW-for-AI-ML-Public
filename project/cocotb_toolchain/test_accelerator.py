import cocotb
from cocotb.triggers import Timer, RisingEdge

# --- Helper: Driving the Clock ---
async def generate_clock(dut):
    """Generate clock pulses."""
    for cycle in range(50):
        dut.clk.value = 0
        await Timer(1, units="ns")
        dut.clk.value = 1
        await Timer(1, units="ns")

# --- The Main Algorithm ---
@cocotb.test()
async def main_python_program(dut):
    """Your main Python program loop."""
    
    # 1. Start the clock background task
    cocotb.start_soon(generate_clock(dut))
    
    # 2. Reset the HDL hardware
    dut.rst.value = 1
    dut.start.value = 0
    dut.data_in.value = 0
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    
    # 3. Main Python Logic
    print("[Python] Starting heavy data processing pipeline...")
    input_data_vector = [10, 20, 30]
    results = []
    
    for value in input_data_vector:
        print(f"[Python] Sending data {value} to HDL accelerator...")
        
        # --- HOOK INTO HDL ---
        dut.data_in.value = value
        dut.start.value = 1
        await RisingEdge(dut.clk)
        dut.start.value = 0
        
        # Python pauses here and waits for the Verilog 'ready' signal
        while not dut.ready.value:
            await RisingEdge(dut.clk)
            
        # HDL returns control and data back to Python memory
        hardware_result = int(dut.data_out.value)
        print(f"[Python] Received accelerated result: {hardware_result}")
        results.append(hardware_result)
        # ---------------------
        
    # 4. Resume Pure Python Logic
    print(f"[Python] Processing complete. Final dataset: {results}")
    assert results == [50, 100, 150], "Acceleration failed!"
