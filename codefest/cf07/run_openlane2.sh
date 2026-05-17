#!/bin/bash
# Created with Cursor - Manager (GPT-5.5)
# Created: 2026-05-16
# Modified: 2026-05-16
#
# Run OpenLane2 for the cf07 synth_top design.
# Default mode runs through Yosys synthesis only.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENLANE2_ROOT="${OPENLANE2_ROOT:-$HOME/openlane2}"
PDK_ROOT="${PDK_ROOT:-$HOME/.volare}"
CONFIG="${CONFIG:-$SCRIPT_DIR/config.json}"
MODE="${1:-synth}"

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
        echo "Usage: $0 [synth|full|smoke]"
        echo "  synth: run OpenLane2 through Yosys.Synthesis (default)"
        echo "  full : run full OpenLane2 flow"
        echo "  smoke: run OpenLane2 smoke test"
        exit 1
        ;;
esac
