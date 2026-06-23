#!/usr/bin/env bash
# Docker entrypoint (Phase 2L.32B): OFFLINE, reproducible frozen_csv export of the current
# best independent-v11 submission. NO API key required, NO v10, NO inference.
#
# No-arg default: just runs `final_infer.py`, which auto-detects the input from /data
# (doc_public_test.csv / private_test.csv / public-test*.json) and writes /output/pred.csv,
# printing its own timing block + validating the result.
#
# If the user passes any arguments to the container, they are forwarded to final_infer.py
# (e.g. `docker run ... fastmcq-final --mode v10`). To run an arbitrary command instead,
# override the entrypoint (`docker run --entrypoint bash ...`).
set -euo pipefail

OUT_DIR="${OUT_DIR:-/output}"
mkdir -p "$OUT_DIR" 2>/dev/null || true

echo "============================================================"
echo "[entrypoint] FASTMCQ FINAL — frozen_csv (independent v11, offline)"
echo "[entrypoint] start : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "[entrypoint] args  : ${*:-<none> (no-arg default: auto /data -> /output/pred.csv)}"
echo "============================================================"

# No-arg: final_infer.py resolves input from /data and output to /output/pred.csv itself,
# prints the timing block, and validates. With args, forward them verbatim.
if [ "$#" -eq 0 ]; then
  python scripts/final_infer.py --config configs/production_v11_independent.json
else
  python scripts/final_infer.py "$@"
fi

echo "============================================================"
echo "[entrypoint] end   : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "============================================================"
