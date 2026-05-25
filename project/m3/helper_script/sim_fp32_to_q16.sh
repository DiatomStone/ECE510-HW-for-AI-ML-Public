#!/bin/bash
# Created with Cursor - Manager (Claude Opus 4.6)
# Created: 2026-05-03
# Modified: 2026-05-03

set -e
. ~/.venv/bin/activate
cd ..
make opt=convin SIM=icarus 2>&1 | tee sim/fp32_to_p16.log
cp dump.vcd sim/fp32_to_p16.vcd
make clean

