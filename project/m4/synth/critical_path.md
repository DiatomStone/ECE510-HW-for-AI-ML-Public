# Critical Path Analysis — gelu_top (x8, no DMA)

Run: `RUN_2026-06-07_14-45-32` · GELU_NUM_LANES = 8 · clk = 22 ns ·
corner nom_tt_025C_1v80.

## Path Identification

**Start register:** `_102449_` — the Stage-2 slope register `s2_m[17]` inside
`u_interface.g_lane[5].u_gelu_fp32.u_synth_top` — i.e. `compute_core`
(instantiated as `u_synth_top` inside `gelu_fp32`), in **lane 5** of the 8-lane
generate array `g_lane[0..7]`.

**End register:** `_103435_` — a downstream pipeline register at the Stage-3/4
boundary of the same lane's `compute_core` (the accumulator holding the partial
product `s3_mult` / the saturated `out`).

**Total data arrival:** 12.345 ns (of which ~2.04 ns is clock-tree launch
latency → ~10.3 ns of launch-FF + combinational logic).
**Setup slack:** +11.382 ns (well met, 22 ns budget).

---

## Logic Stages on the Critical Path

1. **FF output + clock tree** (~2.0 ns launch): `_102449_/Q` launches through the
   clock buffer tree (`clkbuf_0_clk → clkbuf_2/3/6/7 → clkbuf_leaf_74`).

2. **Fanout buffers** (~1.4 ns): the high-fanout slope net `s2_m[17]` drives
   `fanout4371 → 4370 → 4369 → 4368 → 4367` (dlymetal6s2s + buf_2 chain) before
   reaching logic — buffering inserted by OpenROAD to relieve capacitive load.

3. **Multiply logic — partial-product generation** (~6.8 ns): the slope `s2_m`
   is one input to the 32×32-bit signed multiply `s3_mult = s2_m * s2_dx` in
   Stage 3 of `compute_core`. Yosys maps this to a combinational AND/OR/XOR
   adder tree; the path traverses ~15–20 gate levels of `o21a`, `a21o`,
   `nand3`, `nand`, `or`, `and` cells implementing the carry-save / carry-
   propagate structure. This is the bulk of the delay.

4. **Adder tree — carry propagation + saturation** (~1.6 ns): resolves the final
   carry chain and feeds the saturation logic (`s4_sum = (s3_mult >>> 16) +
   s3_b`).

5. **Endpoint capture** (~0.1 ns): a final gate drives `_103435_/D`.

---

## Why This Is the Critical Path

Identical in structure to the v1 `gelu_top` critical path: the **32×32-bit
signed multiply in Stage 3 of `compute_core`** is the dominant delay source. The
PWL approximation multiplies a 32-bit slope (`s2_m`, Q16.16) by a 32-bit offset
(`s2_dx`, Q16.16); with no hard multiplier in sky130_fd_sc_hd, Yosys builds a
Wallace/Baugh-Wooley-style tree entirely from standard cells (~15–20 gate
levels). All other stages — FP32 unpack in `fp32_to_q16`, CLZ/normalise in
`q16_to_fp32`, and the FIFO/counter logic in
`gelu_axi_stream_interface` — are shallower and not timing-critical.

**Parallelism does not lengthen it.** The 8 lanes are an independent
`generate` array sharing one valid/ready/tlast handshake — they run in lockstep,
*in parallel, not in series*. So the worst path is still **one lane's** multiply
(here lane 5; which lane wins is just placement/routing variation). x8 keeps
essentially the same per-lane delay as v1 (v1 setup slack +11.83 ns → x8
+11.38 ns at nom_tt — the small drop is congestion/longer routes from the ~8×
larger placed area, not deeper logic).

---

## What Would Shorten the Critical Path

1. **Pipeline the multiply**: split Stage 3 (partial-product generation in one
   cycle, carry-propagate/add in the next) to roughly halve the multiply depth.
   Costs one pipeline register per lane and +1 cycle latency (12 → 13), but
   raises the achievable frequency of the limiting stage.

2. **Reduce coefficient bit width**: `s2_m` is bounded to ±2.0 (≈18 significant
   bits). Truncating to an 18×32 multiply (keeping only bits that survive the
   `>>> 16`) trims gate depth.

3. **Tighter clock constraint**: there is +11.4 ns of slack at 22 ns, so the x8
   design could target a much shorter period (e.g. 10–12 ns) and let
   OpenROAD/Yosys up-size and buffer — at the cost of area/power. The current
   large margin means the clock could be tightened with no RTL change, though
   x8 area/congestion would grow.

---

Source: `54-openroad-stapostpnr/nom_tt_025C_1v80/max.rpt` (worst setup path),
`summary.rpt`, `ws.max.rpt`.
