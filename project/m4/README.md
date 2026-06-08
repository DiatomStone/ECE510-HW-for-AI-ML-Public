# M4 GELU Accelerator — Final Deliverable Package

A hardware **GELU activation kernel** that offloads the FFN GELU of a small M1
transformer. FP32 in → internal Q16.16 PWL approximation → FP32 out; pipelined,
**12-cycle latency, 1 result/cycle/lane** at the synthesized **22 ns clock
(45.45 MHz)**. The design is parameterized for SIMD width (`NUM_LANES`): the M4
final hardened design is the **8-lane streaming** build (`gelu_top` @
`GELU_NUM_LANES=8`, 256-bit AXI-Stream); a 1-lane build is kept as the baseline.

- **Design justification report:** [`report/design_justification.md`](report/design_justification.md)
- **Benchmark + speedup vs software:** [`bench/benchmark.md`](bench/benchmark.md)
  (raw data: [`bench/benchmark_data.csv`](bench/benchmark_data.csv))

---

## M4 deliverable map (checklist item → path)

| # | Deliverable | Path(s) in this folder |
|---|-------------|------------------------|
| 1 | M4 folder README (this file) | `README.md` |
| 2 | Final RTL — top, compute core, interface | `rtl/top.sv`, `rtl/compute_core.sv`, `rtl/interface.sv` (+ `gelu_fp32`, `fp32_to_q16`, `q16_to_fp32`) |
| 2 | Final testbench | `tb/tb_top.py` (cocotb full-model in-loop co-sim) |
| 2 | Final simulation log (PASS) | `sim/final_run.log` (8-lane in-loop, PASS) |
| 2 | Final waveform image | `sim/final_waveform.png` |
| 3 | Synthesis results (config, run log, timing, area, power) | `synth/config.json`, `synth/openlane_run.log`, `synth/timing_report.txt`, `synth/area_report.txt`, `synth/power_report.txt` |
| 4 | Benchmark + speedup (+ energy) | `bench/benchmark.md` |
| 4 | Raw measurement data | `bench/benchmark_data.csv`, `bench/sim_output/` |
| 4 | Final roofline plot | `bench/roofline_final.png` |
| 5 | Design justification report | `report/design_justification.md` (PDF export pending) |

> **Synthesis files (item 3) are at the exact checklist paths** — `synth/config.json`,
> `synth/openlane_run.log`, `synth/timing_report.txt`, `synth/area_report.txt`,
> `synth/power_report.txt` — for the final **8-lane `gelu_top`** design
> (run `RUN_2026-06-07_14-45-32`, headers read `gelu_top`). The **1-lane baseline**
> reports are in `synth/gelu_x1s/` (same file set).

> **Final testbench naming.** The checklist names `tb/tb_top.sv`; this is a cocotb
> project, so the testbench is **`tb/tb_top.py`** (there is no SystemVerilog tb).
> It is run via `make opt=inloop_x8` / `helper_script/sim_master.sh inloop_x8`.

> **RTL diff vs M3.** The top/interface modules were unified and renamed
> `gelu_top_x32`→`gelu_top`, `gelu_axi_stream_interface_x32`→`gelu_axi_stream_interface`
> into a single parameterized source (`top.sv` / `interface.sv`, lane count set by
> `GELU_NUM_LANES`). Numerically identical to the M3 8-lane design.

---

## File Index

### Top level

| Path | Description | Supports |
|------|-------------|----------|
| `README.md` | This file — M4 catalog + reproduction steps | Item 1 |
| `Makefile` | cocotb/Icarus build rules; `opt=<target>` selects DUT + testbench | Item 2 |

### `rtl/` — RTL sources (item 2)

| Path | Description |
|------|-------------|
| `rtl/top.sv` | `gelu_top` — synthesis top; thin wrapper around the interface. Parameterized SIMD (**final M4 design**, hardened @ `NUM_LANES=8`) |
| `rtl/interface.sv` | `gelu_axi_stream_interface` — AXI4-Lite control + AXI4-Stream datapath + output FIFO + backpressure; `NUM_LANES*32`-bit bus, scalar handshake |
| `rtl/gelu_fp32.sv` | `gelu_fp32` — 12-cycle FP32 GELU pipeline; chains the three stages below |
| `rtl/compute_core.sv` | `compute_core` — 4-stage Q16.16 PWL GELU (20 non-uniform segments) |
| `rtl/fp32_to_q16.sv` | `fp32_to_q16` — 4-stage IEEE-754 FP32 → Q16.16 (RNE, FTZ, saturate) |
| `rtl/q16_to_fp32.sv` | `q16_to_fp32` — 4-stage Q16.16 → IEEE-754 FP32 (CLZ normalise, RNE) |
| `rtl/DMA_memory/gelu_dma_top.sv` | `gelu_dma_top` — parameterized DMA wrapper (mm2s + `gelu_top` + s2mm); `NUM_LANES*32`-bit AXI4-MM + AXI-Stream |
| `rtl/DMA_memory/mm2s_buffer.sv`, `s2mm_buffer.sv` | Input/output DMA buffers — macro-free inferred FIFO (`DATA_W=NUM_LANES*32`, `DEPTH=256`) |

### `tb/` — cocotb testbenches (item 2)

Per-test coverage is catalogued in [`documents/TB_summary.md`](documents/TB_summary.md).

| Path | Description |
|------|-------------|
| `tb/tb_top.py` | **Final benchmark tb** — full-model in-loop co-sim of `gelu_top` (x1/x8/x16/x32 via `GELU_NUM_LANES`) |
| `tb/tb_top_inloop_dma.py` | Full-model in-loop through the DMA path, parameterized `gelu_dma_top` (x1/x8/x16/x32) |
| `tb/tb_interface.py` | AXI-Stream/Lite interface protocol tb (parameterized SIMD) |
| `tb/tb_gelu_fp32.py` | `gelu_fp32` end-to-end datapath unit tb |
| `tb/tb_compute_core.py` | `compute_core` PWL GELU unit tb |
| `tb/tb_fp32_to_q16.py`, `tb/tb_q16_to_fp32.py` | Format-converter unit tbs |

### `sim/` — simulation logs (item 2) and waveform

| Path | Description |
|------|-------------|
| `sim/final_run.log` | **Final 8-lane in-loop run (PASS) — item-2 deliverable** |
| `sim/final_waveform.png` | **Final end-to-end transaction waveform — item-2 deliverable** |
| `sim/final_run_dma_x8.log` | 8-lane DMA round-trip in-loop run (PASS) |
| `sim/inloop_x1_run.log`, `inloop_x8_run.log`, `inloop_x16_run.log`, `inloop_x32_run.log` | Direct-stream in-loop runs per lane count (PASS) |
| `sim/inloop_dma_x1_run.log`, `inloop_dma_x8_run.log`, `inloop_dma_x16_run.log`, `inloop_dma_x32_run.log` | DMA-path in-loop runs per lane count (PASS) |
| `sim/interface_run.log`, `sim/interface_x32_run.log` | Interface protocol tb logs |
| `sim/compute_core_run.log`, `sim/gelu.log`, `sim/fp32_to_p16.log`, `sim/p16_to_fp32.log` | Sub-module tb logs |
| `sim/cosim_run.log`, `sim/mm2s_buffer_run.log`, `sim/s2mm_buffer_run.log`, `sim/openram_wrap_run.log`, `sim/gelu_dma_top_run.log` | Earlier integration / DMA-buffer tb logs |

> **Naming note.** The in-loop simulation outputs were renamed from
> `inloop_x<lane>` to **`final_run_x<lane>`** (and `inloop_dma_x<lane>` →
> `final_run_dma_x<lane>`) so they match the M4 `sim/final_run.log` deliverable.
> **They are the same simulation output** — only the filename changed, plus the
> saved log is now the summary block (`tail`) instead of the multi-MB full
> capture; the measured results (HW time, throughput, accuracy, PASS) are
> identical (verified by diffing the tails). `sim_master.sh` applies this for all
> `inloop_*` targets. The per-lane `inloop_*` logs still present above are the
> earlier full captures.

### `synth/` — synthesis (item 3)

The flat files below are the **item-3 deliverables for the final 8-lane design**.

| Path | Description | Item 3 |
|------|-------------|:------:|
| `synth/config.json` | Exact OpenLane2 config (`DESIGN_NAME=gelu_top`, `GELU_NUM_LANES=8`, 22 ns) | ✅ |
| `synth/openlane_run.log` | Full flow log (`RUN_2026-06-07_14-45-32`, ends `Flow complete.`) | ✅ |
| `synth/timing_report.txt` | Post-route STA — WNS/slack, clock period, per-corner | ✅ |
| `synth/area_report.txt` | Total area (µm²) + cell counts by type/module | ✅ |
| `synth/power_report.txt` | Power estimate (nom_tt 1.8 V; ff-corner bound noted) | ✅ |
| `synth/critical_path.md` | Narrative of the critical path (the stage-3 multiply) | support |
| `synth/{summary,stat,power}.rpt`, `synth/{wns,ws}.{max,min}.rpt` | Raw OpenROAD/Yosys reports behind the curated ones | support |
| `synth/gelu_x1s/` | Same report set for the **1-lane baseline** | support |
| `synth/config_v1.json`, `config_x8.json`, `config_x16.json`, `config_x32.json`, `config_dma.json` | OpenLane2 configs for each build variant | support |
| `synth/CURATED_REPORTS_HOWTO.md` | How a raw run is distilled into the curated reports | support |
| `synth/runs/` | Raw OpenLane2 run artifacts (generated; not catalogued) | — |

### `bench/` — benchmark comparison (item 4)

| Path | Description |
|------|-------------|
| `bench/benchmark.md` | Throughput, speedup vs software, energy (incl. SW-baseline estimate), synthesis comparison, roofline, PCIe projection, detailed measurements |
| `bench/benchmark_data.csv` | Raw per-config measurements behind the summary |
| `bench/roofline_final.png` | Final roofline plot (OP/s vs OP/B; measured x8 accelerator point) |
| `bench/roofline_final_elem.png` | Roofline in the elements/s view (G elem/s vs elem/B) |
| `bench/roofline_all.png` | Roofline with **all** measured configs, OP/B view (x1/x8/x16/x32, stream + DMA) |
| `bench/roofline_all_elem.png` | Roofline with **all** measured configs, elem/B view |
| `bench/roofline_flop.png` | Floating-point roofline (FLOP/B): software baseline + measured x8 |
| `bench/speedup.png` | Speedup-vs-lane-count chart |
| `bench/sim_output/` | Extracted metrics blocks (`s1…s6`) from the in-loop runs (provenance) |

### `report/`

| Path | Description |
|------|-------------|
| `report/design_justification.md` | 9-section design justification report (PDF export pending) |
| `report/PWL_values_check.png` | PWL GELU fit vs reference (max err ≈0.026) |
| `report/roofline_plot.png` | §II roofline figure — software baseline only (memory-bound), via `make_roofline.py swonly` |
| `report/speedup.png` | Speedup figure referenced by the report |

### `documents/` — supporting material

| Path | Description |
|------|-------------|
| `documents/M4_requirement.md` | The milestone-4 assignment spec (reference) |
| `documents/gelu_pipeline_stages.md` | Stage-by-stage description of the 12-cycle `gelu_fp32` pipeline |
| `documents/TB_summary.md` | What each testbench / individual test covers |
| `documents/info_tb_top.md` | Annotated walkthrough of `tb_top.py` |
| `documents/explanation.md` | Walkthrough of each logical block in the interface |
| `documents/PWL_values_check.png` | Plot verifying the 20-segment PWL GELU coefficients |

### `helper_script/`, `orginal_software/`

| Path | Description |
|------|-------------|
| `helper_script/sim_master.sh` | Unified cocotb/Icarus runner (table-driven; `opt=` targets) |
| `helper_script/run_openlane2.sh` | OpenLane2 launcher (variant-aware: `v1`/`x8`/`x16`/`x32`/`dma`) |
| `helper_script/make_roofline.py` | Regenerates the roofline figures from `benchmark_data.csv` — `swonly`→`report/roofline_plot.png` (report §II, sw only), `flop`→`bench/roofline_flop.png`, `op`→`bench/roofline_final.png`, `elem`→`bench/roofline_final_elem.png`, `allpts`→`bench/roofline_all.png`, `allelem`→`bench/roofline_all_elem.png` (needs numpy + matplotlib) |
| `orginal_software/transformer.py`, `train.py` | Reference M1 transformer model + trainer (GELU is the accelerated kernel) |
| `orginal_software/project_profile.txt` | M1 software profiling data |

---

## Reproducing the simulation

Dependencies: Icarus Verilog 13, Python 3.13, cocotb 2.0.0, cocotbext-axi, numpy.

```bash
python3 -m venv ~/.venv
~/.venv/bin/pip install cocotb==2.0.0 cocotbext-axi numpy
```

Run the **final (8-lane) full-model in-loop co-simulation** — the run behind the
M4 benchmark numbers:

```bash
cd project/m4
./helper_script/sim_master.sh inloop_x8        # → sim/final_run_x8.log (summary)
```

Expected tail:

```
GELU failures      : 0 / 262144  (threshold 0.05)
tb_top.test_gelu_top_inloop  PASS
```

Other targets (`./helper_script/sim_master.sh list` for the full set):
`inloop_x1`, `inloop_x16`, `inloop_x32`, `inloop_dma_x8`, `interface_x8`,
`compute_core`, `gelu`, `convin`, `convout`, etc.

## Reproducing the synthesis

OpenLane 2 via Nix; `OPENLANE2_ROOT` and `PDK_ROOT` set. Run the final 8-lane
hardening:

```bash
cd project/m4
./helper_script/run_openlane2.sh full x8       # uses synth/config_x8.json → gelu_top @ NUM_LANES=8
```

Output lands in `synth/runs/RUN_<timestamp>/`; the curated item-3 reports for the
committed run are the flat files in `synth/`.

### Final synthesis result (8-lane `gelu_top`, sky130A)

| Metric | Value |
|--------|-------|
| Clock period closed | 22 ns (45.45 MHz) |
| WNS setup / hold (all 9 corners) | 0.0 ns / 0.0 ns — **timing met**, TNS = 0 |
| Worst setup slack | +11.382 ns (nom_tt); +0.468 ns (worst corner) |
| Synth cell area | 676,371 µm² (placed 738,475; die 1,733,820) |
| Cell count / flip-flops | 58,045 / 8,451 |
| Total power (nom_tt 1.8 V) | 228.37 mW (267.8 mW at the 1.95 V ff corner) |

See `synth/{timing,area,power}_report.txt` and `synth/critical_path.md` for
detail; the 1-lane baseline is in `synth/gelu_x1s/`.

---

## Design hierarchy (final 8-lane build)

```
gelu_top                          (rtl/top.sv)
└── gelu_axi_stream_interface     (rtl/interface.sv)
    └── 8 × gelu_fp32                 (rtl/gelu_fp32.sv)   ← generate loop, NUM_LANES=8
        ├── fp32_to_q16               (rtl/fp32_to_q16.sv)
        ├── compute_core              (rtl/compute_core.sv)
        └── q16_to_fp32               (rtl/q16_to_fp32.sv)
```
