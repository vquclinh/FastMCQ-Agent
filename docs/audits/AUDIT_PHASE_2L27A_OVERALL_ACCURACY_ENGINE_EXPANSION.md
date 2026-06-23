# Audit — Phase 2L.27A: Overall Accuracy Engine Expansion

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Strengthened option grounding, evidence extraction, domain solvers, and adaptive
planning to broaden overall accuracy beyond v10. Everything is offline/deterministic;
**no API call, no inference, and NOTHING written under `outputs/`** — all artifacts are
under `scratch/accuracy_engine_2l27/`.

## No-output rule confirmation

`outputs/` still contains only the pre-existing `pred.csv`,
`pred_v10_full_production_user_run.csv`, `pred_v8_clean_generalized_from_v7.csv`. This
phase wrote zero files to `outputs/`; both new scripts hard-refuse any non-`scratch/`
output dir (tested).

## Files changed

**New (src)**: `option_grounding.py`, `evidence_pack.py`, `adaptive_accuracy_planner.py`,
`tool_solvers/probability_solver.py`, `tool_solvers/geometry_solver.py`.
**New (scripts)**: `audit_selective_runner_behavior.py`, `build_overall_accuracy_plan.py`.
**New (tests)**: `tests/test_accuracy_engine.py`.
**Modified**: `src/candidate_consistency.py` (`is_candidate_consistent` combined gate),
`src/answer_ranker.py` (uses the combined gate + new deterministic sources),
`src/answer_factory.py` (adds probability/geometry tools),
`src/formula_bank_solver.py` (+`try_monopoly_linear`, `try_hex_decimal`,
`try_subnet_hosts`), `tool_solvers/cs_solver.py` + `finance_econ_solver.py` (wire new rules).

## Option grounding design (`option_grounding.py`)

`extract_option_features` (numeric + key phrases per option); `map_claim_to_option`
maps a numeric OR text claim to a UNIQUE option (declines on ambiguity);
`verify_answer_label_matches_reasoning` rejects a candidate whose selected label
contradicts its own evidence (numeric result must appear in the chosen option; a clean
text mapping must point to the chosen label). Integrated via
`candidate_consistency.is_candidate_consistent` (used by `answer_ranker`, and
transitively by `build_v11_from_api_candidates`).

## Evidence pack design (`evidence_pack.py`)

`build_long_context_evidence_pack` (option-aware snippets), `build_short_knowledge_
evidence_pack` (RAG-lite cards + per-option), `build_calculation_evidence_pack`
(formula-bank result + hints). All return an `EvidencePack` and **never select an
answer**; deterministic, lexical, no API.

## Domain solvers expanded

- `probability_solver` — expected value + independent-events product (declines otherwise).
- `geometry_solver` — pythagorean/circle/triangle + rectangle area/perimeter.
- `formula_bank` — `monopoly_linear_quantity` `q*=(a−c)/2b`, `hex_decimal` (both ways),
  `subnet_usable_hosts` `2^(32−prefix)−2`; wired into `cs_solver`/`finance_econ_solver`.
  All keep Cournot and decline on ambiguity; each has positive + decline tests.

## Adaptive planner design (`adaptive_accuracy_planner.py`)

`score_question_difficulty` (0 if a deterministic tool answers; higher for low-conf /
calc-without-proof / weak long-context / ambiguous / law-admin / parse issues);
`recommend_layers_for_question` → `tool_only | evidence_pack | cheap_api | rich_api |
manual_review` per route; `estimate_calls_for_plan`; `build_adaptive_plan` (prioritizes
hardest API-needing qids, supports a `cheap` budget mode). Plans only — no API.

## Selective runner behavior audit (no API)

`scratch/accuracy_engine_2l27/selective_runner_behavior.{md,csv}` over the existing
163 API candidate records: 4 agents (~41 each), **pairwise_judge did NOT run**
(judge_ran=False — fix before scaling), parse failures 8, placeholder evidence 47,
answer/evidence mismatches 43, **rejected by consistency guard 46**. This validates
that the guard catches real problems before they can become overrides.

## Overall accuracy plan (no API)

`scratch/accuracy_engine_2l27/overall_accuracy_plan.{csv,md}`: 463 questions →
recommended layers **tool_only 18, evidence_pack 129, cheap_api 316**; 18 questions
already have a deterministic tool candidate; total estimated API calls ≈ 632 across all
layers (most are cheap_api @2). No submission written.

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **476 passed** (was 462; +14).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: option grounding map/verify (match/mismatch/ambiguous); evidence packs
  build without selecting answers; probability/geometry/cs(hex,subnet)/finance(monopoly)
  positive + decline; planner tool_only for deterministic + API for hard calc + plan
  build/estimate; scripts refuse `outputs/`; no qid hardcoding.

## Confirmations

- **No OpenRouter/API call**; no inference run.
- **No files written under `outputs/`**; `outputs/pred.csv` and
  `pred_v10_full_production_user_run.csv` untouched. All artifacts under `scratch/`.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed
  model introduced.
- Nothing committed.

## Recommended next phase

Before scaling the selective API to 60/120 qids: **fix the runner so the pairwise
judge actually runs** (audit shows it did not), then re-run the behavior audit. With the
consistency guard now rejecting ~28% of candidates, the API pass will be cleaner. Use
`overall_accuracy_plan.csv` to drive a budget-aware run (cheap_api for the 316
mid-difficulty qids, rich_api for the hardest), feed candidates through the factory +
consistency-guarded ranker, and only build a v11 candidate (NEW file, A/B vs v10) for a
`submit_candidate`/reviewed result. v10 (77.75) remains the submission.

Do not commit until a result is accepted.
