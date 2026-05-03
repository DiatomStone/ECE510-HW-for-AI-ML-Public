# Created with Cursor - Manager (Claude Opus 4.6)
# Created: 2026-05-03
# Modified: 2026-05-03

import numpy as np

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


CONST_1 = 0.7978845608028654
CONST_2 = 0.03567740813630012
FRAC_BITS = 16
SCALE = 2 ** FRAC_BITS


def gelu_ref(x_float):
    return 0.5 * x_float * (1.0 + np.tanh(CONST_1 * x_float + CONST_2 * x_float**3))


def to_fixed(x_float):
    return int(round(x_float * SCALE))


def to_float(x_fixed):
    return x_fixed / SCALE


async def reset_dut(dut):
    dut.rst.value = 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tuser.value = 0
    dut.m_axis_tready.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def axis_send(dut, x_float, is_last=False, user=0):
    dut.s_axis_tdata.value = to_fixed(x_float) & 0xFFFFFFFF
    dut.s_axis_tlast.value = int(is_last)
    dut.s_axis_tuser.value = user
    dut.s_axis_tvalid.value = 1

    while True:
        await RisingEdge(dut.clk)
        if int(dut.s_axis_tready.value) == 1:
            break

    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tuser.value = 0


async def axis_recv(dut):
    dut.m_axis_tready.value = 1

    while True:
        await RisingEdge(dut.clk)
        if int(dut.m_axis_tvalid.value) == 1:
            raw = dut.m_axis_tdata.value.to_signed()
            tlast = int(dut.m_axis_tlast.value)
            tuser = int(dut.m_axis_tuser.value)
            return to_float(raw), tlast, tuser


@cocotb.test()
async def test_axi_stream_gelu_packet(dut):
    """Drive one AXI4-Stream packet and verify GELU outputs."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    inputs = [0.5, 1.0, 1.5, 2.0, -0.5, -1.0, -1.5, -2.0]
    tolerance = 0.10

    # Hold output ready low while writing the packet to exercise buffering.
    dut.m_axis_tready.value = 0
    for idx, x_float in enumerate(inputs):
        await axis_send(dut, x_float, is_last=(idx == len(inputs) - 1), user=idx & 0x1)

    # Let several results accumulate in the output FIFO before reading.
    for _ in range(8):
        await RisingEdge(dut.clk)

    outputs = []
    for _ in inputs:
        outputs.append(await axis_recv(dut))

    dut.m_axis_tready.value = 0

    for idx, (x_float, (result, tlast, _tuser)) in enumerate(zip(inputs, outputs)):
        expected = gelu_ref(x_float)
        if abs(expected) > 1e-6:
            err = abs(result - expected) / abs(expected)
        else:
            err = abs(result - expected)

        print(
            f"[{idx}] x={x_float:6.2f} expected={expected:.4f} "
            f"got={result:.4f} rel_err={err:.4f} tlast={tlast}"
        )
        assert err < tolerance, (
            f"x={x_float}: expected {expected:.4f}, got {result:.4f}, rel_err={err:.4f}"
        )
        assert tlast == int(idx == len(inputs) - 1), f"TLAST mismatch at output {idx}"

    print("PASS: AXI4-Stream GELU interface packet matched Python reference")
