#!/bin/bash
# =========================================================================
# sim_master.sh — unified cocotb/Icarus simulation runner.
#
# Replaces the per-test sim_*.sh scripts. They all did the same thing:
# activate ~/.venv, cd to the m3 root, run `make opt=<X> SIM=icarus WAVES=1`,
# tee to a log, and copy a waveform. This collapses them into one array.
#
# To add a new testbench: add its make `opt=` value to the TARGETS array below.
# (Pick the default run with DEFAULT_TARGET.)
#
# Usage:
#   ./sim_master.sh                 run the default target (DEFAULT_TARGET)
#   ./sim_master.sh <target> [args] run one testbench (extra make args passed through)
#   ./sim_master.sh all   [args]    run every target, then print a pass/fail summary
#   ./sim_master.sh list            list available targets
# =========================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."

# shellcheck source=/dev/null
. ~/.venv/bin/activate

# -------------------------------------------------------------------------
# All simulation targets (= the Makefile `opt=` value for each testbench).
# Add a new testbench by appending its name here.
# -------------------------------------------------------------------------
TARGETS=(
    compute_core      # default Makefile target (fp32 GELU PWL core)
    convin            # fp32_to_q16
    convout           # q16_to_fp32
    gelu              # gelu_fp32 end-to-end datapath
    interface         # gelu_axi_stream_interface
    interface_v2      # gelu_axi_stream_interface_v2 (32-lane, 1024-bit)
    mac               # mac PE (weight-stationary MAC cell)
    sarray            # systolic_array (8x8 weight-stationary)
    mm2s              # mm2s_buffer
    s2mm              # s2mm_buffer
    openram_wrap      # openram_1k_wrap behavioral SRAM
    top               # gelu_top (needs vectors)
    dma_top           # gelu_dma_top (needs vectors)
    inloop            # full-model in-loop, single kernel
    inloop_v2         # full-model in-loop, 32 parallel lanes
    inloop_dma        # full-model in-loop, through DMA buffers
    inloop_dma_v2     # full-model in-loop, 32 lanes through wide DMA buffers
)

# The target run when no argument is given.
DEFAULT_TARGET=sarray

# Targets that must generate test vectors first (tb/gen_vectors.py).
VEC_TARGETS=" top dma_top "

# Terminal output truncation. The verbose in-loop tests print a lot; set
# TAIL_LINES to show only the last N lines ON SCREEN (the log always keeps the
# full output, unlike the old `tail -36 | tee` which truncated the log too).
#   e.g.  TAIL_LINES=36 ./sim_master.sh inloop_v2
TAIL_LINES=${TAIL_LINES:-0}

# -------------------------------------------------------------------------
in_targets() { local n=$1 t; for t in "${TARGETS[@]}"; do [ "$t" = "$n" ] && return 0; done; return 1; }

usage() {
    cat <<EOF
sim_master.sh — unified simulation runner (replaces the sim_*.sh scripts)

Usage:
  $0                 run the default target ($DEFAULT_TARGET)
  $0 <target> [args] run one testbench (extra args passed to make)
  $0 all   [args]    run all targets, then print a pass/fail summary
  $0 list            list available targets

Targets: ${TARGETS[*]}
EOF
}

# run_one <name> [extra make args...]
run_one() {
    local name=$1; shift
    if ! in_targets "$name"; then
        echo "Unknown target: '$name' (try '$0 list')" >&2
        return 2
    fi

    local log="sim/${name}_run.log"
    cd "$ROOT"
    mkdir -p sim

    echo "================================================================"
    echo "=== [$name]  ->  make opt=$name SIM=icarus WAVES=1"
    echo "================================================================"

    # Clean cached sim_build: cocotb's WAVES dump module + compiled sim.vvp are
    # keyed to the previous TOPLEVEL and are not regenerated when it changes.
    make opt="$name" clean >/dev/null 2>&1 || rm -rf sim_build

    if [[ "$VEC_TARGETS" == *" $name "* ]]; then
        echo "--- generating test vectors (tb/gen_vectors.py) ---"
        python3.13 tb/gen_vectors.py
    fi

    # Full output always goes to the log; terminal is truncated only if asked.
    if [ "$TAIL_LINES" -gt 0 ] 2>/dev/null; then
        make opt="$name" SIM=icarus WAVES=1 "$@" 2>&1 | tee "$log" | tail -n "$TAIL_LINES"
    else
        make opt="$name" SIM=icarus WAVES=1 "$@" 2>&1 | tee "$log"
    fi
    local rc=${PIPESTATUS[0]}

    # Copy whatever waveform was produced (cocotb names it after TOPLEVEL;
    # legacy unit tbs dump to ./dump.vcd) — newest match wins.
    local wv
    wv=$(ls -t sim_build/*.vcd sim_build/*.fst dump.vcd 2>/dev/null | head -1 || true)
    if [ -n "$wv" ]; then
        cp "$wv" "sim/${name}_run.${wv##*.}"
        echo "--- waveform: sim/${name}_run.${wv##*.} ---"
    fi

    if [ "$rc" -eq 0 ]; then echo "--- [$name] OK ---"
    else echo "--- [$name] FAILED (exit $rc) ---" >&2; fi
    return "$rc"
}

# -------------------------------------------------------------------------
# Dispatch
# -------------------------------------------------------------------------
cmd=${1:-$DEFAULT_TARGET}
case "$cmd" in
    -h|--help|help)
        usage
        ;;
    list)
        for k in "${TARGETS[@]}"; do
            if [ "$k" = "$DEFAULT_TARGET" ]; then printf "  %-14s (default)\n" "$k"
            else printf "  %s\n" "$k"; fi
        done
        ;;
    all)
        shift
        pass=(); fail=()
        for k in "${TARGETS[@]}"; do
            if run_one "$k" "$@"; then pass+=("$k"); else fail+=("$k"); fi
        done
        echo
        echo "======================= SUMMARY ========================"
        echo "  PASS (${#pass[@]}): ${pass[*]:-none}"
        echo "  FAIL (${#fail[@]}): ${fail[*]:-none}"
        echo "========================================================"
        [ "${#fail[@]}" -eq 0 ]
        ;;
    *)
        shift || true
        run_one "$cmd" "$@"
        ;;
esac
read
