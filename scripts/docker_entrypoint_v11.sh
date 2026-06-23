#!/usr/bin/env bash
# Docker entrypoint (Phase 2L.36B): runs the real DYNAMIC FASTMCQ system over the mounted input.
# No-arg default = dynamic_full (API-free): auto-detects the input from /data
# (private_test.csv|json / doc_public_test.csv / public-test*.json), runs the dynamic base
# predictor + official V12B layer, and writes /output/pred.csv for exactly the input qids,
# printing the resolved mode + timing block + validating the result. No API key required by
# default (add --execute-api --model ... --budget-usd ... for the full V12B layer).
#
# If the user passes arguments, they are forwarded to final_infer.py (e.g. `--mode public_replay`
# to reproduce the public 78.83 artifact, or `--mode v10`). Override with `--entrypoint bash`.
set -euo pipefail

OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR" 2>/dev/null || true

echo "============================================================"
echo "[entrypoint] FASTMCQ FINAL — dynamic_full (real system, API-free default)"
echo "[entrypoint] start : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] args  : ${*:-<none> (no-arg default: auto /data -> /output/pred.csv)}"
echo "============================================================"

# No-arg: final_infer.py resolves input from /data and output to /output/pred.csv itself,
# prints the timing block, and validates. With args, forward them verbatim.
if [ "$#" -eq 0 ]; then
  python scripts/final_infer.py --config configs/production_v13_multilayer_7970.json
else
  python scripts/final_infer.py "$@"
fi

echo "============================================================"
echo "[entrypoint] end   : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
