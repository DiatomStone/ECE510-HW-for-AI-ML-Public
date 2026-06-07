import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

# ---------------------------------------------------------------------------
# Memory map — simulates the DMA buffer a PCIe/DMA backend would use
# ---------------------------------------------------------------------------
MEM_SIZE    = 0x0002_0000   # 128 KB
INPUT_BASE  = 0x0000_0000   # host DMA writes input FP32 vectors here
OUTPUT_BASE = 0x0001_0000   # DMA writes GELU results back here

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def hex_to_bytes_le(hex_str):
    return struct.pack('<I', int(hex_str, 16))

def bytes_le_to_float(b):
    return struct.unpack('<f', b)[0]

# ---------------------------------------------------------------------------
# DMA coroutines — the "DMA controller" that moves data between memory and
# the AXI-Stream ports of gelu_top
# ---------------------------------------------------------------------------
async def dma_to_stream(mem, base_addr, n_beats, axis_source, log):
    """Read n_beats × 4 bytes from mem starting at base_addr and stream to DUT."""
    payload = bytes(mem[base_addr : base_addr + n_beats * 4])
    log.info(f"DMA → stream: {n_beats} beats from mem[0x{base_addr:08X}]")
    await axis_source.write(payload)
    log.info("DMA → stream: transfer complete")

async def dma_from_stream(mem, base_addr, axis_sink, log):
    """Receive one AXI-Stream frame from DUT and write it back to mem at base_addr."""
    log.info(f"DMA ← stream: waiting for output frame → mem[0x{base_addr:08X}]")
    frame = await axis_sink.recv()
    data  = bytes(frame.tdata)
    mem[base_addr : base_addr + len(data)] = data
    log.info(f"DMA ← stream: {len(data)} bytes ({len(data)//4} beats) written to memory")

# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_gelu_top(dut):
    """End-to-end co-simulation of gelu_top via a memory-mapped DMA path.

    Flow:
      Region 1 — AXI-Lite: configure pipeline_enable via control register
      Region 2 — Host DMA write: pack input vectors into the DMA memory buffer
      Region 3 — DMA transfer: memory → AXI-Stream → DUT (concurrent with
                 DUT → AXI-Stream → memory write-back)
      Region 4 — Host DMA read: read results from memory buffer and verify
    """

    # -----------------------------------------------------------------------
    # Clock and reset
    # -----------------------------------------------------------------------
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    await Timer(50, unit="ns")
    dut.rst.value = 0
    await Timer(50, unit="ns")
    await RisingEdge(dut.clk)

    # -----------------------------------------------------------------------
    # AXI VIPs
    # -----------------------------------------------------------------------
    axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)
    axis_source = AxiStreamSource(AxiStreamBus.from_prefix(dut, "s_axis"), dut.clk, dut.rst)
    axis_sink   = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

    # -----------------------------------------------------------------------
    # Load test vectors from gen_vectors.py output
    # -----------------------------------------------------------------------
    with open("tb/gelu_in.hex",  "r") as f:
        in_hex  = [l.strip() for l in f if l.strip()]
    with open("tb/gelu_exp.hex", "r") as f:
        exp_hex = [l.strip() for l in f if l.strip()]

    N = len(in_hex)

    # -----------------------------------------------------------------------
    # Allocate DMA memory buffer
    # -----------------------------------------------------------------------
    mem = bytearray(MEM_SIZE)

    # -----------------------------------------------------------------------
    # Region 1: AXI-Lite — enable pipeline
    # -----------------------------------------------------------------------
    dut._log.info("Region 1: AXI-Lite control — writing pipeline_enable=1")
    await axil_master.write(0x00, b'\x01\x00\x00\x00')
    readback = await axil_master.read(0x00, 4)
    assert readback.data == b'\x01\x00\x00\x00', \
        f"AXI-Lite readback failed: got {readback.data}"
    dut._log.info("pipeline_enable=1 verified via AXI-Lite readback.")

    # -----------------------------------------------------------------------
    # Region 2: Host DMA write — input vectors → memory
    # -----------------------------------------------------------------------
    dut._log.info(f"Region 2: Host DMA write — {N} FP32 values → mem[0x{INPUT_BASE:08X}]")
    for i, h in enumerate(in_hex):
        chunk = hex_to_bytes_le(h)
        mem[INPUT_BASE + i*4 : INPUT_BASE + i*4 + 4] = chunk
    dut._log.info(f"Region 2: {N * 4} bytes staged in DMA memory buffer")

    # -----------------------------------------------------------------------
    # Region 3: DMA transfer — memory ↔ AXI-Stream ↔ DUT
    # Send and receive run concurrently: the receive coroutine must be armed
    # before data arrives at m_axis or beats can be lost.
    # -----------------------------------------------------------------------
    dut._log.info("Region 3: DMA transfer start — send and receive running concurrently")
    recv_task = cocotb.start_soon(dma_from_stream(mem, OUTPUT_BASE, axis_sink,   dut._log))
    send_task = cocotb.start_soon(dma_to_stream  (mem, INPUT_BASE, N, axis_source, dut._log))
    await send_task
    await recv_task
    dut._log.info("Region 3: DMA transfer complete")

    # -----------------------------------------------------------------------
    # Region 4: Host DMA read — results from memory → verification
    # -----------------------------------------------------------------------
    dut._log.info(f"Region 4: Host DMA read — verifying {N} results from mem[0x{OUTPUT_BASE:08X}]")

    fail_count = 0
    max_err    = 0.0
    worst_idx  = 0
    avg_err    = 0.0

    for i in range(N):
        b_chunk = bytes(mem[OUTPUT_BASE + i*4 : OUTPUT_BASE + i*4 + 4])
        got_r   = bytes_le_to_float(b_chunk)
        exp_r   = bytes_le_to_float(hex_to_bytes_le(exp_hex[i]))
        err_r   = abs(got_r - exp_r)
        avg_err += err_r
        if err_r > max_err:
            max_err   = err_r
            worst_idx = i
        if err_r > 0.05:
            fail_count += 1

    avg_err /= float(N)

    dut._log.info("\n=== GELU Co-Simulation Results ===")
    dut._log.info("  Kernel    : M1 small-config FFN layer-0, batch=0, token=0")
    dut._log.info(f"  N         : {N}  (d_ff=256, seed=42)")
    dut._log.info(f"  Avg error : {avg_err:f}")
    dut._log.info(f"  Max error : {max_err:f}  (index {worst_idx})")
    worst_in_f  = bytes_le_to_float(hex_to_bytes_le(in_hex[worst_idx]))
    dut._log.info(f"  Input[{worst_idx}] : 0x{in_hex[worst_idx]}  ({worst_in_f:f})")
    worst_got_b = bytes(mem[OUTPUT_BASE + worst_idx*4 : OUTPUT_BASE + worst_idx*4 + 4])
    dut._log.info(f"  Got[{worst_idx}]   : 0x{worst_got_b.hex()}  ({bytes_le_to_float(worst_got_b):f})")
    dut._log.info(f"  Exp[{worst_idx}]   : 0x{exp_hex[worst_idx]}  ({bytes_le_to_float(hex_to_bytes_le(exp_hex[worst_idx])):f})")
    dut._log.info(f"  Failures  : {fail_count} / {N}  (threshold 0.05)")
    dut._log.info("==================================\n")

    if fail_count == 0:
        print("PASS")
        dut._log.info("PASS")
    else:
        print(f"FAIL: {fail_count} outputs exceeded error threshold 0.05")
        dut._log.error(f"FAIL: {fail_count} outputs exceeded error threshold 0.05")
        assert False, "Simulation failed due to accuracy threshold."
