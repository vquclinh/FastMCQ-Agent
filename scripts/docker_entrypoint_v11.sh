#!/usr/bin/env bash
# Docker entrypoint (Phase 2L.44D): runs the real DYNAMIC FASTMCQ system (dynamic_full:
# base predictor -> V12B -> V13 -> selector) over the mounted input and writes the final
# prediction following the EXACT BTC input/output priority contract.
#
# INPUT priority  : --input (CLI) > $INPUT_FILE > /data/private_test.csv > /data/public_test.csv
#                   > /data/private_test.json > /data/public_test.json
# OUTPUT priority : --output (CLI) > $OUTPUT_FILE > /output/pred.csv (Docker) > output/pred.csv (local)
#   (final_infer.py applies this priority itself; the entrypoint only chooses the profile.)
#
# API key         : OPENROUTER_API_KEY present -> API production profile; absent -> offline
#                   no-api fallback (still writes pred.csv). NO key is baked into the image;
#                   the evaluator supplies OPENROUTER_API_KEY via the container env when desired.
#
# Any extra args are forwarded verbatim to final_infer.py (override entrypoint via `--entrypoint bash`).
set -euo pipefail

OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR" 2>/dev/null || true

# Choose the production profile by API-key presence (no secret is ever baked into the image).
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  PROFILE="production_full_system"        # dynamic_full + V12B + V13, API on
  API_STATE="on (OPENROUTER_API_KEY present)"
else
  PROFILE="production_full_system_noapi"  # offline fallback; still writes pred.csv
  API_STATE="off (no OPENROUTER_API_KEY -> no-api fallback)"
fi

echo "============================================================"
echo "[entrypoint] FASTMCQ FINAL — dynamic_full (real system)"
echo "[entrypoint] start  : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] profile: $PROFILE"
echo "[entrypoint] api    : $API_STATE"
echo "[entrypoint] input  : ${INPUT_FILE:-<auto: --input > INPUT_FILE > /data/private_test.csv > /data/public_test.csv > .json>}"
echo "[entrypoint] output : ${OUTPUT_FILE:-<auto: --output > OUTPUT_FILE > /output/pred.csv>}"
echo "[entrypoint] args   : ${*:-<none>}"
echo "============================================================"

# final_infer.py enforces the exact I/O priority (reads $INPUT_FILE/$OUTPUT_FILE and the
# /data defaults). Any CLI flags after --profile override both the profile and env/defaults.
python scripts/final_infer.py --profile "$PROFILE" "$@"

echo "============================================================"
echo "[entrypoint] end    : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
