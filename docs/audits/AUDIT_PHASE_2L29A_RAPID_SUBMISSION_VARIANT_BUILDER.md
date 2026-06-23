# Audit — Phase 2L.29A: Rapid Submission Variant Builder + Ensemble Merge

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Built deadline-ready tooling to generate multiple real full-run submission candidates
under explicit override policies, merge them into ensembles, and audit all variants
against v10 — with no manual patching, no qid hardcoding, and no answer leakage. **This
coding phase calls no API, runs no inference, and writes NO real `outputs/` file** (the
builders write `outputs/` only when a human runs them with explicit acknowledgement; tests
write only to temp dirs). v10 (77.75) remains the locked baseline.

## No-output rule confirmation

`outputs/` still contains only `pred.csv`, `pred_v10_full_production_user_run.csv`,
`pred_v8_clean_generalized_from_v7.csv`. No submission candidate was created this phase.

## Files changed

**New (scripts):** `build_submission_variant.py`, `build_submission_ensemble.py`,
`audit_submission_variants.py`, `print_submission_runbook.py`.
**New (tests):** `tests/test_submission_variants_2l29a.py` (+9).

## Part A — Variant builder (`build_submission_variant.py`)

Builds one full-run candidate from adaptive API candidates under an override **policy**,
via the existing consistency-guarded ranker. Fail-closed guards: explicit
`--i-understand-this-writes-outputs`; refuses pilot inputs (`pilot` in filename); requires
the output under `outputs/`; refuses protected/locked names (`pred.csv`,
`pred_v10_full_production_user_run.csv`, `pred_v8_*`, + `adaptive_proposal_common.
guard_output`); requires coverage ≥ `--min-coverage`; caps total + model-only overrides;
validates labels and row count == dataset size.

Policy gate (applied after the ranker; **no policy ever allows a model-only/evidence-less
override**):
- `conservative` — deterministic/tool override **and** low risk only.
- `balanced` — deterministic **or** evidence-backed low/medium risk.
- `aggressive` — deterministic **or** evidence-backed low/medium risk (placeholder &
  numeric-mismatch candidates are already filtered by the consistency guard upstream).

Writes the candidate to `outputs/`, plus `variant_diff.csv` and `variant_summary.md` under
the scratch review dir. Summary includes coverage, override count, override-by-source,
override-by-route (when `--plan` given), risk breakdown, consistency rejections,
placeholder rejections, numeric mismatches, model-only (blocked) count, and the top changed
qids with evidence summaries. Consensus overrides correctly draw evidence from the
agreeing candidates (not a single `best_by_source` lookup).

## Part B — Ensemble merger (`build_submission_ensemble.py`)

Merges N validated candidate CSVs against v10 by strategy. Validates each candidate's qid
set == dataset (row-count) and label set before voting; refuses protected output names and
non-`outputs/` paths; requires the ack flag. Per qid (no ground truth):
- `majority` — a single alternative held by > half the candidates.
- `at_least_two` — a single alternative held by ≥ 2 candidates.
- `non_v10_consensus` — every non-v10 change agrees on one label.
Ties among alternatives keep v10. Writes the ensemble to `outputs/` + `ensemble_diff.csv`
and `ensemble_summary.md` under scratch; caps total overrides; final label/row validation.

## Part C — Variant audit (`audit_submission_variants.py`)

Read-only comparison of any candidate CSVs vs v10: per-candidate changed count + label
distribution + route distribution of changes (when `--plan` given); pairwise overlap
(both-changed, agree-on-change) and total disagreement matrix; qids changed by ≥2
candidates; qids where candidates disagree with each other. No ground truth; scratch-only
output (`variant_comparison.csv` + `.md`); refuses non-`scratch/` output dir.

## Part D — Runbook printer (`print_submission_runbook.py`)

Pure text printer (executes nothing): emits the ordered human commands for pilot rerun →
full v11a cheap run → v11a conservative → full v11b balanced run → v11b balanced → v11c
aggressive (same balanced candidates) → ensemble `at_least_two` → audit all variants.

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **525 passed** (was 516; +9 in `tests/test_submission_variants_2l29a.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: variant builder refuses pilot input / non-outputs path / protected name /
  missing ack; conservative ≤ aggressive overrides on fake consensus data (conservative
  blocks the medium-risk consensus override, aggressive keeps it); ensemble `at_least_two`
  overrides on 2-agreement and keeps v10 on lone change; ensemble validates row-count +
  labels; audit changed-count comparison + refuses `outputs/`; no 4-digit qid hardcoded in
  any new script; runbook executes nothing.

## Confirmations

- **No OpenRouter/API call**; no inference run.
- **No real `outputs/` writes**; `pred.csv` and v10 untouched. Builders write `outputs/`
  only under explicit human acknowledgement; tests used temp dirs only.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth;
  no hidden/public ground truth anywhere.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact human commands (after full adaptive runs)

```bash
# v11a conservative (from a full cheap adaptive run)
.venv/bin/python scripts/build_submission_variant.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --api-candidates scratch/full_adaptive_v11a/adaptive_api_candidates.jsonl \
  --output outputs/pred_v11a_conservative.csv \
  --review-dir scratch/v11a_conservative_review \
  --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
  --policy conservative --max-total-overrides 40 --max-model-only-overrides 0 \
  --min-coverage 0.90 --i-understand-this-writes-outputs

# v11b balanced (from a full balanced adaptive run)
.venv/bin/python scripts/build_submission_variant.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --api-candidates scratch/full_adaptive_v11b/adaptive_api_candidates.jsonl \
  --output outputs/pred_v11b_balanced.csv \
  --review-dir scratch/v11b_balanced_review \
  --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
  --policy balanced --max-total-overrides 60 --max-model-only-overrides 0 \
  --min-coverage 0.90 --i-understand-this-writes-outputs

# v11c aggressive (same balanced candidates)
.venv/bin/python scripts/build_submission_variant.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --api-candidates scratch/full_adaptive_v11b/adaptive_api_candidates.jsonl \
  --output outputs/pred_v11c_aggressive.csv \
  --review-dir scratch/v11c_aggressive_review \
  --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
  --policy aggressive --max-total-overrides 80 --max-model-only-overrides 0 \
  --min-coverage 0.90 --i-understand-this-writes-outputs

# ensemble (at_least_two)
.venv/bin/python scripts/build_submission_ensemble.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --candidates outputs/pred_v11a_conservative.csv outputs/pred_v11b_balanced.csv \
               outputs/pred_v11c_aggressive.csv \
  --output outputs/pred_v11_ensemble.csv \
  --review-dir scratch/v11_ensemble_review --strategy at_least_two \
  --max-total-overrides 60 --i-understand-this-writes-outputs

# audit all variants
.venv/bin/python scripts/audit_submission_variants.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --candidates outputs/pred_v11a_conservative.csv outputs/pred_v11b_balanced.csv \
               outputs/pred_v11c_aggressive.csv outputs/pred_v11_ensemble.csv \
  --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
  --output-dir scratch/submission_variant_audit
```

`scripts/print_submission_runbook.py` prints the full ordered sequence (incl. the pilot
rerun and full adaptive runs) on demand.

## Recommended next phase

Human runs the runbook: rerun the calc-first pilot, confirm `proceed_full_run`, do the
full adaptive runs, build the three policy variants + ensemble, audit diffs vs v10, and
pick one to submit while keeping v10 as the fallback. Do not commit until a result is
accepted.
