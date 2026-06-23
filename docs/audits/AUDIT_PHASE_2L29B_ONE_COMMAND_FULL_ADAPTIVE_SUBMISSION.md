# Audit — Phase 2L.29B: One-Command Full Adaptive Submission Runner

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Collapsed the fragmented two-step workflow (adaptive candidate generation → policy variant
build) into a single production command, `scripts/run_full_adaptive_submission.py`. One
command now produces one real submission file. **This coding phase calls no API, runs no
inference, and writes NO real `outputs/` file** (only a dry-run estimate was produced). v10
(77.75) remains the locked baseline.

## No-output rule confirmation

`outputs/` still contains only `pred.csv`, `pred_v10_full_production_user_run.csv`,
`pred_v8_clean_generalized_from_v7.csv`. No submission file was created this phase.

## Files changed

**New (scripts):** `run_full_adaptive_submission.py`.
**New (tests):** `tests/test_full_adaptive_submission_2l29b.py` (+10).

## Part A/B — One-command runner design (reuse, no duplication)

`run_full_adaptive_submission.py` is a thin orchestrator. It **reuses verbatim** (via
`importlib`, no copied ranking/solver logic):
- `run_adaptive_selective_api.py` — full adaptive candidate generation (route-aware
  calc-first cheap mode, judge, budget, resume).
- `build_submission_variant.py` — policy-gated candidate build through the
  consistency-guarded ranker.
- `src.adaptive_proposal_common.guard_output`, `src.labels.labels_for`,
  `src.model_policy.assert_allowed_llm_model` — output/label/model guards.

Flow:
- **`--dry-run` (default)** — prints the two-step plan, delegates to the adaptive runner's
  own dry-run estimate, and prints the build policy + caps. No API, no outputs.
- **`--execute`** — (1) runs the full adaptive generation into `--work-dir`
  (`adaptive_api_candidates.jsonl`), (2) builds the real candidate under `--policy` into
  `--output`, writing diffs/summary under `<work-dir>/variant_review`, (3) re-validates the
  final CSV.

Guards (enforced in **both** modes before any work):
- `--dry-run`/`--execute` mutually exclusive.
- `assert_allowed_llm_model(--model)` — rejects any disallowed model up front.
- `--work-dir` must be under `scratch/`; `--output` must be under `outputs/`.
- Refuses protected/locked output names (`pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v8_*`, + `guard_output`).
- `--execute` requires `--i-understand-this-writes-outputs`.
- Final output validation: qid set == dataset, row count == dataset, all labels valid.
- Prints the final submission file location.

## Part D — Dry-run summary (no API)

```
run_full_adaptive_submission.py ... --mode cheap --budget-usd 3.00 --max-qids 463 \
    --policy aggressive --max-total-overrides 80 --max-model-only-overrides 0 \
    --min-coverage 0.60 --dry-run
  step 1/2 adaptive generation -> scratch/full_adaptive_v11_final/adaptive_api_candidates.jsonl
    ADAPTIVE DRY-RUN (cheap): plan rows 463; scheduled 316 [cheap_api];
    upper-bound 948 calls; est $1.90; budget 3.0
  step 2/2 variant build (policy=aggressive) -> outputs/pred_v11_full_adaptive_test.csv
    caps: total<=80, model_only<=0, min_coverage>=0.6
```

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **535 passed** (was 525; +10 in `tests/test_full_adaptive_submission_2l29b.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: dry-run constructs no API client and writes no output; execute requires the
  ack flag; protected output name rejected; disallowed model rejected; output must be under
  `outputs/`; work-dir must be under `scratch/`; dry-run/execute mutually exclusive;
  execute calls **generation then build in that order** (fakes record order) and validates
  the full output; execute rejects an output whose qid set != dataset; no 4-digit qid
  hardcoded.

## Confirmations

- **No OpenRouter/API call** during this coding phase; no inference run.
- **No real `outputs/` writes**; `pred.csv` and v10 untouched. The runner writes `outputs/`
  only under `--execute --i-understand-this-writes-outputs` (human-initiated); tests used
  temp dirs only.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth;
  no hidden/public ground truth.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact human command (one full adaptive submission)

```bash
.venv/bin/python scripts/run_full_adaptive_submission.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --v10-log scratch/v10_full_production/run_v10_full_production_user_run.jsonl \
  --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
  --work-dir scratch/full_adaptive_v11_final \
  --output outputs/pred_v11_full_adaptive_test.csv \
  --mode cheap --model qwen/qwen3.5-9b-20260310 --budget-usd 3.00 --max-qids 463 \
  --policy aggressive --max-total-overrides 80 --max-model-only-overrides 0 \
  --min-coverage 0.90 --resume \
  --execute --i-understand-this-writes-outputs
```

This runs the full adaptive generation, builds the policy variant, and writes the single
submission CSV — review the diff under `scratch/full_adaptive_v11_final/variant_review/`
before submitting. v10 remains the fallback.

## Recommended next step

Human runs the calc-first pilot first (Phase 2L.28B / 2L.29A runbook), confirms
`proceed_full_run`, then runs the one command above. Pick the variant to submit after
reviewing diffs; keep v10 as the fallback. Do not commit until a result is accepted.
