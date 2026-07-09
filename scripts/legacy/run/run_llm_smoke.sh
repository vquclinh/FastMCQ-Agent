#!/usr/bin/env bash
# Smoke-test the local LLM solver on the first 10 samples.
#
# Usage: bash scripts/run_llm_smoke.sh /path/to/local/model [SCORE_MODE] [INPUT]
#   SCORE_MODE: label_only | label_plus_choice | choice_only  (default: label_plus_choice)
#
# Runs hf_option_score (the preferred solver) on a tiny slice so you can confirm
# the model loads and produces a valid submission before committing to a full run.
set -euo pipefail

cd "$(dirname "$0")/../../.."

MODEL_PATH="${1:-}"
SCORE_MODE="${2:-label_plus_choice}"
INPUT="${3:-public-test_1780368312.json}"
OUTPUT="output/pred_llm_smoke.csv"
LOG="output/run_debug_smoke.jsonl"

if [[ -z "$MODEL_PATH" ]]; then
  echo "ERROR: provide a local model path." >&2
  echo "Usage: bash scripts/run_llm_smoke.sh /path/to/local/model [SCORE_MODE] [INPUT]" >&2
  exit 1
fi

PY=$(command -v python || command -v python3)

echo ">> REMINDER: confirm the model is allowed first:"
echo "     $PY scripts/legacy/checks/check_model_compliance.py --model-path \"$MODEL_PATH\""
echo

CMD=("$PY" run.py
  --input "$INPUT"
  --output "$OUTPUT"
  --solver hf_option_score
  --model-path "$MODEL_PATH"
  --score-mode "$SCORE_MODE"
  --limit 10
  --save-raw
  --log-path "$LOG")

echo ">> Smoke test command:"
echo "   ${CMD[*]}"
echo
"${CMD[@]}"

echo ">> Validating smoke submission"
"$PY" scripts/validate_submission.py --input "$INPUT" --submission "$OUTPUT"

echo ">> Smoke output: $OUTPUT"
echo ">> Debug log   : $LOG"
echo ">> If this looks good, run the full test: bash scripts/run_llm_full.sh $MODEL_PATH $SCORE_MODE"
