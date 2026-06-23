# Audit — Phase 2L.1C: Calculation Solver Docs Consistency Cleanup

**Date:** 2026-06-21
**Branch:** `main` @ `88e6760`
**Type:** Documentation-only cleanup before committing Phase 2L.1 / 2L.1B.
**No API call, no inference, no output/`pred.csv` modification, no commit.**

## 1. Files inspected

`docs/CALCULATION_SOLVER.md`,
`docs/AUDIT_PHASE_2L1B_GENERIC_CALCULATION_SOLVER_HARDENING.md`,
`src/openrouter_graph_solver.py` (the `_calculation_node` route gate).

## 2. Documentation inconsistencies found

In `docs/CALCULATION_SOLVER.md`:

1. **Contradictory route claim.** The "Integration" section correctly stated the
   calc node runs on `calculation` **and** `ambiguous`, but the "Limitations"
   section still said *"Duplicate-choice questions route to `ambiguous`, so the
   override won't apply there (e.g. the resistor sample)"* — the **old** behavior,
   contradicting the code (`s["route"] in ("calculation", "ambiguous")`) and the
   2L.1B audit.
2. **Stale coverage numbers.** "matches **7 samples** … would **change 3**" and
   "(96/159 … left to the LLM)" predate the 2L.1B expansion (GDP + sphere added),
   which raised the match count to **9** and the v1 differences to **4**.

## 3. What was fixed

- Rewrote the Limitations bullet: duplicate-choice numeric questions **are now
  covered** via the `ambiguous` route; added that safety holds because a family
  must match a real formula pattern and only overrides when `safe_to_override`
  (non-numeric ambiguous text is never touched); and added an explicit
  conservative rule for **equally valid duplicate labels** — override only when the
  selected label is the unique closest/exact match, else no override.
- Updated coverage figures to **9 matches / 4 changes** (elasticity/cylinder/GDP)
  and replaced the stale `96/159` with an accurate "≈9/463 match; the rest,
  including most of the 159 calculation-route questions, go to the LLM."
- Broadened "elasticity/cylinder" to "elasticity/cylinder/sphere/GDP" in the
  nearest-match limitation note.

The doc is now consistent with the code and the 2L.1B audit.

## 4. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **164 passed**.
- `validate_submission.py --submission outputs/pred.csv` → **PASS** (unchanged).

## 5. 2K.4 audit tracking status

`git ls-files docs/AUDIT_PHASE_2K4_SYSTEM_OVERVIEW_AND_ACCURACY_ROADMAP.md`
returns the path and it does **not** appear in `git status` → it is **tracked /
already committed** (not untracked). No action needed.

## 6. Confirmations

- **No OpenRouter API call.** **No inference.** **No `pred.csv`/output modified.**
- Only `docs/CALCULATION_SOLVER.md` changed in this phase (plus this audit).
- `.env`/`.venv`/`outputs`/model dirs untouched.

## 7. Git status (uncommitted)

```
 M configs/default.yaml
 M docs/CALCULATION_SOLVER.md
 M run.py
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2L1B_GENERIC_CALCULATION_SOLVER_HARDENING.md
?? docs/AUDIT_PHASE_2L1C_CALC_DOCS_CONSISTENCY.md
?? docs/AUDIT_PHASE_2L1_CALCULATION_SOLVER.md
?? docs/CALCULATION_SOLVER.md
?? src/calculation_solver.py
?? tests/test_calculation_solver.py
```

(Note: `docs/CALCULATION_SOLVER.md` is new/untracked, so it shows under `??`, not
`M`; listed above for clarity.)

## 8. Recommended commit command for the user

```bash
git add src/calculation_solver.py \
        src/openrouter_graph_solver.py \
        configs/default.yaml run.py \
        tests/test_calculation_solver.py tests/test_openrouter_graph_solver.py \
        docs/CALCULATION_SOLVER.md \
        docs/AUDIT_PHASE_2L1_CALCULATION_SOLVER.md \
        docs/AUDIT_PHASE_2L1B_GENERIC_CALCULATION_SOLVER_HARDENING.md \
        docs/AUDIT_PHASE_2L1C_CALC_DOCS_CONSISTENCY.md
git status --short            # confirm no .venv/ or outputs/ staged
git commit -m "Add deterministic calculation solver (PAL-lite) for calculation route"
```

Leave `outputs/`, `.env`, `.venv/` unstaged. Do not commit `pred.csv` changes
(there are none).
