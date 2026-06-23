# Audit — Phase 2L.25: High-Accuracy Multi-Agent Answer Factory Skeleton

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Built a controlled multi-candidate answer-factory architecture for the next jump
beyond v10 (public 77.75): a candidate object model, five domain tool solvers, a
RAG-lite knowledge-card layer, a candidate factory (with no-op API stubs), an
evidence-grounded ranker that keeps v10 unless clearly beaten, and offline analysis
scripts. **No API call, no full inference, no final prediction; v10 and `pred.csv`
untouched.** The offline v11 generator proposes **0 overrides** to v10 (the safe,
honest outcome) after a `safe_math` misfire was caught and fixed.

## Files changed

**New (foundations / src)**
- `src/candidate_answer.py` — `AnswerCandidate`, `CandidatePool` (add/dedup/votes/sources).
- `src/tool_solvers/` — `__init__` helper + `safe_math_solver`, `stats_solver`,
  `finance_econ_solver`, `cs_solver`, `physics_solver`.
- `src/rag_lite.py` — `retrieve_cards_for_question` / `retrieve_cards_per_option` / `best_card`.
- `src/answer_factory.py` — `build_candidate_pool` + 3 API-agent STUBS (return None).
- `src/answer_ranker.py` — `score_candidate`, `select_answer` (conservative policy).
- `src/knowledge_cards.py` — **+10 general cards** (subnet, Big-O, kinematics, KE/PE,
  wave, probability/EV, mean/median/mode, break-even, ROI/profit, civic-general);
  retrieval threshold raised so incidental overlap retrieves nothing.

**New (scripts)**
- `scripts/analyze_v10_geography.py`, `scripts/build_v11_answer_factory_proposals.py`,
  `scripts/plan_selective_multicandidate_api.py`.

**New (other)**
- `experiments/best_candidate_manifest.json` (v10 locked), `tests/test_answer_factory.py`
  (+ minor updates to `tests/test_candidate_lab.py` for the expanded card set).

## Method inspiration

Multi-candidate, tool-augmented, RAG/card-supported, verifier-ranked MCQ answering:
many independent solvers propose candidates; deterministic proofs and multi-tool
agreement rank highest; raw LLM/self-consistency confidence ranks weakest; the base
(v10) is the anchor and is only overridden by strong, evidence-grounded signals.

## v10 locked best manifest

`experiments/best_candidate_manifest.json`: candidate `v10_full_production`,
`outputs/pred_v10_full_production_user_run.csv`, public **77.75**, preset
`competition_qwen35_9b`, md5 `c12e32fdf16ee5472e6a791c1e52e86a`, 463 rows,
`do_not_overwrite: true`. The CSV was not altered.

## Tool solvers added

Each returns an `AnswerCandidate` (risk=low, with proof) or declines, delegating to
already-tested rules:
- `safe_math` — bare-arithmetic via `pot_lite.safe_eval_arithmetic` (+ generic numeric).
- `stats` — mean/median/mode, range, expected value.
- `finance_econ` — ROI, profit, margin, asset turnover, break-even, elasticity, GDP,
  depreciation, MC-vs-avg, money multiplier.
- `cs` — binary/decimal, cache AMAT/hit-rate, Big-O, paging.
- `physics` — kinematics, KE/PE, Ohm/power, wave, density, pressure, pythagorean,
  capacitor/resistor, relativistic, related-rates.

## RAG-lite / card expansion

`knowledge_cards` now holds **20 general cards** (CS/DB/networking, economics/finance,
physics, probability/statistics, civic-general). `rag_lite` does deterministic lexical
retrieval per-question and per-option, with embedding/rerank hooks reserved (off,
fail-closed). Retrieval selects no answer; the factory only adds a card-backed
candidate when exactly one card maps uniquely to one option (rare, medium risk).

## Answer factory architecture

`build_candidate_pool(sample, base_answer, base_record)` gathers candidates from:
v10 base, formula bank, concept solver, the five tool solvers, and card/RAG-lite — then
deduplicates. Future API agents (`direct_route_prompt_agent_stub`,
`self_consistency_agent_stub`, `pairwise_judge_agent_stub`) are present but **return
None** (no network this phase).

## Ranker policy

Keep v10 unless beaten. A deterministic proof with a unique option (and no
deterministic proof supporting the base) overrides; deterministic candidates must
agree among themselves; a candidate contradicting a base-supporting proof is rejected;
card-only / medium-risk / raw-LLM-confidence never overrides alone.

## Misfire caught & fixed

The first v11 run proposed 2 overrides, both **`safe_math` misfires**: it grabbed a
date `24/1/2016` (computed 24) from a long-context weather question and polynomial
coefficients `2+3` (computed 5) from a physics word problem. The expression extractor
was hardened: reject embedded dates and long-context markers, cap question length, and
require the expression to be essentially the whole question (≤3 residual content
words) with exactly one unambiguous match. After the fix both correctly decline and
real bare arithmetic still fires.

## v11 proposal count & sources

After the fix: **0 proposed overrides** vs v10 across 463 questions. The factory's
deterministic tools either agree with v10 or decline — so there is no safe, evidence-
grounded change to make offline. (Artifacts in `scratch/answer_factory_2l25/`:
`answer_factory_candidates.jsonl`, `answer_factory_proposals.csv` (empty),
`answer_factory_review.md`.)

## V10 geography summary (no API)

463 questions → risk buckets: short_knowledge 188, calculation 146, long_context 100,
deterministic_safe 17, law_admin 6, ambiguous 6.
(`scratch/answer_factory_2l25/v10_geography.csv` + `_summary.md`.)

## Selective API plan summary (no API)

447/463 flagged; **120 selected** (cap). Dominant signals among the selected:
`calculation_no_tool_proof` and `no_safe_deterministic_candidate` (calc-route
questions the deterministic bank can't prove → highest value for a future
multi-candidate API pass). (`scratch/answer_factory_2l25/selective_api_plan.csv` + `.md`.)

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **424 passed** (was 411; +13).
- Coverage: candidate pool dedup/votes; each tool solver positive + decline; safe_math
  rejects dates/word-problems; RAG-lite retrieval; factory builds without API; stubs
  return None; ranker overrides only on deterministic proof and keeps base otherwise
  (incl. contradiction-with-proof); scripts refuse non-`scratch/` output; no qid
  hardcoding / no external sheet.

## Confirmations

- **No OpenRouter/API call**; no full inference (all offline/deterministic).
- **No final prediction generated**; `outputs/pred.csv` and
  `outputs/pred_v10_full_production_user_run.csv` untouched; v11 wrote only to scratch.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used.
- Only competition-compliant components (Qwen3.5-9B base, BGE-M3/Qwen-rerank hooks);
  no disallowed model introduced.
- `outputs/scratch` not deleted; nothing committed.

## git status (new this phase)

```
?? experiments/best_candidate_manifest.json
?? src/candidate_answer.py, src/answer_factory.py, src/answer_ranker.py, src/rag_lite.py
?? src/tool_solvers/ (5 modules + __init__)
?? scripts/analyze_v10_geography.py, build_v11_answer_factory_proposals.py,
   plan_selective_multicandidate_api.py
?? tests/test_answer_factory.py
?? docs/AUDIT_PHASE_2L25_HIGH_ACCURACY_ANSWER_FACTORY.md
 M src/knowledge_cards.py, tests/test_candidate_lab.py
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*`, `scratch/*` are
gitignored, so the analysis artifacts are untracked.)

## Recommended next phase

**Selective multi-candidate API execution**: for the 120 planned qids, run a small,
gated API pass (route prompts + self-consistency + pairwise judge) to produce
*additional* candidates, feed them into the same factory + ranker, and emit
proposals (still proposal-only, evidence-grounded, no auto-override beyond the strict
policy). Only after reviewing those proposals consider a v11 build into a NEW file,
A/B vs v10. Until then, v10 remains the submission and v9/v8_clean the fallbacks.

Do not commit until a result is accepted.
