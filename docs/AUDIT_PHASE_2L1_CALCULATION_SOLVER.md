# Audit — Phase 2L.1: Deterministic Calculation / PAL-lite Module

**Date:** 2026-06-21
**Branch:** `main` @ `88e6760` (+ uncommitted 2L.1 changes)
**Result:** Added a deterministic calculation helper and integrated it
conservatively into the `openrouter_graph` calculation route (override + skip LLM
when a high-confidence family matches). **No OpenRouter API call, no full
inference, no `pred.csv` change, no leaderboard upload, no commit.**

## 1. Repo state

Branch `main`; latest commit `88e6760 add system overview and accuracy roadmap`.
`outputs/pred.csv` and `outputs/pred_phase2k3_openrouter_full.csv` present and
**untouched** (pred.csv re-validated PASS). Priority honored: correctness first.

## 2. Files inspected

`src/openrouter_graph_solver.py`, `src/openrouter_prompts.py`,
`src/structured_answer.py`, `src/question_profiler.py`, `src/question_router.py`,
`src/confidence.py`, `src/solver_factory.py`, `run.py`, `configs/default.yaml`,
`docs/OPENROUTER_ROUND1_STRATEGY.md`, `docs/AUDIT_PHASE_2K4_*`, the tests dir, and
`public-test_1780368312.json` (for pattern design only — **no qid hardcoding**).

## 3. Files created / modified

### Created
- `src/calculation_solver.py` — `CalculationResult` + `solve_calculation_sample`.
- `tests/test_calculation_solver.py` — 11 unit tests.
- `docs/CALCULATION_SOLVER.md` — families, override policy, limitations.
- `docs/AUDIT_PHASE_2L1_CALCULATION_SOLVER.md` — this audit.

### Modified
- `src/openrouter_graph_solver.py` — `OpenRouterConfig` calc fields; `_calculation_node`
  (calculation route only; safe override skips the LLM); calc trace fields.
- `configs/default.yaml` — `calc_enabled/override_when_safe/min_confidence` (`openrouter:`).
- `run.py` — `--calculation-solver` / `--no-calculation-solver`.
- `tests/test_openrouter_graph_solver.py` — 4 integration tests (override 0 calls,
  disabled→LLM, no-match→LLM, metadata logged).

## 4. Formulas implemented

`exponential_decay` (X0·e^{-kt}), `hess_law` (ΔH1+ΔH2), `cylinder_rate`
((dV/dt)/(πr²)), `price_elasticity_midpoint` (arc elasticity; signed or |E|),
`expected_distinct` (k(1-(1-1/k)^n)), `resistor_cut_parallel` (R/4 ⇒ I'=4I). All
return a label only; never a label outside the choices; no `eval`/exec/network.

## 5. Integration behavior

`openrouter_graph` runs the calc node after routing, **only on the calculation
route**. If a family is `safe_to_override` (confidence ≥ `calc_min_confidence`,
default 0.95) and `calc_override_when_safe` is on, it sets the answer and **skips
the LLM (0 API calls)**. Otherwise the normal OpenRouter path runs. Calc metadata
is logged per sample; disabling (`--no-calculation-solver`) restores old behavior.

## 6. Tests added/updated

`pytest -q` → **156 passed** (141 prior + 11 calc unit + 4 graph integration).
Unit tests cover all 6 families, ambiguous→no-match, never-out-of-range label,
duplicate/ambiguous-choice safety, and Vietnamese signed/positive elasticity.
Integration tests confirm: safe override = **0 client calls**; disabled and
no-match = normal LLM path; calc metadata present in the trace.

## 7. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **156 passed**.
- `validate_submission.py --submission outputs/pred.csv` → **PASS** (unchanged).
- No new prediction CSV created.

## 8. Dry-run match statistics (public set, no CSV written)

- total samples: **463**; calculation-routed: **159**.
- calc solver **matched: 7** (all `safe_to_override`).
- on the calculation route: **6** (the 7th, the resistor sample, routes
  `ambiguous` due to duplicate choices, so the graph override would not fire there).
- method distribution: elasticity 2, cylinder 2, decay 1, Hess 1, resistor 1.

### Matched qids + proposed labels (no ground-truth claim)

| qid | method | proposed | v1 (pred.csv) | changes v1? |
|---|---|---|---|---|
| test_0002 | price_elasticity_midpoint | B | C | **yes** |
| test_0006 | exponential_decay | A | A | no |
| test_0009 | cylinder_rate | C | A | **yes** |
| test_0013 | cylinder_rate | A | B | **yes** |
| test_0016 | hess_law | A | A | no |
| test_0021 | resistor_cut_parallel | E | E | no (route=ambiguous; not overridden) |
| test_0406 | price_elasticity_midpoint | B | B | no |

**3 of 7 would change vs v1** — all elasticity/cylinder cases the formulas compute
exactly (e.g. cylinder `dh/dt=0.6366→0.6`, `0.2546→0.25`; midpoint `|E|=1.0`). These
are the buckets flagged as likely LLM errors in the 2K.4 overview. *No ground
truth exists*; correctness of these labels is asserted from the formulas, to be
confirmed by the leaderboard.

## 9. Confirmations

- **No OpenRouter API call**, **no full inference**, **no `pred.csv` overwrite**
  (re-validated identical/PASS), **no leaderboard upload**, **no commit**.
- **No API key** read/printed; `.env`/`.venv`/`outputs`/model dirs untouched.
- **No qid-specific logic**; patterns are generic regex/formula matchers.

## 10. Remaining risks

- Small family set (matches ~7/463); most calculation samples still rely on the LLM.
- No ground truth — the 3 proposed changes are *likely* fixes, not certified.
- Regex extraction is phrasing-sensitive (esp. elasticity); deliberately fails
  closed (no override) when unsure.
- Nearest-numeric tolerance could in principle mis-snap; guarded by a margin
  requirement and small relative-error bound.

## 11. Recommended next phase

1. **Phase 2L.1-run (controlled v2):** regenerate the full CSV with the chosen
   OpenRouter config **plus** the calculation override (≈6 deterministic answers,
   LLM for the rest) into a **new** file (e.g. `outputs/pred_v2_calc.csv`) —
   **only after the v1 score is recorded** so v2 is measured against a baseline.
2. Or proceed to **long-context reranking (Phase 2L.0)** next.

Either way, record the v1 leaderboard score in `experiments/leaderboard_log.csv`
first, then treat v2 (with calc override) as the next measured iteration.

## 12. Git status (uncommitted)

```
 M configs/default.yaml
 M run.py
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2K4_SYSTEM_OVERVIEW_AND_ACCURACY_ROADMAP.md
?? docs/AUDIT_PHASE_2L1_CALCULATION_SOLVER.md
?? docs/CALCULATION_SOLVER.md
?? src/calculation_solver.py
?? tests/test_calculation_solver.py
```

All changes **uncommitted**, for user review. `pred.csv` unchanged.
