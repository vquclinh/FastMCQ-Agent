#!/usr/bin/env bash
# Docker entrypoint for the competition: run the generalized production pipeline.
# Detects the input under /data (private before public, csv before json, then any
# .csv/.json), ensures /output exists, and runs the stable preset. No API key is
# baked into the image — OPENROUTER_API_KEY is provided by the evaluator's env.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR"

# Single source of truth for detection (shared with tests).
if ! INPUT="$(python scripts/run_production_pipeline.py --detect-only --data-dir "$DATA_DIR")"; then
  echo "ERROR: no input file found in $DATA_DIR (expected a .csv or .json)." >&2
  exit 1
fi

OUTPUT="$OUT_DIR/pred.csv"
LOG="$OUT_DIR/run_production.jsonl"
PRESET="competition_qwen35_9b"

echo "============================================================"
echo "[entrypoint] FASTMCQ production run"
echo "[entrypoint] detected input : $INPUT"
echo "[entrypoint] output path    : $OUTPUT"
echo "[entrypoint] log path       : $LOG"
echo "[entrypoint] preset         : $PRESET"
echo "[entrypoint] start          : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
START_TS=$(date +%s)

# Run (do not 'exec' so we can print an end timestamp after completion).
set +e
python scripts/run_production_pipeline.py \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --preset "$PRESET" \
  --log-path "$LOG" \
  --skip-existing --checkpoint-every 50
RC=$?
set -e

END_TS=$(date +%s)
echo "============================================================"
echo "[entrypoint] end            : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] wall_seconds   : $((END_TS - START_TS))"
echo "[entrypoint] exit_code       : $RC"
echo "[entrypoint] output path    : $OUTPUT"
echo "[entrypoint] log path       : $LOG"
echo "============================================================"
exit $RC
