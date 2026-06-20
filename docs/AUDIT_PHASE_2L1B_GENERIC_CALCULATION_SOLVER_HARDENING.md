# Audit — Phase 2L.1B: Generic Calculation Solver Hardening + Coverage Expansion

**Date:** 2026-06-21
**Branch:** `main` @ `88e6760` (+ uncommitted 2L.1 / 2L.1B changes)
**Result:** Audited the calculation solver for hardcoding (clean), refactored it
into a generic `try_*` formula-family registry, and expanded coverage. **No
OpenRouter API call, no full inference, no `pred.csv` change, no leaderboard
upload, no commit.** Priority honored: correctness/generalization first.

## 1. Repo state

Branch `main` @ `88e6760`. `outputs/pred.csv` present and **untouched**
(re-validated PASS). The Phase 2L.1 changes were still uncommitted; 2L.1B builds
on them.

## 2. Files inspected

`src/calculation_solver.py`, `tests/test_calculation_solver.py`,
`src/openrouter_graph_solver.py`, `tests/test_openrouter_graph_solver.py`,
`configs/default.yaml`, `run.py`, `docs/CALCULATION_SOLVER.md`,
`docs/AUDIT_PHASE_2L1_CALCULATION_SOLVER.md`, `src/question_profiler.py`,
`src/question_router.py`, `public-test_1780368312.json` (pattern inventory only).

## 3. Hardcoding audit result

- `grep` for `test_[0-9]{4}` / `answer_key` / `gold` / `ground_truth` / `qid ==`
  in `src/` → **no public qids, no answer tables, no qid-equality logic**. (The
  only `answer_key` hit is the generic JSON-parser function `_recover_answer_key`
  in `structured_answer.py`.)
- `eval(` / `exec(` / `__import__` / `compile(` → none (only `re.compile`).
- `src/calculation_solver.py` reads only `question` + `choices`; the two textual
  occurrences of "qid" are docstring prose stating that no qid is used. A test now
  asserts there is **no qid access** in the source and **no unsafe eval/exec**.

**Conclusion:** the solver was already generic; no hardcoding to remove.

## 4. Files created / modified

### Created (2L.1, carried) / modified now
- `src/calculation_solver.py` — **rewritten** as a generic `try_*` family registry;
  `CalculationResult` gained `formula_family` + `extracted_values`; added generic
  numeric/expression utilities (Vietnamese comma decimals, signed numbers,
  percentages, π-coefficient matching, nearest-with-margin, exact-symbolic).
- `src/openrouter_graph_solver.py` — calc node now runs on **`calculation` and
  `ambiguous`** routes (safe override only).
- `tests/test_calculation_solver.py` — expanded to **19 tests**.
- `tests/test_openrouter_graph_solver.py` — calc integration tests (4).
- `configs/default.yaml`, `run.py` — calc config + CLI (from 2L.1).
- `docs/CALCULATION_SOLVER.md` — generic-approach + no-hardcoding + all families.
- `docs/AUDIT_PHASE_2L1B_...md` — this audit.

## 5. Formula families added / improved

- **Added:** `exponential_growth` (dX/dt=kX→e^{kt}); `sphere_rate`
  (dV/dt=4πr²·dr/dt, π-coefficient matching); `gdp_inflation`
  (deflator=nom/real·100, inflation vs prev deflator).
- **Generalized:** `hess_law` now sums 2–3 sequential ΔH steps; elasticity
  extraction is position-based and handles signed/positive choices + Vietnamese
  comma decimals; numeric helpers are shared and unit-tolerant (LaTeX `\,`,
  `\text{}`).
- **Kept:** `exponential_decay`, `cylinder_rate`, `price_elasticity_midpoint`,
  `expected_distinct`, `resistor_cut_parallel`.

All return a label only, never out-of-range, and refuse borderline/ambiguous
matches (nearest-numeric requires a clear margin + small relative error).

## 6. Route integration decision

**Option B chosen:** run the calc node on the **`calculation` AND `ambiguous`**
routes. Justification: duplicate-choice numeric questions (e.g. the resistor item)
route to `ambiguous`; running the solver there recovers them. It is safe because a
family only matches genuine formula patterns and only overrides when
`safe_to_override=True`, so non-numeric `ambiguous` text never gets overridden.
Non-calculation text questions are never touched.

## 7. Tests added/updated

`pytest -q` → **164 passed**. New coverage: all 9 families; exponential growth;
multi-step Hess; GDP/inflation; sphere (π choices); Vietnamese signed/positive
elasticity; comma-decimal + percent parsing; ambiguous-nearest → no override;
duplicate/ambiguous-choice safety; never out-of-range label; **no-qid-effect**
(same content under different qids incl. a public-looking one → identical result);
**source has no qid usage and no unsafe eval/exec**; `extracted_values` recorded;
graph integration (safe override = 0 calls, disabled→LLM, no-match→LLM, metadata logged).

## 8. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **164 passed**.
- `validate_submission.py --submission outputs/pred.csv` → **PASS** (unchanged).
- No prediction CSV created or overwritten.

## 9. Dry-run inventory (public set; diagnostic only, no CSV written)

- total **463**; routes: short_knowledge 190, calculation 159, long_context 100,
  ambiguous 7, law_admin 7.
- calc solver **matched: 9** (all `safe_to_override`):
  - methods: elasticity 2, cylinder 2, decay 1, hess 1, gdp_inflation 1, sphere 1,
    resistor 1.
  - would override in-graph (calculation+ambiguous & safe): **9**.
  - **differ from current `pred.csv` (v1): 4** — the elasticity/cylinder/GDP cases.

Matched qids (diagnostic, **not** hardcoded; produced by generic families):

| qid | method | label | route |
|---|---|---|---|
| test_0002 | price_elasticity_midpoint | B | calculation |
| test_0006 | exponential_decay | A | calculation |
| test_0008 | gdp_inflation | B | calculation |
| test_0009 | cylinder_rate | C | calculation |
| test_0013 | cylinder_rate | A | calculation |
| test_0016 | hess_law | A | calculation |
| test_0021 | resistor_cut_parallel | E | ambiguous |
| test_0312 | sphere_rate | A | calculation |
| test_0406 | price_elasticity_midpoint | B | calculation |

No ground-truth accuracy is claimed; these are the deterministic formula outputs.

## 10. Confirmations

- **No OpenRouter API call, no full inference, no `pred.csv` overwrite** (PASS,
  unchanged), **no leaderboard upload**, **no commit**.
- **No qid logic, no public-test answer table, no `eval`/`exec`.**
- `.env`/`.venv`/`outputs`/model dirs untouched; key never read/printed.

## 11. Remaining risks

- Regex extraction is phrasing-sensitive; deliberately fails closed (no override)
  when unsure — so the main risk is *missing* a solvable question, not answering wrong.
- Nearest-numeric families (cylinder/sphere/elasticity/GDP) could in principle
  mis-snap; guarded by a margin requirement + small relative tolerance.
- No ground truth — the 4 deviations from v1 are *likely* corrections, confirmed
  only by the leaderboard.
- Coverage is still small (9/463) by design; the LLM handles the rest.

## 12. Recommended next phase

1. **Controlled v2 generation** (after the v1 score is recorded): chosen
   OpenRouter config **+ calculation override**, written to a **new** file (e.g.
   `outputs/pred_v2_calc.csv`) and validated — measured against the v1 baseline.
2. Or proceed to **long-context reranking (Phase 2L.0)**.

## 13. Git status (uncommitted)

```
 M configs/default.yaml
 M run.py
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2K4_SYSTEM_OVERVIEW_AND_ACCURACY_ROADMAP.md
?? docs/AUDIT_PHASE_2L1_CALCULATION_SOLVER.md
?? docs/AUDIT_PHASE_2L1B_GENERIC_CALCULATION_SOLVER_HARDENING.md
?? docs/CALCULATION_SOLVER.md
?? src/calculation_solver.py
?? tests/test_calculation_solver.py
```

All changes **uncommitted**, for user review. `pred.csv` unchanged.
