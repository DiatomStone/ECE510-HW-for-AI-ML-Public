#!/bin/bash
# Created with Cursor - Manager (GPT-5.5)
# Created: 2026-05-10
# Modified: 2026-05-10

set -e

iverilog -g2012 \
    -s crossbar_tb \
    -o crossbar_tb.vvp \
    crossbar_mac.sv \
    crossbar_tb.sv

vvp crossbar_tb.vvp 2>&1 | tee crossbar_run.log

rm -f crossbar_tb.vvp

