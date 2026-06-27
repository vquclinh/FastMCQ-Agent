#!/usr/bin/env bash
# Official BTC pipeline runner (Phase 2L.47A). Runs the end-to-end entry point predict.py,
# forwarding any flags (e.g. --submission / --submission-time / --no-api) verbatim.
set -euo pipefail
python predict.py "$@"
