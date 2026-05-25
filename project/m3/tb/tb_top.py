import os
import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

def hex_to_bytes_le(hex_str):
    """Converts a 32-bit hex string to a little-endian byte array for AXI."""
    val = int(hex_str, 16)
    return struct.pack('<I', val)

def bytes_le_to_float(b_chunk):
    """Decodes 4 little-endian AXI bytes directly into an IEEE-754 FP32 float."""
    return struct.unpack('<f', b_chunk)[0]

@cocotb.test()
async def test_gelu_top(dut):
    """End-to-end black-box test of gelu_top using AXI VIPs."""

    # 1. Clock and Reset Setup
    clock = Clock(dut.clk, 10, units="ns")  # 100 MHz
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    await Timer(50, units="ns")
    dut.rst.value = 0
    await Timer(50, units="ns")
    await RisingEdge(dut.clk)

    # 2. Instantiate AXI Verification IPs
    axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)
    axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
    axis_sink   = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

    # 3. Load independent test vectors
    # Assumes execution from the project root (e.g., project/m3/)
    in_hex, exp_hex = [], []
    with open("tb/gelu_in.hex", "r") as f:
        in_hex = [l.strip() for l in f.readlines() if l.strip()]
    with open("tb/gelu_exp.hex", "r") as f:
        exp_hex = [l.strip() for l in f.readlines() if l.strip()]
        
    N = len(in_hex) # Should be 256 for M1 small-config FFN layer-0

    # 4. Region 1: AXI-Lite Configuration
    dut._log.info("Region 1: AXI-Lite control transaction")
    # Write pipeline_enable = 1 to offset 0x00 (little-endian byte array)
    await axil_master.write(0x00, b'\x01\x00\x00\x00')
    
    readback = await axil_master.read(0x00, 4)
    assert readback.data == b'\x01\x00\x00\x00', f"AXI-Lite readback failed: got {readback.data}"
    dut._log.info("pipeline_enable=1 verified via AXI-Lite readback.")

    # 5. Region 2: Stream Inputs
    dut._log.info(f"Region 2: streaming {N} FP32 beats into DUT")
    
    # Pack all N inputs into a continuous byte array.
    # AxiStreamSource writes these as 32-bit (4 byte) beats and automatically 
    # asserts TLAST on the final beat of the frame.
    input_bytes = bytearray()
    for h in in_hex:
        input_bytes.extend(hex_to_bytes_le(h))
        
    await axis_source.write(input_bytes)

    # 6. Region 3: AXI-Stream Output Capture
    dut._log.info("Region 3: Waiting for output beats...")
    # .recv() blocks until a full frame (terminated by TLAST) is received and returns AxiStreamFrame
    out_frame = await axis_sink.recv()
    out_bytes = out_frame.tdata
    
    dut._log.info(f"Received frame length: {len(out_bytes)} bytes ({len(out_bytes)//4} beats)")

    # 7. Verification and Formatting
    fail_count = 0
    max_err = 0.0
    worst_idx = 0
    avg_err = 0.0

    for i in range(N):
        # Extract the 4 bytes for this specific output beat
        b_chunk = out_bytes[i*4 : (i+1)*4]
        
        got_r = bytes_le_to_float(b_chunk)
        exp_r = bytes_le_to_float(hex_to_bytes_le(exp_hex[i]))
        
        err_r = abs(got_r - exp_r)
        avg_err += err_r

        if err_r > max_err:
            max_err = err_r
            worst_idx = i

        if err_r > 0.05:
            fail_count += 1
            
    avg_err /= float(N)

    # Print summary table matching your previous SV formatting
    dut._log.info("\n=== GELU Co-Simulation Results ===")
    dut._log.info("  Kernel    : M1 small-config FFN layer-0, batch=0, token=0")
    dut._log.info(f"  N         : {N}  (d_ff=256, seed=42)")
    dut._log.info(f"  Avg error : {avg_err:f}")
    dut._log.info(f"  Max error : {max_err:f}  (index {worst_idx})")
    
    worst_in_f = bytes_le_to_float(hex_to_bytes_le(in_hex[worst_idx]))
    dut._log.info(f"  Input[{worst_idx}] : 0x{in_hex[worst_idx]}  ({worst_in_f:f})")
    
    worst_got_b = out_bytes[worst_idx*4 : (worst_idx+1)*4]
    dut._log.info(f"  Got[{worst_idx}]   : 0x{worst_got_b.hex()}  ({bytes_le_to_float(worst_got_b):f})")
    dut._log.info(f"  Exp[{worst_idx}]   : 0x{exp_hex[worst_idx]}  ({bytes_le_to_float(hex_to_bytes_le(exp_hex[worst_idx])):f})")
    dut._log.info(f"  Failures  : {fail_count} / {N}  (threshold 0.05)")
    dut._log.info("==================================\n")

    # Final Pass/Fail requirement
    if fail_count == 0:
        print("PASS") # Required for terminal scraper
        dut._log.info("PASS")
    else:
        print(f"FAIL: {fail_count} outputs exceeded error threshold 0.05")
        dut._log.error(f"FAIL: {fail_count} outputs exceeded error threshold 0.05")
        assert False, "Simulation failed due to accuracy threshold."