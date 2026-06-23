# Audit — Phase 2L.28B: Calculation-First Adaptive Fix

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

The 20-question cheap pilot failed the full-run gate (0 overrides, placeholder_rate 0.59,
24 placeholder + 10 mismatch rejections). Root-caused the failures and made the
**calculation route tool-first** with a **compact, numerically-grounded calculation
agent**, route-aware cheap-mode routing, and two new deterministic solvers. **No API, no
inference, nothing under `outputs/`** — all artifacts under `scratch/adaptive_pilot_2l28b/`.
v10 (77.75) remains the locked submission; full adaptive run NOT executed.

## Pilot failure analysis (read-only; `scripts/analyze_pilot_failures.py`)

Over the 41 executed pilot candidates (20 qids, all calculation):

| failure mode (per-qid primary) | count |
|---|---|
| placeholder_evidence | 10 |
| truncation (no-JSON ≥900 tokens) | 5 |
| numeric_mismatch | 5 |

Empty-evidence by agent: **option_elimination 20/20** (its JSON schema has no `evidence`
field, so every record is a placeholder), challenger 3/20, judge 1/1.

**Diagnosis (bottleneck = prompt + runner, not ranker):**
1. **Truncation** — long calculation explanations overflowed `max_tokens=768` → invalid
   JSON (all 5 no-JSON records were 1090–1307 tokens).
2. **Placeholder flood** — `option_elimination` (no evidence field) was a primary cheap
   agent, so 20/20 of its records were placeholders.
3. **Numeric mismatch** — agents stated a number not present in the chosen option.
The consistency guard correctly rejected all of these, but the *candidates* were weak —
so the fix is on candidate generation, not the ranker.

## Calculation-first planner (`src/calculation_first_planner.py`)

- `detect_calculation_subtype` → arithmetic / algebra / probability / geometry / physics /
  finance_econ / cs_numeric / unknown (keyword cues, most-specific-first).
- `recommend_calculation_strategy` → `tool_only` (deterministic solver maps to a unique
  option), `tool_then_llm` (subtype known but solver declined), `compact_llm` (unknown).
- `build_calculation_tool_context` / `format_tool_context_for_prompt` → compact formula
  hints + per-option numeric map + parsed numbers + solver decline reason. Never selects
  an answer; deterministic; no API.

**Integration:** `adaptive_accuracy_planner.recommend_layers_for_question` now consults the
calc strategy for the calculation branch (tool_only when a unique solver hits);
`run_adaptive_selective_api` builds the tool context and uses the calc agent first;
`run_adaptive_pilot` inherits this via delegation.

## Calculation agent + parser (`src/api_candidate_agents.py`)

`build_calculation_solver` — short system prompt, strict JSON only, fields `final_answer,
final_numeric_value, chosen_option_text, calculation_steps (≤4), evidence, confidence,
risk`; explicitly forbids long explanations, placeholder evidence, picking an option that
lacks `final_numeric_value`, and low/medium risk on a non-unique numeric mapping. Designed
for `max_tokens=384`.

`parse_calculation_candidate` rejects (with explicit `parse_status`): `no_valid_label`,
`missing_steps` (low/medium risk), `placeholder_evidence`, `numeric_mismatch`
(`final_numeric_value` doesn't map to the chosen option), `option_text_mismatch`
(`chosen_option_text` maps to a different label). Self-declared high-risk answers pass
through (they won't override).

## Cheap-mode routing changes (`run_adaptive_selective_api.py`)

`_agents_temps_for(layer, route)` is now route-aware:
- **calculation + cheap_api** → `calculation_solver` only (temp 0), `max_tokens=384`, with
  a single `option_elimination` **fallback** run only if the calc agent yields no usable
  candidate or conflicts with v10.
- **non-calculation + cheap_api** → unchanged (`challenger` + `option_elimination`).
- **calculation + rich_api** → `calculation_solver` + challenger + option_elimination.
- Pairwise judge unchanged: only on a valid conflicting candidate.
This cuts the empty-evidence `option_elimination`-as-primary placeholders and the
truncation failures (compact agent + small token budget).

## New deterministic solvers (`src/formula_bank_solver.py`)

Added two conservative, qid-free generic solvers (each declines on ambiguity, maps to a
**unique** close option, provides proof, has positive + decline tests):
- `try_percent_change` — single percent increase/decrease of one base value (requires one
  base + one percent + a clear direction; declines on multiple bases / no percent).
- `try_simple_linear_equation` — solves `ax + b = c` for x against numeric options
  (declines when no explicit equation is present).
Both registered early in `_NEW_RULES`. Existing Cournot/monopoly/hex/subnet rules
unchanged.

## Dry-run summary (no API)

```
analyze_pilot_failures.py  -> qids=20  modes={placeholder:10, truncation:5, mismatch:5}
                              empty_evidence={option_elimination:20, challenger:3, judge:1}
run_adaptive_pilot.py --mode cheap --budget-usd 0.30 --dry-run
  -> scheduled 20 [cheap_api]; upper-bound 60 calls (20 × [calc_solver + fallback + judge])
     est $0.12; budget 0.30
```

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **516 passed** (was 500; +16 in `tests/test_calc_first_2l28b.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: subtype detection (all classes); strategy tool_only/tool_then_llm/compact_llm;
  tool-context shape; calc agent builder compact; parser ok/numeric_mismatch/missing_steps/
  placeholder/high-risk-pass; percent-change + linear-equation positive & decline; runner
  route-aware agent selection; calc upper-bound includes fallback; analyzer classifies
  truncation & refuses `outputs/`.

## Files changed

**New (src):** `calculation_first_planner.py`.
**New (scripts):** `analyze_pilot_failures.py`.
**New (tests):** `tests/test_calc_first_2l28b.py` (+16).
**Modified:** `src/api_candidate_agents.py` (calc agent + parser; AGENTS tuple),
`src/formula_bank_solver.py` (+`try_percent_change`, `try_simple_linear_equation`),
`src/adaptive_accuracy_planner.py` (calc-first hook),
`scripts/run_adaptive_selective_api.py` (route-aware agents, calc tool context, calc
fallback, `_CALC_MAX_TOKENS=384`).

## Confirmations

- **No OpenRouter/API call**; no inference run (analysis read existing pilot records;
  pilot re-run was dry-run only).
- **No files written under `outputs/`**; `pred.csv` and v10 untouched. All artifacts under
  `scratch/adaptive_pilot_2l28b/`.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Recommended next human command (pilot rerun)

Re-run the calculation-first pilot with execute (small budget), then rebuild the decision
report and re-check the gate recommendation:

```bash
.venv/bin/python scripts/run_adaptive_pilot.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --v10-log scratch/v10_full_production/run_v10_full_production_user_run.jsonl \
  --pilot-qids scratch/adaptive_pilot_2l28/pilot_qids.csv \
  --output-dir scratch/adaptive_pilot_2l28b \
  --mode cheap --model qwen/qwen3.5-9b-20260310 --budget-usd 0.30 --execute --resume

.venv/bin/python scripts/build_pilot_decision_report.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --pilot-qids scratch/adaptive_pilot_2l28/pilot_qids.csv \
  --pilot-candidates scratch/adaptive_pilot_2l28b/pilot_api_candidates.jsonl \
  --output-dir scratch/adaptive_pilot_2l28b
```

Expect: fewer placeholder candidates (no empty-evidence option_elimination as primary),
fewer truncations (compact calc agent @384 tokens), fewer numeric mismatches (numeric-
grounded parser). If the gate then reads `proceed_full_run`, proceed to the full adaptive
run + full candidate builder (Phase 2L.28A commands 4–5). v10 remains the submission until
a result is accepted. Do not commit until then.
