#!/usr/bin/env bash
# Run the full public test with the local LLM option-scoring solver.
#
# Usage: bash scripts/run_llm_full.sh /path/to/local/model [INPUT]
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_PATH="${1:-}"
INPUT="${2:-public-test_1780368312.json}"
OUTPUT="outputs/pred_llm.csv"
LOG="outputs/run_debug.jsonl"

if [[ -z "$MODEL_PATH" ]]; then
  echo "ERROR: provide a local model path." >&2
  echo "Usage: bash scripts/run_llm_full.sh /path/to/local/model [INPUT]" >&2
  exit 1
fi

PY=$(command -v python || command -v python3)

echo ">> Full run: hf_option_score on all samples"
"$PY" run.py \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --solver hf_option_score \
  --model-path "$MODEL_PATH" \
  --log-path "$LOG"

echo ">> Validating full submission"
"$PY" scripts/validate_submission.py --input "$INPUT" --submission "$OUTPUT"

echo ">> Runtime benchmark"
"$PY" scripts/benchmark_runtime.py --log-path "$LOG" || true

echo
echo "=============================================================="
echo " Full submission written to: $OUTPUT"
echo " NEXT STEPS:"
echo "   1. Upload $OUTPUT to the leaderboard."
echo "   2. Record the score in experiments/leaderboard_log.csv."
echo "=============================================================="
