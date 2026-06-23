# Audit — Phase 2L.35A: V13 Multi-Layer Reasoning Stack

**Date:** 2026-06-23  **Branch:** `main`  **Status:** experimental shadow stack (no commit, no API, default unchanged)

## Motivation for the three methods

Three new shadow layers target failure modes that v11/v12B do not address:
1. **Programmatic Solver** — for numeric/formula MCQs, force the model to emit a *structured
   calculation spec* (operation + expression), then **safely** evaluate it (whitelisted AST,
   no arbitrary code) and map the numeric result to a unique option. Removes
   "model did the arithmetic in its head and picked the wrong option."
2. **Content-First Answerer** — ask for the *answer content first* (not a label), then map the
   content back to an option via exact/normalized/numeric matching. Removes "reasoning right,
   label wrong."
3. **Least-to-Most Constraint Table** — decompose multi-condition questions into atomic
   constraints, evaluate every option, and accept only when exactly one option survives.
   Targets "chọn phát biểu đúng/sai", law/admin, pedagogy, psychology, proverbs, multi-condition
   CS/DB questions.

## Files created / changed

**Created (all untracked; nothing committed):**
- `src/programmatic_solver_layer.py`, `src/content_first_answerer.py`,
  `src/least_to_most_constraint_solver.py` — pure deterministic core modules (no API/client).
- `scripts/build_v13_multilayer_plan.py` (D), `scripts/run_v13_multilayer_verifier.py` (E),
  `scripts/build_v13_multilayer_candidate.py` (F), `scripts/audit_v13_multilayer_candidate.py` (G).
- `tests/test_v13_multilayer_2l35a.py` — 18 tests (H).
- `docs/audits/AUDIT_PHASE_2L35A_…md` — this audit.
- `outputs/pred_v13_multilayer_candidate_dryrun.csv` — shadow candidate (**gitignored**;
  byte-identical to v11 in dry-run).

**Changed:** none of the production/default files.

## New src modules and APIs

- **programmatic_solver_layer**: `CalculationSpec`, `ProgrammaticMatchResult`,
  `extract_numeric_values`, `classify_programmatic_domain`, `build_programmatic_prompt`,
  `parse_calculation_spec`, `safe_execute_calculation` (whitelisted AST: + - * / ** % //,
  sqrt/abs/log/exp/min/max/round; rejects names/imports/lambda/assignment),
  `match_result_to_options` (unique numeric option match or reject),
  `validate_programmatic_candidate`.
- **content_first_answerer**: `ContentAnswer`, `ContentOptionMatch`,
  `build_content_first_prompt`, `parse_content_answer`, `normalize_answer_content`,
  `match_content_to_options` (numeric → exact → normalized containment, unique-or-reject),
  `validate_content_first_candidate` (rejects label/content disagreement).
- **least_to_most_constraint_solver**: `Constraint`, `OptionConstraintEvaluation`,
  `ConstraintTableDecision`, `build_ltm_constraint_prompt`, `parse_constraint_table`,
  `validate_constraint_table` (exactly one survivor + contradiction check + valid label),
  `select_answer_from_constraint_table`.

## Unified plan summary (Part I.1)

`build_v13_multilayer_plan.py` → 463 qids, **457 planned**; layer assignments:
`content_first=417, programmatic_solver=301, least_to_most=257` (a qid may get several). Top
targets (score 13.0) are the multi-condition 10-option `direct_fallback`+high-risk+v11≠v10 qids,
which receive all three layers. No answer changed.

## Dry-run verifier summary (Part I.2)

`run_v13_multilayer_verifier.py --max-qids 30 --dry-run`: **candidates_written=87,
model_calls_made=0, mode=dry_run**. Records carry qid, layer, proposed_label,
proposed_option_text, confidence, parse_status, valid, rejection_reason, evidence,
raw_response, current_answer. In dry-run all are `parse_status=dry_run, valid=false`.

## Candidate dry-run summary (Part I.3/I.4)

Selector (conservative, max-overrides 30): **overrides_applied=0, changed_vs_v11=0,
validation=PASS**. Audit: `identical_to_v11=True`, candidate md5
`69f4e7c990e8c612e7bee53084d13b4d` == v11, validation PASS. (With no valid model records, no
rule fires — exactly the safe no-op expected before a real pilot.)

## Unified selector rules (Part F)

Conservative acceptance: (1) programmatic unique deterministic match; (2) content_first ∧
least_to_most agree on the same non-current label; (3) content_first agrees with a v12B stable
mapped vote; (4) least_to_most unique survivor corroborated by another layer. Rejects single
weak source, label/option or numeric mismatch, ambiguous match, parse failure, or a label
invalid for the sample. Output protection refuses frozen best / v10 / v8 / pred.csv; final CSV
fully validated (qid set, labels, no dup/missing).

## Tests and model-policy result (Part H)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_v13_multilayer_2l35a.py`: **18 passed**
- `pytest -q` (full suite): **673 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Confirmations

- **Production default unchanged** — `final_infer.py`, Docker, and
  `configs/production_v11_independent.json` untouched (unit-tested: frozen_csv + v11 best).
- **No API calls** — dry-run only; `model_calls_made = 0`; clients constructed only under
  `--execute` and guarded by `assert_allowed_llm_model`.
- **No outputs/best artifacts overwritten** — v11 md5 still `69f4e7c990e8c612e7bee53084d13b4d`;
  v10 / pred.csv untouched; shadow candidate gitignored (`outputs/*`).
- **No qid hardcoding / no ground truth / no external 3-LLM sheet** — modules + scripts regex-clean.
- **Safe executor** — programmatic layer evaluates only a whitelisted arithmetic AST; unsafe
  expressions (imports, lambda, names, assignment) are rejected (unit-tested).
- **Not committed.**

## Exact command — real API pilot (opt-in; needs OPENROUTER_API_KEY + budget)

```bash
.venv/bin/python scripts/build_v13_multilayer_plan.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --v10 outputs/pred_v10_full_production_user_run.csv \
  --decisions scratch/full_v11_independent_rerun1/v11_independent_decisions_repaired.csv \
  --candidates scratch/full_v11_independent_rerun1/v11_independent_candidates.jsonl \
  --v12b-records scratch/v12b_option_permutation_api30/permutation_records.jsonl \
  --output scratch/v13_multilayer_api/v13_multilayer_plan.csv

.venv/bin/python scripts/run_v13_multilayer_verifier.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --plan scratch/v13_multilayer_api/v13_multilayer_plan.csv --work-dir scratch/v13_multilayer_api \
  --model qwen/qwen3.5-9b-20260310 --max-qids 30 --budget-usd 0.50 --execute
```

## Exact command — build / audit V13 candidate after the pilot

```bash
.venv/bin/python scripts/build_v13_multilayer_candidate.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --candidates scratch/v13_multilayer_api/v13_multilayer_candidates.jsonl \
  --v12b-records scratch/v12b_option_permutation_api30/permutation_records.jsonl \
  --output outputs/pred_v13_multilayer_candidate.csv \
  --review-dir scratch/v13_multilayer_api/review --policy conservative --max-overrides 30

.venv/bin/python scripts/audit_v13_multilayer_candidate.py \
  --input public-test_1780368312.json --current outputs/pred_v11_independent_rerun1.csv \
  --candidate outputs/pred_v13_multilayer_candidate.csv \
  --candidates scratch/v13_multilayer_api/v13_multilayer_candidates.jsonl \
  --output-dir scratch/v13_multilayer_api/audit
```
(The shadow candidate is evaluation-only; it is **not** wired into `final_infer.py` and must
beat v11 on evidence before any future promotion.)

## Git status

```
?? src/programmatic_solver_layer.py
?? src/content_first_answerer.py
?? src/least_to_most_constraint_solver.py
?? scripts/build_v13_multilayer_plan.py
?? scripts/run_v13_multilayer_verifier.py
?? scripts/build_v13_multilayer_candidate.py
?? scripts/audit_v13_multilayer_candidate.py
?? tests/test_v13_multilayer_2l35a.py
?? docs/audits/AUDIT_PHASE_2L35A_V13_MULTILAYER_REASONING_STACK.md
```
(`outputs/pred_v13_multilayer_candidate_dryrun.csv` and `scratch/v13_multilayer/` are
gitignored.) Nothing committed.
