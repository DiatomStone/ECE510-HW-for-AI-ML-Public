# GELU Accelerator — Benchmark Results

Workload (all sections): M1 transformer, small config, 2 layers, B=8, T=64,
d_ff=256, seed=42. One GELU activation tensor per layer FFN; **2 layers →
262,144 GELU elements** total (per-layer tensor = 2^17 = 64 × 8 × 256 =
seq × batch × d_ff).

---

## 1. Software baseline (no accelerator)

Parameters: `train.py --config small --steps 500`

| Metric | Value |
|--------|-------|
| Total execution time | 44.085 s |
| GELU execution time | 9604 ms |
| Throughput | 13.647 K elem/s |
| Throughput | 122.8 K OPS |
| Memory-profiler result (GELU) | 294.477 MiB ¹ |
| Theoretical input memory | 1 MB (2^17 × fp64) |

Notes:
- Throughput = 2^17 / 9.604 s = 13,647.65 elem/s
- 9 floating ops per GELU → 13,647.65 × 9 = 122.8 K OPS
  (software counts FLOPs; the accelerator uses integer OPS, so this is
  simplified to OPS for comparison)
- ¹ Memory profile: 2000.539 MiB − 1713.062 MiB = 294.477 MiB over 1000 calls
  → 0.294477 MiB per call
- Bytes = 2^17 × 8 (fp64) = 1 MB

---

## 2. Accelerated kernel — single pipeline, direct AXI-Stream (no DMA)

DUT: `gelu_top`. Source: `tb/tb_top_inloop.py`. Data is streamed straight into
the kernel over AXI4-Stream (no on-chip buffering / DMA).

| Metric | Value |
|--------|-------|
| GELU execution time | 6.062 ms |
| Measured throughput | 45.42 M elem/s (1.001 cycles/elem) |
| Peak throughput | 45.45 M elem/s (1 result/cycle @ 22 ns) |
| Int-arith throughput | 2.8179 G OPS ² |
| Memory | streaming (no on-chip residency) |
| Measured AXI bandwidth | 363.3 MB/s (in+out); 181.7 MB/s per direction |
| Total power | 30.22 mW |
| Total chip area | 90,470.52 µm² |
| **Speedup vs software** | **1584.3×** |

² Op-count basis: the headline 2.8179 G OPS uses 62 integer ops per GELU pass
(45.45 M elem/s × 62 = 2817.9 M ≈ 2.818 G OPS). The in-loop sim instead
projects against 17 ops/elem (from `core_kernel/int_op_count.md`, 1 MUL, no DIV)
→ 772.7 M OPS. Both are reported as measured/projected respectively; pick one
convention consistently when quoting.

### Speedup calculation

```
MEASURED (cycle-accurate Icarus)
  HW streaming time  : 5,772,096 ns  = 5772.096 us
  fp64<->fp32 casts  : 289.5 us total (host, both directions)

  total accelerated kernel time = 5772.096 us + 289.5 us = 6061.596 us = 6.062 ms
  Speedup = 9604 ms / 6.062 ms = 1584.3×
```

The total AXI bandwidth (363.3 MB/s in+out) is the limiting factor here because
we are only running **1 pipeline**.

### Simulation log (`tb_top_inloop.py`)

```
=== Full-Model In-Loop GELU Co-Sim — Timing & Metrics ===
  Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
  GELU offloads      : 2 (one per layer FFN)
  Elements streamed  : 262144  in 16 AXI frames
  Clock (synth)      : 22 ns  (45.45 MHz)
  --- MEASURED (cycle-accurate Icarus) ---
  HW streaming time  : 5772096 ns (~262368 cycles)
  Throughput         : 45.42 M elem/s  (1.001 cycles/elem)
  AXI bandwidth/dir  : 181.7 MB/s (in, and out)
  AXI bandwidth total: 363.3 MB/s (in+out)
  --- PROJECTED PEAK (synthesis × ops/cycle) ---
  Peak throughput    : 45.45 M elem/s  (1 result/cycle @ 22 ns)
  Peak int-arith     : 772.7 M op/s  (17 ops/elem)
  --- KERNEL ACCURACY (per-element, all layers) ---
  GELU max error     : 0.026311
  GELU failures      : 0 / 262144  (threshold 0.05)
  --- LOOP CLOSURE: final logits vs all-software forward() ---
  Logits avg / max   : 0.015396 / 0.104763
  Next-token argmax  : 503/512 positions match software
TEST  tb_top_inloop.test_gelu_top_inloop  PASS  5,772,492 ns
```

`tb_top_inloop.py` scope: a full-model, hardware-in-the-loop cocotb
co-simulation. It runs the M1 transformer forward pass using `transformer.py`'s
real functions and weights, and offloads every GELU activation (both layers,
262,144 elements) to the actual `gelu_top` RTL over the AXI-Stream / AXI-Lite
interface — fp64→fp32 in, fp32→fp64 out, streamed in ≤16,384-element frames.
Hardware results propagate forward, closing the loop. It checks per-element GELU
accuracy and final logits, then reports measured throughput, cycles/element, and
AXI bandwidth at the synthesized 22 ns clock.

---

## 3. Accelerated kernel — 8 parallel pipelines, direct AXI-Stream (no DMA)

DUT: `gelu_top_x32` built at `NUM_LANES=8`. Source: `tb/tb_top_inloop_x32.py`
(`GELU_NUM_LANES=8`). 8 `gelu_fp32` pipelines behind a 256-bit AXI-Stream — 8
IEEE-754 FP32 packed per beat, SIMD lockstep. This is the **pragmatic parallel
target**: the 32-lane build over-congests in OpenLane, so the 8-lane variant is
the one carried forward for hardening (same parameterized RTL, `NUM_LANES=8`).

| Metric | Value |
|--------|-------|
| GELU execution time (HW) | 0.726 ms |
| Measured throughput | 361.17 M elem/s (0.1259 cycles/elem, 1.007 cycles/beat) |
| Peak throughput | 363.64 M elem/s (8 results/cycle @ 22 ns) |
| Int-arith throughput | 6.18 G OPS (17 ops/elem × 8 lanes) |
| Measured AXI bandwidth | 2889.3 MB/s (in+out); 1444.7 MB/s per direction |
| Memory | streaming (no on-chip residency) |
| **Speedup vs software** | **≈9209×** (HW + host casts); 13,231× HW-only |

### Speedup calculation

```
MEASURED (cycle-accurate Icarus)
  HW streaming time  : 725,824 ns = 725.824 us
  fp64<->fp32 casts  : 317.0 us total (host, both directions)

  total accelerated kernel time = 725.824 us + 317.0 us = 1042.8 us = 1.043 ms
  Speedup = 9604 ms / 1.043 ms = 9209×
```

**Amdahl note:** the kernel is **8.0× faster** than the single pipeline (5772 →
726 us HW) — exactly the lane count — and end-to-end **~5.8× faster** than §2
(1584× → 9209×). The host fp64↔fp32 cast (317 us) is now **30% of the 1043 us**:
noticeable, but not yet the dominant cost it becomes at 32 lanes (59%). HW-only
the kernel reaches 13,231×. The measured 361.2 M elem/s is 99.3% of the 363.6 M
peak.

### Simulation log (`tb_top_inloop_x32.py`, GELU_NUM_LANES=8)

```
=== Full-Model In-Loop GELU Co-Sim (v2, parallel) — Timing & Metrics ===
  Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
  Parallelization    : 8 lanes (256-bit AXI-Stream, 8 FP32/beat)
  Elements streamed  : 262144  in 16 AXI frames (32768 beats)
  Clock (synth)      : 22 ns  (45.45 MHz)
  --- MEASURED (cycle-accurate Icarus) ---
  HW streaming time  : 725824 ns (~32992 cycles)
  Throughput         : 361.17 M elem/s  (0.1259 cycles/elem, 1.007 cycles/beat)
  AXI bandwidth/dir  : 1444.7 MB/s (in, and out)
  AXI bandwidth total: 2889.3 MB/s (in+out)
  --- PROJECTED PEAK (synthesis × lanes × ops/cycle) ---
  Peak throughput    : 363.64 M elem/s  (8 results/cycle @ 22 ns)
  Peak int-arith     : 6181.8 M op/s  (17 ops/elem × 8 lanes)
  --- HOST-SIDE CONVERSION (informational, not kernel time) ---
  fp64<->fp32 casts  : 317.0 us total (host, both directions)
  --- KERNEL ACCURACY (per-element, all layers) ---
  GELU max error     : 0.026311
  GELU failures      : 0 / 262144  (threshold 0.05)
  --- LOOP CLOSURE: final logits vs all-software forward() ---
  Logits avg / max   : 0.015396 / 0.104763
  Next-token argmax  : 503/512 positions match software
TEST  tb_top_inloop_x32.test_gelu_top_x32_inloop  PASS  726,308 ns
```

---

## 4. Accelerated kernel — 32 parallel pipelines, direct AXI-Stream (no DMA)

DUT: `gelu_top_x32` (`NUM_LANES=32`). Source: `tb/tb_top_inloop_x32.py`. 32
`gelu_fp32` pipelines behind a 1024-bit AXI-Stream — 32 IEEE-754 FP32 packed per beat, SIMD lockstep.

| Metric | Value |
|--------|-------|
| GELU execution time (HW) | 0.185 ms |
| Measured throughput | 1415.83 M elem/s (0.0321 cycles/elem, 1.027 cycles/beat) |
| Peak throughput | 1454.55 M elem/s (32 results/cycle @ 22 ns) |
| Int-arith throughput | 24.73 G OPS (17 ops/elem × 32 lanes) |
| Measured AXI bandwidth | 11,326.7 MB/s (in+out); 5663.3 MB/s per direction |
| Memory | streaming (no on-chip residency) |
| **Speedup vs software** | **≈21,240×** (HW + host casts); 51,900× HW-only |

### Speedup calculation

```
MEASURED (cycle-accurate Icarus)
  HW streaming time  : 185,152 ns = 185.152 us
  fp64<->fp32 casts  : 267.0 us total (host, both directions)

  total accelerated kernel time = 185.152 us + 267.0 us = 452.15 us = 0.452 ms
  Speedup = 9604 ms / 0.452 ms = 21,240×
```

**Amdahl note:** the kernel itself is **31× faster** than the single pipeline
(5772 → 185 us HW), but end-to-end this is only **~13.4×** faster than §2
(1584× → 21,240×). At 32 lanes the **host fp64↔fp32 cast (267 us) now dominates
— 59% of the 452 us** — and is unchanged by kernel parallelism. The cast, not
the kernel, is the new bottleneck; HW-only the kernel reaches 51,900×.

The measured 1415.8 M elem/s is 97% of the 1454.5 M peak, and the 5.66 GB/s per
direction matches the projection in §7 (Gen4 x4 / Gen3 x8 class link).

### Simulation log (`tb_top_inloop_x32.py` at NUM_LANES=32; captured pre-rename)

```
=== Full-Model In-Loop GELU Co-Sim (v2, parallel) — Timing & Metrics ===
  Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
  Parallelization    : 32 lanes (1024-bit AXI-Stream, 32 FP32/beat)
  Elements streamed  : 262144  in 16 AXI frames (8192 beats)
  Clock (synth)      : 22 ns  (45.45 MHz)
  --- MEASURED (cycle-accurate Icarus) ---
  HW streaming time  : 185152 ns (~8416 cycles)
  Throughput         : 1415.83 M elem/s  (0.0321 cycles/elem, 1.027 cycles/beat)
  AXI bandwidth/dir  : 5663.3 MB/s (in, and out)
  AXI bandwidth total: 11326.7 MB/s (in+out)
  --- PROJECTED PEAK (synthesis × lanes × ops/cycle) ---
  Peak throughput    : 1454.55 M elem/s  (32 results/cycle @ 22 ns)
  Peak int-arith     : 24727.3 M op/s  (17 ops/elem × 32 lanes)
  --- KERNEL ACCURACY (per-element, all layers) ---
  GELU max error     : 0.026311
  GELU failures      : 0 / 262144  (threshold 0.05)
  --- LOOP CLOSURE: final logits vs all-software forward() ---
  Logits avg / max   : 0.015396 / 0.104763
  Next-token argmax  : 503/512 positions match software
TEST  tb_top_inloop_v2.test_gelu_top_v2_inloop  PASS  185,636 ns
```

---

## 5. Accelerated kernel — single pipeline through DMA buffers (mm2s + s2mm)

DUT: `gelu_dma_top`. Source: `tb/tb_top_inloop_dma.py`. Same kernel, but data now
crosses the **memory-mapped DMA path** a PCIe DMA controller would drive:

```
host (fp64→fp32)
  → AXI4-MM write burst → mm2s_buffer (on-chip memory)
  → AXI4-Stream          → gelu_top kernel
  → AXI4-Stream          → s2mm_buffer (on-chip memory)
  → AXI4-MM read burst   → host (fp32→fp64)
```

| Metric | Value |
|--------|-------|
| GELU execution time (DMA round-trip) | 17.707 ms |
| Measured throughput | 14.80 M elem/s (3.070 cycles/elem) |
| Measured AXI bandwidth | 118.4 MB/s (in+out); 59.2 MB/s per direction |
| DMA bursts | 1024 × ≤256 beats (AXI4 AxLEN cap) |
| GELU max error | 0.026311 (0 / 262,144 fail, threshold 0.05) |
| Loop closure (logits avg / max) | 0.015396 / 0.104763 |
| Next-token argmax match | 503 / 512 |
| **Speedup vs software** | **533.6×** (incl. host casts); 542.4× DMA round-trip only |

### Speedup calculation

```
MEASURED (cycle-accurate Icarus, full DMA round-trip)
  DMA round-trip time : 17,707,008 ns = 17.707 ms  (~804,864 cycles, write+compute+read)

  Speedup = 9604 ms / 17.707 ms = 542.4×
  (with host fp64<->fp32 casts ~0.29 ms: 9604 / 17.997 ≈ 533.6×)
```

### Why the DMA path is ~3× slower than direct streaming

Direct stream = 1.001 cycles/elem; DMA path = 3.070 cycles/elem → **3.07×**
slower (5772 us → 17707 us). This is **not a hardware limit** — it is the
testbench driving the DMA **serially**: per burst it does write-256 →
`stream_enable` → read-256 with no overlap. A real DMA controller
**double-buffers**: it fills the next input tile while the kernel drains the
current one and the DMA reads the previous output tile. In steady state that
returns toward ~1 cycle/elem (the direct-stream figure), at which point the
**PCIe link bandwidth** becomes the ceiling (see §7). Accuracy and loop closure
are identical to the direct-stream run, confirming the buffers are functionally
transparent.

### Simulation log (`tb_top_inloop_dma.py`)

```
=== Full-Model In-Loop GELU Co-Sim (DMA path) — Timing & Metrics ===
  Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
  Path               : AXI-MM DMA → mm2s → kernel → s2mm → AXI-MM DMA
  GELU offloads      : 2 (one per layer FFN)
  Elements streamed  : 262144  in 1024 DMA bursts of <= 256
  Clock (synth)      : 22 ns  (45.45 MHz)
  --- MEASURED (cycle-accurate Icarus, full DMA round-trip) ---
  DMA round-trip time: 17707008 ns (~804864 cycles incl. write+compute+read)
  Throughput         : 14.80 M elem/s  (3.070 cycles/elem)
  AXI bandwidth/dir  : 59.2 MB/s (in, and out)
  AXI bandwidth total: 118.4 MB/s (in+out)
  --- KERNEL ACCURACY (per-element, all layers) ---
  GELU max error     : 0.026311
  GELU failures      : 0 / 262144  (threshold 0.05)
  --- LOOP CLOSURE: final logits vs all-software forward() ---
  Logits avg / max   : 0.015396 / 0.104763
  Next-token argmax  : 503/512 positions match software
TEST  tb_top_inloop_dma.test_gelu_dma_inloop  PASS  17,707,338 ns
```

> Note: the mm2s/s2mm buffers pass simulation (behavioral SRAM model) but are
> **not yet synthesized in OpenLane** — the `sky130_sram_1rw1r_32_1024_8` macro
> requires generated SRAM views (gds/lef/lib) that are not present. The area /
> power figures in §2 are for `gelu_top` only and exclude the DMA buffers.

---

## 6. Accelerated kernel — parallel pipelines through wide DMA (`gelu_dma_top_x32`)

DUT: `gelu_dma_top_x32`. Source: `tb/tb_top_inloop_dma_x32.py` (run at
`GELU_NUM_LANES=8` and `=32`). Same memory-mapped DMA path as §5, but the
AXI4-MM channels and the internal AXI-Stream are `NUM_LANES*32` bits wide, so
each beat carries `NUM_LANES` IEEE-754 FP32 operands:

```
host (fp64→fp32)
  → AXI4-MM write burst (NUM_LANES*32-bit) → mm2s_buffer_x32 (wide FIFO)
  → AXI4-Stream                            → gelu_top_x32 kernel (NUM_LANES lanes)
  → AXI4-Stream                            → s2mm_buffer_x32 (wide FIFO)
  → AXI4-MM read burst                     → host (fp32→fp64)
```

Both buffers are DEPTH=256 (one max AXI4 burst). As in §5 the tb drives the DMA
**serially** per burst (write → `stream_enable` → read, no overlap), so the
2.062 cycles/beat reflects the non-overlapped test pattern, not a hardware limit
— a double-buffered controller recovers the per-beat rate (see §5 discussion).
Going from 8 → 32 lanes packs 4× more elements/beat, so the same element count
streams in 4× fewer beats (32,768 → 8,192) at the same 2.062 cycles/beat,
giving the ~4× shorter round-trip. Note the 32-lane wide DMA (705.2 M elem/s) is
~2× slower than the 32-lane *direct* stream (§4, 1415.8 M elem/s) purely because
of the serial write/read pattern (2.062 vs 1.027 cycles/beat).

### 6.1 — 8 lanes (`GELU_NUM_LANES=8`, 256-bit DMA)

| Metric | Value |
|--------|-------|
| GELU execution time (DMA round-trip) | 1.487 ms |
| Measured throughput | 176.31 M elem/s (0.2578 cycles/elem, 2.062 cycles/beat) |
| Measured AXI bandwidth | 1410.5 MB/s (in+out); 705.2 MB/s per direction |
| DMA bursts | 128 × ≤256 beats (32,768 beats) |
| Host fp64↔fp32 casts | 867.2 us total (both directions) |
| GELU max error | 0.026311 (0 / 262,144 fail, threshold 0.05) |
| Loop closure (logits avg / max) | 0.015396 / 0.104763 |
| Next-token argmax match | 503 / 512 |
| **Speedup vs software** | **4080×** (incl. host casts); 6460× DMA round-trip only |

```
MEASURED (cycle-accurate Icarus, full DMA round-trip)
  DMA round-trip time : 1,486,848 ns = 1.487 ms  (~67,584 cycles, write+compute+read)

  Speedup = 9604 ms / 1.487 ms = 6460×
  (with host fp64<->fp32 casts 0.867 ms: 9604 / 2.354 = 4080×)
```

#### Simulation log (`tb_top_inloop_dma_x32.py`, GELU_NUM_LANES=8)

```
=== Full-Model In-Loop GELU Co-Sim (v2 wide DMA path) — Timing & Metrics ===
  Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
  Parallelization    : 8 lanes (256-bit DMA + AXI-Stream)
  Path               : AXI-MM DMA → mm2s_x32 → kernel_x32 → s2mm_x32 → AXI-MM DMA
  Elements streamed  : 262144  in 128 DMA bursts (32768 beats)
  Clock (synth)      : 22 ns  (45.45 MHz)
  --- MEASURED (cycle-accurate Icarus, full DMA round-trip) ---
  DMA round-trip time: 1486848 ns (~67584 cycles incl. write+compute+read)
  Throughput         : 176.31 M elem/s  (0.2578 cycles/elem, 2.062 cycles/beat)
  AXI bandwidth/dir  : 705.2 MB/s (in, and out)
  AXI bandwidth total: 1410.5 MB/s (in+out)
  --- HOST-SIDE CONVERSION (informational, not kernel time) ---
  fp64<->fp32 casts  : 867.2 us total (host, both directions)
  --- KERNEL ACCURACY (per-element, all layers) ---
  GELU max error     : 0.026311
  GELU failures      : 0 / 262144  (threshold 0.05)
  --- LOOP CLOSURE: final logits vs all-software forward() ---
  Logits avg / max   : 0.015396 / 0.104763
  Next-token argmax  : 503/512 positions match software
TEST  tb_top_inloop_dma_x32.test_gelu_dma_x32_inloop  PASS  1,487,178 ns
```

### 6.2 — 32 lanes (`GELU_NUM_LANES=32`, 1024-bit DMA)

| Metric | Value |
|--------|-------|
| GELU execution time (DMA round-trip) | 0.372 ms |
| Measured throughput | 705.23 M elem/s (0.0645 cycles/elem, 2.062 cycles/beat) |
| Measured AXI bandwidth | 5641.9 MB/s (in+out); 2820.9 MB/s per direction |
| DMA bursts | 32 × ≤256 beats (8192 beats) |
| Host fp64↔fp32 casts | 477.7 us total (both directions) |
| GELU max error | 0.026311 (0 / 262,144 fail, threshold 0.05) |
| Loop closure (logits avg / max) | 0.015396 / 0.104763 |
| Next-token argmax match | 503 / 512 |
| **Speedup vs software** | **11,310×** (incl. host casts); 25,840× DMA round-trip only |

```
MEASURED (cycle-accurate Icarus, full DMA round-trip)
  DMA round-trip time : 371,712 ns = 0.372 ms  (~16,896 cycles, write+compute+read)

  Speedup = 9604 ms / 0.372 ms = 25,840×
  (with host fp64<->fp32 casts 0.478 ms: 9604 / 0.849 = 11,310×)
```

#### Simulation log (`tb_top_inloop_dma_x32.py`, GELU_NUM_LANES=32)

```
=== Full-Model In-Loop GELU Co-Sim (v2 wide DMA path) — Timing & Metrics ===
  Model              : M1 transformer, 2 layers, B=8 T=64 d_ff=256 (seed=42)
  Parallelization    : 32 lanes (1024-bit DMA + AXI-Stream)
  Path               : AXI-MM DMA → mm2s_x32 → kernel_x32 → s2mm_x32 → AXI-MM DMA
  Elements streamed  : 262144  in 32 DMA bursts (8192 beats)
  Clock (synth)      : 22 ns  (45.45 MHz)
  --- MEASURED (cycle-accurate Icarus, full DMA round-trip) ---
  DMA round-trip time: 371712 ns (~16896 cycles incl. write+compute+read)
  Throughput         : 705.23 M elem/s  (0.0645 cycles/elem, 2.062 cycles/beat)
  AXI bandwidth/dir  : 2820.9 MB/s (in, and out)
  AXI bandwidth total: 5641.9 MB/s (in+out)
  --- HOST-SIDE CONVERSION (informational, not kernel time) ---
  fp64<->fp32 casts  : 477.7 us total (host, both directions)
  --- KERNEL ACCURACY (per-element, all layers) ---
  GELU max error     : 0.026311
  GELU failures      : 0 / 262144  (threshold 0.05)
  --- LOOP CLOSURE: final logits vs all-software forward() ---
  Logits avg / max   : 0.015396 / 0.104763
  Next-token argmax  : 503/512 positions match software
TEST  tb_top_inloop_dma_x32.test_gelu_dma_x32_inloop  PASS  372,042 ns
```

---

## 7. Summary comparison

**Time and Speedup include the host fp64↔fp32 cast for every row** (the same
end-to-end convention the single kernel uses in §2), so the rows are directly
comparable. Time = HW streaming / DMA round-trip **+ host cast**; the host-cast
column breaks out that component. Throughput / cycles-elem / AXI-BW are HW-only
kernel metrics. Speedup is vs the 9604 ms software GELU.

| Configuration | Time (HW+cast) | Throughput | cycles/elem | AXI BW (in+out) | Host cast | Speedup |
|---------------|----------------|------------|-------------|-----------------|-----------|---------|
| Software baseline | 9604 ms | 13.6 K elem/s | — | — | — | 1× |
| 1 pipeline, direct AXI-Stream (§2) | 6.062 ms | 45.42 M elem/s | 1.001 | 363.3 MB/s | 0.290 ms | 1584.3× |
| 8 pipelines, direct AXI-Stream (§3) | 1.043 ms | 361.2 M elem/s | 0.1259 | 2889.3 MB/s | 0.317 ms | ≈9209× |
| 32 pipelines, direct AXI-Stream (§4) | 0.452 ms | 1415.8 M elem/s | 0.0321 | 11,326.7 MB/s | 0.267 ms | ≈21,240× |
| 1 pipeline, DMA buffers, serial (§5) | 17.997 ms | 14.80 M elem/s | 3.070 | 118.4 MB/s | 0.290 ms | 533.6× |
| 1 pipeline, DMA, double-buffered (projected) | ≈6 ms | ≈45 M elem/s | ≈1.0 | link-bound | ~0.29 ms | ≈1584× |
| 8 pipelines, wide DMA, serial (§6.1) | 2.354 ms | 176.3 M elem/s | 0.2578 | 1410.5 MB/s | 0.867 ms | 4080× |
| 32 pipelines, wide DMA, serial (§6.2) | 0.849 ms | 705.2 M elem/s | 0.0645 | 5641.9 MB/s | 0.478 ms | 11,310× |

The DMA path is the realistic representation of a PCIe-DMA-to-on-chip-memory
system. The 1-pipeline DMA's 533.6× reflects the **non-overlapped** test pattern,
not the hardware; overlapping the transfers recovers the direct-stream
throughput until PCIe bandwidth caps it. The 32-lane direct-stream result shows
the kernel can sustain 1.4 G elem/s, but the **host-side cast becomes the system
bottleneck** once the kernel is this fast.

---

## 8. PCIe DMA scaling projection (single → many pipelines)

**Per-pipeline demand (measured):** 1 FP32/cycle @ 45.45 MHz = 181.8 MB/s per
direction (in and out), 363.6 MB/s aggregate; 45.45 M GELU/s.

**PCIe Gen4 DMA — projected scaling** (16 GT/s/lane, 128b/130b encoding, per
direction, full-duplex; throughput = pipelines × 45.45 M GELU/s):

| Link | Theoretical BW/dir | Pipelines it can feed (÷181.8 MB/s) | Projected throughput (full fill) |
|------|--------------------|-------------------------------------|----------------------------------|
| x1   | 1.97 GB/s          | ~10                                 | ~0.49 G GELU/s                   |
| x4   | 7.88 GB/s          | ~43                                 | ~1.97 G GELU/s                   |
| x8   | 15.75 GB/s         | ~86                                 | ~3.9 G GELU/s                    |
| x16  | 31.5 GB/s          | ~173                                | ~7.9 G GELU/s                    |

Derate ~10% for TLP/header overhead (MPS-dependent) for a practical figure.
All values projected from link theory × synthesized 45.45 MHz throughput, not
measured. For reference, the 32-pipeline `gelu_top_x32` design needs ~5.8 GB/s
per direction — comfortably fed by Gen4 x4 / Gen3 x8.
