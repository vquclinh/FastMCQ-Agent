#!/usr/bin/env python3
"""Print the exact human runbook for building v11 submission variants (Phase 2L.29A).

Pure text printer — executes NOTHING (no API, no inference, no file writes). It emits the
ordered, copy-pasteable commands a human runs to rerun the calc-first pilot, perform full
adaptive runs, build conservative/balanced/aggressive variants, merge an ensemble, and
audit all variants. v10 stays the locked baseline until a result is accepted.
"""

from __future__ import annotations

import argparse

_INPUT = "public-test_1780368312.json"
_V10 = "output/pred_v10_full_production_user_run.csv"
_V10LOG = "scratch/v10_full_production/run_v10_full_production_user_run.jsonl"
_PLAN = "scratch/accuracy_engine_2l27/overall_accuracy_plan.csv"


def _runbook():
    return f"""\
================================================================
SUBMISSION RUNBOOK (human-run; nothing here executes)
v10 baseline: {_V10} (public 77.75) — never overwrite.
================================================================

# 1) Rerun the 2L.28B calculation-first pilot (small budget) and re-check the gate
.venv/bin/python scripts/run_adaptive_pilot.py \\
  --input {_INPUT} --base-pred {_V10} --v10-log {_V10LOG} \\
  --pilot-qids scratch/adaptive_pilot_2l28/pilot_qids.csv \\
  --output-dir scratch/adaptive_pilot_2l28b \\
  --mode cheap --model qwen/qwen3.5-9b-20260310 --budget-usd 0.30 --execute --resume
.venv/bin/python scripts/build_pilot_decision_report.py \\
  --input {_INPUT} --base-pred {_V10} \\
  --pilot-qids scratch/adaptive_pilot_2l28/pilot_qids.csv \\
  --pilot-candidates scratch/adaptive_pilot_2l28b/pilot_api_candidates.jsonl \\
  --output-dir scratch/adaptive_pilot_2l28b

# 2) Full v11a CHEAP adaptive run (only if the pilot gate reads proceed_full_run)
.venv/bin/python scripts/run_adaptive_selective_api.py \\
  --input {_INPUT} --base-pred {_V10} --v10-log {_V10LOG} --plan {_PLAN} \\
  --output-dir scratch/full_adaptive_v11a --mode cheap \\
  --model qwen/qwen3.5-9b-20260310 --budget-usd 3.00 --max-qids 463 --execute --resume

# 3) Build v11a CONSERVATIVE
.venv/bin/python scripts/build_submission_variant.py \\
  --input {_INPUT} --base-pred {_V10} \\
  --api-candidates scratch/full_adaptive_v11a/adaptive_api_candidates.jsonl \\
  --output output/pred_v11a_conservative.csv \\
  --review-dir scratch/v11a_conservative_review --plan {_PLAN} \\
  --policy conservative --max-total-overrides 40 --max-model-only-overrides 0 \\
  --min-coverage 0.90 --i-understand-this-writes-outputs

# 4) Full v11b BALANCED adaptive run
.venv/bin/python scripts/run_adaptive_selective_api.py \\
  --input {_INPUT} --base-pred {_V10} --v10-log {_V10LOG} --plan {_PLAN} \\
  --output-dir scratch/full_adaptive_v11b --mode balanced \\
  --model qwen/qwen3.5-9b-20260310 --budget-usd 5.00 --max-qids 463 --execute --resume

# 5) Build v11b BALANCED
.venv/bin/python scripts/build_submission_variant.py \\
  --input {_INPUT} --base-pred {_V10} \\
  --api-candidates scratch/full_adaptive_v11b/adaptive_api_candidates.jsonl \\
  --output output/pred_v11b_balanced.csv \\
  --review-dir scratch/v11b_balanced_review --plan {_PLAN} \\
  --policy balanced --max-total-overrides 60 --max-model-only-overrides 0 \\
  --min-coverage 0.90 --i-understand-this-writes-outputs

# 6) Build v11c AGGRESSIVE from the SAME full balanced candidates
.venv/bin/python scripts/build_submission_variant.py \\
  --input {_INPUT} --base-pred {_V10} \\
  --api-candidates scratch/full_adaptive_v11b/adaptive_api_candidates.jsonl \\
  --output output/pred_v11c_aggressive.csv \\
  --review-dir scratch/v11c_aggressive_review --plan {_PLAN} \\
  --policy aggressive --max-total-overrides 80 --max-model-only-overrides 0 \\
  --min-coverage 0.90 --i-understand-this-writes-outputs

# 7) Build ENSEMBLE (at_least_two)
.venv/bin/python scripts/build_submission_ensemble.py \\
  --input {_INPUT} --base-pred {_V10} \\
  --candidates output/pred_v11a_conservative.csv output/pred_v11b_balanced.csv \\
               output/pred_v11c_aggressive.csv \\
  --output output/pred_v11_ensemble.csv \\
  --review-dir scratch/v11_ensemble_review --strategy at_least_two \\
  --max-total-overrides 60 --i-understand-this-writes-outputs

# 8) Audit ALL variants vs v10
.venv/bin/python scripts/audit_submission_variants.py \\
  --input {_INPUT} --base-pred {_V10} \\
  --candidates output/pred_v11a_conservative.csv output/pred_v11b_balanced.csv \\
               output/pred_v11c_aggressive.csv output/pred_v11_ensemble.csv \\
  --plan {_PLAN} --output-dir scratch/submission_variant_audit
================================================================
Pick ONE candidate to submit after reviewing diffs. Keep v10 as fallback.
================================================================"""


def main(argv=None) -> int:
    argparse.ArgumentParser(description="Print the submission runbook (executes nothing)").parse_args(argv)
    print(_runbook())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
