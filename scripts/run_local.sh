#!/usr/bin/env bash
# Convenience wrapper to run the pipeline end-to-end on the local public test
# and validate the resulting submission.
#
# Usage: bash scripts/run_local.sh [INPUT] [OUTPUT]
set -euo pipefail

cd "$(dirname "$0")/.."

INPUT="${1:-public-test_1780368312.json}"
OUTPUT="${2:-outputs/pred.csv}"

echo ">> Inspecting dataset"
python run.py --input "$INPUT" --output "$OUTPUT" || python3 run.py --input "$INPUT" --output "$OUTPUT"

echo ">> Validating submission"
python scripts/validate_submission.py --input "$INPUT" --submission "$OUTPUT" \
  || python3 scripts/validate_submission.py --input "$INPUT" --submission "$OUTPUT"
