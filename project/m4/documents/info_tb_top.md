# info_tb_top — Annotated walkthrough of `tb_top.py`

Maps each region of `tb/tb_top.py` to the hardware it represents. `tb_top.py` is
the **full-model in-loop benchmark**: it runs the real M1 transformer forward
pass and offloads **every GELU activation** to `gelu_top` over a direct
AXI-Stream, then checks per-element accuracy and end-to-end loop closure against
an all-software reference.

> This is the **direct-stream** path (no DMA, no on-chip memory). The DMA /
> PCIe-style backend is a separate testbench, `tb_top_inloop_dma.py`, which
> hand-drives AXI4-MM bursts through `mm2s`/`s2mm` FIFO buffers — see the
> "Where DMA/PCIe lives" section at the end.

---

## System architecture — what the testbench models

```
┌──────────────────────────────────────────────────────────────────────┐
│  HOST (Python coroutines in tb_top.py)                                │
│                                                                       │
│   transformer.forward()  —  real M1 model, run layer by layer         │
│       │  at each layer FFN: h = xn2 @ W1 + b1   (fp64)                │
│       │  needs GELU(h) back from hardware                            │
│       ▼                                                               │
│   hw_gelu():  fp64 → fp32  →  AXI-Stream  →  fp32 → fp64              │
└───────┼───────────────────────────────────────────────────────────────┘
        │  AXI4-Stream beats (NUM_LANES × FP32 per beat)
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  DEVICE                                                               │
│   ┌────────────────────────────────────────────────────────────────┐ │
│   │  gelu_top  (RTL DUT, the only block running in Icarus)         │ │
│   │   s_axil  ── AXI-Lite ctrl CSRs (enable, NUM_LANES id)         │ │
│   │   s_axis  ── FP32 input stream  (NUM_LANES lanes packed/beat)  │ │
│   │   m_axis  ── FP32 GELU output                                  │ │
│   └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

Everything except `gelu_top` is a Python coroutine driven by `cocotbext-axi`
VIPs. The host↔device boundary is the `axis_source.write()` / `axis_sink.recv()`
call inside `hw_gelu`.

---

## Configuration (module top)

| Constant | Value | Meaning |
|----------|-------|---------|
| `CLK_NS` / `F_CLK_HZ` | 22 ns / 45.45 MHz | the synthesized clock; all timing metrics are reported at this period |
| `NUM_LANES` | `int(os.environ["GELU_NUM_LANES"])`, default 32 | parallel `gelu_fp32` pipelines; **env-driven so one tb covers x1/x8/x16/x32** |
| M1 config | `B=8, T=64, D_MODEL=64, N_HEADS=4, D_FF=256, N_LAYERS=2, SEED=42` | the small transformer whose GELUs are offloaded |
| `CHUNK` | 16384 | max elements per AXI-Stream TLAST frame (must be a whole number of `NUM_LANES`-wide beats) |
| `GELU_THRESHOLD` | 0.05 | per-element accuracy contract — a result above this counts as a failure |
| `ARITH_OPS_PER_ELEM` | 17 | datapath integer-op count for the projected-peak metric |

`transformer.py` (the M1 model) is imported from `../orginal_software` so the
in-loop forward uses the *exact* software functions.

---

## `hw_gelu()` — offload one GELU tensor to the DUT

The core host↔hardware bridge. Called once per layer FFN with the fp64 tensor
`h`; returns `GELU(h)` as fp64.

1. **Host fp64 → fp32 cast** (`flat.astype(np.float32)`), timed into
   `acc["conv_us"]` — this is the conversion cost that becomes the Amdahl
   bottleneck at high lane counts.
2. **Stream in `CHUNK`-sized frames.** For each chunk:
   ```python
   t0      = get_sim_time('ns')
   recv_co = cocotb.start_soon(axis_sink.recv())  # arm the sink FIRST
   await axis_source.write(payload)               # host → AXI-Stream → DUT
   frame   = await recv_co                        # DUT → AXI-Stream → host
   t1      = get_sim_time('ns')
   ```
   The sink is armed **before** driving input because `gelu_top` has a 12-cycle
   pipeline; arming first keeps `m_axis_tready` high so the first results don't
   stall. Only this window consumes simulated time (`acc["lat_ns"]`).
3. **Slice padded lanes.** A chunk that isn't a whole multiple of `NUM_LANES`
   gets zero-padded to a full beat by `cocotbext-axi`; the read-back is sliced
   to `seg.size` so trailing pad lanes are dropped.
4. **Host fp32 → fp64 cast**, also timed into `conv_us`.
5. Accumulates `elems`, `bytes` (in+out), `chunks`, `beats` (ceil-div by lanes).

**Why the payload is width-transparent:** `cocotbext-axi` is a *byte-stream*
model. Widening `s_axis_tdata` from 32 to `NUM_LANES×32` bits just means more
bytes move per beat — the same little-endian FP32 buffer goes in and comes back.
The kernel result is identical across lane counts; only the beat count (and thus
timing) changes.

---

## `test_gelu_top_inloop()` — the test body

### 1. Clock, reset, VIPs
Starts a 22 ns clock, pulses `rst`, then instantiates three VIPs on the DUT
ports: `AxiLiteMaster` (`s_axil`), `AxiStreamSource` (`s_axis`),
`AxiStreamSink` (`m_axis`).

### 2. Lane-width self-check
```python
bus_lanes = len(dut.s_axis_tdata) // 32
assert bus_lanes == NUM_LANES
```
Guarantees the RTL was built at the lane count the tb expects — a mismatched
`GELU_NUM_LANES` build fails loudly here instead of silently mis-packing.

### 3. AXI-Lite control
- Writes `0x00 ← 1` (`pipeline_enable`) and reads it back.
- Reads the **read-only `0x04` CSR** (the `NUM_LANES` identity register) and
  asserts it equals `NUM_LANES` — a second, independent confirmation of the
  build's lane count from inside the RTL.

### 4. Build model + software reference
`init_params(...)` builds the M1 weights; `forward(token_ids, params, config)`
produces `logits_ref`, the **all-software** result the hardware loop is checked
against.

### 5. In-loop forward (the heart)
Re-implements `transformer.forward()` step by step using the real `transformer.py`
functions (`layer_norm_forward`, `mha_forward`, `gelu`), but at each layer's
feed-forward it computes `h = xn2 @ W1 + b1` in software and then **offloads the
GELU to hardware** via `hw_gelu`. Per layer it also checks kernel accuracy:
```python
ref_act = gelu(h.astype(np.float32).astype(np.float64))  # fp32-quantised ref
err     = np.abs(h_act - ref_act)
acc["gelu_max_err"]  = max(acc["gelu_max_err"], err.max())
acc["gelu_fail"]    += (err > GELU_THRESHOLD).sum()
```
The reference is the fp64 GELU of the **fp32-quantised** input, so the check
isolates the PWL approximation error from the fp32 cast.

### 6. Loop closure
After both layers, computes `logits_hw` and compares to `logits_ref`:
- `logit` avg / max absolute error (informational), and
- **next-token argmax agreement** — does the HW-in-the-loop model pick the same
  token as the all-software model at each of `B×T` positions.

### 7. Metrics + PASS/FAIL
Aggregates throughput (`elem/s`, cycles/elem, cycles/beat), AXI bandwidth
(per-dir and total), and the projected synthesis peak (`NUM_LANES` results/cycle),
and prints the timing/accuracy block seen in `sim/inloop_*_run.log`. The test
**PASSES iff `gelu_fail == 0`** (every element within 0.05); loop-closure
numbers are reported but not gating.

---

## Where DMA / PCIe lives (not in this tb)

`tb_top.py` streams straight into the DUT — there is **no on-chip memory or DMA**
in this path. The PCIe-DMA story is modeled separately:

| Concern | `tb_top.py` (this file) | `tb_top_inloop_dma.py` |
|---------|-------------------------|------------------------|
| DUT | `gelu_top` | `gelu_dma_top` (kernel + `mm2s`/`s2mm` buffers) |
| Data into kernel | direct AXI-Stream | AXI4-MM **burst** write → `mm2s` FIFO → AXI-Stream |
| Data out of kernel | direct AXI-Stream | AXI-Stream → `s2mm` FIFO → AXI4-MM **burst** read |
| Buffers | none | 256-deep FIFO, width = bus width |
| What it shows | kernel-limited throughput | DMA round-trip cost (the serial write→compute→read penalty) |

PCIe link bandwidth itself is never simulated (both paths are clock-domain
ideal). The external-interface ceiling is treated analytically in
`bench/benchmark.md §5` (PCIe Gen4 x1/x4/x8/x16 scaling projection).

---

## Summary — Python vs RTL

| Block | `tb_top.py` | A full-system extension |
|-------|-------------|-------------------------|
| `gelu_top` DUT | Icarus RTL ✓ | Icarus RTL ✓ |
| AXI-Lite master (config) | `cocotbext-axi` VIP | `cocotbext-axi` VIP |
| AXI-Stream source/sink | `cocotbext-axi` VIP | `cocotbext-axi` VIP |
| Host model + reference | real `transformer.py` in Python | same |
| DMA controller / on-chip mem | none (direct stream) | `gelu_dma_top` (see `tb_top_inloop_dma.py`) |
| PCIe endpoint / TLP engine | not modeled | `cocotbext-pcie` (future) |
| PCIe link timing | analytical (`benchmark.md §5`) | analytical |

The DUT only ever sees AXI-Stream handshakes, so the kernel result is identical
whether it is fed directly (here) or through a DMA controller — only the timing
differs.
