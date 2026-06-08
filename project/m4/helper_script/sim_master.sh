#!/bin/bash
# =========================================================================
# sim_master.sh — unified cocotb/Icarus simulation runner.
#
# Replaces the per-test sim_*.sh scripts. They all did the same thing:
# activate ~/.venv, cd to the m4 root, run `make opt=<X> SIM=icarus WAVES=1`,
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
    interface_x32      # gelu_axi_stream_interface (32-lane, 1024-bit)
    interface_x16      # same RTL @ NUM_LANES=16 (16-lane, 512-bit)
    interface_x8       # same RTL @ NUM_LANES=8 (8-lane, 256-bit)
    mac               # mac PE (weight-stationary MAC cell)
    sarray            # systolic_array (8x8 weight-stationary)
    top               # gelu_top in-loop (= inloop_x32 @ default 32 lanes)
    inloop_x32         # full-model in-loop, 32 parallel lanes
    inloop_x16         # full-model in-loop, 16 parallel lanes
    inloop_x8          # full-model in-loop, 8 parallel lanes
    inloop_x1          # full-model in-loop, 1 pipeline, direct stream (no DMA)
    inloop_dma_x32     # full-model in-loop, 32 lanes through DMA buffers
    inloop_dma_x16     # full-model in-loop, 16 lanes through DMA buffers
    inloop_dma_x8      # full-model in-loop, 8 lanes through wide DMA buffers
    inloop_dma_x1      # full-model in-loop, 1 lane through the (parameterized) wide DMA path
)

# The target run when no argument is given.
DEFAULT_TARGET=inloop_x8

# Targets that must generate test vectors first (tb/gen_vectors.py).
# (The in-loop tbs build their own data from the transformer, so none currently.)
VEC_TARGETS=" "

# Terminal output truncation. The verbose in-loop tests print a lot; set
# TAIL_LINES to show only the last N lines ON SCREEN (the log always keeps the
# full output, unlike the old `tail -36 | tee` which truncated the log too).
#   e.g.  TAIL_LINES=36 ./sim_master.sh inloop_x32
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

    # Output naming. The in-loop runs (inloop_* and inloop_dma_*) are the FINAL
    # benchmark sims, so their outputs are named final_run_<variant> (e.g.
    # inloop_x16 -> final_run_x16, inloop_dma_x16 -> final_run_dma_x16). Their
    # raw cocotb/Icarus capture is multi-MB (huge per-beat VIP dumps), so we keep
    # only the last SUMMARY_TAIL lines — the metrics/PASS block. Every other
    # target keeps its full <name>_run.log.
    local out_base summary_tail
    if [[ "$name" == inloop_* ]]; then
        out_base="final_run_${name#inloop_}"
        summary_tail=36
    else
        out_base="${name}_run"
        summary_tail=0
    fi
    local log="sim/${out_base}.log"
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

    # Capture the full run to a temp file (terminal is truncated only if asked),
    # then persist either the summary tail (in-loop final runs) or the whole log.
    local tmp; tmp=$(mktemp)
    if [ "$TAIL_LINES" -gt 0 ] 2>/dev/null; then
        make opt="$name" SIM=icarus WAVES=1 "$@" 2>&1 | tee "$tmp" | tail -n "$TAIL_LINES"
    else
        make opt="$name" SIM=icarus WAVES=1 "$@" 2>&1 | tee "$tmp"
    fi
    local rc=${PIPESTATUS[0]}

    if [ "$summary_tail" -gt 0 ]; then
        tail -n "$summary_tail" "$tmp" > "$log"
    else
        cp "$tmp" "$log"
    fi
    rm -f "$tmp"

    # Copy whatever waveform was produced (cocotb names it after TOPLEVEL;
    # legacy unit tbs dump to ./dump.vcd) — newest match wins.
    local wv
    wv=$(ls -t sim_build/*.vcd sim_build/*.fst dump.vcd 2>/dev/null | head -1 || true)
    if [ -n "$wv" ]; then
        cp "$wv" "sim/${out_base}.${wv##*.}"
        echo "--- waveform: sim/${out_base}.${wv##*.} ---"
    fi

    # Remove the cached sim_build now that the waveform has been copied out, so
    # nothing stale is left behind for the next target (and the tree stays clean).
    # Also drop cocotb's auto-generated results.xml (per-run JUnit artifact; the
    # real pass/fail evidence is the saved sim/ log).
    rm -rf sim_build
    rm -f results.xml

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
