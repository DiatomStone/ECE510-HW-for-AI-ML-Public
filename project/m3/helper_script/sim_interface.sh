#!/bin/bash
# Run cocotb simulation for gelu_axi_stream_interface (AXI-Stream + AXI-Lite wrapper).
# Logs to sim/interface_run.log and copies the VCD waveform.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

. ~/.venv/bin/activate
cd "$SCRIPT_DIR/.."

make opt=interface SIM=icarus 2>&1 | tee sim/interface_run.log
# cp dump.vcd sim/interface_run.vcd
make clean
