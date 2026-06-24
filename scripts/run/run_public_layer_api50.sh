#!/usr/bin/env bash
# Layer-only API run: the BASE predictor is deterministic/no-API; only the V12B/V13 verifier
# layers may call the model (capped at 50 high-risk qids; budget $1.50). Full dynamic system
# over the input; predictions for every input qid; never public_replay.
# Usage: bash scripts/run_public_layer_api50.sh <input_test_file> [extra final_infer flags...]
set -euo pipefail

INPUT="${1:?usage: bash scripts/run_public_layer_api50.sh <input_test_file> [extra flags...]}"
shift || true

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY="python"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$ROOT/scratch/runs/public_layer_api50_$TS"
mkdir -p "$RUN_DIR/work"
OUT="$RUN_DIR/pred.csv"

START=$(date +%s)
set +e
"$PY" "$ROOT/scripts/final_infer.py" \
  --profile public_layer_api50 \
  --input "$INPUT" --output "$OUT" \
  --work-dir "$RUN_DIR/work" --resume "$@" 2>&1 | tee "$RUN_DIR/run.log"
rc=${PIPESTATUS[0]}
set -e
END=$(date +%s); EL=$((END-START))

echo "------------------------------------------------------------"
echo "profile : public_layer_api50  (base=no-API, V12B/V13=API)"
echo "output  : $OUT"
if [ -f "$OUT" ]; then echo "md5     : $(md5sum "$OUT" | awk '{print $1}')"; fi
echo "elapsed : ${EL}s ($((EL/60))m$((EL%60))s)"
echo "log     : $RUN_DIR/run.log"
echo "status  : $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
echo "------------------------------------------------------------"
exit $rc
