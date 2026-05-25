#!/bin/bash

set -e
. ~/.venv/bin/activate
cd ..
make opt=convout SIM=icarus 2>&1 | tee sim/p16_to_fp32.log
cp dump.vcd sim/p16_to_fp32.vcd
make clean

