# M3 GELU Accelerator — AXI Interface + Synthesis

Milestone 3 adds a full AXI4-Stream / AXI4-Lite wrapper around the GELU FP32
pipeline and takes the design through OpenLane 2 RTL-to-GDSII synthesis on
sky130A.

---

## File Index

Every file and subfolder under `project/m3/` is listed below.

### Top level

| Path | Description |
|------|-------------|
| `README.md` | This file — M3 index, reproduction steps |
| `Makefile` | cocotb/Icarus build rules; `opt=` selects the DUT and testbench |
| `explanation.md` | Detailed walkthrough of each logical block in `interface.sv` |
| `synthesis_notes.md` | Narrative: what synthesized, what changed, scope status (≥500 words) |
| `PWL_values_check.png` | Plot verifying the 20-segment PWL GELU coefficients |

### `rtl/`

| Path | Description |
|------|-------------|
| `rtl/top.sv` | `gelu_top` — synthesis top; pure passthrough wrapper around `gelu_axi_stream_interface` |
| `rtl/interface.sv` | `gelu_axi_stream_interface` — AXI4-Lite control + AXI4-Stream datapath + output FIFO + backpressure |
| `rtl/gelu_fp32.sv` | `gelu_fp32` — 12-cycle FP32 end-to-end GELU pipeline; chains the three stages below |
| `rtl/compute_core.sv` | `compute_core` — 4-stage Q16.16 PWL GELU (20 non-uniform segments) |
| `rtl/fp32_to_q16.sv` | `fp32_to_q16` — 4-stage IEEE-754 FP32 → Q16.16 converter with RNE rounding |
| `rtl/q16_to_fp32.sv` | `q16_to_fp32` — 4-stage Q16.16 → IEEE-754 FP32 converter with CLZ normalisation |

### `tb/`

| Path | Description |
|------|-------------|
| `tb/tb_top.py` | cocotb end-to-end testbench for `gelu_top` — drives AXI-Lite control and AXI-Stream I/O, compares 256 outputs against `gelu_exp.hex`, prints PASS/FAIL |
| `tb/gen_vectors.py` | Generates `gelu_in.hex` and `gelu_exp.hex` by running a forward pass through the M1 small-config transformer (seed=42, batch=0, token=0, d_ff=256) |
| `tb/gelu_in.hex` | 256 FP32 input test vectors (FFN layer-0 pre-activation h), one 8-digit hex value per line |
| `tb/gelu_exp.hex` | 256 FP32 expected GELU outputs computed in float64 from `gelu_in.hex` (independent software reference) |
| `tb/tb_axis_interface.py` | cocotb testbench for `gelu_axi_stream_interface` — 6 tests covering AXI-Lite control, pipeline gate, single value, TLAST, backpressure, and 50-point accuracy sweep |
| `tb/tb_gelu_fp32.py` | cocotb testbench for the full `gelu_fp32` pipeline |
| `tb/tb_compute_core.py` | cocotb testbench for `compute_core` only |
| `tb/tb_fp32_to_q16.py` | cocotb testbench for the FP32→Q16 converter |
| `tb/tb_q16_to_fp32.py` | cocotb testbench for the Q16→FP32 converter |
| `tb/tb_conversion.py` | Conversion round-trip testbench (fp32→q16→fp32) |
| `tb/archived/tb_top.sv` | Original SystemVerilog testbench for `gelu_top` (archived; superseded by `tb_top.py`) |

### `sim/`

| Path | Description |
|------|-------------|
| `sim/cosim_run.log` | Passing cocotb transcript for `tb_top` end-to-end co-simulation — TESTS=1 PASS=1, 256 beats, max error 0.0263, 0 failures |
| `sim/cosim_waveform.png` | Annotated waveform screenshot showing AXI-Lite write, AXI-Stream input burst, and AXI-Stream output burst |
| `sim/cosim_waveform.vcd` | VCD waveform dump from co-simulation |
| `sim/cosim_run.vcd` | VCD dump from the co-simulation run |
| `sim/interface_run.log` | Passing cocotb transcript for `tb_axis_interface` — TESTS=6 PASS=6 |
| `sim/gelu.log` | Passing cocotb transcript for `tb_gelu_fp32` |
| `sim/compute_core_run.log` | Passing cocotb transcript for `tb_compute_core` |
| `sim/fp32_to_p16.log` | Passing cocotb transcript for `tb_fp32_to_q16` |
| `sim/p16_to_fp32.log` | Passing cocotb transcript for `tb_q16_to_fp32` |

### `synth/`

| Path | Description |
|------|-------------|
| `synth/config.json` | OpenLane 2 flow configuration (design name, RTL sources, clock period, PDK) |
| `synth/openlane_run.log` | Full OpenLane 2 flow log — RUN_2026-05-24_21-40-35, 78 steps, no errors |
| `synth/timing_report.txt` | Post-route STA summary — WNS=0.0 ns all 9 corners (timing met) |
| `synth/area_report.txt` | Post-route area report — 90,650 µm², 7,704 cells, 1,142 FFs |
| `synth/power_report.txt` | Post-route power estimate — 34.22 mW at nom_tt_025C_1v80 |
| `synth/critical_path.md` | Narrative analysis of the critical path (32×32 multiply in compute_core) |
| `synth/power.rpt` | Raw OpenROAD power report (source for `power_report.txt`) |
| `synth/stat.rpt` | Raw OpenROAD statistics report (cell counts by type) |
| `synth/wns.max.rpt` | OpenROAD worst negative slack — max (setup) corners |
| `synth/wns.min.rpt` | OpenROAD worst negative slack — min (hold) corners |
| `synth/ws.max.rpt` | OpenROAD worst slack — max corners |
| `synth/ws.min.rpt` | OpenROAD worst slack — min corners |

### `helper_script/`

| Path | Description |
|------|-------------|
| `helper_script/run_openlane2.sh` | Runs the full OpenLane 2 RTL-to-GDSII flow for `gelu_top` |
| `helper_script/sim_interface.sh` | Runs the AXI interface cocotb simulation; logs to `sim/interface_run.log` |
| `helper_script/sim_gelu.sh` | Runs the `gelu_fp32` cocotb simulation |
| `helper_script/sim_compute_core.sh` | Runs the `compute_core` cocotb simulation |
| `helper_script/sim_fp32_to_q16.sh` | Runs the FP32→Q16 cocotb simulation |
| `helper_script/sim_q16_to_fp32.sh` | Runs the Q16→FP32 cocotb simulation |
| `helper_script/sim_top.sh` | Runs the end-to-end `gelu_top` co-simulation; logs to `sim/cosim_run.log` |

### `orginal_software/`

| Path | Description |
|------|-------------|
| `orginal_software/transformer.py` | Reference PyTorch transformer model; GELU is the activation being accelerated |
| `orginal_software/train.py` | Reference training script for the transformer model |

---

## Reproducing the Co-Simulation

### Dependencies

| Tool | Version used |
|------|-------------|
| Icarus Verilog | 13.0 (stable) |
| Python | 3.13 |
| cocotb | 2.0.0 |
| cocotbext-axi | 0.1.28 |
| numpy | (any recent; 2.x tested) |

Install the Python dependencies into a virtual environment:

```bash
python3 -m venv ~/.venv
~/.venv/bin/pip install cocotb==2.0.0 cocotbext-axi numpy
```

Icarus Verilog 13 must be on `PATH` as `iverilog` and `vvp`. On Fedora:

```bash
sudo dnf install iverilog
```

### Generating test vectors (required before first run)

```bash
cd project/m3
source ~/.venv/bin/activate
python tb/gen_vectors.py
```

This writes `tb/gelu_in.hex` and `tb/gelu_exp.hex`. The committed copies are
already present; re-run only if you change the model configuration.

### Running the end-to-end co-simulation (M3 primary simulation)

```bash
cd project/m3
source ~/.venv/bin/activate
make opt=top SIM=icarus
```

Or via the helper script:

```bash
bash "helper_script/sim_top.sh"
```

Expected result:

```
PASS
TESTS=1 PASS=1 FAIL=0 SKIP=0
```

The committed log is `sim/cosim_run.log`.

### Running the AXI interface testbench

```bash
cd project/m3
bash "helper_script/sim_interface.sh"
```

Expected result:

```
TESTS=6 PASS=6 FAIL=0 SKIP=0
```

### Running other module testbenches

```bash
# Full gelu_fp32 pipeline
bash "helper_script/sim_gelu.sh"

# compute_core only
bash "helper_script/sim_compute_core.sh"

# Converters
bash "helper_script/sim_fp32_to_q16.sh"
bash "helper_script/sim_q16_to_fp32.sh"
```

---

## Reproducing the Synthesis Run

### OpenLane 2 version

| Item | Value |
|------|-------|
| Release tag | `2.3.10` |
| Full version string | `2.3.10-1-ga7b0e6d` |
| Installation method | Nix (official OpenLane 2 Nix flake) |
| Install location | `~/DEV_TOOLS/openlane2/` |

### Dependencies

OpenLane 2 is installed via Nix. The Nix package manager must be installed and
the daemon profile sourced before running the flow:

```bash
# One-time: install Nix (multi-user)
sh <(curl -L https://nixos.org/nix/install) --daemon

# Each shell session (or add to .bashrc):
source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
```

The run script sources the Nix profile automatically, so no manual setup is
needed if Nix is installed.

### Configuration file

```
project/m3/synth/config.json
```

Key settings:

```json
{
  "DESIGN_NAME":     "gelu_top",
  "CLOCK_PORT":      "clk",
  "CLOCK_PERIOD":    22,
  "PDK":             "sky130A",
  "STD_CELL_LIBRARY":"sky130_fd_sc_hd"
}
```

All six RTL source files are listed explicitly in `VERILOG_FILES`.

### Running the flow

```bash
cd project/m3
bash "helper_script/run_openlane2.sh"
```

The script sources the Nix profile, changes to the project root, and invokes:

```bash
openlane synth/config.json
```

Output is written to `synth/runs/RUN_<timestamp>/`. The committed run is
`synth/runs/RUN_2026-05-24_17-01-03/`.

To run synthesis only (no place-and-route):

```bash
bash "helper_script/run_openlane2.sh" --last-step yosys-synthesis
```

### Result summary

| Metric | Value |
|--------|-------|
| WNS (all 9 corners) | 0.0 ns (timing met) |
| Critical path delay | 10.174 ns |
| Clock period | 22 ns (slack +11.83 ns) |
| Total cell area | 90,470 µm² |
| Cell count | 7,704 |
| Flip-flops | 1,142 |
| Total power (nom TT) | 30.22 mW |

See `synth/timing_report.txt`, `synth/area_report.txt`, `synth/power_report.txt`,
and `synth/critical_path.md` for details.

---

## Design Hierarchy

```
gelu_top                          (rtl/top.sv)
└── gelu_axi_stream_interface     (rtl/interface.sv)
    └── gelu_fp32                 (rtl/gelu_fp32.sv)
        ├── fp32_to_q16           (rtl/fp32_to_q16.sv)
        ├── compute_core          (rtl/compute_core.sv)
        └── q16_to_fp32           (rtl/q16_to_fp32.sv)
```

See `explanation.md` for a detailed walkthrough of `interface.sv`.
