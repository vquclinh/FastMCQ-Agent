# Audit — Phase 2L.18: Finalize v8_clean + Strict Output Cleanup

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Finalized the submission: `outputs/pred.csv` is now a copy of the generalized,
qid-free **v8_clean**, and `outputs/` contains only one best file per meaningful
version (plus its run log). The old `pred.csv` and all provenance/diff/mini/archive
artifacts were **moved** (not deleted) to `scratch/final_cleanup_2l18/`. No API call,
no qid hardcoding, no source/tests/docs deleted.

## Part A — code already finalized (no modification needed)

- `src/concept_solver.py` and `scripts/apply_clean_generalized_fixes_to_predictions.py`
  exist (added in 2L.17); no changes required this phase.
- **No qid hardcoding:** `grep -rnE "test_0[0-9]{3}|if qid|qid =="` over
  `src/concept_solver.py` and the new scripts → **CLEAN** (no matches). The concept
  rules (`paging_logical_address`, `mc_vs_avc`) key off generic wording + option text
  only; tested on synthetic variants, never a public-test answer table.
- Tests run:
  - `compileall -q src scripts tests` → **OK**
  - `pytest -q` → **317 passed**
  - `validate_submission.py … pred_v8_clean_generalized_from_v7.csv` → **PASS**

## Part B — pred.csv set to v8_clean

```bash
mkdir -p scratch/final_cleanup_2l18
cp outputs/pred.csv scratch/final_cleanup_2l18/pred_before_2l18.csv   # archived old pred.csv
cp outputs/pred_v8_clean_generalized_from_v7.csv outputs/pred.csv
```
- Old `pred.csv` was the original v1 baseline; it differed from v8_clean by **25**
  answers (the full v2-calc → v6/v6b/v7/v8 pipeline evolution). Archived to scratch.
- New `outputs/pred.csv` is **byte-identical** to
  `outputs/pred_v8_clean_generalized_from_v7.csv` (`diff -q` → identical).
- `validate_submission.py … outputs/pred.csv` → **PASS** (463 rows).

> Note: overwriting `pred.csv` was explicitly authorized by this finalization phase
> (with the archive-first step). Earlier phases deliberately protected it; that
> protection is intentionally lifted now that v8_clean is the chosen submission.

## Part C — strict outputs/ cleanup (moved, not deleted)

Moved out of `outputs/` → `scratch/final_cleanup_2l18/`:
- `pred_v8_mini_safe_from_v7.csv`, `pred_v8_mini_safe_diff.csv` (manual-patch provenance)
- `pred_v8_clean_generalized_diff.csv` (diff artifact)
- `archive_before_cleanup/` (the whole directory)

### Final `outputs/` listing (exactly the target)

```
.gitkeep
pred.csv
pred_phase2i0_baseline.csv
pred_v6_qwen_rerank_calc_verifier.csv
pred_v6b_qwen_rerank_calc_verifier_fast.csv
pred_v7_programmatic_assist_from_v6b.csv
pred_v8_clean_generalized_from_v7.csv
run_v6_qwen_rerank_calc_verifier.jsonl
run_v6b_qwen_rerank_calc_verifier_fast.jsonl
run_v7_programmatic_assist_from_v6b.jsonl
run_v8_clean_generalized_from_v7.jsonl
```
One best prediction per meaningful version (v6, v6b, v7, v8_clean) + the chosen
`pred.csv` + the phase2i0 baseline, each with its full run log where available.
Final `validate_submission.py … outputs/pred.csv` → **PASS**.

`scratch/final_cleanup_2l18/` now holds: `pred_before_2l18.csv`,
`pred_v8_mini_safe_from_v7.csv`, `pred_v8_mini_safe_diff.csv`,
`pred_v8_clean_generalized_diff.csv`, `archive_before_cleanup/`.

## Confirmations

- **No OpenRouter API call**; no full LLM inference (file copy + deterministic checks).
- **No qid hardcoding; no public-test answer table; external 3-LLM sheet not used.**
- **No source code, tests, docs, configs, scripts, or audits deleted** — only
  `outputs/` artifacts were *moved* to scratch.
- `outputs/pred.csv` is gitignored (`.gitignore:32: outputs/*`), so the submission
  copy is not tracked; tracked changes are code/docs only.
- v6/v6b/v7/v8_clean prediction + run files preserved in `outputs/`.

## Recommended final submission file

**`outputs/pred.csv`** — equivalent (byte-identical) to
`outputs/pred_v8_clean_generalized_from_v7.csv`: v6b + 2 deterministic calculation
fixes (v7) + 2 generalized concept fixes (paging logical address, MC>AVC), all
qid-free and validated PASS.

## git status

```
 M .gitignore
 M docs/CALCULATION_TAXONOMY.md
 M run.py
 M src/calculation_solver.py
 M src/openrouter_graph_solver.py
 M tests/test_calculation_solver.py
?? configs/adaptive_reasoning.yaml
?? docs/ADAPTIVE_REASONING_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2L13_*.md … docs/AUDIT_PHASE_2L18_*.md
?? scripts/ (adaptive/audit/cleanup/concept-fix scripts)
?? src/adaptive_*.py, src/concept_solver.py, src/evidence_sufficiency.py,
   src/formula_registry.py, src/formula_cards/, src/programmatic_solver.py,
   src/adaptive_proposal_common.py
?? tests/test_adaptive_*.py, tests/test_concept_solver.py, tests/test_sk_verifier_proposal.py
```
(`outputs/*` and `scratch/*` are gitignored.)

## Next step

Submit `outputs/pred.csv` (v8_clean). After the leaderboard result, commit the
accepted code/docs/audits. Do not commit now; all changes left uncommitted for review.
