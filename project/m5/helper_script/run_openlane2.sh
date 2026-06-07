#!/bin/bash
# Created with Cursor - Manager (GPT-5.5)
# Created: 2026-05-16
# Modified: 2026-05-16
#
# Run OpenLane2 for the gelu hardening flow.
# Selects a design variant (default v1 = gelu_top, the single-kernel design —
# the smallest, macro-free design, used to validate the flow first). Pass 'v2'
# for the 32-parallel-pipeline gelu_top_v2, or 'dma' for the original
# gelu_dma_top. Default mode runs the full OpenLane2 RTL-to-GDS flow.

set -e

# Source Nix profile so the nix binary is on PATH
# shellcheck source=/dev/null
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENLANE2_ROOT="${OPENLANE2_ROOT:-$HOME/DEV_TOOLS/openlane2}"
PDK_ROOT="${PDK_ROOT:-$HOME/.volare}"
MODE="${1:-full}"
VARIANT="${2:-dma}"

# Select the design config by variant (2nd arg, default v1):
#   v1  -> gelu_top        (single gelu_fp32 kernel, 32-bit AXI-Stream, no macros)
#   v2  -> gelu_top_v2     (32 parallel gelu_fp32 pipelines, 1024-bit AXI-Stream)
#   dma -> gelu_dma_top    (original DMA-wrapped design; needs SRAM macros)
# An explicit CONFIG=... env var overrides the variant selection.
case "$VARIANT" in
    v1)  DEFAULT_CONFIG="$SCRIPT_DIR/../synth/config_v1.json" ;;
    v2)  DEFAULT_CONFIG="$SCRIPT_DIR/../synth/config_v2.json" ;;
    dma) DEFAULT_CONFIG="$SCRIPT_DIR/../synth/config.json" ;;
    *)
        echo "Unknown VARIANT '$VARIANT' (expected: v1 | v2 | dma)"
        exit 1
        ;;
esac
CONFIG="${CONFIG:-$DEFAULT_CONFIG}"

echo "Synthesizing variant '$VARIANT' using config: $CONFIG"
cd "$SCRIPT_DIR"

case "$MODE" in
    synth)
        nix develop "$OPENLANE2_ROOT" --command \
            openlane --pdk-root "$PDK_ROOT" --to Yosys.Synthesis "$CONFIG"
        ;;
    full)
        nix develop "$OPENLANE2_ROOT" --command \
            openlane --pdk-root "$PDK_ROOT" "$CONFIG"
        ;;
    smoke)
        nix develop "$OPENLANE2_ROOT" --command \
            openlane --smoke-test
        ;;
    *)
        echo "Usage: $0 [synth|full|smoke] [v1|v2|dma]"
        echo "  Mode (1st arg):"
        echo "    synth: run OpenLane2 through Yosys.Synthesis"
        echo "    full : run full OpenLane2 flow (default)"
        echo "    smoke: run OpenLane2 smoke test"
        echo "  Variant (2nd arg, default v1):"
        echo "    v1  : gelu_top     (single kernel, 32-bit AXI-Stream, no macros)"
        echo "    v2  : gelu_top_v2  (32 parallel pipelines, 1024-bit AXI-Stream)"
        echo "    dma : gelu_dma_top (original DMA-wrapped design; needs SRAM macros)"
        echo "  Override config entirely with CONFIG=/path/to/config.json"
        exit 1
        ;;
esac

read

