# Audit — Phase 2L.4: Selective MCQ Verifier + Option Elimination

**Date:** 2026-06-21
**Branch:** `main` @ `8824994` (+ uncommitted 2L.4 changes)
**Result:** Added an optional, selective second-pass MCQ verifier (off by default)
and integrated it into the OpenRouter graph. **No OpenRouter API call, no full
inference, no `pred.csv`/v1/v2 overwrite, no leaderboard upload, no commit.**

## 1. Repo state

Branch `main`; recent commits `8824994` (calc+rerank preflight audit), `5aa5f17`
(reranker), `694bf19` (calc solver). Frozen outputs present and **untouched**:
`pred.csv`, `pred_phase2k3_openrouter_full.csv`, `pred_v2_calc_rerank.csv`,
`run_v2_calc_rerank.jsonl`. Both `pred.csv` and `pred_v2_calc_rerank.csv` re-validate **PASS**.

## 2. Files inspected

`src/openrouter_graph_solver.py`, `src/openrouter_client.py`,
`src/openrouter_prompts.py`, `src/structured_answer.py`, `src/confidence.py`,
`src/question_profiler.py`, `src/question_router.py`, `src/calculation_solver.py`,
`src/evidence_reranker.py`, `configs/default.yaml`, `run.py`,
`tests/test_openrouter_graph_solver.py`, and the 2L docs/audits.

## 3. Files created / modified

### Created
- `src/mcq_verifier.py` — `OptionAssessment`, `VerificationResult`,
  `build_verifier_messages`, `verifier_response_format_schema`, `parse_verification`,
  `should_run_verifier`.
- `tests/test_mcq_verifier.py` — 14 tests.
- `docs/MCQ_VERIFIER.md`, `docs/AUDIT_PHASE_2L4_*`.

### Modified
- `src/openrouter_graph_solver.py` — `OpenRouterConfig` verifier fields;
  `_verifier_node` (runs after answer/repair, before finalize); verifier trace
  fields; budget-capped extra call.
- `configs/default.yaml` — nested `mcq_verifier:` block (default `enabled: false`).
- `run.py` — flattens the nested block; `--mcq-verifier` / `--no-mcq-verifier` /
  `--mcq-verifier-threshold`.
- `tests/test_openrouter_graph_solver.py` — 5 verifier integration tests.
- `docs/OPENROUTER_ROUND1_STRATEGY.md` — v3/v4 verifier note.

## 4. Verifier design summary

Structured-JSON second pass: per-option `status` (supported/contradicted/
irrelevant/uncertain) + brief evidence reason, `original_answer_supported`,
`best_answer ∈ labels`, `should_override`, `confidence`, short `rationale`. No
hidden chain-of-thought requested/logged; reasons capped (~120–160 chars). Parser
reuses `structured_answer`'s robust JSON extraction; output validated against the
sample's labels.

## 5. Trigger policy

Runs only when enabled AND route ∈ {long_context, ambiguous, law_admin,
safety_ethics} AND a trigger fires: `partial_answer_key` parse, confidence
< 0.70, repair was used, or a reranked long-context answer. **Never** when a
calculation safe-override produced the answer, when there is no valid original
answer, or when the route is out of scope.

## 6. Config / CLI

Nested `openrouter.mcq_verifier` (enabled, apply_routes,
min_confidence_to_override=0.80, trigger_below_confidence=0.70, trigger_on_*,
max_extra_calls_per_sample=1). CLI `--mcq-verifier` / `--no-mcq-verifier` /
`--mcq-verifier-threshold`. **Default disabled.**

## 7. Graph integration behavior

- Disabled or not triggered → exact prior behavior (0 extra calls).
- Triggered → one extra verifier call (budget-capped via `max_extra_calls`).
- Override applied only if `should_override` AND valid, different label AND
  `confidence >= min_confidence_to_override`; else keep original.
- Verifier call failure / unparseable / invalid label → keep original.
- Calculation safe-override path returns before the verifier (never overridden).

## 8. Tests added/updated

`pytest -q` → **198 passed** (179 prior + 14 verifier unit + 5 graph integration).
Coverage: prompt includes choices + original answer; valid JSON parse; invalid
label rejected; override requires a different valid label; unparseable keeps
original; bounded reasons; trigger on low-confidence/partial-parse; no-trigger for
calc-override / out-of-scope / disabled / no-valid-answer; **no qid/eval in
source**. Graph: disabled = no extra call; triggered low-confidence long-context
override applied; weak-confidence override rejected; invalid verifier output keeps
original; calc-override skips verifier (0 calls); trace fields populated.

## 9. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **198 passed**.
- `validate_submission.py` on `pred.csv` and `pred_v2_calc_rerank.csv` → **PASS**
  (both unchanged). No prediction CSV created/overwritten.

## 10. Dry-run trigger inventory (from `run_v2_calc_rerank.jsonl`, default-on settings)

- total **463**; routes: short_knowledge 190, calculation 159, long_context 100,
  ambiguous 7, law_admin 7.
- would trigger verifier: **102** — by route: long_context **100**, ambiguous **2**.
- reasons: `reranked_long_context` 91, `partial_parse+low_confidence+reranked` 9,
  `partial_parse+low_confidence` 2.
- calc-override samples that skip the verifier: **9**.
- expected **additional** API calls if enabled: **+102** (~22%).
- **Tuning note:** `trigger_on_reranked_long_context` makes every reranked
  long-context trigger; set it false to restrict to low-confidence/partial/repair
  (~11 samples) for a cheaper, more selective pass.

## 11. No-hardcoding interpretation

No qid logic / answer tables / web retrieval / `eval`/`exec` in `mcq_verifier.py`
(asserted by a source-inspection test). The verifier reads only question/evidence
+ choices + the original answer. Generic across unseen private-test questions.

## 12. Confirmations

- **No OpenRouter API call, no full inference, no `pred.csv`/v1/v2 overwrite, no
  leaderboard upload, no commit.**
- `.env`/`.venv`/`outputs`/model dirs untouched; key never read/printed.

## 13. Remaining risks

- A second LLM opinion can also err; mitigated by the 0.80 override threshold
  (overrides only on confident disagreement) and keep-original-on-failure.
- Default-on triggering is broad for long-context (tunable, see §10).
- No ground truth — net accuracy effect is confirmed only by the leaderboard.

## 14. Recommended next step

- **Controlled v3 verifier preflight:** enable on a `--limit 20` slice
  (calc + rerank + verifier), inspect `verifier_*` traces and override rate, then a
  full v3 into a **new** file (e.g. `outputs/pred_v3_verifier.csv`), validated and
  A/B-compared against v1/v2 — **after** the v1 leaderboard score is recorded.
- Alternatively: true local BGE-M3 / Qwen-rerank integration for the reranker.

## 15. Git status (uncommitted)

```
 M configs/default.yaml
 M docs/OPENROUTER_ROUND1_STRATEGY.md
 M run.py
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2L4_SELECTIVE_MCQ_VERIFIER.md
?? docs/MCQ_VERIFIER.md
?? src/mcq_verifier.py
?? tests/test_mcq_verifier.py
```

All changes **uncommitted**, for user review. Frozen outputs unchanged.
