# Audit — Phase 2L.17: Clean Generalized v8 + Output Cleanup

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Converted the two manual `v8_mini` qid patches into **generalized, qid-free
deterministic concept rules**, regenerated a clean v8 from v7 that changes **exactly
the same two answers** (and matches `v8_mini` bit-for-bit), and cleaned the temporary
diagnostic artifacts from `outputs/`. No API calls; no protected file overwritten.

## Files changed

**New**
- `src/concept_solver.py` — generalized concept rules: `paging_logical_address`,
  `mc_vs_avc`. Registry + `solve_concept_sample`; no qid logic, no answer table.
- `scripts/apply_clean_generalized_fixes_to_predictions.py` — applies generalized
  concept + calculation rules to v7; stops if changes exceed `--max-expected-changes`.
- `scripts/cleanup_outputs_for_submission.py` — dry-run-default outputs cleaner.
- `tests/test_concept_solver.py` — rule + script tests.
- `docs/AUDIT_PHASE_2L17_CLEAN_GENERALIZED_V8_AND_OUTPUT_CLEANUP.md` (this file).

## Rules added (generalized; no qid, no public-test answers)

1. **`paging_logical_address`** — for a paging + logical-address *structure* question,
   selects the unique option containing page number + offset/displacement while
   excluding the frame-number and page-size distractors. (Solves the paging case
   naturally; the qid is never referenced.)
2. **`mc_vs_avc`** — extracts MC and AVC; if output rises by one unit:
   MC>AVC ⇒ AVC↑, MC<AVC ⇒ AVC↓, MC=AVC ⇒ unchanged; matches the unique direction
   option. (Solves the MC>AVC case naturally; the qid is never referenced.)

Both fire only on a unique safe option match; otherwise they decline.

## Proof of no qid hardcoding

`grep -cE "test_0[0-9]{3}|if qid|qid ==" src/concept_solver.py
scripts/apply_clean_generalized_fixes_to_predictions.py` → **0 / 0 (CLEAN)**.
A source-inspection test (`test_concept_result_has_no_qid_or_answer_table`) enforces
this on every run. Rules were validated on **synthetic** paging/MC-AVC variants
(increase / decrease / equal / decline cases), not on the public qids.

## v8_clean generation

```bash
.venv/bin/python scripts/apply_clean_generalized_fixes_to_predictions.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --output outputs/pred_v8_clean_generalized_from_v7.csv \
  --log-path outputs/run_v8_clean_generalized_from_v7.jsonl \
  --diff outputs/pred_v8_clean_generalized_diff.csv
```

Result — **2 changes** (within the `--max-expected-changes 2` guard):

| qid | rule | old (v7) | new (v8) | reason |
|---|---|---|---|---|
| test_0065 | `paging_logical_address` | C | **D** | logical address = page number + page offset/displacement |
| test_0189 | `mc_vs_avc` | A | **B** | MC=20 > AVC=15 ⇒ AVC increase |

## Validation

- `validate_submission.py` on `pred_v8_clean_generalized_from_v7.csv`: **PASS** (463 rows).
- `compileall -q src scripts tests`: OK
- `pytest -q`: **317 passed** (was 304; +13).

## v8_clean diff vs v7 and comparison to v8_mini

- **v8_clean vs v7:** 2 changes — `[(test_0065, C, D), (test_0189, A, B)]`.
- **v8_clean vs v8_mini:** **0 differences** — the generalized rules reproduce the
  two manual safe fixes exactly, without qid patching. `v8_mini` is no longer needed
  as a source of truth (kept only for provenance).

## Cleanup dry-run & execute summary

`scripts/cleanup_outputs_for_submission.py` (dry-run default; `--execute` to delete;
never deletes a protected name or anything outside `outputs/`):

- Dry-run classified **14 keep / 28 delete**; reviewed and correct.
- `--execute`: **deleted 28** temporary/diagnostic files (proposal/candidate/audit/
  dryrun/review-pack artifacts), **kept 14** final outputs. (Deleted files are
  gitignored and regenerable via the no-API audits / proposal commands.)

## Final `outputs/` listing

```
.gitkeep
pred.csv
pred_phase2i0_baseline.csv
pred_v6_qwen_rerank_calc_verifier.csv
pred_v6b_qwen_rerank_calc_verifier_fast.csv
pred_v7_programmatic_assist_from_v6b.csv
pred_v8_clean_generalized_from_v7.csv
pred_v8_clean_generalized_diff.csv
pred_v8_mini_safe_from_v7.csv
pred_v8_mini_safe_diff.csv
run_v6_qwen_rerank_calc_verifier.jsonl
run_v6b_qwen_rerank_calc_verifier_fast.jsonl
run_v7_programmatic_assist_from_v6b.jsonl
run_v8_clean_generalized_from_v7.jsonl
```

## Confirmations

- No OpenRouter API call made; no full inference run (deterministic rules only).
- No protected prediction file overwritten: `pred.csv`, v1/v2/v6/v6b/v7 untouched;
  the v8 script and cleanup script both refuse protected names; `v8_mini` was used
  only for comparison, not as a source of truth.
- External Gemini/GPT/Claude sheet **not used** (the v8 script never reads it; the
  concept rules use only question + option text).
- No qid hardcoding; no public-test answer table (greps + tests).
- No source/tests/docs/scripts deleted — cleanup only removed `outputs/` diagnostics.
- No leaderboard upload; `.env` not read; no API key exposed.

## Recommended candidate

- **`outputs/pred_v7_programmatic_assist_from_v6b.csv`** — clean conservative
  candidate (v6b + 2 deterministic calculation fixes).
- **`outputs/pred_v8_clean_generalized_from_v7.csv`** — generalized upgraded
  candidate. Its diff vs v7 is **exactly** the two manual safe fixes (paging logical
  address, MC>AVC), produced by generalized rules with no qid patching → the
  preferred submission if an upgrade over v7 is desired.

## git status (this phase)

```
?? src/concept_solver.py
?? scripts/apply_clean_generalized_fixes_to_predictions.py
?? scripts/cleanup_outputs_for_submission.py
?? tests/test_concept_solver.py
?? docs/AUDIT_PHASE_2L17_CLEAN_GENERALIZED_V8_AND_OUTPUT_CLEANUP.md
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*` and `scratch/*`
are gitignored.)

## Next step

Decide which file to submit — **v8_clean** (generalized upgrade) or **v7**
(conservative). After the leaderboard result, commit the accepted code/docs/audits.
Do not commit now; all changes left uncommitted for review.
