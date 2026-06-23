# Audit — Phase 2L.15A: Adaptive Reasoning Orchestrator Architecture

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added an additive, **trace-only** adaptive reasoning orchestrator that covers the
whole MCQ pipeline (5 branches), with a Formula Registry/Cards layer and clean hooks
for Phases 2L.15B–E. It is **OFF by default**; when enabled it only logs an
`adaptive` diagnostics object and **never** changes a final answer, makes an extra
API call, or overwrites a prediction. **v6b remains the stable fallback.**

## Files changed

**New**
- `src/adaptive_types.py` — `FormulaCard`, `BranchCandidate`, `AdaptiveTrace`.
- `src/formula_cards/__init__.py` — 11 metadata cards (gamma/momentum disambiguation).
- `src/formula_registry.py` — metadata-only eligibility (`eligible_formula_ids`).
- `src/adaptive_routing.py` — route→branch map + per-branch risk flags.
- `src/programmatic_solver.py` — non-binding calculation candidate hook.
- `src/adaptive_orchestrator.py` — `AdaptiveConfig`, `AdaptiveOrchestrator`.
- `configs/adaptive_reasoning.yaml` — overlay config (OFF, trace_only).
- `scripts/audit_adaptive_orchestrator_trace.py` — trace-only public audit.
- `docs/ADAPTIVE_REASONING_ARCHITECTURE.md`, this audit, + tests.

**Modified**
- `src/openrouter_graph_solver.py` — `adaptive_reasoning_enabled` / `_mode` config;
  `_adaptive_node` invoked from `_emit` (covers all return paths) — attaches
  `s["adaptive"]` only when enabled and re-asserts the answer is unchanged.
- `run.py` — `--adaptive-reasoning` flag + nested `adaptive_reasoning` flattening.

## Architecture decisions

- **Global, not calculation-only:** branches for calculation / long_context /
  short_knowledge / law_admin / ambiguous, because 2L.13 risk spans all routes.
- **Trace-only by default:** answers come from v6b; the orchestrator is read-only.
- **Metadata Formula Registry:** cards describe *how* to solve (triggers, variables,
  intents, executor name) — not answers. Executors stay in `calculation_solver.py`.
- **Relativity disambiguation encoded in metadata:** `relativistic_gamma` eligible
  only when γ is asked (and excluded on momentum/energy); `relativistic_momentum`
  eligible only for momentum. Verified disjoint.
- **Single integration seam** (`_emit` → `_adaptive_node`) keeps coupling minimal and
  guarantees the answer-preservation invariant on every path (incl. calc-override
  early return and the exception path).

## What changed / what did NOT change

- Changed: an optional, default-off diagnostics object + new modules + CLI/config.
- **Did NOT change:** any final answer, the calculation override behavior, the
  reranker, the verifier, prediction CSVs, or trace schema when disabled (no
  `adaptive` key appears unless enabled — backward compatible).

## Validation results

- `compileall -q src scripts tests`: OK
- `pytest -q`: **271 passed** (was 260; +11 adaptive tests).
- Tests cover: config default OFF; trace-only never overrides; registry loads all 11
  ids; gamma vs momentum eligibility disjoint; legal/admin count not deterministically
  overridden; short_knowledge `verifier_recommended` is a trace flag only (no API);
  enabling adaptive does not change the answer or add API calls; long_context answer
  unchanged on/off; disabled → no `adaptive` key; no qid/network/eval in source.

## Trace audit results (`scripts/audit_adaptive_orchestrator_trace.py`, no API)

```
total samples 463
route/branch distribution: long_context 100, calculation 159, short_knowledge 190,
  ambiguous 7, law_admin 7  (matches v6b routing)
risk flags: evidence_check_pending 100, domain_admin_or_policy 31,
  verifier_recommended 32, needs_adjudication 7, source_grounding_recommended 7
formula-card metadata eligibility (loose triggers; executors decline most):
  linear_total_equation 76, cobb_douglas_isoquant_scaling 37, relativistic_momentum 14,
  t_statistic_one_sample 12, accrued_simple_interest 9, supply_demand_price_control 5,
  henderson_hasselbalch_buffer 5, operating_margin_asset_turnover 3,
  nuclear_binding_energy_release 2, relativistic_gamma 1
rows where a candidate WOULD change the answer (informational): 2
would_override rows (MUST be 0 in trace_only): 0   ✓
unexpected branch selections: 0
predictions changed: 0 (no prediction file written)
```
The 2 "candidate would change" rows are the deterministic finds from 2L.14B
(physically/mathematically correct on test_0085/test_0099) — informational only;
trace-only applies nothing.

## Confirmations

- No OpenRouter API call made; no full inference run.
- No qid hardcoding; no public-test answer table; no `eval`/`exec`/network in the new
  modules (asserted by a source-inspection test).
- External Gemini/GPT/Claude sheet **not** used as ground truth anywhere.
- `outputs/pred.csv` and v1/v2/v6/v6b predictions/logs untouched; the only new
  `outputs/` artifact is the gitignored diagnostic CSV.
- No leaderboard upload; `.env` not read; no API key exposed; model files untouched.

## git status

```
 M .gitignore                       # pre-existing (scratch/ ignore)
 M docs/CALCULATION_TAXONOMY.md     # 2L.14B (still uncommitted)
 M run.py
 M src/calculation_solver.py        # 2L.14B
 M src/openrouter_graph_solver.py
 M tests/test_calculation_solver.py # 2L.14B
?? configs/adaptive_reasoning.yaml
?? docs/ADAPTIVE_REASONING_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md
?? docs/AUDIT_PHASE_2L14A_P0P1_REVIEW_PACK.md
?? docs/AUDIT_PHASE_2L14B_CALCULATION_FORMULA_EXPANSION.md
?? docs/AUDIT_PHASE_2L15A_ADAPTIVE_REASONING_ORCHESTRATOR.md
?? scripts/audit_adaptive_orchestrator_trace.py
?? scripts/audit_calculation_solver_on_public.py
?? scripts/audit_first100_consensus_risks.py
?? scripts/export_risk_review_pack.py
?? src/adaptive_orchestrator.py
?? src/adaptive_routing.py
?? src/adaptive_types.py
?? src/formula_cards/
?? src/formula_registry.py
?? src/programmatic_solver.py
?? tests/test_adaptive_orchestrator.py
```
(`outputs/*` diagnostics and `scratch/*` are gitignored.)

## Recommended next step

**Phase 2L.15B — Programmatic Formula Executors:** bind the formula cards to the
`calculation_solver` executors, expand the extract→execute→match→gate hooks, and
enable gated overrides in an `assist` mode — validated by re-running the trace audit
and an A/B of a controlled v7/v8 run vs v6b. No leaderboard claim without validation.

Do not commit. All changes left uncommitted for user review.
