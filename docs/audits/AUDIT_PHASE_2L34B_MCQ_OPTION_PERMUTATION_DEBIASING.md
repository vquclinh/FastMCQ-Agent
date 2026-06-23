# Audit — Phase 2L.34B: MCQ Option-Permutation Debiasing Layer

**Date:** 2026-06-23  **Branch:** `main`  **Status:** experimental shadow pipeline (no commit, no API)

## Motivation: MCQ option-order / label-position bias

Some remaining v11 errors may stem from **label-position bias**: an LLM can prefer certain
letter positions or flip its choice when the option order changes. This layer probes that
directly — it asks the same question under several deterministic option orders, maps each
selected option *back to its original label*, and treats **stability of the mapped answer
across permutations** as the override signal. An answer that survives reshuffling is
position-bias resistant; one that moves is fragile and is left as v11.

## Files created / changed

**Created (all untracked; nothing committed):**
- `scripts/build_v12b_permutation_plan.py` — offline target plan (Part A).
- `scripts/run_v12b_option_permutation.py` — permutation verifier + map-back, dry-run default (Part B).
- `scripts/build_v12b_permutation_candidate.py` — consensus selector (Part C).
- `scripts/audit_v12b_permutation_candidate.py` — offline review tool (Part D).
- `tests/test_v12b_permutation_2l34b.py` — 14 tests (Part E).
- `docs/audits/AUDIT_PHASE_2L34B_…md` — this audit.
- `outputs/pred_v12b_permutation_candidate.csv` — shadow candidate (**gitignored** via `outputs/*`;
  in this dry-run byte-identical to v11).

**Changed:** none. `scripts/final_infer.py`, the Docker entrypoint, and the production config
are untouched.

## Why this differs from v11 and the v12 (2L.34A) verifier

- **v11** decides each qid once from its candidate pool (fixed option order).
- **v12 delta verifier (2L.34A)** re-derives answers with independent specialist agents, still
  in the original option order — it targets *evidence weakness*.
- **v12B (this layer)** holds the agents constant and varies the *option order itself*, then
  requires the mapped-back answer to be **stable across permutations**. It targets a different
  failure mode — *position/label bias* — that order-fixed verifiers cannot detect.

## Plan summary (Part F.1, offline)

`build_v12b_permutation_plan.py` over 463 qids → **459 planned** (priority > 0), 136 with
≥5 options. Priority rewards fallback provenance, high risk, v11≠v10, option_count≥5,
near-duplicate options, API disagreement, parse failures, and labels beyond H. Top targets
(priority 17.0) are the **10-option `direct_fallback` + high-risk + v11≠v10** qids
(e.g. `test_0043`, `test_0222`) — exactly where position bias is most plausible. No answer
changed; output is `scratch/v12b_option_permutation/permutation_plan.csv`.

## Dry-run summary (Part F.2, NO API)

`run_v12b_option_permutation.py --max-qids 30 --permutations 6 --dry-run`:
```
planned_qids   : 30
prompts_built  : 179   (deterministic permutations: original/reverse/rotate+1/rotate+2/random_seed1/2, deduped)
records_written: 179
model_calls_made: 0
mode           : dry_run
```
Each record carries `original_qid, permutation_id, permutation_map, permuted_selected_label,
mapped_original_label, selected_option_text, parse_status, label_option_match, confidence,
evidence, valid`. Validity requires: parsed ok, in-range label, option-text match after
normalization, and the model's own `label_matches_option` not False. End-to-end on the dry-run
records: selector → **0 accepted / 0 applied / changed_vs_v11 = 0**, validation PASS; audit tool
confirms `identical_to_v11 = True` (md5 `69f4e7c990e8c612e7bee53084d13b4d`).

## Consensus override rules (Part C)

- **Conservative:** ≥5 valid records, ≥4 map to the same non-current label, current label gets
  ≤1 mapped vote, no mismatch/parse failure among supporters.
- **Balanced:** 3/5 or 4/6 stable mapped votes with mean supporting confidence ≥ 0.6.
Unit-tested: accepts 4/6 stable non-current; rejects 3/6; rejects when current has 2 votes;
rejects option-text mismatch and self label/option mismatch.

## Tests run and results (Part E)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_v12b_permutation_2l34b.py`: **14 passed**
- `pytest -q` (full suite): **645 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Model policy audit result

**PASS** — only `qwen/qwen3.5-9b-20260310` referenced (allowed ≤9B Qwen3.5); guarded by
`assert_allowed_llm_model` before any client construction.

## Confirmations

- **No API calls** — verifier ran dry-run; `model_calls_made = 0`; client never constructed.
- **Production default unchanged** — `final_infer.py` / Docker still serve frozen v11; config
  `default_mode=frozen_csv`, `current_best_csv=…pred_v11_independent_rerun1.csv` (unit-tested).
- **No outputs overwritten** — v11 `69f4e7c990e8c612e7bee53084d13b4d`, v10 `c12e32fd…`,
  `pred.csv` `002a0f73…` all unchanged; shadow CSV is gitignored.
- **No qid hardcoding / no ground truth / no external 3-LLM sheet** — regex-tested; plan and
  selector derive only from existing v11 artifacts.
- **Not committed.**

## Exact command — real API pilot (opt-in; needs OPENROUTER_API_KEY + budget)

```bash
.venv/bin/python scripts/build_v12b_permutation_plan.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --v10 outputs/pred_v10_full_production_user_run.csv \
  --decisions scratch/full_v11_independent_rerun1/v11_independent_decisions_repaired.csv \
  --candidates scratch/full_v11_independent_rerun1/v11_independent_candidates.jsonl \
  --output scratch/v12b_option_permutation/permutation_plan.csv

.venv/bin/python scripts/run_v12b_option_permutation.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --plan scratch/v12b_option_permutation/permutation_plan.csv \
  --work-dir scratch/v12b_option_permutation \
  --model qwen/qwen3.5-9b-20260310 \
  --max-qids 30 --permutations 6 --budget-usd 0.50 --execute
```

## Exact command — build candidate (offline, from permutation records)

```bash
.venv/bin/python scripts/build_v12b_permutation_candidate.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --permutation-records scratch/v12b_option_permutation/permutation_records.jsonl \
  --output outputs/pred_v12b_permutation_candidate.csv \
  --review-dir scratch/v12b_option_permutation/review \
  --policy conservative

.venv/bin/python scripts/audit_v12b_permutation_candidate.py \
  --input public-test_1780368312.json \
  --current outputs/pred_v11_independent_rerun1.csv \
  --candidate outputs/pred_v12b_permutation_candidate.csv \
  --plan scratch/v12b_option_permutation/permutation_plan.csv \
  --permutation-records scratch/v12b_option_permutation/permutation_records.jsonl \
  --output-dir scratch/v12b_option_permutation/audit
```
(The shadow candidate is evaluation-only; it is **not** wired into `final_infer.py` and must
beat v11 on evidence before any future promotion.)

## Git status

```
?? scripts/audit_v12b_permutation_candidate.py
?? scripts/build_v12b_permutation_candidate.py
?? scripts/build_v12b_permutation_plan.py
?? scripts/run_v12b_option_permutation.py
?? tests/test_v12b_permutation_2l34b.py
?? docs/audits/AUDIT_PHASE_2L34B_MCQ_OPTION_PERMUTATION_DEBIASING.md
```
(`outputs/pred_v12b_permutation_candidate.csv` and `scratch/v12b_option_permutation/` are
gitignored.) Nothing committed.
