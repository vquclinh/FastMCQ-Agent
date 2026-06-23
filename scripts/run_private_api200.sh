#!/usr/bin/env bash
# Recommended BTC/private API run (V12B/V13 capped at 200 qids).
# Usage: bash scripts/run_private_api200.sh <input_test_file> [extra final_infer flags...]
# Profile: private_api200 (see configs/run_profiles.json). CLI flags after the input override the profile.
set -euo pipefail

INPUT="${1:?usage: bash scripts/run_private_api200.sh <input_test_file> [extra flags...]}"
shift || true

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$ROOT/scratch/runs/private_api200_$TS"
mkdir -p "$RUN_DIR/work"
OUT="$RUN_DIR/pred.csv"

START=$(date +%s)
set +e
"$PY" "$ROOT/scripts/final_infer.py" \
  --input "$INPUT" --output "$OUT" \
  --profile private_api200 --work-dir "$RUN_DIR/work" "$@" 2>&1 | tee "$RUN_DIR/run.log"
rc=${PIPESTATUS[0]}
set -e
END=$(date +%s); EL=$((END-START))

echo "------------------------------------------------------------"
echo "profile : private_api200"
echo "output  : $OUT"
if [ -f "$OUT" ]; then echo "md5     : $(md5sum "$OUT" | awk '{print $1}')"; fi
echo "elapsed : ${EL}s ($((EL/60))m$((EL%60))s)"
echo "log     : $RUN_DIR/run.log"
echo "status  : $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
echo "------------------------------------------------------------"
exit $rc
