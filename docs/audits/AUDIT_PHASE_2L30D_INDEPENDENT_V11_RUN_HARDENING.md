# Audit — Phase 2L.30D: Independent V11 Run Hardening (No Missing / No None / Single-Pass)

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (for review)

## Root invariant being enforced

**Every processed qid has exactly one valid final answer label (from the sample's own
choices) before the output CSV is written — no missing qids, no duplicates, no `None`, no
empty, no invalid labels — and the dataset is validated up front so a full run succeeds in
a single pass without needing the repair script.** v10 is never used as a base or fallback.

## Files changed

- `scripts/run_full_v11_independent_submission.py` — preflight, safer resume, stronger
  `_finalize_decision`, pre-output write guard + post-write re-validation, new
  `_collect_problems` / `_assert_ready_for_output` / `_preflight` / `_scan_resume_decisions`
  helpers.
- **New:** `scripts/audit_v11_independent_integrity.py` — one-shot read-only integrity audit.
- **New:** `tests/test_v11_hardening_2l30d.py` (+14).
- `tests/test_repair_v11_2l30c.py` — updated one assertion to the renamed last-resort source.

## Preflight design (Part B)

`_preflight(samples)` runs before any API spend: rejects an empty dataset, any sample
missing a `qid`, and any sample whose choices can't map to ≥1 valid label (listing
offending qids). This converts the old "fail at output-writing after a full run" into a
**clear early abort**. The execute path calls it first thing.

## Resume hardening design (Part C)

`_scan_resume_decisions(workdir, samples)` reads an existing `v11_independent_decisions.csv`
and classifies each row: **completed only if it has a valid label AND
`needs_direct_fallback` is not true.** `None`/empty/invalid/flagged rows are never treated
as done; duplicates keep the **latest valid** row. `_execute` (with `--resume`) carries
forward completed-valid decisions, regenerates everything else, and writes
`resume_state_summary.{json,md}`. (The previous runner parsed `--resume` but ignored it.)

## Fallback finalization design (Part D)

`_finalize_decision(dec, sample, direct_fallback_fn, pool)` order:
1. valid label + not flagged → keep;
2. direct allowed-model fallback → use if it parses to a valid label;
3. **best valid-label candidate already in the pool** → use (`pool_valid_label_repair`);
4. **first available option label from THIS sample's choices** (`labels[0]`, not a blind
   global "A") → `final_source="last_resort_valid_choice"`, `risk="high"`,
   `fallback_used=True`, note carries the original failure;
5. if the sample yields **no** labels → raise a clear error (preflight defense).
Never returns `None`/invalid when choices exist; never uses v10. Tested: a fallback label
outside a 2-option sample is rejected in favour of a valid in-sample label.

## Final output write guard (Part E)

`_assert_ready_for_output(decisions, samples, outdir)` runs `_collect_problems` (missing /
duplicate / invalid / none) and, on any failure, writes
`v11_independent_pre_output_failure_report.{json,md}` and raises **before** writing the CSV.
After writing, the runner **re-reads the CSV from disk** and re-validates it, writing
`v11_independent_final_validation.{json,md}`; a post-write problem also raises. So a broken
run produces a diagnostic report and no (or no trusted) submission, never a silent bad CSV.

## Integrity audit (Part F) — result on existing artifacts

`scripts/audit_v11_independent_integrity.py` (read-only, no API) over
`scratch/full_v11_independent_rerun1/`:
- decision rows **463**, unique 463, missing 0, duplicate 0, invalid 0, **none/empty 9**
  (`test_0042, test_0063, test_0103, test_0202, test_0240, test_0241, test_0275, test_0314,
  test_0335`) → **decisions clean: False** (these are the original failed decisions);
- candidate records 856; fallback_used 30; last_resort 0;
- submission `outputs/pred_v11_independent_rerun1.csv`: rows 463, **valid: True** (0
  missing/dup/invalid/none) — i.e. the 2L.30C repair already produced a clean submission.
A missing `--submission` is reported as "NOT PRESENT" without error (verified).

## Dry-run summary (Part H; no API)

```
audit_v11_independent_integrity.py --work-dir scratch/full_v11_independent_rerun1 \
    --submission outputs/pred_v11_independent_rerun1.csv
  -> decisions clean: False (9 none/empty);  submission valid: True
run_full_v11_independent_submission.py ... --mode cheap --max-qids 463 --dry-run
  -> qids 463; deterministic 18 (0 API); need API 445; upper-bound 1335 calls; est $2.67
```

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **577 passed** (was 563; +14 in `tests/test_v11_hardening_2l30d.py`, +1 updated
  assertion in `tests/test_repair_v11_2l30c.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: finalize last-resort uses only in-sample labels / pool candidate before last
  resort / never invalid when choices exist / raises with no choices; preflight catches
  missing-qid + no-choices and passes clean; resume does not treat invalid/None/flagged rows
  as completed and keeps latest valid on duplicate; output guard catches missing qid and
  writes a failure report (and passes clean); integrity audit detects none/dup/missing and
  validates a good submission + handles a missing submission; no qid hardcoding.

## Confirmations

- **No v10 fallback** anywhere (selector, finalize, resume, repair, audit). Last resort is
  a valid label from the sample's own choices.
- **No OpenRouter/API call** during this coding phase; no inference; no full run.
- **No `outputs/` writes** this phase. `outputs/` currently holds `pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v11_full_adaptive_test.csv`,
  `pred_v11_independent_rerun1.csv` (the last two were written by earlier human-run
  executes, not by this coding phase), `pred_v8_clean_generalized_from_v7.csv`. v10 untouched.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact human command — clean one-pass rerun

```bash
.venv/bin/python scripts/run_full_v11_independent_submission.py \
  --input public-test_1780368312.json \
  --work-dir scratch/full_v11_independent_clean \
  --output outputs/pred_v11_independent_clean.csv \
  --mode cheap --model qwen/qwen3.5-9b-20260310 --budget-usd 3.00 --max-qids 463 \
  --compare-pred outputs/pred_v10_full_production_user_run.csv \
  --resume --execute --i-understand-this-writes-outputs
```
Preflight aborts early on a malformed dataset; `_finalize_decision` guarantees a valid
label per qid; the pre-output guard + post-write re-validation guarantee a complete, valid
CSV — so this should succeed in one pass with no `None`/missing/duplicate and no repair.

## Exact human command — repair the existing run (if desired)

```bash
.venv/bin/python scripts/repair_v11_independent_run.py \
  --input public-test_1780368312.json \
  --work-dir scratch/full_v11_independent_rerun1 \
  --output outputs/pred_v11_independent_rerun1.csv \
  --model qwen/qwen3.5-9b-20260310 --budget-usd 0.20 \
  --execute --i-understand-this-writes-outputs
```
(Already produced a valid `pred_v11_independent_rerun1.csv` per the integrity audit.)

## git status (this phase)

```
?? scripts/run_full_v11_independent_submission.py   (untracked from 2L.30B; edited here)
?? scripts/audit_v11_independent_integrity.py
?? tests/test_v11_hardening_2l30d.py
?? docs/AUDIT_PHASE_2L30D_INDEPENDENT_V11_RUN_HARDENING.md
 M tests/test_repair_v11_2l30c.py   (untracked from 2L.30C; one assertion updated)
```
(Several v11 files are untracked from prior uncommitted phases and were edited in place.
`outputs/` unchanged by this phase.)
