"""
tb_mac — unit testbench for the weight-stationary MAC / processing element.

Checks the Q16.16 multiply-accumulate against a bit-exact Python reference:
    psum_out = saturate( psum_in + (a_in * w_q) >> 16 )
plus the activation pass-through (a_out = a_in delayed one cycle), weight hold,
and signed saturation. Matches the project Q16.16 convention (truncating
arithmetic shift, signed 32-bit saturate) used by compute_core.
"""

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

FRAC_BITS = 16
SCALE     = 1 << FRAC_BITS
INT_MAX   = 0x7FFFFFFF
INT_MIN   = -0x80000000


# ----------------------------------------------------------------------
# Fixed-point helpers / bit-exact reference
# ----------------------------------------------------------------------
def to_fixed(x):
    return int(round(x * SCALE))


def to_float(x):
    return x / SCALE


def to_signed(v, bits=32):
    v &= (1 << bits) - 1
    return v - (1 << bits) if (v >> (bits - 1)) else v


def q16_mul(a, w):
    # Python >> on ints floors -> same as Verilog arithmetic >>> (truncate).
    return (a * w) >> FRAC_BITS


def sat32(v):
    if v > INT_MAX:
        return INT_MAX
    if v < INT_MIN:
        return INT_MIN
    return v


def mac_ref(a, w, p):
    return sat32(q16_mul(a, w) + p)


# ----------------------------------------------------------------------
# DUT drivers
# ----------------------------------------------------------------------
async def reset(dut):
    dut.rst.value = 1
    dut.load_w.value = 0
    dut.w_in.value = 0
    dut.a_in.value = 0
    dut.psum_in.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def load_weight(dut, w_fix):
    """Latch a stationary weight (registered: takes effect next cycle)."""
    dut.load_w.value = 1
    dut.w_in.value = w_fix & 0xFFFFFFFF
    dut.a_in.value = 0
    dut.psum_in.value = 0
    await RisingEdge(dut.clk)
    dut.load_w.value = 0


async def step(dut, a_fix, p_fix):
    """Present one MAC operand set; return (psum_out, a_out) after the edge."""
    dut.a_in.value = a_fix & 0xFFFFFFFF
    dut.psum_in.value = p_fix & 0xFFFFFFFF
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    return to_signed(int(dut.psum_out.value)), to_signed(int(dut.a_out.value))


# ----------------------------------------------------------------------
# Test 1 — random MAC accuracy (bit-exact)
# ----------------------------------------------------------------------
@cocotb.test()
async def test_mac_random(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    random.seed(1)
    max_ferr = 0.0
    for _ in range(200):
        w = to_fixed(random.uniform(-2.0, 2.0))
        a = to_fixed(random.uniform(-4.0, 4.0))
        p = to_fixed(random.uniform(-8.0, 8.0))

        await load_weight(dut, w)
        ps, ao = await step(dut, a, p)

        exp = mac_ref(a, w, p)
        assert ps == exp, (
            f"psum mismatch: a={to_float(a):.4f} w={to_float(w):.4f} "
            f"p={to_float(p):.4f} -> got {ps} ({to_float(ps):.4f}), "
            f"exp {exp} ({to_float(exp):.4f})"
        )
        max_ferr = max(max_ferr, abs(to_float(ps) - to_float(exp)))

    print(f"\nMAC random: 200 ops bit-exact. Max float delta {max_ferr:.6g}\n")


# ----------------------------------------------------------------------
# Test 2 — weight is stationary (held across many ops)
# ----------------------------------------------------------------------
@cocotb.test()
async def test_mac_weight_hold(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    w = to_fixed(1.5)
    await load_weight(dut, w)

    random.seed(2)
    for _ in range(50):
        a = to_fixed(random.uniform(-3.0, 3.0))
        p = to_fixed(random.uniform(-5.0, 5.0))
        ps, _ = await step(dut, a, p)   # load_w stays low: weight must persist
        assert ps == mac_ref(a, w, p), "stationary weight changed without load_w"

    print("MAC weight-hold: 50 ops with one load — weight stayed put.")


# ----------------------------------------------------------------------
# Test 3 — activation pass-through (a_out = a_in delayed 1 cycle)
# ----------------------------------------------------------------------
@cocotb.test()
async def test_mac_passthrough(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    await load_weight(dut, to_fixed(0.5))
    dut.psum_in.value = 0

    random.seed(3)
    seq = [to_fixed(random.uniform(-100.0, 100.0)) for _ in range(20)]

    # Prime the pipe: clock seq[0] into a_out.
    dut.a_in.value = seq[0] & 0xFFFFFFFF
    await RisingEdge(dut.clk)

    # Each iteration drives seq[i] but reads a_out BEFORE the next edge — so it
    # must still hold seq[i-1] (the value captured one cycle earlier).
    for i in range(1, len(seq)):
        dut.a_in.value = seq[i] & 0xFFFFFFFF
        await Timer(1, unit="ns")
        ao = to_signed(int(dut.a_out.value))
        assert ao == seq[i - 1], \
            f"a_out {ao} != prev a_in {seq[i-1]} (1-cycle delay broken)"
        await RisingEdge(dut.clk)

    print("MAC pass-through: a_out tracks a_in with 1-cycle delay.")


# ----------------------------------------------------------------------
# Test 4 — saturation clamps
# ----------------------------------------------------------------------
@cocotb.test()
async def test_mac_saturate(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # Large weight * large activation + large psum -> overflow both rails.
    cases = [
        (to_fixed(20000.0),  to_fixed(20000.0),  to_fixed(20000.0),  INT_MAX),
        (to_fixed(-20000.0), to_fixed(20000.0),  to_fixed(-20000.0), INT_MIN),
    ]
    for w, a, p, exp in cases:
        await load_weight(dut, w)
        ps, _ = await step(dut, a, p)
        assert ps == exp, f"saturation: got {ps}, exp {exp}"
        # cross-check against the reference saturator too
        assert ps == mac_ref(a, w, p)

    print("MAC saturation: clamps to signed Q16.16 min/max.")
