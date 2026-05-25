# Critical Path Analysis — gelu_top

## Path Identification

**Start register:** `_13490_` — the Stage-2 slope register `s2_m[9]` inside
`u_interface.u_gelu_fp32.u_synth_top` (i.e., `compute_core`, instantiated as
`u_synth_top` inside `gelu_fp32`).

**End register:** `_13822_` — a downstream pipeline register capturing bit
`_00844_`, which lies in the Stage-3/4 boundary of `compute_core` (the
accumulator that holds the partial product `s3_mult` or the saturated output
`out`).

**Total combinational delay:** 10.605 ns out of a 22 ns budget.
**Setup slack:** +12.070 ns (well met).

---

## Logic Stages on the Critical Path

The path traverses the following stages after leaving `s2_m[9]`:

1. **FF output + clock tree** (~1.1 ns): `_13490_/Q` launches after the
   rising clock edge through the clock buffer tree
   (`clkbuf_0_clk → clkbuf_3_3 → clkbuf_leaf_14`).

2. **Fanout buffers** (~0.9 ns): The high-fanout net `s2_m[9]` drives
   `fanout637 → fanout636 → fanout635` (clkbuf_2, buf_2, clkbuf_4) before
   reaching logic gates. This buffering is inserted by OpenROAD to relieve
   capacitive load.

3. **Multiply logic — partial product generation** (~5.8 ns): The slope
   `s2_m` is one input to the 32×32-bit signed multiply `s3_mult = s2_m *
   s2_dx` in Stage 3 of `compute_core`. Yosys maps this multiply to a
   combinational AND/OR/XOR adder tree. The path traverses roughly 15–20
   gate levels of NAND, OR, AND, a21o, o211a, or3, and or4b cells, which
   account for the majority of the delay. These gates implement the carry-save
   and carry-propagate adder structure used to sum the 32 partial products.

4. **Adder tree — carry propagation and saturation** (~1.7 ns): The lower
   portion of the path resolves the final carry chain of the multiply result
   and feeds into the saturation logic (`s4_sum = (s3_mult >>> 16) + s3_b`).
   Gates here include `or4_1`, `o211a_1`, `o311a_1`, and `or4b_1`.

5. **Endpoint capture** (~0.1 ns): A final `o21a_1` gate drives the
   data input `_13822_/D`.

---

## Why This Is the Critical Path

The 32×32-bit signed multiply in Stage 3 of `compute_core` is the dominant
delay source. The PWL approximation requires multiplying a 32-bit slope
coefficient (`s2_m`, Q16.16) by a 32-bit offset (`s2_dx`, Q16.16). Yosys
synthesises this using a Baugh-Wooley or Wallace-tree-style structure built
entirely from standard cells — no dedicated multiplier macro is available in
the sky130_fd_sc_hd library. The resulting combinational depth (≈15–20 gate
levels) creates the longest data path in the design. All other pipeline
stages — the FP32 unpacking in `fp32_to_q16`, the CLZ and normalisation in
`q16_to_fp32`, and the FIFO and counter logic in `gelu_axi_stream_interface`
— complete in fewer gate levels and are not timing-critical.

---

## What Would Shorten the Critical Path

1. **Pipeline the multiply**: Splitting Stage 3 into two sub-stages
   (partial-product generation in one cycle, carry-propagation and add in the
   next) would halve the multiply depth. This adds one pipeline register and
   increases total latency from 12 to 13 cycles, but would roughly double the
   achievable clock frequency for the multiply stage.

2. **Reduce coefficient bit width**: `s2_m` and `s2_dx` are both 32-bit
   Q16.16 values, but the PWL coefficients stored in `s2_m` are bounded to
   ±2.0 (fitting in approximately 18 significant bits). Truncating the
   multiply to 18×32 bits (keeping only the bits that contribute to the final
   Q16.16 product after the right-shift) would reduce gate depth.

3. **Tighter clock constraint**: Constraining to a shorter period (e.g.,
   10 ns) would force Yosys/OpenROAD to use higher-drive-strength cells and
   more aggressive buffering, at the cost of increased area and power.
   The current 12 ns of positive slack means significant margin is available
   without any RTL changes.
