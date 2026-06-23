# Audit — Phase 2L.34C: Promote V12B Option-Permutation Debiaser into SRC Core Layer

**Date:** 2026-06-23  **Branch:** `main`  **Status:** refactor (no commit, no API, default unchanged)

## Why this refactor was needed

The V12B debiaser's deterministic core (permutation construction, permuted→original label
mapping, record validity, vote tally, override policy) lived inside CLI scripts — hard to
reuse and to unit-test in isolation, and duplicated across the runner and the selector. This
phase promotes that logic into a single pure module, making V12B a real architecture layer and
the scripts thin wrappers. Behavior is preserved exactly (dry-run candidate still == v11).

## Files created / changed

**Created:**
- `src/mcq_permutation_debiaser.py` — pure deterministic core (no API/OpenRouter/client).
- `tests/test_mcq_permutation_debiaser_2l34c.py` — 15 unit tests for the core module.
- `docs/audits/AUDIT_PHASE_2L34C_…md` — this audit.

**Changed (refactored to thin wrappers / updated tests):**
- `scripts/run_v12b_option_permutation.py` — now imports `build_option_permutations` +
  `map_permuted_answer_to_original`; keeps CLI, prompting, model I/O, JSONL output.
- `scripts/build_v12b_permutation_candidate.py` — `decide_override` is now a thin wrapper over
  `summarize_permutation_votes` + `select_permutation_override`; keeps CLI, protection,
  validation, review-file writing.
- `tests/test_v12b_permutation_2l34b.py` — retargeted to CLI integration (dry-run, selector
  wrapper, protection, plan ranking); core-logic tests moved to the 2L.34C file.

**Unchanged:** `scripts/build_v12b_permutation_plan.py` (uses `src.option_grounding`, no
debiaser-core duplication), `scripts/audit_v12b_permutation_candidate.py` (reads the `valid`
field already produced via the core mapper), `final_infer.py`, Docker, production config.

## Public API of `src/mcq_permutation_debiaser.py`

Dataclasses: `OptionPermutation`, `PermutationMapResult`, `PermutationVoteSummary`,
`PermutationOverrideDecision`.
Functions:
- `normalize_option_text(text) -> str` — NFKD fold + casefold + strip punctuation + collapse ws.
- `build_option_permutations(sample, n=6, seed=42) -> list[OptionPermutation]` — original,
  reverse, rotate+1, rotate+2, random_seed1/2 (seed+1/seed+2), deduped; supports labels beyond H.
- `map_permuted_answer_to_original(sample, permutation, selected_label, selected_option_text,
  label_matches_option=None) -> PermutationMapResult` — maps back and validates (out-of-range,
  self-conflict, text-no-match, label/text conflict).
- `validate_permutation_record(record) -> (bool, reason)`.
- `summarize_permutation_votes(qid, current_answer, records) -> PermutationVoteSummary`.
- `select_permutation_override(summary, policy="conservative") -> PermutationOverrideDecision`.

## Which logic moved from scripts → src

| Was (script) | Now (module) |
|---|---|
| `run.make_permutations` + permuted-choice assembly | `build_option_permutations` (richer OptionPermutation) |
| `run.map_back` + `run.option_text_matches` + `run._record_from_parsed` validity | `map_permuted_answer_to_original` (+ `normalize_option_text`) |
| `candidate._valid` + `candidate.decide_override` vote/policy logic | `validate_permutation_record` + `summarize_permutation_votes` + `select_permutation_override` |

## Behavior-preservation summary

The conservative rule is unchanged (≥5 valid, ≥4 same non-current, current ≤1; supporters are
valid by construction so "no supporter mismatch/parse failure" holds). Balanced unchanged
(3/5 or 4/6 with mean supporting confidence ≥0.6). Dry-run records are all invalid (no model
answer) → 0 overrides → candidate identical to v11.

## Dry-run regression summary (Part D)

```
run_v12b … --dry-run   -> records_written: 180, model_calls_made: 0, mode: dry_run
build candidate        -> overrides_applied: 0, changed_vs_v11: 0, validation: PASS
audit candidate        -> changed_vs_v11: 0, identical_to_v11: True, validation: PASS
candidate md5 == v11   -> 69f4e7c990e8c612e7bee53084d13b4d (same: True)
```

## Tests run and results (Part E)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_mcq_permutation_debiaser_2l34c.py tests/test_v12b_permutation_2l34b.py`: **24 passed**
- `pytest -q` (full suite): **655 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Confirmations

- **No API calls** — dry-run only; `model_calls_made = 0`; the core module constructs no client
  (unit-tested: no `SelectiveAPIClient`/`OpenRouterClient`/`requests` in code).
- **Production default unchanged** — `final_infer.py`, Docker, and
  `configs/production_v11_independent.json` untouched (`default_mode=frozen_csv`, v11 best).
- **No outputs/best artifacts overwritten** — v11 md5 still `69f4e7c990e8c612e7bee53084d13b4d`;
  refactor shadow CSV is gitignored (`outputs/*`); `pred.csv` untouched.
- **No qid hardcoding / no ground truth** — module + scripts regex-clean.
- **Not committed.**

## Exact command — real API pilot after refactor (opt-in; needs OPENROUTER_API_KEY + budget)

```bash
.venv/bin/python scripts/build_v12b_permutation_plan.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --v10 outputs/pred_v10_full_production_user_run.csv \
  --decisions scratch/full_v11_independent_rerun1/v11_independent_decisions_repaired.csv \
  --candidates scratch/full_v11_independent_rerun1/v11_independent_candidates.jsonl \
  --output scratch/v12b_option_permutation_api30/permutation_plan.csv

.venv/bin/python scripts/run_v12b_option_permutation.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --plan scratch/v12b_option_permutation_api30/permutation_plan.csv \
  --work-dir scratch/v12b_option_permutation_api30 \
  --model qwen/qwen3.5-9b-20260310 --max-qids 30 --permutations 6 --budget-usd 0.50 --execute
```

## Exact command — build / audit V12B candidate after the pilot

```bash
.venv/bin/python scripts/build_v12b_permutation_candidate.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --permutation-records scratch/v12b_option_permutation_api30/permutation_records.jsonl \
  --output outputs/pred_v12b_permutation_candidate.csv \
  --review-dir scratch/v12b_option_permutation_api30/review --policy conservative

.venv/bin/python scripts/audit_v12b_permutation_candidate.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --candidate outputs/pred_v12b_permutation_candidate.csv \
  --plan scratch/v12b_option_permutation_api30/permutation_plan.csv \
  --permutation-records scratch/v12b_option_permutation_api30/permutation_records.jsonl \
  --output-dir scratch/v12b_option_permutation_api30/audit
```

## Git status

```
?? src/mcq_permutation_debiaser.py
?? scripts/build_v12b_permutation_plan.py
?? scripts/run_v12b_option_permutation.py
?? scripts/build_v12b_permutation_candidate.py
?? scripts/audit_v12b_permutation_candidate.py
?? tests/test_v12b_permutation_2l34b.py
?? tests/test_mcq_permutation_debiaser_2l34c.py
?? docs/audits/AUDIT_PHASE_2L34C_MCQ_PERMUTATION_DEBIASER_SRC_MODULE.md
```
(The V12B scripts were created in 2L.34B *after* commit `92ef1fa`, so all V12B files —
scripts, the new module, and tests — are untracked. `outputs/pred_v12b_*candidate*.csv` and
`scratch/v12b_option_permutation*/` are gitignored.) Nothing committed.
