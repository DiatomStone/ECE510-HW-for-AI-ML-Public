#!/bin/bash

. ~/.venv/bin/activate
cd ..
make opt=gelu SIM=icarus 2>&1 | tee sim/gelu.log
#cp dump.vcd sim/gelu.vcd
make clean
read


