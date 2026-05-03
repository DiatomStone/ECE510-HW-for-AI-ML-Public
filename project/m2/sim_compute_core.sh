#!/bin/bash
# Created with Cursor - Manager (Claude Opus 4.6)
# Created: 2026-05-03
# Modified: 2026-05-03

set -e

make SIM=icarus 2>&1 | tee sim/compute_core_run.log
cp dump.vcd sim/compute_core_run.vcd
make clean
