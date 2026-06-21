# Audit — Phase 2L.14B: Calculation Formula Expansion + Relativity Bug Fix

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Fixed the `relativistic_gamma` over-match and added 10 generic, conservative
calculation families informed by the 2L.14A risk pack. All families fire only when
extraction is unambiguous and option matching has a clear margin; otherwise they
defer to the LLM. No qids, no answer tables, no external answers in code.

## Repo state / files changed

```
 M .gitignore                         # (pre-existing user change: ignore scratch/)
 M docs/CALCULATION_TAXONOMY.md
 M src/calculation_solver.py
 M tests/test_calculation_solver.py
?? scripts/audit_calculation_solver_on_public.py
?? docs/AUDIT_PHASE_2L14B_CALCULATION_FORMULA_EXPANSION.md
(plus still-untracked 2L.13/2L.14A scripts & docs)
```

## Families added / modified

**Modified**
- `relativistic_gamma` — now fires **only** when γ is the asked quantity
  ("hệ số Lorentz" / "hệ số giãn nở thời gian" / …) and **declines** if the question
  asks for "động lượng"/"năng lượng"/"động năng". Fixes the 2L.13 bug where it
  answered γ for a momentum question.

**Added (10)**
- `relativistic_momentum` — `p = γβ·m₀c`, options as multiples of `m₀c`.
- `cobb_douglas_isoquant_scaling` — `Q=A·K^a·L^b` at `(K0,L0)` × fraction → pick `(K,L)`.
- `t_statistic_one_sample` — t-test with **interval** options (`< 1.0`, `1.0 đến 1.5`, …).
- `z_score_one_sample` — `z=(x̄−μ₀)/(σ/√n)`; requires **population** σ to fire.
- `supply_demand_price_control` — general linear `Qd/Qs` incl. P-first `cP−d`; shortage/surplus.
- `henderson_hasselbalch_buffer` — `pH=pKa+log10([base]/[acid])` (decimal comma OK).
- `linear_total_equation` — ≥2 linear eqs summed to a total → `y=(T−ΣC)/ΣK`.
- `nuclear_binding_energy_release` — `ΔE=A·Δ(BE/nucleon)` MeV.
- `accrued_simple_interest` — `I=P·r·(months/12)` between two dates (VN thousands-safe).
- `operating_margin_asset_turnover` — margin=(gross−opex)/sales; turnover=sales/assets; combined option.

Helpers added: `_to_amount` (VN thousands grouping), `_first_amount`, `_parse_interval`,
`_parse_linear_in_P`, `_m0c_coeff`, `_abs_nearest_label`, `_extract_mean_test`,
`_relativistic_beta`, `_asks_gamma`. Public API (`solve_calculation_sample`,
`CalculationResult`) unchanged; prior safe families unchanged.

## Legal/admin handled correctly (NOT a formula)

Per the brief, no public-test-specific numeric rule was added for legal/admin count
questions ("Theo Luật … có bao nhiêu nguyên tắc…"). A test
(`test_legal_admin_count_not_formula_overridden`) asserts the solver does **not**
fire on such a question; they stay LLM/verifier territory.

## Tests added

14 synthetic, qid-free tests: gamma-still-fires-when-γ-asked; gamma-does-not-fire-for-
momentum; momentum=0.75m₀c; cobb-douglas half-output; t interval; z numeric; supply
price-control shortage; Henderson-Hasselbalch (decimal comma); linear total y=0;
nuclear BE release; accrued interest Jul→Dec; operating margin+turnover combined;
legal/admin no-fire; new-families no-qid-effect. **No real model/data required.**

## Validation results

- `compileall -q src tests scripts`: OK
- `pytest -q`: **260 passed** (was 247; +13).
- No-hardcoding grep on `src/calculation_solver.py`: CLEAN (no `test_0xxx`, no
  `if qid`, no `eval`/`exec`, no `gemini/claude/chatgpt/external`).

## Deterministic public audit (`scripts/audit_calculation_solver_on_public.py`)

```
total samples 463; matched 13 (v6b: 12); safe overrides 13
method dist: price_elasticity 2, cylinder 2, exponential_decay 1, gdp 1, hess 1,
  resistor 1, relativistic_gamma 1, money_multiplier 1, relativistic_momentum 1,
  operating_margin_asset_turnover 1, sphere 1
route of matches: {calculation: 12, ambiguous: 1}
matches on law_admin/long_context routes: NONE (no over-matching)
```

### Newly matched / changed vs v6b

- **Newly safe-overridden:** `test_0099` (`operating_margin_asset_turnover`).
- **Changed family:** `test_0085` moved `relativistic_gamma` → `relativistic_momentum`
  (the gamma fix), changing its answer.
- **No-longer-safe vs v6b:** none.
- The other 9 `calculation_solver_missing_formula` risk items did **not** match — the
  new families are pattern-specific and conservatively decline rather than guess.

### Deterministic answers on the two changed cases (external sheet = risk signal only)

- `test_0085`: deterministic `p=γβ·m₀c=0.75·m₀c` (label **C**) — physically correct.
- `test_0099`: deterministic operating margin `=(400k−150k)/800k=31.25%`,
  turnover `800k/2M=0.40` (label **B**) — arithmetically correct.

> **Correction (made in Phase 2L.15B):** an earlier version of this section claimed
> the external 3/3 majority *disagreed* (0.6·m₀c / 25%). That was a **sheet-read
> bug** — an ad-hoc line-by-line read of `scratch/first100_external_3llm.csv` drifted
> by one row after an embedded-newline record (row 80 contains `'C\n'`), so 100
> physical lines ≠ 100 CSV records. The authoritative `csv.reader` alignment (used by
> `audit_first100_consensus_risks.py` and `compare_v7_programmatic_assist_pseudo.py`)
> gives the external majority as **C** (test_0085) and **B** (test_0099) — which
> **agree** with the deterministic answers. The leaderboard remains the only ground
> truth; the external sheet is never used as such.

## Safety checks

- Output is always a label from the sample's choices, or no override.
- `safe_to_override` requires confidence ≥ `min_confidence` (0.95).
- New families use clear-margin nearest / exact / interval-membership matching and
  decline on ambiguity (e.g. two `(K,L)` options hitting the same Q → no match).
- No matcher fires on law_admin/long_context routes on the public set.

## Confirmations

- No OpenRouter API call made; no full inference run.
- No qid hardcoding; no public-test answer table; no `eval`/`exec`.
- External Gemini/GPT/Claude sheet **not** used as ground truth in code (only the
  separate diagnostic scripts read it; the solver never does).
- No answer overrides keyed to a qid.
- `outputs/pred.csv` and v1/v2/v6/v6b prediction/log files untouched; the only new
  `outputs/` artifact is the diagnostic `calculation_solver_2l14b_audit.csv` (gitignored).
- No leaderboard upload; `.env` not read; no API key exposed; no model files touched.

## Remaining risks

- Several new families (accrued interest, operating margin, nuclear) rely on
  keyword+number extraction that may miss unusual phrasings → they decline (safe).
- The deterministic answers for test_0085/test_0099 disagree with the external
  majority; they are mathematically correct but unverified against the true key.
- Net accuracy effect is confirmable only by the leaderboard.

## Recommended next command — controlled v7 into NEW files (user runs; calls OpenRouter)

```bash
.venv/bin/python run.py \
  --solver openrouter_graph \
  --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 \
  --openrouter-max-tokens 512 \
  --config configs/verifier_selective.yaml \
  --calculation-solver \
  --evidence-reranker --evidence-reranker-method reranker \
  --evidence-reranker-model models/qwen3-reranker-0.6b --evidence-candidate-top-k 12 \
  --evidence-neural-batch-size 8 \
  --mcq-verifier \
  --input public-test_1780368312.json \
  --output outputs/pred_v7_calc_taxonomy_expanded.csv \
  --save-raw \
  --log-path outputs/run_v7_calc_taxonomy_expanded.jsonl
```

After: re-run `scripts/audit_calculation_solver_on_public.py` and the first-100
consensus audit, A/B-diff `pred_v7` vs `pred_v6b` — no leaderboard claim without
validation. Then proceed to **2L.14C** (short-knowledge selective verification).

## git status

```
 M .gitignore
 M docs/CALCULATION_TAXONOMY.md
 M src/calculation_solver.py
 M tests/test_calculation_solver.py
?? docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md
?? docs/AUDIT_PHASE_2L14A_P0P1_REVIEW_PACK.md
?? docs/AUDIT_PHASE_2L14B_CALCULATION_FORMULA_EXPANSION.md
?? scripts/audit_calculation_solver_on_public.py
?? scripts/audit_first100_consensus_risks.py
?? scripts/export_risk_review_pack.py
```
(`outputs/*` diagnostics and `scratch/*` are gitignored.)

Do not commit. All changes left uncommitted for user review.
