#!/bin/bash
# Run the gelu_top co-simulation testbench (pure Icarus Verilog, no cocotb).
# Step 1: generate test vectors from the M1 small-config transformer (python3.13).
# Step 2: compile all RTL + tb_top.sv with iverilog.
# Step 3: run vvp and tee output to sim/cosim_run.log.
# VCD is written to sim/cosim_run.vcd.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Activate venv
. ~/.venv/bin/activate

echo "=== Generating test vectors ==="
python3.13 tb/gen_vectors.py

echo "=== Running Co-Simulation ==="
# Add WAVES=1 to automatically inject VCD dumping
make opt=top SIM=icarus WAVES=1 2>&1 | tee sim/cosim_run.log

# Cocotb creates the VCD in sim_build using the TOPLEVEL name
cp sim_build/gelu_top.vcd sim/cosim_waveform.vcd

read

