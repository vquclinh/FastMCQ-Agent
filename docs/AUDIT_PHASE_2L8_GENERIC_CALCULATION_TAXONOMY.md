# Audit — Phase 2L.8: Generic Calculation Taxonomy Expansion

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Goal

Improve accuracy on **unseen private-test** questions by adding generic deterministic
formula families to `src/calculation_solver.py` — keyed on generic wording + numbers
+ formulas, never on public-test qids or memorized answers. The solver overrides the
LLM only when the formula match is unambiguous and the chosen label is a clear
winner; otherwise it defers. **Prefer no answer over a risky answer.**

## Repo state

Working tree was clean at start (2L.6/2L.7 already committed as `c92e766`). Changes
from this phase (`git status --short`):

```
 M docs/CALCULATION_SOLVER.md
 M src/calculation_solver.py
 M tests/test_calculation_solver.py
 M tests/test_openrouter_graph_solver.py
?? docs/CALCULATION_TAXONOMY.md
?? scripts/inventory_calculation_families.py
```

Frozen outputs untouched: `outputs/pred.csv`, `outputs/pred_v2_calc_rerank.csv`
(both still validate PASS).

## Files inspected

`src/calculation_solver.py`, `src/openrouter_graph_solver.py`,
`src/question_router.py`, `src/question_profiler.py`, `src/labels.py`,
`configs/default.yaml`, `run.py`, `tests/test_calculation_solver.py`,
`tests/test_openrouter_graph_solver.py`, `docs/CALCULATION_SOLVER.md`.

## Files created / modified

- **M** `src/calculation_solver.py` — added `_first_int` helper and 9 families:
  `try_kepler`, `try_relativistic_gamma`, `try_money_multiplier`,
  `try_t_statistic`, `try_acid_base_volume`, `try_supply_demand`,
  `try_cobb_douglas_isoquant`, `try_modular_arithmetic` (8 implemented; polynomial
  substitution intentionally declined). Registered in `_FAMILIES`
  (exact-result families ordered before nearest-numeric ones).
- **M** `tests/test_calculation_solver.py` — 27 new synthetic tests.
- **M** `tests/test_openrouter_graph_solver.py` — 1 new test (new family bypasses LLM).
- **M** `docs/CALCULATION_SOLVER.md` — new families table, modular safety note,
  route-interaction limitation, reranker/verifier interaction, inventory script,
  v5 guidance.
- **A** `docs/CALCULATION_TAXONOMY.md` — full taxonomy, declined families + reasons,
  extraction examples, route consideration, safety invariants, future candidates.
- **A** `scripts/inventory_calculation_families.py` — read-only diagnostic inventory.

## Families implemented (8)

| Family | Domain | Formula | Match |
|---|---|---|---|
| kepler_third_law | astronomy | `T'=T·k^(3/2)` (or ratio `k^(3/2)`) | nearest |
| relativistic_gamma | physics | `γ=1/√(1−β²)` (β from `0,6c`/`%`/`lần c`) | nearest |
| money_multiplier | economics | `m=1/rr` | nearest |
| t_statistic | statistics | `(x̄−μ₀)/(s/√n)` | nearest |
| acid_base_neutralization | chemistry | `V_b=(M_a·V_a)/M_b` (1:1) | nearest |
| supply_demand_gap | economics | shortage `Qd−Qs` / surplus `Qs−Qd` at controlled P | nearest |
| cobb_douglas_isoquant | economics | unique `(K,L)` with `A√(KL)=Q` | exact |
| modular_arithmetic | number theory | `pow(base,exp,n)` / `a%n` (integers only) | exact |

## Families intentionally declined / not implemented

- **Polynomial / function substitution** (`g(x)=f(x−a)`, coefficient extraction):
  safe (no-`eval`) parsing of arbitrary polynomials + substitution is fragile; a
  wrong override is worse than deferring. Declined.
- **pH / titration / buffer (Henderson–Hasselbalch)**: multi-branch weak-acid logic
  is error-prone; only the clean 1:1 neutralization-volume case is implemented.
- **General Cobb-Douglas `K^aL^b` optimisation**: needs exponent + price parsing +
  constrained optimisation; only the robust `√(KL)` isoquant case is implemented.
- **Free-form arithmetic via `eval`**: forbidden by design; modular uses integer
  `pow`/`%` on parsed integers only.

## Safety / margin policy

- Every family sets `formula_family` + `extracted_values`; symbolic/exact matches
  score `0.99`, nearest-numeric `0.96`. `safe_to_override` requires
  `confidence ≥ calc_min_confidence` (default 0.95).
- Nearest-numeric families use `_nearest_label` (relative-tolerance + a clear margin
  vs the second-nearest); exact families require a single matching label.
- Ambiguity (e.g. two `(K,L)` pairs hitting the same Q; a shortage requested when
  `Qd≤Qs`; missing extracted value) → `matched=False`, no override.
- Output is always a label from the sample's choices, never option text or an
  out-of-range label. A matcher exception is caught and treated as no-match.

## Tests added/updated

- Calc solver: **27** new tests — ≥2 positive + ≥1 decline per new family, a
  no-qid-effect test for the new families, and a network/`eval`/`open`-free
  source-inspection test. Existing no-qid/no-`eval` source tests still pass.
- Graph: **1** new test — a new family (money multiplier) produces a safe override
  with **0 API calls** (LLM bypassed); existing tests confirm disabled→LLM,
  no-match→LLM, and trace fields preserved.
- Full suite: **233 passed** (was 206). `compileall` OK.

## Dry-run inventory (diagnostic only; no CSV, no network, no labels)

`scripts/inventory_calculation_families.py --input public-test_1780368312.json`:

- total samples 463; **matched 12** (was 9 before expansion); **safe overrides 12**,
  unsafe/declined **0**.
- by method: price_elasticity 2, cylinder 2, relativistic_gamma **2 (new)**,
  exponential_decay 1, gdp_inflation 1, hess_law 1, resistor 1,
  money_multiplier **1 (new)**, sphere 1.
- new families with **0** public matches (private-test generalization):
  kepler, t_statistic, acid_base, supply_demand, cobb_douglas, modular.
- **Deterministic-only vs v2:** would change exactly **2** qids — `test_0037`
  (gamma, v2 `H`→`F`) and `test_0055` (money, v2 `A`→`B`); the other 10 already
  agree with v2. No correctness claim — leaderboard decides.
- **Route check:** all 12 safe matches route to `calculation`/`ambiguous`, so none
  are blocked by the calc-node gate on the public set.

## Validation results

- `compileall -q src tests scripts`: **OK**
- `pytest -q`: **233 passed**
- `validate_submission.py` on `outputs/pred.csv`: **PASS**
- `validate_submission.py` on `outputs/pred_v2_calc_rerank.csv`: **PASS**
- `outputs/pred_v3a_verifier_selective.csv`: not present (only a smoke subset exists).

## No-hardcoding grep interpretation

`grep -nE "if qid|qid ==|\.get\(['\"]qid|eval\(|exec\(|__import__|test_0[0-9]{3}|import requests|urllib|socket|httpx" src/calculation_solver.py` → **CLEAN (none found)**. The
solver reads only `question` + `choices`; no qid drives any decision; no public-test
answer table; no dynamic code execution; no network imports. `test_0xxx` strings
appear only in *test files* (as synthetic-equivalence fixtures), never in `src/`.

## Confirmations

- No OpenRouter API call made.
- No full public inference run.
- No `outputs/pred.csv` / v1 / v2 / v3 / v4 created or overwritten.
- No leaderboard upload.
- No `OPENROUTER_API_KEY` printed/logged; `.env` not read.
- No model downloaded; no dependency installed.
- No qids hardcoded; no public-test answers; no answer tables; no ground truth used
  (the inventory reports patterns only).

## Remaining risks

- No ground truth → net accuracy of the new families is unverified; the 2 changed
  qids vs v2 are *likely* improvements (exact formulas) but only the leaderboard
  confirms.
- Regex extraction is phrasing-sensitive; unusual private phrasings may not match
  (safe — they simply defer to the LLM).
- **Route gap (latent):** a prose-phrased private physics/stat formula question
  could route to `short_knowledge` and miss the override (no public instance). The
  optional `calc_apply_routes` widening (documented, not enabled) would close it but
  needs A/B validation first.

## Recommended next step

1. **Controlled v5 calc-taxonomy preflight/run** into a **new** file
   (`outputs/pred_v5_calc_taxonomy.csv` / `outputs/run_v5_calc_taxonomy.jsonl`),
   user-run manually, then validate + A/B-diff vs v1/v2 (expect ≈2 deterministic
   changes plus any from re-routing). Do not overwrite v1/v2/v3/v4.
2. Optionally evaluate enabling `calc_apply_routes` to include `short_knowledge`
   (A/B first) to capture under-routed formula questions on the private test.
3. Neural reranker remains deferred until a local model + dep are staged (Phase 2L.7).

Do not commit. All changes left uncommitted for user review.
