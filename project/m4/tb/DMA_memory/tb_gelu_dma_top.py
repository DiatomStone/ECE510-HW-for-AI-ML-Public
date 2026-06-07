import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ReadOnly
from cocotbext.axi import AxiLiteBus, AxiLiteMaster

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fp32_to_bytes(f):
    return struct.pack("<f", f)

def bytes_to_fp32(b):
    return struct.unpack("<f", b)[0]

def word_to_bytes(w):
    return struct.pack("<I", w)

def bytes_to_word(b):
    return struct.unpack("<I", b)[0]

async def init_dut(dut):
    dut.stream_enable.value     = 0
    dut.dma_in_awaddr.value     = 0
    dut.dma_in_awlen.value      = 0
    dut.dma_in_awvalid.value    = 0
    dut.dma_in_wdata.value      = 0
    dut.dma_in_wstrb.value      = 0xF
    dut.dma_in_wlast.value      = 0
    dut.dma_in_wvalid.value     = 0
    dut.dma_in_bready.value     = 0
    dut.dma_out_araddr.value    = 0
    dut.dma_out_arlen.value     = 0
    dut.dma_out_arvalid.value   = 0
    dut.dma_out_rready.value    = 0

async def reset_dut(dut):
    dut.rst.value = 1
    await Timer(50, unit="ns")
    dut.rst.value = 0
    await Timer(20, unit="ns")
    await RisingEdge(dut.clk)

# ---------------------------------------------------------------------------
# DMA helpers — AXI4-MM write (dma_in) and read (dma_out)
# ---------------------------------------------------------------------------

async def dma_write_burst(dut, data_words, strb_list=None):
    """Burst-write a list of 32-bit words into the input buffer.

    Handshake signals (awready/wready/bvalid) must be sampled in the ReadOnly
    phase. Reading them in the active region right after a RisingEdge can
    return stale pre-NBA values: just after the AW handshake, aw_state's
    IDLE->BURST update has not propagated, so wready reads 0, the wait loop
    burns an extra edge with wvalid held high, and the first beat is written
    twice (mem[1] == mem[0]).
    """
    if strb_list is None:
        strb_list = [0xF] * len(data_words)
    n = len(data_words)

    dut.dma_in_awaddr.value  = 0
    dut.dma_in_awlen.value   = n - 1
    dut.dma_in_awvalid.value = 1
    await ReadOnly()
    while not dut.dma_in_awready.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.dma_in_awvalid.value = 0

    for i, (data, strb) in enumerate(zip(data_words, strb_list)):
        dut.dma_in_wdata.value  = data
        dut.dma_in_wstrb.value  = strb
        dut.dma_in_wlast.value  = 1 if i == n - 1 else 0
        dut.dma_in_wvalid.value = 1
        await ReadOnly()
        while not dut.dma_in_wready.value:
            await RisingEdge(dut.clk)
            await ReadOnly()
        await RisingEdge(dut.clk)
    dut.dma_in_wvalid.value = 0
    dut.dma_in_wlast.value  = 0

    dut.dma_in_bready.value = 1
    await ReadOnly()
    while not dut.dma_in_bvalid.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.dma_in_bready.value = 0


async def dma_read_burst(dut, n_beats):
    """Burst-read n_beats 32-bit words from the output buffer."""
    data_out = []

    dut.dma_out_araddr.value  = 0
    dut.dma_out_arlen.value   = n_beats - 1
    dut.dma_out_arvalid.value = 1
    while not dut.dma_out_arready.value:
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.dma_out_arvalid.value = 0

    dut.dma_out_rready.value = 1
    while len(data_out) < n_beats:
        await RisingEdge(dut.clk)
        if dut.dma_out_rvalid.value:
            data_out.append(int(dut.dma_out_rdata.value))
            if dut.dma_out_rlast.value:
                break
    dut.dma_out_rready.value = 0
    return data_out

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_gelu_dma_small(dut):
    """End-to-end: 8 FP32 values through DMA buffers and GELU kernel."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    axil = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)

    # Enable kernel pipeline via AXI-Lite
    await axil.write(0x00, b'\x01\x00\x00\x00')
    rb = await axil.read(0x00, 4)
    assert rb.data == b'\x01\x00\x00\x00', "pipeline_enable readback failed"

    # Input values
    inputs = [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0]
    in_words = [bytes_to_word(fp32_to_bytes(v)) for v in inputs]

    # DMA write to input buffer
    await dma_write_burst(dut, in_words)

    # Enable streaming and wait for all outputs
    dut.stream_enable.value = 1

    # Wait enough cycles for pipeline (12) + buffer latency
    for _ in range(100):
        await RisingEdge(dut.clk)

    dut.stream_enable.value = 0

    # DMA read from output buffer
    results = await dma_read_burst(dut, len(inputs))
    assert len(results) == len(inputs), \
        f"expected {len(inputs)} results, got {len(results)}"

    # Verify with loose tolerance (PWL approximation)
    def gelu_ref(x):
        import math
        return x * 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    dut._log.info("=== GELU DMA small test results ===")
    for i, (word, inp) in enumerate(zip(results, inputs)):
        got = bytes_to_fp32(word_to_bytes(word))
        exp = gelu_ref(inp)
        err = abs(got - exp)
        dut._log.info(f"  [{i}] input={inp:6.2f}  expected={exp:.4f}  got={got:.4f}  err={err:.4f}")
        assert err < 0.05, f"input {inp}: error {err:.4f} exceeds threshold 0.05"

    dut._log.info("PASS: test_gelu_dma_small")


@cocotb.test()
async def test_gelu_dma_vectors(dut):
    """End-to-end co-simulation using gelu_in.hex / gelu_exp.hex vectors."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    axil = AxiLiteMaster(AxiLiteBus.from_prefix(dut, "s_axil"), dut.clk, dut.rst)

    # Load test vectors
    with open("tb/gelu_in.hex",  "r") as f:
        in_hex  = [l.strip() for l in f if l.strip()]
    with open("tb/gelu_exp.hex", "r") as f:
        exp_hex = [l.strip() for l in f if l.strip()]

    N = len(in_hex)
    dut._log.info(f"Loaded {N} test vectors")

    # Enable kernel
    await axil.write(0x00, b'\x01\x00\x00\x00')

    # Chunk DMA writes into 256-beat bursts (== the 256-deep mm2s/s2mm buffers)
    CHUNK = 256
    in_words = [int(h, 16) for h in in_hex]
    exp_words = [int(h, 16) for h in exp_hex]

    all_results = []

    for chunk_start in range(0, N, CHUNK):
        chunk = in_words[chunk_start : chunk_start + CHUNK]

        # Write chunk to input buffer
        await dma_write_burst(dut, chunk)

        # Enable stream and wait for pipeline to drain
        dut.stream_enable.value = 1
        wait_cycles = len(chunk) + 12 + 32  # pipeline + buffer margin
        for _ in range(wait_cycles):
            await RisingEdge(dut.clk)
        dut.stream_enable.value = 0

        # Read chunk from output buffer
        chunk_results = await dma_read_burst(dut, len(chunk))
        assert len(chunk_results) == len(chunk), \
            f"chunk {chunk_start}: expected {len(chunk)}, got {len(chunk_results)}"
        all_results.extend(chunk_results)

        dut._log.info(f"Chunk {chunk_start}–{chunk_start+len(chunk)-1} done")

    # Verify all results
    fail_count = 0
    max_err    = 0.0
    worst_idx  = 0

    for i, (got_word, exp_word) in enumerate(zip(all_results, exp_words)):
        got = bytes_to_fp32(word_to_bytes(got_word))
        exp = bytes_to_fp32(word_to_bytes(exp_word))
        err = abs(got - exp)
        if err > max_err:
            max_err   = err
            worst_idx = i
        if err > 0.05:
            fail_count += 1

    avg_err = sum(
        abs(bytes_to_fp32(word_to_bytes(g)) - bytes_to_fp32(word_to_bytes(e)))
        for g, e in zip(all_results, exp_words)
    ) / N

    dut._log.info("=== GELU DMA Co-Simulation Results ===")
    dut._log.info(f"  N         : {N}")
    dut._log.info(f"  Avg error : {avg_err:.6f}")
    dut._log.info(f"  Max error : {max_err:.6f}  (index {worst_idx})")
    dut._log.info(f"  Failures  : {fail_count} / {N}  (threshold 0.05)")
    dut._log.info("=======================================")

    assert fail_count == 0, \
        f"FAIL: {fail_count} outputs exceeded error threshold 0.05"
    dut._log.info("PASS: test_gelu_dma_vectors")
