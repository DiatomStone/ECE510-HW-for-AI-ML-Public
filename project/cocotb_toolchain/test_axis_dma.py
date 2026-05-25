import cocotb
from cocotb.triggers import Timer, RisingEdge
from cocotb.utils import get_sim_time
import time

from cocotbext.axi import AxiLiteMaster, AxiStreamSource, AxiStreamSink, AxiStreamBus, AxiLiteBus

async def generate_clock(dut):
    while True:
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await Timer(5, unit="ns")

@cocotb.test()
async def main_pure_axi_buffered_test(dut):
    # Start System Clock Engine and Clear Reset
    cocotb.start_soon(generate_clock(dut))
    dut.rst.value = 1
    await Timer(20, unit="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Initialize Interface Buses
    axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axi"), dut.clk, dut.rst)
    axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
    axis_sink   = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

    payload_data = [1, 2, 3, 4]
    print(f"\n[Host PC] Initial Dataset: {payload_data}")

    # STEP 1: Turn on the pipeline processing loop switch first
    print("[AXI-Lite Command] Activating pipeline processing channels (Reg 0x00 -> 1)...")
    await axil_master.write(0x00, 0x1)
    await RisingEdge(dut.clk)

    # STEP 2: Blast data packets into the chip memory streaming channels
    print("[AXI-Stream] Transmitting stream package data...")
    await axis_source.send(payload_data)

    # STEP 3: Read back the processed data straight from the output buffer
    print("[AXI-Stream] Collecting processed output stream elements...")
    returned_stream = await axis_sink.recv()
    processed_results = list(returned_stream.tdata)

    print("\n=======================================================")
    print("💎 COMPLIANT BUS PIPELINE REPORT")
    print("=======================================================")
    print(f"📥 Received Back From Chip via Master Stream: {processed_results}")
    print("=======================================================")

    assert processed_results == [5, 10, 15, 20], f"Data path logic error! Got: {processed_results}"
