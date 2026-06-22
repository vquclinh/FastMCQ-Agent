# Audit — Phase 2L.19: Generalized Formula/Concept Bank v9

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added a clean, qid-free **formula/concept bank** layer that delegates to the existing
deterministic solvers and adds new generalized rules (electricity, waves, geometry,
linear algebra, transforms, probability, CS, extra economics). Generated **v9** from
v8_clean: it changes **exactly 1 answer**, a verified-correct geometry fix, and
validates PASS. `outputs/pred.csv` was NOT modified.

## Files changed

**New**
- `src/formula_bank_solver.py` — `solve_formula_bank_sample` + `FormulaBankResult`;
  delegates to `calculation_solver` + `concept_solver`, then 14 new generalized rules.
- `scripts/apply_formula_bank_to_predictions.py` — v8_clean → v9 patcher with
  protected-file guard and `--max-expected-changes` stop.
- `tests/test_formula_bank_solver.py` — 20 rule + safety tests.
- `docs/AUDIT_PHASE_2L19_FORMULA_BANK_V9.md` (this file).

## Formula / concept rules

Delegated (already in v8_clean, idempotent): `resistor_cut_parallel`,
`relativistic_momentum`, `operating_margin_asset_turnover`, `supply_demand*`,
`paging_logical_address`, `mc_vs_avc`, and all `calculation_solver` families.

New generalized rules added here (each with synthetic tests):
`ohms_law`, `electric_power`, `resistor_series_parallel_basic`,
`wave_speed_frequency_wavelength`, `pythagorean_distance`, `determinant_2x2`,
`matrix_vector_multiply`, `laplace_polynomial`, `basic_probability_expected_value`,
`mc_vs_average_cost` (AVC/ATC-aware), `elasticity_revenue_direction`,
`tax_supply_shift_basic`, `cache_hit_rate`, `time_complexity_nested_loops`.

Each fires ONLY on clear detection + extractable facts + a unique safe option match,
else declines (prefer no answer over a risky one).

## Misfire caught and fixed during calibration

The first v9 run produced **2** changes; one was a **misfire**: a power-matching
question (24V battery, 6Ω fixed + variable resistor adjusted to equal power; answer
6Ω) was wrongly treated by `resistor_series_parallel_basic` as a series-sum (12Ω). It
contained "nối tiếp" and two "6Ω" tokens. **Fix:** the rule now requires the question
to explicitly ask for the *equivalent* resistance ("tương đương"/"equivalent"/
"tổng trở") and declines when "biến trở/biến đổi/công suất/variable/power" appears.
After the fix, that question correctly declines (keeps v8_clean's 6Ω), leaving **1**
change. A regression test (`test_resistor_power_matching_does_not_fire`) locks this in.

(Also fixed a parser bug: matrix/determinant now use integer-token parsing so
`[[1,2],[3,4]]` is read as entries 1,2,3,4 — not the comma-decimal `1.2, 3.4`.)

## Tests run and results

- `compileall -q src scripts tests`: OK
- `pytest -q`: **337 passed** (was 317; +20).
- Tests cover every implemented rule (positive), decline/ambiguity cases, the
  power-matching no-misfire guard, the apply script's protected-output refusal, the
  `--max-expected-changes` stop, and source safety.

## No qid hardcoding / no external sheet / no API (proof)

`grep -nE "qid ==|test_0[0-9]{3}|\.env|OPENROUTER_API_KEY|first100_external|OpenRouterClient"`
over `src/formula_bank_solver.py` and `scripts/apply_formula_bank_to_predictions.py`
→ **none**. A source-inspection test enforces it (the only `"qid"` occurrences are
CSV column names, not qid-value comparisons). No OpenRouter import; `.env` not read;
external 3-LLM sheet never referenced.

## v9 generation command

```bash
.venv/bin/python scripts/apply_formula_bank_to_predictions.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v8_clean_generalized_from_v7.csv \
  --output outputs/pred_v9_formula_bank_from_v8_clean.csv \
  --log-path outputs/run_v9_formula_bank_from_v8_clean.jsonl \
  --diff outputs/pred_v9_formula_bank_diff.csv \
  --max-expected-changes 10
```

## Validation result

`validate_submission.py … pred_v9_formula_bank_from_v8_clean.csv` → **PASS** (463 rows).

## v9 diff vs v8_clean (changes by rule)

`pythagorean_distance`: **1**.

| qid | rule | old (v8_clean) | new (v9) | reason |
|---|---|---|---|---|
| test_0327 | `pythagorean_distance` | D (190.53) | **B (180.28)** | drone altitude 100 m, horizontal 150 m → straight distance √(100²+150²)=180.28 m |

This is a **mathematically verified** correction (180.28 is the unique correct
straight-line distance; v8_clean's D=190.53 is wrong). No ground truth is claimed —
but the geometry is unambiguous.

## Recommendation

- **`outputs/pred_v9_formula_bank_from_v8_clean.csv`** is a **safe upgrade candidate**:
  it equals v8_clean plus one deterministically-correct geometry fix, produced by a
  generalized qid-free rule, validated PASS. Recommended for submission as the new
  best.
- `outputs/pred.csv` (= v8_clean, score 75.59) is unchanged and remains the
  conservative fallback. Per this phase's rule, `pred.csv` was NOT overwritten;
  promoting v9 to `pred.csv` is a separate, explicit finalization step (as done for
  v8 in 2L.18) to be taken only if v9 is accepted.

## git status (this phase)

```
?? src/formula_bank_solver.py
?? scripts/apply_formula_bank_to_predictions.py
?? tests/test_formula_bank_solver.py
?? docs/AUDIT_PHASE_2L19_FORMULA_BANK_V9.md
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*` and `scratch/*`
are gitignored, so the v9 prediction/diff/log are untracked.)

## Next step

Decide whether to submit **v9** (one verified geometry fix over v8_clean). If the
leaderboard confirms ≥ 75.59, finalize by copying v9 → `outputs/pred.csv` (archive
first, as in 2L.18) and commit the accepted code/docs/audits. Do not commit now.
