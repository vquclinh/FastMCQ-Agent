#!/usr/bin/env bash
# Smoke-test the local LLM solver on the first 10 samples.
#
# Usage: bash scripts/run_llm_smoke.sh /path/to/local/model [INPUT]
#
# Runs hf_option_score (the preferred solver) on a tiny slice so you can confirm
# the model loads and produces a valid submission before committing to a full run.
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_PATH="${1:-}"
INPUT="${2:-public-test_1780368312.json}"
OUTPUT="outputs/pred_llm_smoke.csv"
LOG="outputs/run_debug_smoke.jsonl"

if [[ -z "$MODEL_PATH" ]]; then
  echo "ERROR: provide a local model path." >&2
  echo "Usage: bash scripts/run_llm_smoke.sh /path/to/local/model [INPUT]" >&2
  exit 1
fi

PY=$(command -v python || command -v python3)

echo ">> Smoke test: hf_option_score on first 10 samples"
"$PY" run.py \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --solver hf_option_score \
  --model-path "$MODEL_PATH" \
  --limit 10 \
  --save-raw \
  --log-path "$LOG"

echo ">> Validating smoke submission"
"$PY" scripts/validate_submission.py --input "$INPUT" --submission "$OUTPUT"

echo ">> Smoke output: $OUTPUT"
echo ">> Debug log   : $LOG"
echo ">> If this looks good, run the full test: bash scripts/run_llm_full.sh $MODEL_PATH"
