# Audit — Phase 2L.24A: Clean Outputs to Two Candidate Versions

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Cleaned `outputs/` to the current best prediction and the safest upgrade candidate.
Everything else was **moved (not deleted)** into a timestamped `scratch/` archive.
No prediction content was modified (checksums identical); both kept CSVs validate PASS.

## Archive directory

`scratch/outputs_archive_2l24a_cleanup_20260622_130008/`

## Files kept in `outputs/`

```
.gitkeep
pred.csv                                       # v8_clean (best known, public 75.59)
pred_v9_formula_bank_from_v8_clean.csv         # safest upgrade (1 deterministic geometry fix)
```
(No `outputs/README.md` exists, so none was kept.)

## Files moved to archive (15)

`candidate_disagreement_review.csv`, `hidden_generalization_readiness_audit.csv`,
`pred_phase2i0_baseline.csv`, `pred_production_user_run.csv`,
`pred_v6_qwen_rerank_calc_verifier.csv`, `pred_v6b_qwen_rerank_calc_verifier_fast.csv`,
`pred_v7_programmatic_assist_from_v6b.csv`, `pred_v8_clean_generalized_from_v7.csv`,
`run_production_user_run.jsonl`, `run_v6_qwen_rerank_calc_verifier.jsonl`,
`run_v6b_qwen_rerank_calc_verifier_fast.jsonl`, `run_v7_programmatic_assist_from_v6b.jsonl`,
`run_v8_clean_generalized_from_v7.jsonl`, `run_v9_formula_bank_from_v8_clean.jsonl`,
`submission_candidate_recommendation.md`.

(`outputs/` contained only files — no subdirectories to preserve. The production
rerun was archived per plan; its v9-equivalent log remains in the archive too.)

## Validation results (kept CSVs)

| file | md5 (unchanged) | validate_submission.py |
|---|---|---|
| `outputs/pred.csv` | `927f334ee11f50720f718fc797c30cca` | **PASS** |
| `outputs/pred_v9_formula_bank_from_v8_clean.csv` | `0df0deec7cfeb1f6c1a4aae6600056f2` | **PASS** |

Checksums match the pre-cleanup values → **no prediction content changed**.

## Final `outputs/` tree

```
outputs/.gitkeep
outputs/pred.csv
outputs/pred_v9_formula_bank_from_v8_clean.csv
```

## Confirmations

- **No prediction content changed** (md5 identical before/after; files were *moved*,
  the kept ones untouched).
- **No files deleted permanently** — all moved to `scratch/outputs_archive_2l24a_cleanup_20260622_130008/`.
- **No new prediction generated**; `outputs/pred.csv` not overwritten.
- **No OpenRouter/API call**; no full inference run.
- Nothing committed.

## git status (relevant)

```
 M Dockerfile                                   # from 2L.20
?? scripts/…, src/…, tests/…, docs/AUDIT_PHASE_2L19..2L24A_*.md   # uncommitted from 2L.x
```
`outputs/*` and `scratch/*` are gitignored, so the cleanup itself produces no tracked
git changes (only the new audit doc is tracked-new).

## Recommended next step

Two clean candidates remain in `outputs/`:
- **`pred.csv`** — conservative fallback (known 75.59).
- **`pred_v9_formula_bank_from_v8_clean.csv`** — recommended upgrade (1 deterministic
  geometry fix; see 2L.23 recommendation).

To submit the upgrade: promote v9 → `outputs/pred.csv` via the explicit archive-first
finalization (as in 2L.18), validate, and submit — keeping one submission in reserve.
Do not commit until a result is accepted.
