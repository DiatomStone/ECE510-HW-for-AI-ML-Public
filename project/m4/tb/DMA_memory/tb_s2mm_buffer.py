import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotbext.axi import AxiStreamBus, AxiStreamSource
from cocotbext.axi import AxiStreamFrame

# ---------------------------------------------------------------------------
# AXI4-MM read helper — drives AR + collects R beats manually
# ---------------------------------------------------------------------------

async def init_dut(dut):
    dut.s_axis_tdata.value  = 0
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value  = 0
    dut.m_axi_araddr.value  = 0
    dut.m_axi_arlen.value   = 0
    dut.m_axi_arvalid.value = 0
    dut.m_axi_rready.value  = 0

async def reset_dut(dut):
    dut.rst.value = 1
    await Timer(50, unit="ns")
    dut.rst.value = 0
    await Timer(20, unit="ns")
    await RisingEdge(dut.clk)

async def axi_read_burst(dut, n_beats):
    """Drive one AXI4-MM read burst from s2mm_buffer.
    Returns list of 32-bit data words in order received.
    """
    data_out = []

    # AR channel — arready is combinationally high in AR_IDLE
    dut.m_axi_araddr.value  = 0
    dut.m_axi_arlen.value   = n_beats - 1
    dut.m_axi_arvalid.value = 1
    while not dut.m_axi_arready.value:
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)          # AR handshake completes
    dut.m_axi_arvalid.value = 0

    # R channel — collect all beats
    dut.m_axi_rready.value = 1
    while len(data_out) < n_beats:
        await RisingEdge(dut.clk)
        if dut.m_axi_rvalid.value:
            data_out.append(int(dut.m_axi_rdata.value))
            if dut.m_axi_rlast.value:
                break

    dut.m_axi_rready.value = 0
    return data_out

async def stream_send(dut, words):
    """Send a list of 32-bit words over the AXI-Stream slave port."""
    import struct
    payload = b"".join(struct.pack("<I", w) for w in words)
    frame = AxiStreamFrame(payload)
    frame.tdata = payload
    # drive manually to keep strobe/tlast control simple
    for i, word in enumerate(words):
        dut.s_axis_tdata.value  = word
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tlast.value  = 1 if i == len(words) - 1 else 0
        while not dut.s_axis_tready.value:
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)   # beat accepted
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value  = 0

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_single_beat_then_read(dut):
    """Stream one word in, read it back via AXI-MM."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    await stream_send(dut, [0xDEAD_BEEF])

    result = await axi_read_burst(dut, 1)
    assert len(result) == 1, f"expected 1 beat, got {len(result)}"
    assert result[0] == 0xDEAD_BEEF, \
        f"expected 0xDEADBEEF, got 0x{result[0]:08X}"
    dut._log.info(f"single beat: 0x{result[0]:08X} OK")
    dut._log.info("PASS: test_single_beat_then_read")


@cocotb.test()
async def test_burst_stream_then_burst_read(dut):
    """Stream 8 words in, read all 8 back as a burst."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    payload = [0xB000_0000 + i for i in range(8)]
    await stream_send(dut, payload)

    result = await axi_read_burst(dut, 8)
    assert len(result) == 8, f"expected 8 beats, got {len(result)}"
    for i, (exp, got) in enumerate(zip(payload, result)):
        assert got == exp, f"beat {i}: expected 0x{exp:08X}, got 0x{got:08X}"
        dut._log.info(f"beat {i}: 0x{got:08X} OK")

    dut._log.info("PASS: test_burst_stream_then_burst_read")


@cocotb.test()
async def test_backpressure_to_kernel(dut):
    """Fill the FIFO; verify s_axis_tready deasserts when full."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    # Stream in 1024 beats (full depth) without DMA reading
    payload = list(range(1024))
    await stream_send(dut, payload)

    # One more beat — tready should now be low (FIFO full)
    dut.s_axis_tdata.value  = 0xFFFF_FFFF
    dut.s_axis_tvalid.value = 1
    await RisingEdge(dut.clk)
    assert not dut.s_axis_tready.value, \
        "s_axis_tready should be deasserted when FIFO is full"
    dut.s_axis_tvalid.value = 0

    dut._log.info("tready correctly deasserted on full FIFO")

    # Drain via DMA and verify order
    result = await axi_read_burst(dut, 256)
    assert len(result) == 256
    for i, (exp, got) in enumerate(zip(payload[:256], result)):
        assert got == exp, f"beat {i}: expected 0x{exp:08X}, got 0x{got:08X}"

    dut._log.info("PASS: test_backpressure_to_kernel")


@cocotb.test()
async def test_simultaneous_fill_drain(dut):
    """Kernel streams in while DMA reads out concurrently."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    payload = [0xD000_0000 + i for i in range(32)]

    # Pre-load some data so DMA has something to read immediately
    await stream_send(dut, payload[:8])

    # Start DMA read and kernel stream concurrently
    read_task  = cocotb.start_soon(axi_read_burst(dut, 32))
    write_task = cocotb.start_soon(stream_send(dut, payload[8:]))

    await write_task
    result = await read_task

    assert len(result) == 32, f"expected 32 beats, got {len(result)}"
    for i, (exp, got) in enumerate(zip(payload, result)):
        assert got == exp, f"beat {i}: expected 0x{exp:08X}, got 0x{got:08X}"

    dut._log.info("PASS: test_simultaneous_fill_drain")


@cocotb.test()
async def test_rlast(dut):
    """Verify rlast is asserted on the final beat of each read burst."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    await stream_send(dut, list(range(16)))

    # Issue two back-to-back 8-beat reads; rlast must fire on beat 8 of each
    for burst_idx in range(2):
        dut.m_axi_araddr.value  = 0
        dut.m_axi_arlen.value   = 7   # 8 beats
        dut.m_axi_arvalid.value = 1
        while not dut.m_axi_arready.value:
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        dut.m_axi_arvalid.value = 0

        dut.m_axi_rready.value = 1
        beats_seen = 0
        rlast_idx  = -1
        timeout = 256
        while timeout > 0:
            await RisingEdge(dut.clk)
            if dut.m_axi_rvalid.value and dut.m_axi_rready.value:
                if dut.m_axi_rlast.value:
                    rlast_idx = beats_seen
                beats_seen += 1
                if beats_seen == 8:
                    break
            timeout -= 1

        dut.m_axi_rready.value = 0

        assert rlast_idx == 7, \
            f"burst {burst_idx}: rlast at beat {rlast_idx}, expected 7"
        dut._log.info(f"burst {burst_idx}: rlast correctly on beat 7")

    dut._log.info("PASS: test_rlast")
