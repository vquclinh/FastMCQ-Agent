#!/usr/bin/env bash
# Run the full public test with the local LLM option-scoring solver.
#
# Usage: bash scripts/run_llm_full.sh /path/to/local/model [SCORE_MODE] [INPUT]
#   SCORE_MODE: label_only | label_plus_choice | choice_only  (default: label_plus_choice)
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_PATH="${1:-}"
SCORE_MODE="${2:-label_plus_choice}"
INPUT="${3:-public-test_1780368312.json}"
OUTPUT="output/pred_llm.csv"
LOG="output/run_debug.jsonl"

if [[ -z "$MODEL_PATH" ]]; then
  echo "ERROR: provide a local model path." >&2
  echo "Usage: bash scripts/run_llm_full.sh /path/to/local/model [SCORE_MODE] [INPUT]" >&2
  exit 1
fi

PY=$(command -v python || command -v python3)

echo ">> REMINDER: confirm the model is allowed first:"
echo "     $PY scripts/check_model_compliance.py --model-path \"$MODEL_PATH\""
echo

CMD=("$PY" run.py
  --input "$INPUT"
  --output "$OUTPUT"
  --solver hf_option_score
  --model-path "$MODEL_PATH"
  --score-mode "$SCORE_MODE"
  --save-raw
  --log-path "$LOG")

echo ">> Full run command:"
echo "   ${CMD[*]}"
echo
"${CMD[@]}"

echo ">> Validating full submission"
"$PY" scripts/validate_submission.py --input "$INPUT" --submission "$OUTPUT"

echo ">> Runtime benchmark"
"$PY" scripts/benchmark_runtime.py --log-path "$LOG" || true

echo
echo "=============================================================="
echo " Full submission written to: $OUTPUT  (score_mode=$SCORE_MODE)"
echo " NEXT STEPS:"
echo "   1. Upload $OUTPUT to the leaderboard."
echo "   2. Record the score in experiments/leaderboard_log.csv."
echo "=============================================================="
