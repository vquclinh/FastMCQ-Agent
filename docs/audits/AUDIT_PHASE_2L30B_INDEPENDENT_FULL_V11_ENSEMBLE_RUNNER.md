# Audit — Phase 2L.30B: Independent Full V11 Ensemble Runner

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Built a **true independent v11** answering system — NOT a v10 overlay. It answers every
question from v11's own candidates (deterministic tools + evidence/card candidates +
allowed-model API agents + a direct fallback) and selects one final answer per qid via a
new independent selector that has **no v10 base**. **This coding phase calls no API, runs
no inference, and writes NO `outputs/` file** (dry-run only). v10 remains the git fallback
but is never used for generation.

## Files changed

**New (src):** `independent_answer_selector.py`.
**New (scripts):** `run_full_v11_independent_submission.py`.
**New (tests):** `tests/test_independent_v11_2l30b.py` (+15).

## Confirmation: this is NOT a v10 overlay

- The runner has **no `--base-pred` argument** (test asserts no such `add_argument`, and
  passing `--base-pred` is rejected by argparse).
- Candidate generation calls `build_candidate_pool(sample, None, ...)` — passing
  `base_answer=None` means the factory never adds the `v10_base` candidate; every candidate
  is produced by v11's own tools/evidence/API. The runner source contains **no `v10_base`**.
- The selector (`independent_answer_selector.py`) contains **no `v10_base` / `_BASE_SOURCE`
  / `base_answer`** usage; it always derives the answer from the candidates (or a high-risk
  direct fallback) — never from v10.

## Independent candidate generation design (Part B)

Per qid (no v10):
1. **Deterministic/tool** — via `build_candidate_pool(sample, None)`: `formula_bank_solver`
   (incl. calculation-first rules, Cournot/monopoly/hex/subnet/percent-change/linear),
   `concept_solver`, and the domain tool solvers (`safe_math`, `stats`, `finance_econ`,
   `cs`, `physics`, `probability`, `geometry`).
2. **Evidence-pack / knowledge** — the factory's card candidate (unique-option RAG-lite
   card); long-context / option-aware packs enrich the API prompts (they never select).
3. **API agents** (allowed model only) by `(mode, route)`:
   - calculation → `calculation_solver` first, `option_elimination` fallback only if no
     valid calc candidate;
   - non-calc cheap → `route_specialist` + `option_elimination`;
   - balanced → `route_specialist` + `challenger` + `option_elimination`;
   - rich → + `tool_hint` (and temp 0.0/0.2);
   - `pairwise_judge` only when valid candidates conflict.
   `challenger`'s "current" answer is the best valid candidate so far — **never v10**.
4. **Direct fallback** — if no valid candidate exists, one direct allowed-model answer,
   parsed to a valid label, marked **high risk**, logged; never v10.

## Independent selector design (Part C)

`select_independent_answer(pool, sample, route, judge, fallback)` order: (1) unique
deterministic low-risk tool answer; (2) deterministic conflict → judge if valid, else
best-scored deterministic marked high-risk; (3) ≥2 consistent independent sources agree +
evidence → consensus; (4) single grounded evidence candidate passing option grounding;
(5) conflicting grounded candidates + valid judge → judge; (6) direct fallback (high risk);
(7) weakest-link consistent choice. Emits per-qid decision fields: `qid, final_answer,
final_source, route, risk, evidence_summary, proof_summary, candidate_count,
rejected_count, judge_used, fallback_used, parse_status_summary, note`.

## Logs / summaries (Part D)

Execute writes under the work-dir: `v11_independent_candidates.jsonl`,
`v11_independent_decisions.csv`, `v11_independent_summary.json`, `v11_independent_summary.md`
with total qids, output path, elapsed seconds, API calls, estimated cost, route breakdown,
final-source breakdown, deterministic/api/evidence-pack/fallback answer counts, judge-used
count, parser-failure / placeholder / numeric-mismatch / invalid-no-json counts.

## Compare-to-v10 is report-only (Part E)

`--compare-pred` is optional and read **only after all v11 decisions are finalized**
(`_compare_to_v10`), producing `compare_to_v10.csv` + `.md` (changed count, changed-by-route,
changed-by-final_source, label distribution). It never feeds candidate generation or
selection — tests confirm a dry-run succeeds even when `--compare-pred` points to a
nonexistent file, and that a dry-run without `--compare-pred` never loads any prediction.

## Dry-run summary (no API) — Part G

```
run_full_v11_independent_submission.py ... --mode cheap --budget-usd 3.00 --max-qids 463 \
    --compare-pred outputs/pred_v10_full_production_user_run.csv --dry-run
  qids 463; deterministic now 18 (0 API calls); need API 445;
  upper-bound 1335 calls; est $2.67; budget 3.0
  compare-pred: REPORT-ONLY (not used for answers)
```

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **550 passed** (was 535; +15 in `tests/test_independent_v11_2l30b.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: no `--base-pred` arg / `v10_base`; rejects `--base-pred` flag; dry-run never
  loads a pred file; `--compare-pred` not required to run (report-only); dry-run no API +
  no outputs; execute requires ack; protected output names rejected; disallowed model
  rejected; output under `outputs/`; work-dir under `scratch/`; `_validate_decisions`
  catches bad labels + missing qids; fallback answer comes from the fallback (not v10);
  selector module has no v10/base usage; unique-deterministic selection; no qid hardcoding.

## Confirmations

- **No OpenRouter/API call** during this coding phase; no inference; no full run.
- **No `outputs/` writes**; the new `pred_v11_independent_full.csv` was not created.
  `outputs/` is unchanged (`pred.csv`, `pred_v10_full_production_user_run.csv`,
  `pred_v11_full_adaptive_test.csv`, `pred_v8_clean_generalized_from_v7.csv`). v10 untouched.
- **Not a v10 overlay**; **no `--base-pred`**; v10 never used for generation or selection.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth;
  no hidden/public ground truth.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact human command (execute independent v11 full run)

```bash
.venv/bin/python scripts/run_full_v11_independent_submission.py \
  --input public-test_1780368312.json \
  --work-dir scratch/full_v11_independent \
  --output outputs/pred_v11_independent_full.csv \
  --mode cheap --model qwen/qwen3.5-9b-20260310 --budget-usd 3.00 --max-qids 463 \
  --compare-pred outputs/pred_v10_full_production_user_run.csv \
  --resume --execute --i-understand-this-writes-outputs
```

This answers all 463 qids from v11 itself, writes the single submission CSV, and (since
`--compare-pred` is given) a report-only diff vs v10 under
`scratch/full_v11_independent/`. v10 remains the fallback in git until a result is accepted.

## git status (this phase)

```
?? src/independent_answer_selector.py
?? scripts/run_full_v11_independent_submission.py
?? tests/test_independent_v11_2l30b.py
?? docs/AUDIT_PHASE_2L30B_INDEPENDENT_FULL_V11_ENSEMBLE_RUNNER.md
```
(plus pre-existing untracked files from earlier phases; `outputs/` unchanged.)
