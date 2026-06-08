# Testbench Summary — `m4/tb/`

What each cocotb testbench covers and what every individual test inside it
*checks*. All tests currently **PASS** (see `m4/sim/*.log` for the captured
runs); this document is about **coverage/intent**, not results.

Each test runs against a Python reference model in the same testbench
(bit-exact for the converters, ±0.05 GELU error for the approximation), so a
"pass" means the RTL matched the reference for that scenario.

The DUT clock is the synthesized **22 ns (45.45 MHz)** period. `PIPE_DEPTH` is
each block's pipeline latency (converters/core = 4, full `gelu_fp32` = 12).

| Testbench | DUT | Make target(s) | # tests |
|-----------|-----|----------------|---------|
| `tb_compute_core.py` | `compute_core` (Q16.16 GELU PWL core) | *(default)* | 5 |
| `tb_fp32_to_q16.py` | `fp32_to_q16` (IEEE-754 → Q16.16) | `convin` | 12 |
| `tb_q16_to_fp32.py` | `q16_to_fp32` (Q16.16 → IEEE-754) | `convout` | 13 |
| `tb_gelu_fp32.py` | `gelu_fp32` (full 12-cycle datapath) | `gelu` | 7 |
| `tb_interface.py` | `gelu_axi_stream_interface` (SIMD, AXI-Stream+Lite) | `interface_x8` / `_x16` / `_x32` | 6 |
| `tb_top.py` | `gelu_top` (full kernel, parameterized lanes) | `inloop_x1` / `_x8` / `_x16` / `_x32` | 1 |
| `tb_top_inloop_dma.py` | `gelu_dma_top` (wide DMA round-trip) | `inloop_dma_x1` / `_x8` / `_x16` / `_x32` | 1 |

The last three are **lane-parameterized** (`GELU_NUM_LANES` env var): the *same*
testbench is re-run against the RTL built at 1, 8, 16, and 32 lanes, and asserts
the DUT bus width matches the requested lane count at runtime.

---

## 1. `tb_compute_core.py` — Q16.16 GELU PWL core (5 tests)

The fixed-point heart of the kernel: takes a Q16.16 input, returns the
piecewise-linear GELU approximation in Q16.16.

| Test | What it checks |
|------|----------------|
| `test_gelu_sweep_error` | Sweeps the input −4.0 → 4.0 in 0.05 steps and compares HW output to the algebraic GELU reference; reports max/avg error and asserts **max error < 0.05** (the accuracy contract). |
| `test_gelu_edge_cases` | Zero-crossing, saturation clamps, and the extreme tails — confirms `x < −3.0` clamps to 0 and `x ≥ 3.0` passes through linearly. |
| `test_gelu_valid_pipeline` | `valid_out` asserts **exactly `PIPE_DEPTH` cycles** after `valid_in` (latency contract). |
| `test_gelu_streaming` | Streams 100 random values back-to-back and verifies **no sample is dropped** (1 result/cycle throughput). |
| `test_gelu_segment_boundaries` | Drives values *just inside* each PWL segment boundary to catch **off-by-one errors in the boundary-decode logic** that selects the active linear piece. |

## 2. `tb_fp32_to_q16.py` — IEEE-754 FP32 → Q16.16 converter (12 tests)

Input-side format conversion, including rounding and out-of-range policy.

| Test | What it checks |
|------|----------------|
| `test_reset` | After reset, `valid_out` and `data_out` are both 0. |
| `test_zero` | `0.0` → `0x0000_0000`. |
| `test_positive_integers` | Small positive integers that are exactly representable in Q16.16. |
| `test_negative_values` | Negative values including the `−32768.0` boundary. |
| `test_negative_one` | `−1.0` → `0xFFFF_0000` (two's-complement Q16.16). |
| `test_fractional_values` | Fractional inputs; allows 2-LSB tolerance (Q16.16 LSB ≈ 1.5e-5). |
| `test_positive_overflow_clamp` | Values above Q16.16 max **clamp to `0x7FFF_FFFF`** (no wrap). |
| `test_negative_overflow_clamp` | Values below Q16.16 min **clamp to `0x8000_0000`**. |
| `test_subnormal_flush_to_zero` | Subnormals (biased exp == 0) **flush to zero** per the FTZ policy. |
| `test_rne_half_lsb` | A value exactly one half-LSB rounds to **even (0)** — round-nearest-even, not round-up. |
| `test_pipeline_latency` | `valid_out` appears exactly `PIPE_DEPTH` cycles after `valid_in`. |
| `test_pipeline_throughput` | N back-to-back inputs produce **exactly N** outputs (no bubbles/drops). |

## 3. `tb_q16_to_fp32.py` — Q16.16 → IEEE-754 FP32 converter (13 tests)

Output-side format conversion: leading-zero normalize + round back to FP32.

| Test | What it checks |
|------|----------------|
| `test_reset` | After reset, `valid_out` and `data_out` are both 0. |
| `test_zero` | `0x0000_0000` → `+0.0`. |
| `test_one` | `0x0001_0000` (= 1.0) → exactly `1.0`. |
| `test_neg_one` | `0xFFFF_0000` (= −1.0) → exactly `−1.0`. |
| `test_positive_integers` | Exact positive integers 1, 2, 4, 256. |
| `test_negative_integers` | Negative integers −1, −2, −32768. |
| `test_fractional_values` | Fractional Q16.16 values; 2-LSB tolerance (~3e-5). |
| `test_max_positive` | `0x7FFF_FFFF` (≈ +32767.99998) → positive, near 32768. |
| `test_min_negative` | `0x8000_0000` (= −32768.0) → exactly `−32768.0`. |
| `test_sign_bit_positive` | All-positive inputs produce FP32 with **sign bit = 0**. |
| `test_rne_consecutive_lsb` | Two adjacent Q16.16 LSBs produce **ordered, distinct** FP32 outputs — RNE doesn't collapse neighbors. |
| `test_pipeline_latency` | `valid_out` exactly `PIPE_DEPTH` cycles after `valid_in`. |
| `test_pipeline_throughput` | N back-to-back inputs → exactly N outputs. |

## 4. `tb_gelu_fp32.py` — full FP32 datapath (7 tests)

The chained `fp32_to_q16 → compute_core → q16_to_fp32` (12-cycle, FP32 in/out).
Re-verifies end-to-end GELU plus the FP32-specific corner cases the converters
introduce.

| Test | What it checks |
|------|----------------|
| `test_reset` | After reset, `valid_out` and `data_out` are both 0. |
| `test_gelu_sweep_error` | Same −4.0 → 4.0 sweep as the core, but FP32 in/out; asserts **max error < 0.05** through the whole chain. |
| `test_gelu_edge_cases` | Zero-crossing, saturation clamps, tails — now exercising both the input clamp (`fp32_to_q16`) and the core clamp. |
| `test_valid_pipeline_timing` | `valid_out` exactly `PIPE_DEPTH` (=12) cycles after `valid_in`. |
| `test_gelu_streaming` | 100 random values back-to-back, no drops, across the full pipeline. |
| `test_segment_boundaries` | Values just inside each PWL boundary, off-by-one decode check end-to-end. |
| `test_fp32_special_values` | `±inf` and large magnitudes **clamp to a finite value**; zero/subnormals **flush to zero** through FTZ. |

## 5. `tb_interface.py` — AXI protocol wrapper (6 tests)

Drives the raw AXI-Stream + AXI-Lite ports of `gelu_axi_stream_interface`
directly (no cocotbext). Every beat packs `NUM_LANES` FP32 operands (lane *i* at
`tdata[i*32 +: 32]`). Run at 8 / 16 / 32 lanes.

| Test | What it checks |
|------|----------------|
| `test_axil_enable_readback` | AXI-Lite `pipeline_enable` write/read, **plus** the read-only `NUM_LANES` register at `0x04` (asserts it equals the build's lane count — catches a mismatched RTL build). |
| `test_pipeline_gate` | `s_axis_tready` stays **low while `pipeline_enable = 0`** (control gates the data plane). |
| `test_single_beat` | One packed beat of `NUM_LANES` distinct operands → `NUM_LANES` correct GELU results. |
| `test_tlast_propagation` | `TLAST` on the last input beat appears on the **corresponding output beat** (framing preserved through pipeline latency). |
| `test_backpressure` | Fills the output FIFO with `tready = 0`; verifies `tready` **deasserts then recovers** (lossless backpressure). |
| `test_accuracy_sweep` | N FP32 inputs spread over multiple beats; every result within **0.05** of the GELU reference. |

## 6. `tb_top.py` — full-model in-loop co-sim (1 test)

| Test | What it checks |
|------|----------------|
| `test_gelu_top_inloop` | Runs the **real M1 transformer forward pass** and offloads **every GELU** to `gelu_top` (fp64→fp32 in, fp32→fp64 out). Checks per-element accuracy (threshold 0.05), final-logit **loop closure** vs the all-software reference, and reports throughput/cycles-elem. Asserts the DUT bus width matches `NUM_LANES`. Re-run at 1/8/16/32 lanes. |

## 7. `tb_top_inloop_dma.py` — full-model in-loop through the DMA path (1 test)

| Test | What it checks |
|------|----------------|
| `test_gelu_dma_inloop` | Same full-model offload as `tb_top`, but every GELU travels the **wide DMA round-trip**: host → AXI4-MM write burst → `mm2s_buffer` → AXI-Stream → kernel → `s2mm_buffer` → AXI4-MM read burst → host. Hand-drives AXI4-MM bursts (≤256 beats), toggles `stream_enable`, and checks the same accuracy + loop-closure contract. Re-run at 1/8/16/32 lanes. |

---

### Coverage at a glance

- **Numeric correctness** is checked at three levels: per-block (`compute_core`,
  the two converters), per-datapath (`gelu_fp32`), and full-model
  (`tb_top` / `tb_top_inloop_dma`) — so an error is localized to a block.
- **Format/rounding policy** (clamp, FTZ, RNE) is pinned down in the converter
  tbs and re-confirmed end-to-end in `tb_gelu_fp32`.
- **Pipeline behavior** (fixed latency, no-drop throughput) is asserted in every
  block-level tb.
- **Protocol** (AXI-Lite control gating, TLAST framing, backpressure, lane
  packing, NUM_LANES discovery) lives in `tb_interface`.
- **System integration + accuracy under the real workload** is the job of the
  two in-loop tbs, across all four lane counts and both the direct-stream and
  DMA datapaths.

> Note: buffer-level unit testbenches (`mm2s_buffer`, `s2mm_buffer`,
> `openram_1k_wrap`, `gelu_dma_top`) were exercised earlier (logs in `m4/sim/`)
> but are not part of the current `m4/tb/` set; their coverage is folded into
> `tb_top_inloop_dma.py` at the system level.
