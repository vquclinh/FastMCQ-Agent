# Audit — Phase 2L.15C: Short-Knowledge Selective Verifier

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added a **conservative, gated, OFF-by-default** short_knowledge verifier branch to
the adaptive orchestrator, plus a no-API candidate audit and a dry-run-default
controlled runner. **No API call was made. No answer was changed.** The verifier
targets only flagged short_knowledge items and never touches other routes.

## Files changed

**New**
- `scripts/audit_short_knowledge_verifier_candidates.py` — no-API eligibility audit.
- `scripts/run_short_knowledge_verifier_sample.py` — controlled runner, **dry-run by
  default** (OpenRouter client lazily imported only under `--execute`).
- `docs/AUDIT_PHASE_2L15C_SHORT_KNOWLEDGE_SELECTIVE_VERIFIER.md` (this file).

**Modified**
- `src/adaptive_orchestrator.py` — `AdaptiveConfig` gains `sk_allow_override`,
  `sk_trigger_confidence_max`, `sk_max_verifier_calls`, `sk_require_strong_confidence`
  (+ `from_dict`); `analyze()` computes SK verifier **eligibility only** (no candidate,
  no API, no override) and records it in `extra`.
- `src/adaptive_routing.py` — `sk_verifier_eligibility(sample, route, state,
  trigger_confidence_max)`.
- `configs/adaptive_reasoning.yaml` — `short_knowledge_verifier` block.
- `tests/test_adaptive_orchestrator.py` — +7 SK tests.

## Config added

```yaml
adaptive_reasoning:
  enabled: true
  mode: "assist"
  short_knowledge_verifier:
    enabled: false            # OFF by default
    allow_override: false     # never changes an answer until explicitly enabled
    trigger_confidence_max: 0.95
    max_verifier_calls: 0     # 0 = dry-run only (no API)
    require_strong_confidence: true
```

Default `adaptive_reasoning` remains OFF / `trace_only`.

## Trigger rules (short_knowledge only)

Eligible iff `route == short_knowledge` AND the current answer is valid AND ≥1 of:
`confidence <= trigger_confidence_max` (`confidence_below_max`),
`domain_admin_or_policy`, `answer_has_uncertain_reasoning`. When any fires,
`verifier_recommended` is added. Calculation / long_context / law_admin / ambiguous
are **never** triggered in this phase.

## Override gate (applied only under `--execute` + `allow_override`)

`should_override` AND `selected_answer` valid AND `!= current` AND
`confidence >= 0.90` AND `reason` non-empty AND `evidence_type != "uncertain"` AND
`allow_override == true`. The verifier prompt forbids using any external answer sheet
and returns strict JSON (`selected_answer`, `should_override`, `confidence`, `reason`,
`evidence_type`).

## Candidate counts (`audit_short_knowledge_verifier_candidates.py`, no API)

```
total samples            : 463
short_knowledge count    : 190
verifier-eligible        : 121
trigger reasons          : confidence_below_max 107, domain_admin_or_policy 25,
                           verifier_recommended 121
eligible ∩ first-100 P0/P1: 11   (captures all 11 short_knowledge P0/P1 risk rows)
would_override rows      : 0
```
Output: `outputs/short_knowledge_verifier_candidates.csv` (gitignored diagnostic).

121/190 are eligible because most v6b short_knowledge answers carry confidence ≈ 0.9
(≤ the 0.95 default). A real controlled run would bound work via `max_verifier_calls`
and could lower `trigger_confidence_max`; the eligibility set already covers the
high-value first-100 P0/P1 cluster (11/11).

## Validation results

- `compileall -q src scripts tests`: OK
- `pytest -q`: **284 passed** (was 277; +7).
- Dry-run runner executed (`--max-calls 5`): planned 5 items, **no API call**, no
  answer changed; wrote `outputs/short_knowledge_verifier_sample_dryrun.{jsonl,csv}`.

## Whether any API call was made

**No.** The candidate audit and the runner (default dry-run) made zero OpenRouter
calls. The OpenRouter client is imported lazily and only constructed under
`--execute` with `--max-calls > 0` (a user-initiated action not taken here).

## Confirmations

- No answer changes: SK branch computes eligibility only; `would_override == 0`;
  predictions untouched.
- No qid hardcoding; no public-test answer table.
- External Gemini/GPT/Claude sheet is **diagnostic only** — never read by the
  verifier/orchestrator code; the candidate audit only counts overlap with the
  first-100 P0/P1 risk CSV.
- `outputs/pred.csv` and v1/v2/v6/v6b/v7 prediction/log files untouched; new scripts
  refuse to write protected files; diagnostics are gitignored.
- No leaderboard upload; `.env` not read; no API key exposed.

## Recommended next command (controlled SK verifier sample — DO NOT run unless asked)

```bash
# Small, user-initiated controlled run (calls OpenRouter; gated override):
.venv/bin/python scripts/run_short_knowledge_verifier_sample.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --max-calls 5 --allow-override --execute \
  --output-jsonl outputs/short_knowledge_verifier_sample.jsonl \
  --output-csv outputs/short_knowledge_verifier_sample.csv
```
Review the JSONL, confirm the override gate behaves, then scale up cautiously and
A/B a v8 against v7 — no leaderboard claim without validation. Leave the default
config OFF.

## git status

```
 M .gitignore
 M docs/CALCULATION_TAXONOMY.md        (2L.15B correction, still uncommitted)
 M run.py
 M src/calculation_solver.py
 M src/openrouter_graph_solver.py
 M tests/test_calculation_solver.py
?? configs/adaptive_reasoning.yaml
?? docs/ADAPTIVE_REASONING_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md
?? docs/AUDIT_PHASE_2L14A_P0P1_REVIEW_PACK.md
?? docs/AUDIT_PHASE_2L14B_CALCULATION_FORMULA_EXPANSION.md
?? docs/AUDIT_PHASE_2L15A_ADAPTIVE_REASONING_ORCHESTRATOR.md
?? docs/AUDIT_PHASE_2L15B_PROGRAMMATIC_ASSIST_MODE.md
?? docs/AUDIT_PHASE_2L15C_SHORT_KNOWLEDGE_SELECTIVE_VERIFIER.md
?? scripts/apply_programmatic_assist_to_predictions.py
?? scripts/audit_adaptive_orchestrator_trace.py
?? scripts/audit_calculation_solver_on_public.py
?? scripts/audit_first100_consensus_risks.py
?? scripts/audit_short_knowledge_verifier_candidates.py
?? scripts/compare_v7_programmatic_assist_pseudo.py
?? scripts/export_risk_review_pack.py
?? scripts/run_short_knowledge_verifier_sample.py
?? src/adaptive_orchestrator.py … (2L.15A modules) + src/formula_cards/
?? tests/test_adaptive_orchestrator.py
```
(`outputs/*` diagnostics and `scratch/*` are gitignored.)

Do not commit. All changes left uncommitted for user review.
