# Audit — Phase 2L.28A: End-to-End Adaptive Pilot Run and Full-Run Gate

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Built a clean, offline end-to-end **pilot workflow**: select a small set of difficult
API-eligible questions, run the adaptive system over them (dry-run here), and produce a
**decision report** comparing v10 vs the adaptive final decision — used only to judge
system behavior. Added a separate **full-run candidate gate** (the only script allowed to
write under `outputs/`) that refuses pilot inputs and partial runs; it is **not executed**
this phase. **No API call, no inference, nothing written under `outputs/`.** All artifacts
live under `scratch/adaptive_pilot_2l28/`.

## No-output rule confirmation

`outputs/` still contains only `pred.csv`, `pred_v10_full_production_user_run.csv`,
`pred_v8_clean_generalized_from_v7.csv`. This phase wrote zero files to `outputs/`. v10
(public 77.75) remains the locked submission. No submission file was produced from the
pilot.

## Files changed

**New (scripts):** `select_adaptive_pilot_qids.py`, `run_adaptive_pilot.py`,
`build_pilot_decision_report.py`, `build_full_adaptive_submission_candidate.py`.
**New (tests):** `tests/test_pilot_gate.py` (+13).
**Modified:** `scripts/run_adaptive_selective_api.py` — added `--out-prefix` so the pilot
wrapper reuses the exact adaptive logic but emits `pilot_*`-prefixed artifacts.

## Part A — Pilot selector (`select_adaptive_pilot_qids.py`)

Reads the overall accuracy plan, keeps only questions whose `recommended_layer` is
API-eligible **for the chosen mode** (reusing the adaptive runner's `_MODE_LAYERS`), and
**excludes `tool_only`**. Selects exactly `--count` (default 20) by **highest
`priority_score` first**, with **route round-robin only within equal-score buckets** for
diversity. `expected_calls` per qid = agents×temps + 1 (possible judge) from the adaptive
runner's `_agents_temps_for`. Output columns: `qid, route, recommended_layer,
priority_score, reason, expected_calls`. Caps at the available count when fewer than N are
eligible. Refuses non-`scratch/` output. No qid hardcoding.

**Observation:** in `cheap` mode the highest-difficulty bucket (`priority_score=2.0`, 145
questions) is **entirely `calculation`** (calc-without-proof), so the top-20 are all
calculation — diversity can't apply when the top score bucket is single-route. `balanced`/
`rich` modes (which add `rich_api`/`evidence_pack` layers) surface other routes.

## Part B — Pilot runner (`run_adaptive_pilot.py`)

Thin **dry-run-by-default** wrapper: treats `pilot_qids.csv` (which already carries `qid`
+ `recommended_layer`) as the plan and delegates to `run_adaptive_selective_api` with
`--out-prefix pilot`, reusing the exact adaptive selection/judge/budget logic. Writes
`pilot_api_candidates.jsonl/.csv` and `pilot_run_summary.json/.md`. `--dry-run`/`--execute`
mutually exclusive; refuses non-`scratch/` output; model policy enforced by the delegate.
No `outputs/` writes.

## Part C — Pilot decision report (`build_pilot_decision_report.py`)

For each pilot qid builds the candidate pool (v10 base + offline tool candidates + API
candidates + any judge candidate), runs the **consistency-guarded ranker**
(`answer_ranker.select_answer`), and classifies the decision:
`keep_v10 | override_candidate | manual_review | reject` (`reject` = v10 kept while
conflicting candidates existed but failed the guard). Emits `pilot_decisions.csv` and a
`pilot_decisions.md` with totals (kept / override / manual-review / rejected / judge /
placeholder / mismatch / model-only-override counts), a full 20-qid table, and a
**recommendation**:
- `proceed_full_run` only if placeholder rate ≤ 0.25, **no model-only override**, every
  override is evidence/proof-backed, and the judge is present when conflicts exist;
- `stop_keep_v10` if the system rejected every proposal;
- otherwise `revise_prompts_or_ranker`.
Never writes a submission CSV; refuses non-`scratch/` output.

## Part D — Full-run candidate gate (`build_full_adaptive_submission_candidate.py`)

The **only** script permitted to write a real candidate under `outputs/`. **Not run this
phase.** Fail-closed guards, in order:
1. requires explicit `--i-understand-this-writes-outputs`;
2. **refuses any candidate file whose name contains `pilot`**;
3. requires the output path under `outputs/` and refuses protected pred names
   (`adaptive_proposal_common.guard_output`);
4. **requires a full candidate set** — API-candidate coverage ≥ `--min-coverage` (default
   0.80) of dataset qids, else refuses as a partial/pilot run;
5. review-policy gates: `--require-low-risk-or-reviewed`, `--max-model-only-overrides`,
   `--max-total-overrides`, `--min-evidence-score`;
6. validates output format (valid labels, row count == dataset size).
Writes the real candidate CSV to `outputs/` and a diff under `scratch/`. No ground truth,
no qid hardcoding.

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **500 passed** (was 487; +13 in `tests/test_pilot_gate.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: selector returns exactly 20 eligible (caps at available; excludes `tool_only`;
  refuses non-scratch); no qid hardcoding in any new script; pilot runner dry-run
  constructs **no** API client (monkeypatched to raise), refuses `outputs/` + mutual-
  exclusive flags + disallowed model; report builds override & keep decisions from fake
  candidates and refuses `outputs/`; full gate refuses pilot input, refuses partial
  coverage, requires ack + `outputs/` path + rejects protected pred name.

## Dry-run summary (no API)

```
select_adaptive_pilot_qids.py --count 20 --mode cheap
  -> selected 20/20  routes={calculation:20}  layers={cheap_api:20}
     -> scratch/adaptive_pilot_2l28/pilot_qids.csv
run_adaptive_pilot.py --mode cheap --budget-usd 0.50 --dry-run
  -> 20 qids; scheduled 20 [cheap_api]; upper-bound 60 calls; est $0.12; budget 0.5
```

## Confirmations

- **No OpenRouter/API call**; no inference run (dry-run only; API client never constructed).
- **No files written under `outputs/`**; `pred.csv` and v10 untouched. All artifacts under
  `scratch/adaptive_pilot_2l28/`.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth;
  no hidden/public ground truth.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- The full-run gate was **created but not executed**.
- Nothing committed.

## Exact human commands

1. **Select 20 pilot qids**
   ```bash
   .venv/bin/python scripts/select_adaptive_pilot_qids.py \
     --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
     --output scratch/adaptive_pilot_2l28/pilot_qids.csv --count 20 --mode cheap
   ```
2. **Execute the pilot** (human-initiated; spends budget)
   ```bash
   .venv/bin/python scripts/run_adaptive_pilot.py \
     --input public-test_1780368312.json \
     --base-pred outputs/pred_v10_full_production_user_run.csv \
     --v10-log scratch/v10_full_production/run_v10_full_production_user_run.jsonl \
     --pilot-qids scratch/adaptive_pilot_2l28/pilot_qids.csv \
     --output-dir scratch/adaptive_pilot_2l28 \
     --mode cheap --model qwen/qwen3.5-9b-20260310 --budget-usd 0.50 --execute --resume
   ```
3. **Build the pilot decision report**
   ```bash
   .venv/bin/python scripts/build_pilot_decision_report.py \
     --input public-test_1780368312.json \
     --base-pred outputs/pred_v10_full_production_user_run.csv \
     --pilot-qids scratch/adaptive_pilot_2l28/pilot_qids.csv \
     --pilot-candidates scratch/adaptive_pilot_2l28/pilot_api_candidates.jsonl \
     --output-dir scratch/adaptive_pilot_2l28
   ```
4. **If recommendation is `proceed_full_run`, run the full adaptive execution**
   ```bash
   .venv/bin/python scripts/run_adaptive_selective_api.py \
     --input public-test_1780368312.json \
     --base-pred outputs/pred_v10_full_production_user_run.csv \
     --v10-log scratch/v10_full_production/run_v10_full_production_user_run.jsonl \
     --plan scratch/accuracy_engine_2l27/overall_accuracy_plan.csv \
     --output-dir scratch/full_adaptive_run --mode balanced \
     --model qwen/qwen3.5-9b-20260310 --budget-usd 5.00 --max-qids 463 --execute --resume
   ```
5. **Build the full submission candidate** (only after review)
   ```bash
   .venv/bin/python scripts/build_full_adaptive_submission_candidate.py \
     --input public-test_1780368312.json \
     --base-pred outputs/pred_v10_full_production_user_run.csv \
     --api-candidates scratch/full_adaptive_run/adaptive_api_candidates.jsonl \
     --output outputs/pred_v11_full_adaptive_candidate.csv \
     --review-dir scratch/full_adaptive_candidate \
     --require-low-risk-or-reviewed --max-model-only-overrides 0 \
     --max-total-overrides 40 --min-coverage 0.90 \
     --i-understand-this-writes-outputs
   ```

## Recommended next phase

A human runs commands 1–3 (small budget) and reads `pilot_decisions.md`. If the
recommendation is `proceed_full_run`, command 4 produces the full candidate set and
command 5 (after diff review) writes the first v11 `outputs/` candidate for A/B vs v10.
v10 (77.75) remains the submission until a result is accepted. Do not commit until then.
