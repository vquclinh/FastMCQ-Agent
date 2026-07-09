#!/usr/bin/env bash
# OFFICIAL full-system runner (Phase 2L.41A). One command, end-to-end:
#   arbitrary test set -> base predictor -> V12B -> V13 -> selector -> output/pred.csv
#
# Usage:
#   bash scripts/run_full_system.sh [<test_json_or_csv>] [extra final_infer flags...]
#   bash scripts/run_full_system.sh <test_file> --fail-on-quality-guard
#
# Input priority  : <test_file> (CLI) > $INPUT_FILE > /data/private_test.csv > /data/public_test.csv
#                   > /data/private_test.json > /data/public_test.json   (resolved by final_infer.py;
#                   the positional <test_file> is OPTIONAL — omit it to use $INPUT_FILE / the /data
#                   defaults).
# Profile         : local_selective_auto (dynamic_full; local Base + V12B + V13 + selector).
# Final local artifact: output/pred.csv (override dir with FASTMCQ_FINAL_DIR). Timestamped run
# logs/records stay under scratch/runs/full_system_<ts>/ but are NOT the official artifact.
set -euo pipefail

# Optional positional input (CLI input wins over everything). If the first arg is a flag or
# omitted, final_infer.py resolves the input via $INPUT_FILE -> /data defaults (BTC priority).
INPUT=""
if [ "${1:-}" ] && [ "${1#-}" = "$1" ]; then INPUT="$1"; shift; fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$ROOT/scratch/runs/full_system_$TS"
mkdir -p "$RUN_DIR/work"
RUN_OUT="$RUN_DIR/pred.csv"
FINAL_DIR="${FASTMCQ_FINAL_DIR:-$ROOT/output}"
FINAL_OUT="$FINAL_DIR/pred.csv"

# Strip --fail-on-quality-guard (handled here, not by final_infer).
FAIL_GUARD=0; PASS_ARGS=()
for a in "$@"; do
  case "$a" in
    --fail-on-quality-guard) FAIL_GUARD=1 ;;
    *) PASS_ARGS+=("$a") ;;
  esac
done
PROFILE="local_selective_auto"

# Pass --input only when a CLI input was given; otherwise final_infer resolves it (BTC priority).
FI_INPUT_ARGS=()
[ -n "$INPUT" ] && FI_INPUT_ARGS=(--input "$INPUT")

START=$(date +%s)
set +e
"$PY" "$ROOT/scripts/final_infer.py" \
  --profile "$PROFILE" \
  "${FI_INPUT_ARGS[@]}" --output "$RUN_OUT" \
  --work-dir "$RUN_DIR/work" --resume "${PASS_ARGS[@]}" 2>&1 | tee "$RUN_DIR/run.log"
rc=${PIPESTATUS[0]}
set -e
END=$(date +%s); EL=$((END-START))

PROMOTED=0
if [ "$rc" -eq 0 ] && [ -f "$RUN_OUT" ]; then
  # Quality report (warns; only blocks promotion if --fail-on-quality-guard).
  QARGS=(--pred "$RUN_OUT" --out "$RUN_DIR/quality_report.json")
  [ "$FAIL_GUARD" -eq 1 ] && QARGS+=(--fail-on-guard)
  set +e
  "$PY" "$ROOT/scripts/output_quality_report.py" "${QARGS[@]}"
  qrc=$?
  set -e
  if [ "$qrc" -eq 0 ]; then
    mkdir -p "$FINAL_DIR"
    cp "$RUN_OUT" "$FINAL_OUT"
    PROMOTED=1
  else
    echo "[run_full_system] quality guard tripped (--fail-on-quality-guard); $FINAL_OUT NOT promoted"
  fi
else
  echo "[run_full_system] run FAILED (rc=$rc); existing $FINAL_OUT left unchanged"
fi

echo "============================================================"
echo "profile : $PROFILE"
echo "run_out : $RUN_OUT"
if [ "$PROMOTED" -eq 1 ]; then
  echo "final   : $FINAL_OUT"
  echo "md5     : $(md5sum "$FINAL_OUT" | awk '{print $1}')"
else
  echo "final   : (not promoted)"
fi
echo "elapsed : ${EL}s ($((EL/60))m$((EL%60))s)"
echo "log     : $RUN_DIR/run.log"
echo "quality : $RUN_DIR/quality_report.json"
echo "status  : $([ "$rc" -eq 0 ] && [ "$PROMOTED" -eq 1 ] && echo PASS || echo FAIL)"
echo "============================================================"
[ "$rc" -eq 0 ] && [ "$PROMOTED" -eq 1 ]
