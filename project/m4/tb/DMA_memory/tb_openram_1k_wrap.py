import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# ---------------------------------------------------------------------------
# Helpers — direct signal drives (no AXI VIP needed for bare SRAM wrapper)
# ---------------------------------------------------------------------------

async def init_dut(dut):
    dut.p0_en.value    = 0
    dut.p0_we.value    = 0
    dut.p0_wmask.value = 0xF
    dut.p0_addr.value  = 0
    dut.p0_din.value   = 0
    dut.p1_en.value    = 0
    dut.p1_addr.value  = 0

async def p0_write(dut, addr, data, wmask=0xF):
    """Issue one port-0 write; returns on the cycle after the write commits."""
    await RisingEdge(dut.clk)
    dut.p0_en.value    = 1
    dut.p0_we.value    = 1
    dut.p0_wmask.value = wmask
    dut.p0_addr.value  = addr
    dut.p0_din.value   = data
    await RisingEdge(dut.clk)   # write captured here
    dut.p0_en.value = 0
    dut.p0_we.value = 0

async def p0_read(dut, addr):
    """Issue one port-0 read; returns data after the 1-cycle SRAM latency."""
    await RisingEdge(dut.clk)
    dut.p0_en.value   = 1
    dut.p0_we.value   = 0
    dut.p0_addr.value = addr
    await RisingEdge(dut.clk)   # read issued; SRAM latches address
    dut.p0_en.value = 0
    await Timer(1, unit="ns")   # let combinational settle after posedge
    return int(dut.p0_dout.value)

async def p1_read(dut, addr):
    """Issue one port-1 read; returns data after the 1-cycle SRAM latency."""
    await RisingEdge(dut.clk)
    dut.p1_en.value   = 1
    dut.p1_addr.value = addr
    await RisingEdge(dut.clk)   # read issued
    dut.p1_en.value = 0
    await Timer(1, unit="ns")
    return int(dut.p1_dout.value)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_p0_write_read(dut):
    """Write via port 0, read back via port 0."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await Timer(20, unit="ns")

    vectors = [
        (0,    0xDEAD_BEEF),
        (1,    0xCAFE_BABE),
        (511,  0x1234_5678),
        (1023, 0xFFFF_FFFF),
    ]

    for addr, data in vectors:
        await p0_write(dut, addr, data)

    for addr, expected in vectors:
        got = await p0_read(dut, addr)
        assert got == expected, \
            f"p0 addr={addr}: expected 0x{expected:08X}, got 0x{got:08X}"
        dut._log.info(f"p0 addr={addr}: 0x{got:08X} OK")

    dut._log.info("PASS: test_p0_write_read")


@cocotb.test()
async def test_p1_read_after_p0_write(dut):
    """Write via port 0, read back via port 1."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await Timer(20, unit="ns")

    vectors = [
        (10,  0xABCD_1234),
        (20,  0x0000_0001),
        (100, 0x7FFF_FFFF),
    ]

    for addr, data in vectors:
        await p0_write(dut, addr, data)

    for addr, expected in vectors:
        got = await p1_read(dut, addr)
        assert got == expected, \
            f"p1 addr={addr}: expected 0x{expected:08X}, got 0x{got:08X}"
        dut._log.info(f"p1 addr={addr}: 0x{got:08X} OK")

    dut._log.info("PASS: test_p1_read_after_p0_write")


@cocotb.test()
async def test_byte_mask(dut):
    """Partial-byte writes via p0_wmask."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await Timer(20, unit="ns")

    addr = 50

    # Write full word first
    await p0_write(dut, addr, 0x0000_0000, wmask=0xF)

    # Write only byte 0 (bits 7:0)
    await p0_write(dut, addr, 0xFFFF_FFAA, wmask=0x1)
    got = await p0_read(dut, addr)
    assert got == 0x0000_00AA, \
        f"byte0 mask: expected 0x000000AA, got 0x{got:08X}"

    # Write only bytes 2:1 (bits 23:8)
    await p0_write(dut, addr, 0xFFBB_CC00, wmask=0x6)
    got = await p0_read(dut, addr)
    assert got == 0x00BB_CCAA, \
        f"bytes 2:1 mask: expected 0x00BBCCAA, got 0x{got:08X}"

    # Write only byte 3 (bits 31:24)
    await p0_write(dut, addr, 0xDD00_0000, wmask=0x8)
    got = await p0_read(dut, addr)
    assert got == 0xDDBB_CCAA, \
        f"byte3 mask: expected 0xDDBBCCAA, got 0x{got:08X}"

    dut._log.info("PASS: test_byte_mask")


@cocotb.test()
async def test_simultaneous_p0_write_p1_read(dut):
    """Port 0 write and port 1 read to different addresses on the same cycle."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await init_dut(dut)
    await Timer(20, unit="ns")

    # Pre-load address 5 with a known value
    await p0_write(dut, 5, 0xA5A5_A5A5)

    # On the same cycle: write to addr 10 via p0, read addr 5 via p1
    await RisingEdge(dut.clk)
    dut.p0_en.value    = 1
    dut.p0_we.value    = 1
    dut.p0_wmask.value = 0xF
    dut.p0_addr.value  = 10
    dut.p0_din.value   = 0x1111_2222
    dut.p1_en.value    = 1
    dut.p1_addr.value  = 5

    await RisingEdge(dut.clk)   # both issued on same cycle
    dut.p0_en.value = 0
    dut.p0_we.value = 0
    dut.p1_en.value = 0

    await Timer(1, unit="ns")
    p1_result = int(dut.p1_dout.value)
    assert p1_result == 0xA5A5_A5A5, \
        f"simultaneous: p1 addr=5 expected 0xA5A5A5A5, got 0x{p1_result:08X}"

    # Verify the p0 write also committed
    got = await p0_read(dut, 10)
    assert got == 0x1111_2222, \
        f"simultaneous: p0 addr=10 expected 0x11112222, got 0x{got:08X}"

    dut._log.info("PASS: test_simultaneous_p0_write_p1_read")
