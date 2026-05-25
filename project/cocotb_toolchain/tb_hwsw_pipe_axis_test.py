import cocotb
from cocotb.triggers import Timer, RisingEdge
from cocotb.utils import get_sim_time
import time
import struct

# High-performance AXI-Stream simulation abstractions
from cocotbext.axi import AxiStreamSource, AxiStreamSink, AxiStreamBus

async def generate_clock(dut):
    """Generate a standard 100MHz clock (10ns period)."""
    while True:
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

@cocotb.test()
async def main_python_algorithm(dut):
    """Main Python routine that executes an algorithm via AXI-Stream."""
    
    # 1. Initialize Clock and Hardware Reset Channels
    cocotb.start_soon(generate_clock(dut))
    dut.rst.value = 1
    await Timer(20, unit="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # 2. Hook up Cocotb's AXI-Stream drivers straight to the Accelerator Ports
    axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
    axis_sink   = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

    # 3. Running a Software Python Algorithm
    print("\n[Python Step 1] Executing raw software algorithm...")
    input_vector = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    print(f"📦 Source Data Array created in Python RAM: {input_vector}")

    # =========================================================================
    # HOOK INTO HDL: Start Performance Timers and Stream over AXI-Stream
    # =========================================================================
    print("\n[Python Step 2] Offloading calculation payload to HDL via AXI-Stream...")
    await axis_source.send(input_vector)
    
    start_wall_time = time.perf_counter()
    start_sim_time  = get_sim_time(unit='ns')

    print("[Python Step 3] Awaiting accelerated streaming payload from hardware...")
    returned_packet = await axis_sink.recv()
    
    end_wall_time = time.perf_counter()
    end_sim_time  = get_sim_time(unit='ns')
    # =========================================================================

    # 4. Data Extraction using straight index casting
    print("\n[Python Step 4] Resuming main program. Processing return metrics...")
    
    # Extract the raw bytes array from the frame object container
    raw_bytes = returned_packet.tdata
    
    # Map each single byte index directly back to a Python integer list
    unfiltered_results = [int(b) for b in raw_bytes]
    
    # Enforce strict length matching to remove trailing padding elements
    accelerated_results = unfiltered_results[:len(input_vector)]

    # Benchmarking calculations
    sim_ns_elapsed = end_sim_time - start_sim_time
    wall_seconds   = end_wall_time - start_wall_time

    print("\n=======================================================")
    print("📈 AXI-STREAM DIRECT HOOK BENCHMARK REPORT")
    print("=======================================================")
    print(f"📥 Received Array (Cleaned) : {accelerated_results}")
    print(f"⏱️  Hardware Time             : {sim_ns_elapsed} ns")
    print(f"💻 Wall-Clock Time           : {wall_seconds:.6f} seconds")
    print("=======================================================")

    # Verify correctness
    expected_results = [x * 5 for x in input_vector]
    assert accelerated_results == expected_results, f"Mismatch! Got {accelerated_results}, Expected {expected_results}"
    print("✅ Success! Hardware acceleration math matches software expectations.")
