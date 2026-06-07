import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ReadOnly
from cocotbext.axi import AxiStreamBus, AxiStreamSink

# ---------------------------------------------------------------------------
# AXI4-MM write helper — drives AW + W + B channels manually
# ---------------------------------------------------------------------------

async def init_dut(dut):
    dut.s_axi_awaddr.value  = 0
    dut.s_axi_awlen.value   = 0
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wdata.value   = 0
    dut.s_axi_wstrb.value   = 0xF
    dut.s_axi_wvalid.value  = 0
    dut.s_axi_wlast.value   = 0
    dut.s_axi_bready.value  = 0
    dut.stream_enable.value = 0

async def reset_dut(dut):
    dut.rst.value = 1
    await Timer(50, unit="ns")
    dut.rst.value = 0
    await Timer(20, unit="ns")
    await RisingEdge(dut.clk)

async def axi_write_burst(dut, data_words, strb_list=None):
    """Drive one AXI4-MM write burst into mm2s_buffer.
    awlen is derived from len(data_words) - 1.

    Handshake signals (awready/wready/bvalid) are sampled in the ReadOnly
    phase. Reading them in the active region right after a RisingEdge can
    return stale pre-NBA values: just after the AW handshake, aw_state's
    IDLE->BURST update has not propagated, so wready reads 0, the wait loop
    burns an extra edge with wvalid held high, and the first beat is written
    twice (mem[1] == mem[0]). ReadOnly sampling sees settled values.
    """
    if strb_list is None:
        strb_list = [0xF] * len(data_words)
    n = len(data_words)

    # AW channel — awready is combinationally high in IDLE
    dut.s_axi_awaddr.value  = 0
    dut.s_axi_awlen.value   = n - 1
    dut.s_axi_awvalid.value = 1
    await ReadOnly()
    while not dut.s_axi_awready.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)      # AW handshake consumed here
    dut.s_axi_awvalid.value = 0

    # W channel — send one beat at a time, respect wready backpressure
    for idx, (data, strb) in enumerate(zip(data_words, strb_list)):
        dut.s_axi_wdata.value  = data
        dut.s_axi_wstrb.value  = strb
        dut.s_axi_wlast.value  = 1 if idx == n - 1 else 0
        dut.s_axi_wvalid.value = 1
        await ReadOnly()
        while not dut.s_axi_wready.value:
            await RisingEdge(dut.clk)
            await ReadOnly()
        await RisingEdge(dut.clk)  # beat consumed here
    dut.s_axi_wvalid.value = 0
    dut.s_axi_wlast.value  = 0

    # B channel — collect response
    dut.s_axi_bready.value = 1
    await ReadOnly()
    while not dut.s_axi_bvalid.value:
        await RisingEdge(dut.clk)
        await ReadOnly()
    await RisingEdge(dut.clk)
    dut.s_axi_bready.value = 0

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_single_beat(dut):
    """Write one word via AXI-MM, stream it out, verify value and tlast."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    sink = AxiStreamSink(AxiStreamBus.from_prefix(dut, "m_axis"), dut.clk, dut.rst)

    await axi_write_burst(dut, [0xDEAD_BEEF])

    dut.stream_enable.value = 1
    frame = await sink.recv()
    dut.stream_enable.value = 0

    got = int.from_bytes(frame.tdata, "little")
    assert got == 0xDEAD_BEEF, f"expected 0xDEADBEEF, got 0x{got:08X}"
    dut._log.info(f"single beat: 0x{got:08X} OK")
    dut._log.info("PASS: test_single_beat")


@cocotb.test()
async def test_burst_write_drain(dut):
    """Write an 8-beat burst via AXI-MM, drain all 8 beats via AXI-Stream."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    # Drive tready directly — no AxiStreamSink to avoid VPI-NBA race
    dut.m_axis_tready.value = 1

    payload = [0xA000_0000 + i for i in range(8)]
    await axi_write_burst(dut, payload)

    dut.stream_enable.value = 1

    # Sample in ReadOnly phase (after NBA settles) so registered values are stable
    received = []
    timeout = 128
    while len(received) < 8 and timeout > 0:
        await ReadOnly()
        if dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1:
            received.append(int(dut.m_axis_tdata.value))
        await RisingEdge(dut.clk)
        timeout -= 1

    dut.stream_enable.value = 0

    assert len(received) == 8, f"only got {len(received)} beats"
    for i, (exp, got) in enumerate(zip(payload, received)):
        assert got == exp, f"beat {i}: expected 0x{exp:08X}, got 0x{got:08X}"
        dut._log.info(f"beat {i}: 0x{got:08X} OK")

    dut._log.info("PASS: test_burst_write_drain")


@cocotb.test()
async def test_stream_enable_gate(dut):
    """Verify no output beats are issued while stream_enable=0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    await axi_write_burst(dut, [0x1111_2222, 0x3333_4444])

    # Hold stream_enable=0 for 20 cycles — nothing should come out
    for _ in range(20):
        await RisingEdge(dut.clk)
        assert not dut.m_axis_tvalid.value, \
            "m_axis_tvalid asserted while stream_enable=0"

    dut._log.info("PASS: test_stream_enable_gate")


@cocotb.test()
async def test_backpressure_wready(dut):
    """Fill the FIFO to the backpressure limit; verify wready deasserts."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    dut.m_axis_tready.value = 1

    payload = list(range(512))
    await axi_write_burst(dut, payload[:256])
    await axi_write_burst(dut, payload[256:])
    dut._log.info("512 beats written without stall — wready held correctly")

    dut.stream_enable.value = 1

    received = []
    timeout = 4096
    while len(received) < 512 and timeout > 0:
        await ReadOnly()
        if dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1:
            received.append(int(dut.m_axis_tdata.value))
        await RisingEdge(dut.clk)
        timeout -= 1

    dut.stream_enable.value = 0
    assert len(received) == 512, f"expected 512 beats drained, got {len(received)}"

    for i, (exp, got) in enumerate(zip(payload, received)):
        assert got == exp, f"beat {i}: expected 0x{exp:08X}, got 0x{got:08X}"

    dut._log.info("PASS: test_backpressure_wready")


@cocotb.test()
async def test_simultaneous_write_drain(dut):
    """DMA writes and kernel drains run concurrently (pipelined)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await reset_dut(dut)

    dut.m_axis_tready.value = 1
    payload = [0xC000_0000 + i for i in range(32)]

    await axi_write_burst(dut, payload[:8])
    dut.stream_enable.value = 1

    write_task = cocotb.start_soon(axi_write_burst(dut, payload[8:]))

    received = []
    timeout = 2048
    while len(received) < 32 and timeout > 0:
        await ReadOnly()
        if dut.m_axis_tvalid.value == 1 and dut.m_axis_tready.value == 1:
            received.append(int(dut.m_axis_tdata.value))
        await RisingEdge(dut.clk)
        timeout -= 1

    await write_task
    dut.stream_enable.value = 0

    assert len(received) == 32, f"expected 32 beats, got {len(received)}"
    for i, (exp, got) in enumerate(zip(payload, received)):
        assert got == exp, f"beat {i}: expected 0x{exp:08X}, got 0x{got:08X}"

    dut._log.info("PASS: test_simultaneous_write_drain")
