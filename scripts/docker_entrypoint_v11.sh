#!/usr/bin/env bash
# Compatibility helper for the optional local selective system.
set -euo pipefail

OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR" 2>/dev/null || true

echo "============================================================"
echo "[entrypoint] FASTMCQ local selective run"
echo "[entrypoint] start  : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] profile: local_selective_auto"
echo "[entrypoint] args   : ${*:-<none>}"
echo "============================================================"

python scripts/final_infer.py --profile local_selective_auto "$@"

echo "============================================================"
echo "[entrypoint] end    : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
