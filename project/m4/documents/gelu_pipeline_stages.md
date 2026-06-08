# `gelu_fp32` — The 12-Stage Pipeline

`gelu_fp32` is the main datapath of the accelerator: **FP32 in → GELU(x) → FP32
out**, in **12 clock cycles**, **1 result/cycle** once filled, at the synthesized
**22 ns (45.45 MHz)** clock. It is a *pure datapath* — no handshaking; the
enclosing `gelu_axi_stream_interface` does all AXI flow control. A lane is one
`gelu_fp32`; the SIMD kernel instantiates `NUM_LANES` of them in lockstep.

It chains three 4-stage sub-modules (`rtl/gelu_fp32.sv`):

```
data_in ─▶ fp32_to_q16 (stages 1–4) ─▶ compute_core (stages 5–8) ─▶ q16_to_fp32 (stages 9–12) ─▶ data_out
 IEEE-754 FP32          Q16.16 signed fixed-point GELU PWL          back to IEEE-754 FP32
```

Internally everything runs in **Q16.16** signed fixed-point (16 integer, 16
fractional bits; LSB ≈ 1.526e-5; range [−32768, +32767.99998]). The middle block
does the actual GELU as a 20-segment piecewise-linear (PWL) approximation; the
two outer blocks just translate number formats with correct rounding.

---

## Block A — `fp32_to_q16` : IEEE-754 FP32 → Q16.16  (stages 1–4)

Decode the float, align it to the fixed-point grid, round, and saturate.

| # | Stage | What it does |
|---|-------|--------------|
| **1** | Unpack & subnormal flush | Registers the IEEE fields: `sign = data_in[31]`, `exp = data_in[30:23]`, `mant = data_in[22:0]`. Sets `is_zero` when `exp == 0`, so **subnormals flush to zero (FTZ)** — standard for AI hardware. |
| **2** | Shift-amount & overflow detect | Rebuilds the absolute magnitude with the implicit leading 1 (`{1, mant, 8'b0}`). Computes the right-shift to reach Q16.16: `raw_shift = 142 − exp`. Flags **overflow** if the value is outside Q16.16 range (`exp > 142`, or `exp == 142` with positive sign or nonzero mantissa). Caps the shift at 63 so heavy underflows fall cleanly to 0. |
| **3** | Barrel shifter | Right-shifts a **64-bit** vector `{norm_mag, 32'b0}` by the stage-2 amount. The top 32 bits become the Q16.16 magnitude; the **bottom 32 bits are kept as sticky bits** so rounding in stage 4 is exact (round/sticky not thrown away). |
| **4** | RNE round, sign, assemble | Round-to-Nearest-Even: `round_up = round_bit & (sticky \| mag[0])`; `rounded_mag = mag + round_up`. Applies **two's complement** for negatives. Output = `0` if zero, **saturated** to `0x8000_0000` / `0x7FFF_FFFF` on overflow (or if positive rounding spills into the sign bit), else the signed Q16.16 value. |

## Block B — `compute_core` : Q16.16 GELU PWL approximation  (stages 5–8)

The GELU itself: pick the linear segment that contains `x`, evaluate
`y = m·(x − t) + b`. Uses **20 non-uniform segments**, densest through the
high-curvature center, so max error stays **< 0.05** (measured 0.0263).

| # | Stage (local) | What it does |
|---|---------------|--------------|
| **5** | Boundary decode (1) | Registers `x` and compares it against the 20 segment boundaries, producing a **one-hot hit vector** `s1_hits[19:0]`. Boundaries are dense near the center (¼-wide bins over [−1.5, 1.5]) and clamp the tails: `x < −3.0` → segment 0, `x ≥ 3.0` → segment 19. |
| **6** | Coefficient select (2) | A `unique case` on the one-hot hit maps the segment to its three precomputed Q16.16 constants — **slope `m`, intercept `b`, segment base `t`**. Registers `m`, `b`, and `dx = x − t` (the offset of `x` inside its segment). |
| **7** | Multiply (3) | Computes the signed **32×32 → 64-bit** product `m · dx` and carries `b` forward. This is the **critical path** of the whole design (the per-lane multiplier in `compute_core`). |
| **8** | Add, saturate, output (4) | Rescales the product back to Q16.16 and adds the intercept: `sum = (m·dx >>> 16) + b`. **Saturates** to signed 32-bit (clamp to ±max if `sum[63:31]` isn't pure sign-extension), drives `out`, and asserts `valid_out` (a parallel `v_pipe` shift register tracks `valid` across the 4 stages). |

## Block C — `q16_to_fp32` : Q16.16 → IEEE-754 FP32  (stages 9–12)

Re-float the fixed-point result: find the leading 1, normalize, round, repack.

| # | Stage (local) | What it does |
|---|---------------|--------------|
| **9** | Sign & absolute magnitude (1) | Registers `sign = data_in[31]` and `is_zero`. Takes the **two's complement** of negatives to get a positive magnitude `mag` to normalize. |
| **10** | CLZ & biased exponent (2) | Counts leading zeros of `mag` (`clz32`, a binary-search tree) and computes the **IEEE biased exponent** `exp = 142 − clz` (bias 127, plus 15 for the Q16.16 binary-point shift); `exp = 0` for a zero input. |
| **11** | Normalize shift (3) | Left-shifts the magnitude by `clz` so the **leading 1 lands at bit 31** — i.e. the IEEE normalized form with the implicit-1 at the top. |
| **12** | RNE round & final assembly (4) | Round-to-Nearest-Even on the normalized mantissa using guard `[7]`, sticky `[6:0]`, and LSB `[8]`. Extracts the 23-bit mantissa and adds the round bit (24-bit, to catch carry-out). Assembles `{sign, exp, mantissa[22:0]}`; if rounding **carried out** of the mantissa, increments the exponent and zeroes the mantissa. Emits a clean `0` for a zero input. |

---

## End-to-end summary

| Stages | Block | Role | Domain crossing |
|--------|-------|------|-----------------|
| 1–4 | `fp32_to_q16` | Decode FP32, align, round, saturate | FP32 → Q16.16 |
| 5–8 | `compute_core` | 20-segment PWL GELU: decode → coeff → multiply → add/saturate | Q16.16 → Q16.16 |
| 9–12 | `q16_to_fp32` | Normalize, round, repack | Q16.16 → FP32 |

- **Latency:** 12 cycles (4 + 4 + 4); **throughput:** 1 result/cycle/lane.
- **Rounding:** Round-to-Nearest-Even at *both* format conversions (stages 4 and
  12); the barrel shifter (stage 3) preserves sticky bits so it's exact.
- **Saturation** guards every range edge: input clamp (stage 4), GELU result
  clamp (stage 8), and the tail-segment clamps in the PWL decode (stage 5).
- **Accuracy:** max abs error **0.0263** vs reference GELU over [−4, 4]
  (threshold 0.05) — verified by `tb_gelu_fp32` / `tb_compute_core`.
- **Critical path:** the signed 32×32 multiply in **stage 7**; data arrival
  ≈12.3 ns against the 22 ns clock, so the pipeline closes timing with margin.

> The PWL coefficient tables (`m`, `b`, `t` per segment) live in
> `rtl/compute_core.sv`; see `documents/PWL_values_check.png` for the fit.
