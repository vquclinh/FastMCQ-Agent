#!/usr/bin/env bash
# Local Docker helper: detect input through predict.py and write the standard output contract.
set -euo pipefail

OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR" 2>/dev/null || true

echo "============================================================"
echo "[entrypoint] FASTMCQ local model run"
echo "[entrypoint] start : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] args  : ${*:-<none>}"
echo "============================================================"

python predict.py "$@"

echo "============================================================"
echo "[entrypoint] end   : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
