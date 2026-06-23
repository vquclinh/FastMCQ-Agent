# Audit — Phase 2L.30C: Repair Independent V11 Null-Answer Failure

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (for review)

## Root cause of `final_answer=None`

The independent v11 run produced `scratch/full_v11_independent_rerun1/
v11_independent_decisions.csv` with **9 qids** (e.g. `test_0042`, `test_0063`, `test_0103`,
`test_0202`, `test_0240`, …) whose `final_answer` was empty and `final_source="none"`. For
those qids every API candidate was rejected by the parsers (`no_json` from truncation +
`numeric_mismatch`), the deterministic tools didn't fire, and the runner's pre-call direct
fallback (only triggered when `pool.candidates` was empty) itself returned an unparseable
answer. The selector's old step 7 then returned `(None, …)` — and the loop appended that
`None` decision, so the final-output validation later refused to write
(`REFUSING: invalid label None for test_0042`). Net effect: candidate generation finished
but no submission was written, and 9 decisions were left as `None`.

## Files changed

- `src/independent_answer_selector.py` — selector fail-safe (no `None`, signal flag).
- `scripts/run_full_v11_independent_submission.py` — `_finalize_decision` repair before
  every append/write.
- **New:** `scripts/repair_v11_independent_run.py` — repair an existing failed run.
- **New:** `tests/test_repair_v11_2l30c.py` (+13).

## Selector fail-safe design (Part A)

`select_independent_answer` no longer silently returns a `None`/invalid label:
- Step 7 now selects the **best candidate with a real option label** (preferring consistent
  ones, then any), high-risk — so any parsed valid label is used before giving up.
- Step 8 (truly nothing valid) returns `(None, decision)` with a new
  `needs_direct_fallback=True` flag and `final_source="needs_fallback"` — a *signal* to the
  runner, not a written answer.
Decisions carry `needs_direct_fallback` so the runner knows to repair. Still no v10 ever.

## Runner repair (Part A)

`run_full_v11_independent_submission._finalize_decision(dec, sample, direct_fallback_fn)` is
called on **every** decision immediately before it is appended:
- valid label and not flagged → unchanged;
- else call the direct allowed-model fallback; if it parses to a valid label →
  `final_source="direct_fallback_repair"`, `risk="high"`, `fallback_used=True`;
- else a deterministic **first-label last resort** (no v10, no ground truth) — guaranteeing
  a valid label and that `None` is never written. The original failure note is preserved.

## Repair script design (Part B) — `repair_v11_independent_run.py`

Repairs an existing failed run **without rerunning all 463 questions** and **without v10**:
- reads `v11_independent_decisions.csv` + `v11_independent_candidates.jsonl`;
- detects missing qids, `None`/empty labels, invalid labels, duplicate qids (dedup keeps a
  valid row over an invalid one);
- for each broken qid: (1) reuse a **valid parsed candidate** from the JSONL (parse ok +
  valid label; agent-priority then confidence), (2) else — only with `--execute` — a direct
  allowed-model fallback, (3) else a deterministic first-label last resort;
- DRY-RUN reports counts (missing/none/invalid/duplicate, repairable-from-candidates,
  need-API) + estimated API calls and writes only a scratch JSON report (no API, no outputs);
- EXECUTE writes `v11_independent_decisions_repaired.csv` + `v11_independent_repair_report.
  {md,json}` under the work-dir and the final CSV under `outputs/` (ack required), after
  validating row count == dataset, qid set == dataset, and all labels valid;
- refuses protected output names and non-scratch work-dir; enforces the model policy.

## Dry-run repair summary (Part D; no API) — on the actual failed run

```
repair_v11_independent_run.py --work-dir scratch/full_v11_independent_rerun1 \
    --output outputs/pred_v11_independent_rerun1.csv --budget-usd 0.20 --dry-run
  total_in_dataset: 463   decision_rows: 463   unique_qids: 463   duplicate_qids: 0
  missing_qids: 0   invalid_labels: 9   none_labels: 9   broken_total: 9
  repairable_from_candidates: 0   need_direct_fallback_api: 9
  estimated_api_calls: 9   estimated_cost_usd: 0.018
```
(The 9 broken qids have no valid parsed candidate in the JSONL, so they require the direct
allowed-model fallback at `--execute` time; an unparseable fallback falls back to the
deterministic first-label last resort. Never v10.)

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **563 passed** (was 550; +13 in `tests/test_repair_v11_2l30c.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: selector uses fallback (not None); selector signals `needs_direct_fallback`
  when nothing valid; selector prefers a valid-label candidate over a None one;
  `_finalize_decision` repairs via direct fallback / first-label last resort / leaves valid
  decisions untouched (and does not invoke the fallback then); repair detects `None` labels
  in dry-run and writes no outputs/no API; repair source has no v10/`--base-pred`; repair
  execute requires ack; repair execute reuses a JSONL candidate without calling API and
  validates the final CSV; protected output + disallowed model rejected; no qid hardcoding.

## Confirmations

- **No v10 fallback** anywhere: neither the selector, the runner repair, nor the repair
  script reads or copies v10. Last resort is a deterministic first option label.
- **No OpenRouter/API call** during this coding phase; no inference; no full run.
- **No `outputs/` writes**; `outputs/` unchanged (`pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v11_full_adaptive_test.csv`,
  `pred_v8_clean_generalized_from_v7.csv`). v10 untouched.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact human command to repair the existing failed run and write the output

```bash
.venv/bin/python scripts/repair_v11_independent_run.py \
  --input public-test_1780368312.json \
  --work-dir scratch/full_v11_independent_rerun1 \
  --output outputs/pred_v11_independent_rerun1.csv \
  --model qwen/qwen3.5-9b-20260310 --budget-usd 0.20 \
  --execute --i-understand-this-writes-outputs
```

This repairs only the 9 broken qids (direct allowed-model fallback, then first-label last
resort), writes `v11_independent_decisions_repaired.csv` + the repair report under the
work-dir, validates, and writes the final submission CSV. v10 remains the fallback in git.
(Future independent runs no longer need this: `_finalize_decision` now repairs inline so
the runner never emits `None`.)

## git status (this phase)

```
 M src/independent_answer_selector.py
 M scripts/run_full_v11_independent_submission.py   (untracked from 2L.30B; edited in place)
?? scripts/repair_v11_independent_run.py
?? tests/test_repair_v11_2l30c.py
?? docs/AUDIT_PHASE_2L30C_REPAIR_INDEPENDENT_V11_NULL_ANSWER.md
```
(`independent_answer_selector.py` and `run_full_v11_independent_submission.py` are untracked
files created in 2L.30B, edited here. Plus pre-existing untracked files; `outputs/`
unchanged.)
