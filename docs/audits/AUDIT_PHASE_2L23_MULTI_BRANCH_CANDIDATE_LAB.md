# Audit — Phase 2L.23: Multi-Branch Candidate Lab + Accuracy Foundations

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Built candidate-comparison tooling and three hidden-test accuracy foundations
(PoT-lite calculator, knowledge-card/RAG-lite retrieval, evidence-grounded override
policy). Ran the no-API analyses: of the two upgrade candidates, **v9 makes 1 low-risk
deterministic change** while the **production rerun makes 19 changes (18 unexplained
model drift)**. No final prediction generated; `outputs/pred.csv` untouched.

## Files changed

**New (foundations)**
- `src/pot_lite.py` — AST-whitelisted safe arithmetic (`safe_eval_arithmetic`) +
  `map_to_option`. Rejects names/calls/imports/attributes/subscripts/lambdas.
- `src/knowledge_cards.py` — 10 general knowledge cards + lexical `retrieve_cards`
  (no answer selection, stopword-filtered).
- `src/evidence_verifier_policy.py` — strict `evaluate_override` policy.

**New (lab scripts)**
- `scripts/analyze_candidate_disagreements.py` — disagreement review CSV.
- `scripts/recommend_submission_candidate.py` — safety-ranked recommendation.

**New (tests)**
- `tests/test_candidate_lab.py` — 19 tests across all foundations + scripts.

(v9 candidate `outputs/pred_v9_formula_bank_from_v8_clean.csv` was regenerated
deterministically from `pred.csv`(=v8_clean); it had been removed by an earlier
cleanup. 1 change, validates PASS.)

## Candidate disagreement summary (vs baseline `pred.csv` = v8_clean)

| candidate | changes | low | medium | high | deterministic-backed | model-drift |
|---|---|---|---|---|---|---|
| `pred_v9_formula_bank_from_v8_clean.csv` | 1 | 1 | 0 | 0 | 1 | 0 |
| `pred_production_user_run.csv` | 19 | 1 | 18 | 0 | 1 | 18 |

- v9's single change = `test_0327` pythagorean_distance D→B (deterministic, low risk).
- production's 19 changes = 1 production_safe_override (matches a safe rule) + **18
  production_model_drift** (medium risk, no deterministic support; e.g. test_0005
  long_context C→A, test_0070 short_knowledge B→C, test_0093 calculation E→F).
- 0 high-risk changes (none contradict a safe deterministic rule).

Output: `outputs/candidate_disagreement_review.csv`.

## Recommendation summary

`scripts/recommend_submission_candidate.py` (safety score = deterministic − drift −
2·high − 0.5·medium):
- v9: safety **+1.0**  → **RECOMMENDED**
- production rerun: safety **−26.0**

> **Submit `pred_v9_formula_bank_from_v8_clean.csv`** as the upgrade candidate (1
> deterministic, low-risk change over the known-75.59 v8_clean; strictly safer than a
> model rerun). Keep `v8_clean`/`pred.csv` as the conservative fallback. **Avoid the
> production rerun** — its 18 unexplained model-drift changes cannot be verified
> offline and could move the score either way.

Output: `outputs/submission_candidate_recommendation.md`.

## PoT-lite foundation

`safe_eval_arithmetic(expr)` parses with `ast` and evaluates ONLY: numbers, `+ - * /
** `, unary ±, parentheses, `sqrt`/`log10`, and `pi`. Everything else (names, calls,
attributes, subscripts, lambdas, imports, `__import__`, `open`, `abs`, ternaries) is
rejected; division-by-zero and oversized powers are guarded. `map_to_option` maps a
numeric result to a unique option (rel-tol + margin) or declines. **Not wired into
production overrides** — foundation only.

## Knowledge-card / RAG-lite foundation

10 general cards (paging logical address; MC vs AVC/ATC; pythagorean distance;
resistor cut parallel; Ohm's law; operating margin / asset turnover; cache AMAT; DB
keys; 1NF/2NF/3NF; elasticity & total revenue) — each with id/domain/trigger_terms/
statement/formula/examples/safety_notes. `retrieve_cards(question, top_k)` is a
deterministic lexical scorer (trigger hits + stopword-filtered token overlap); it
selects NO answer and uses no qid. Irrelevant questions retrieve nothing.

## Evidence-verifier policy

`evaluate_override(proposal)` permits an override ONLY for: (1) deterministic
calculation + unique option; (2) retrieved card support + confidence ≥ 0.90 + unique
option; (3) explicit option elimination + support. It REJECTS internal-knowledge-only,
self-consistency-only, vague rationale, unsupported law/admin, and medium/high-risk
formula hints, and never overrides a no-change/equal answer.

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **410 passed** (was 391; +19).
- Coverage: PoT valid/sqrt/log/pi/reject-code/div-zero/option-map(+decline); cards
  loaded/relevance/deterministic/empty-for-irrelevant; policy accept/reject cases;
  recommender prefers deterministic over drift; no qid hardcoding / no external sheet.

## Confirmations

- **No OpenRouter/API call**; no full inference (all analyses are offline/deterministic).
- **No final prediction generated**; `outputs/pred.csv` not created or overwritten
  (the v9 candidate is a separate file; review/recommendation are diagnostics).
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used.
- `outputs/scratch` not deleted; nothing committed.

## Recommended next submit candidate

Among the three: **`pred_v9_formula_bank_from_v8_clean.csv`** — v8_clean + 1
deterministically-correct geometry fix. It is the safest strict upgrade over the
known-75.59 baseline. `pred_production_user_run.csv` is **not** recommended (18
unverifiable model-drift changes). `v8_clean`/`pred.csv` remains the conservative
fallback if no risk is desired.

## Next step

If an upgrade is wanted, promote v9 to `outputs/pred.csv` via the explicit
archive-first finalization (as in 2L.18) and submit; keep one submission in reserve.
The PoT-lite / knowledge-card / verifier-policy foundations are ready to wire into a
future evidence-grounded override path (behind the strict policy) — not enabled now.
Do not commit until a result is accepted.
