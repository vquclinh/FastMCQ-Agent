# Audit — Phase 2L.29C: Runtime Summary Check + Minimal Timing Instrumentation

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Did timing already exist?

**No.** Before this phase there was **no** runtime/elapsed instrumentation anywhere in the
adaptive submission path:
- `scripts/run_full_adaptive_submission.py` — no `time`/`datetime`/elapsed references at
  all (the only "start"/"end" matches were the `outputs/` path guard).
- `scripts/run_adaptive_selective_api.py` — its execute summary wrote
  `{mode, model, scheduled, calls_made, judge_ran}` to `adaptive_run_summary.json/.md`,
  plus a dry-run cost estimate print — but **no wall-clock, elapsed, or timestamps**.
- `build_submission_variant.py` (`variant_summary.md`) — recorded coverage/overrides/risk
  but **no timing**.
- No `full_adaptive_submission_summary.*` file existed under
  `scratch/full_adaptive_v11_final/`.

So timing was missing. Per the task rules I added **minimal, logging-only** instrumentation
to `scripts/run_full_adaptive_submission.py` **only**. No ranking, model-policy, candidate
selection, or generation logic was touched.

## Files inspected

- `scripts/run_full_adaptive_submission.py`
- `scripts/run_adaptive_selective_api.py`
- adaptive runner summary writers (`adaptive_run_summary.json` / `.md`)
- `scripts/build_submission_variant.py` (`variant_summary.md`)
- `scratch/full_adaptive_v11_final/` (no prior summary present)

## Files changed

- `scripts/run_full_adaptive_submission.py` — added timing/summary instrumentation only:
  - new imports: `json`, `time`, `datetime`/`timezone`;
  - a logging-only fallback constant `_DEFAULT_COST_PER_CALL_USD = 0.002` (matches the
    adaptive runner default; used only if the generation summary omits the rate);
  - `time.perf_counter()` around the whole execute path and around each phase;
  - ISO-8601 UTC start/end timestamps;
  - writes `full_adaptive_submission_summary.json` and `.md` under the **work-dir**
    (never under `outputs/`);
  - prints elapsed + API calls + estimated cost at the end.

No other file changed.

## Exact fields now printed and written

Written to `scratch/<work-dir>/full_adaptive_submission_summary.json` (+ a `.md` digest):

- `submission_file`, `work_dir`, `candidates_file`, `review_dir`
- `mode`, `policy`, `model`
- `start_time`, `end_time` (ISO-8601 UTC)
- `elapsed_seconds` (total wall-clock)
- `adaptive_generation_elapsed_seconds`
- `variant_build_elapsed_seconds`
- `total_api_calls` (pulled from `adaptive_run_summary.json` `calls_made`)
- `judge_ran`, `scheduled` (pulled from the generation summary)
- `cost_per_call_usd`, `estimated_cost_usd` (`calls_made × cost_per_call`)

Printed at the end of an `--execute` run: submission file, review/diffs dir, candidates
file, **elapsed** (with per-phase breakdown), **api calls + est. cost**, and the run-summary
path.

## How to view it after a run

```bash
cat scratch/full_adaptive_v11_final/full_adaptive_submission_summary.json
cat scratch/full_adaptive_v11_final/full_adaptive_submission_summary.md
```
(or read the final block printed to stdout by `run_full_adaptive_submission.py --execute`).

## Validation results

- `compileall -q scripts src tests`: **OK**
- `pytest -q`: **535 passed** (unchanged count — instrumentation is logging-only; the
  existing execute-path order test still passes and now also exercises the summary write).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- End-to-end check with fakes (no API, temp dirs): summary JSON/MD written with
  `start_time/end_time/elapsed_seconds/adaptive_generation_elapsed_seconds/
  variant_build_elapsed_seconds/total_api_calls=5/estimated_cost_usd=0.01/judge_ran=1`.

## Confirmations

- **No OpenRouter/API call** during this phase; no inference; no full adaptive execution
  (verified only via fakes + dry-run).
- **No `outputs/` writes**; `outputs/` still contains only `pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v8_clean_generalized_from_v7.csv`.
- Timing summary is written under the **work-dir** (scratch), never under `outputs/`.
- No ranking/model-policy/candidate-selection logic changed; instrumentation is pure
  logging.
- No qid hardcoding.
- Nothing committed.

## git status (this phase)

```
?? scripts/run_full_adaptive_submission.py
?? docs/AUDIT_PHASE_2L29C_RUNTIME_SUMMARY_CHECK.md
```
`run_full_adaptive_submission.py` is untracked (created in 2L.29B, never committed) — this
phase edited that uncommitted file in place. Plus the pre-existing untracked files from
earlier phases; `outputs/` unchanged.
