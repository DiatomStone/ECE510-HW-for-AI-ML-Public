"""
tb_systolic_array — unit testbench for the 8x8 weight-stationary array.

Loads an 8x8 weight tile, streams A-rows in, and checks the C-rows out against
a bit-exact Python model of the array (per-PE Q16.16 truncating product, signed
saturating accumulation down each column, in the same k=0..N-1 order the
hardware accumulates). Also checks the in_valid -> out_valid latency (2N-2) and
that idle cycles produce clean zero rows.

Vectors are packed like the v2 datapath: lane i = bits [i*32 +: 32].
"""

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

N         = 8
DW        = 32
FRAC_BITS = 16
SCALE     = 1 << FRAC_BITS
INT_MAX   = 0x7FFFFFFF
INT_MIN   = -0x80000000
LAT       = 2 * N - 2          # measured in_valid -> out_valid edge count


# ----------------------------------------------------------------------
# Fixed-point + packing helpers
# ----------------------------------------------------------------------
def to_fixed(x):
    return int(round(x * SCALE))


def to_float(x):
    return x / SCALE


def to_signed(v, bits=DW):
    v &= (1 << bits) - 1
    return v - (1 << bits) if (v >> (bits - 1)) else v


def pack(lanes):
    val = 0
    for i, x in enumerate(lanes):
        val |= (int(x) & ((1 << DW) - 1)) << (i * DW)
    return val


def unpack(val):
    return [to_signed((val >> (i * DW)) & ((1 << DW) - 1)) for i in range(N)]


def q16_mul(a, w):
    return (a * w) >> FRAC_BITS


def sat32(v):
    return INT_MAX if v > INT_MAX else INT_MIN if v < INT_MIN else v


def ref_c_row(a_row, W_fix):
    """C[n] = sat-accumulate over k of trunc(A[k]*W[k][n]) — HW column order."""
    c = []
    for n in range(N):
        acc = 0
        for k in range(N):
            acc = sat32(acc + q16_mul(a_row[k], W_fix[k][n]))
        c.append(acc)
    return c


# ----------------------------------------------------------------------
# DUT drivers
# ----------------------------------------------------------------------
async def reset(dut):
    dut.rst.value = 1
    dut.load_en.value = 0
    dut.load_row.value = 0
    dut.w_row_flat.value = 0
    dut.in_valid.value = 0
    dut.a_row_flat.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


async def load_weights(dut, W_fix):
    """Load the 8x8 weight tile, one PE row per cycle. (rst clears weights, so
    this must run after reset is deasserted.)"""
    for r in range(N):
        dut.load_en.value = 1
        dut.load_row.value = r
        dut.w_row_flat.value = pack([W_fix[r][c] for c in range(N)])
        dut.in_valid.value = 0
        dut.a_row_flat.value = 0
        await RisingEdge(dut.clk)
    dut.load_en.value = 0
    dut.w_row_flat.value = 0


def rand_matrix(rng, n, lo, hi):
    return [[to_fixed(rng.uniform(lo, hi)) for _ in range(n)] for _ in range(n)]


# ----------------------------------------------------------------------
# Test 1 — latency of a single A-row
# ----------------------------------------------------------------------
@cocotb.test()
async def test_latency(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    rng = random.Random(10)
    W = rand_matrix(rng, N, -1.0, 1.0)
    await load_weights(dut, W)

    a = [to_fixed(rng.uniform(-2.0, 2.0)) for _ in range(N)]
    dut.in_valid.value = 1
    dut.a_row_flat.value = pack(a)
    await RisingEdge(dut.clk)          # injection edge
    dut.in_valid.value = 0
    dut.a_row_flat.value = 0

    delay = 0
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        delay += 1
        if dut.out_valid.value == 1:
            break
        assert delay < LAT + 5, "out_valid never asserted"

    got = unpack(int(dut.c_row_flat.value))
    exp = ref_c_row(a, W)
    print(f"\nSystolic latency: {delay} cycles (expected {LAT}=2N-2)\n")
    assert delay == LAT, f"latency {delay} != {LAT}"
    assert got == exp, f"first result mismatch:\n got {got}\n exp {exp}"


# ----------------------------------------------------------------------
# Test 2 — streamed matmul (M back-to-back A-rows), bit-exact
# ----------------------------------------------------------------------
@cocotb.test()
async def test_stream_matmul(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    rng = random.Random(20)
    W = rand_matrix(rng, N, -1.0, 1.0)
    await load_weights(dut, W)

    M = 24
    A = [[to_fixed(rng.uniform(-2.0, 2.0)) for _ in range(N)] for _ in range(M)]
    exp = [ref_c_row(a, W) for a in A]

    results = []

    async def sample():
        await Timer(1, unit="ns")
        if dut.out_valid.value == 1:
            results.append(unpack(int(dut.c_row_flat.value)))

    # stream phase
    for m in range(M):
        dut.in_valid.value = 1
        dut.a_row_flat.value = pack(A[m])
        await RisingEdge(dut.clk)
        await sample()

    # drain phase
    dut.in_valid.value = 0
    dut.a_row_flat.value = 0
    for _ in range(LAT + 4):
        await RisingEdge(dut.clk)
        await sample()

    assert len(results) == M, f"got {len(results)} C-rows, expected {M}"

    max_ferr = 0.0
    for m in range(M):
        assert results[m] == exp[m], (
            f"row {m} mismatch:\n got {results[m]}\n exp {exp[m]}"
        )
        for n in range(N):
            max_ferr = max(max_ferr, abs(to_float(results[m][n]) - to_float(exp[m][n])))

    print(f"\nSystolic stream: {M} A-rows, all {M*N} elements bit-exact.")
    print(f"Max float delta vs reference: {max_ferr:.6g}\n")


# ----------------------------------------------------------------------
# Test 3 — idle cycles produce clean zero rows (skew injects zeros)
# ----------------------------------------------------------------------
@cocotb.test()
async def test_idle_zero(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    rng = random.Random(30)
    W = rand_matrix(rng, N, -1.0, 1.0)
    await load_weights(dut, W)

    # never assert in_valid; just clock and confirm no spurious valid/nonzero out
    for _ in range(2 * N + 5):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert dut.out_valid.value == 0, "out_valid asserted with no input"

    print("Systolic idle: no spurious out_valid, no garbage rows.")
