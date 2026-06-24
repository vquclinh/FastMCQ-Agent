#!/usr/bin/env bash
# Docker entrypoint (Phase 2L.42A): runs the real DYNAMIC FASTMCQ system over the mounted input
# and writes the final prediction to /output/pred.csv.
#
# BTC I/O contract:
#   * reads /data/private_test.csv if present, else /data/public_test.csv, else other /data files
#     (CSV or JSON; auto-detected by final_infer.py). Override with INPUT_FILE=/data/<file>.
#   * writes /output/pred.csv (columns qid,answer). Override with OUTPUT_FILE=/output/<file>.
#
# No API key required by default (dynamic base + V12B/V13 deterministic parts; model-dependent
# layers are skipped_no_api). Add --execute-api --model ... --budget-usd ... for the full layers.
# Any extra args are forwarded to final_infer.py. Override entrypoint with `--entrypoint bash`.
set -euo pipefail

OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR" 2>/dev/null || true

# Optional explicit BTC overrides via env (final_infer also auto-detects when these are unset).
INPUT_FILE="${INPUT_FILE:-}"
OUTPUT_FILE="${OUTPUT_FILE:-$OUT_DIR/pred.csv}"

echo "============================================================"
echo "[entrypoint] FASTMCQ FINAL — dynamic_full (real system, API-free default)"
echo "[entrypoint] start : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] INPUT_FILE=${INPUT_FILE:-<auto-detect /data>} OUTPUT_FILE=$OUTPUT_FILE"
echo "[entrypoint] args  : ${*:-<none>}"
echo "============================================================"

CFG="configs/production/default.json"
if [ "$#" -eq 0 ]; then
  # No-arg BTC default: explicit OUTPUT_FILE; INPUT_FILE if provided, else auto-detect /data.
  if [ -n "$INPUT_FILE" ]; then
    python scripts/final_infer.py --config "$CFG" --input "$INPUT_FILE" --output "$OUTPUT_FILE"
  else
    python scripts/final_infer.py --config "$CFG" --output "$OUTPUT_FILE"
  fi
else
  # Forward user args verbatim (e.g. --mode public_replay, --execute-api ...).
  python scripts/final_infer.py "$@"
fi

echo "============================================================"
echo "[entrypoint] end   : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
