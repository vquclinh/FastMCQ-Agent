# Deterministic Calculation Solver (PAL-lite)

`src/calculation_solver.py` adds a small, deterministic helper for common
math/science/economics MCQ patterns. For the **calculation** route it can answer
(or override the LLM) when a closed-form family matches with high confidence —
replacing error-prone free-form LLM arithmetic with exact formulas.

## Why this helps accuracy

`calculation` is the largest route bucket (159/463). Manual checks found likely
LLM mistakes on simple, well-defined problems (elasticity, cylinder fill rate).
On the public set, the helper matches **9 samples** and, compared to the v1
OpenRouter run, would **change 4** — all elasticity/cylinder/GDP cases that the
formulas compute exactly (the other 5 already agreed). No ground truth exists, so
this is evidence of *likely* gains, confirmed only by the leaderboard.

## Generic formula-family approach (NOT public-test hardcoding)

The solver is a **registry of generic `try_*` formula families**. Each family
keys off *generic* wording, numbers, and formulas — never a question id or a
memorized answer. There is:

- **no `qid` logic** (the solver reads only `question` + `choices`; tests assert
  no `qid` access in the source),
- **no public-test answer table / no `if qid == ...`**,
- **no `eval`/`exec`/`__import__`/code execution** — only regex + arithmetic.

This is why it generalizes to the unseen private test: a private question that
matches a family's *pattern* is solved by the *formula*, exactly as a public one
would be. Matching public qids is incidental, not encoded.

## Supported formula families (high-confidence only)

| Family | `formula_family` | Pattern | Formula |
|---|---|---|---|
| `exponential_decay` | exponential_ode | `dX/dt = -kX`, initial `X0` | `X(t) = X0·e^{-kt}` |
| `exponential_growth` | exponential_ode | `dX/dt = kX` | `X(t) = X0·e^{kt}` |
| `hess_law` | thermochemistry | sequential ΔH steps (2–3 given) | `ΔH(total) = ΣΔH_i` |
| `cylinder_rate` | related_rates | cylinder, `dV/dt`, radius `r` | `dh/dt = (dV/dt)/(π r²)` |
| `sphere_rate` | related_rates | sphere `V=4/3πr³`, `dr/dt`, `r` | `dV/dt = 4π r² dr/dt` |
| `gdp_inflation` | economics | nominal/real GDP, prev deflator | `deflator=nom/real·100`; `inflation=Δdeflator/prev·100` |
| `price_elasticity_midpoint` | economics | two (P,Q) points | `E = (ΔQ/Q̄)/(ΔP/P̄)`; signed or `|E|` |
| `expected_distinct` | probability | `Xi` uniform {1..k}, distinct in `n` | `E[Y]=k(1-(1-1/k)^n)` |
| `resistor_cut_parallel` | circuits | `R` cut in two equal halves, parallel | `R/4 ⇒ I'=4I` |

Each `CalculationResult` records `method`, `formula_family`, `extracted_values`,
`confidence`, `rationale`, `matched`, `safe_to_override`.

## Conservative override policy

- Runs **only** on the `calculation` route, **before** the LLM call.
- Output is always a **label** from the sample's choices, never option text, never
  a label outside the available set.
- A family fires only when its pattern is unambiguous **and** the result maps to
  exactly one choice (nearest-numeric families require a clear gap to the
  second-nearest and small relative error).
- `safe_to_override` requires `confidence >= calc_min_confidence` (default 0.95).
  Exact symbolic/numeric matches score 0.99; nearest-numeric matches score 0.96.
- If anything is uncertain → `matched=False`, `answer=None`, **no override** → the
  normal OpenRouter path runs. **Prefer no answer over a risky answer.**

## Why no arbitrary code execution

There is **no `eval`, no `exec`, no sandbox, no external calls** — only regex +
numeric parsing + fixed arithmetic. This keeps the helper deterministic,
auditable, safe, and dependency-free.

## Integration & config

In `openrouter_graph` the calculation node runs after routing **on the
`calculation` and `ambiguous` routes** (duplicate-choice numeric questions land in
`ambiguous`; running there is safe because a family only matches genuine formula
patterns and only overrides when `safe_to_override`, so non-numeric text is never
touched). On a safe match it sets the answer and **skips the LLM (0 API calls)**.
Config (`openrouter:` block):

```yaml
calc_enabled: true            # master switch
calc_override_when_safe: true # use the deterministic label without an LLM call
calc_min_confidence: 0.95     # override threshold
```

CLI: `--calculation-solver` / `--no-calculation-solver`.

The per-sample JSONL trace records `calculation_matched`, `calculation_method`,
`calculation_answer`, `calculation_confidence`, `calculation_safe_to_override`,
and a short `calculation_rationale` (no hidden chain-of-thought).

## Limitations

- Small set of families; most samples are **not** matched (≈9/463 match on the
  public set; the rest, including most of the 159 calculation-route questions, are
  left to the LLM) — by design.
- Extraction is regex-based and Vietnamese-aware (handles comma decimals like
  `2,50`); unusual phrasings simply don't match.
- Duplicate-choice numeric questions route to `ambiguous`; the calc node runs on
  the `ambiguous` route too, so these **are** now covered (e.g. the resistor
  sample) — they no longer have the old "won't apply there" limitation. Safety is
  preserved because a family must match a real formula pattern and only overrides
  when `safe_to_override=True`, so non-numeric `ambiguous` text is never touched.
- If duplicate choices yield two **equally valid** labels for the computed value,
  the solver stays conservative: it overrides only when the selected label is the
  unique closest/exact match (exact families require a single matching label;
  nearest-numeric families require a clear margin), otherwise it does not override.
- Elasticity/cylinder/sphere/GDP use nearest-choice matching with tolerance; a
  borderline case yields no override rather than a guess.

## How to disable

`--no-calculation-solver`, or set `openrouter.calc_enabled: false`. The solver
then behaves exactly as before (pure LLM path).

## Use in v2

The intended v2 run keeps the chosen OpenRouter config and **adds the calculation
override**: deterministic answers for the matched calculation samples, LLM for the
rest. This should be A/B-compared against the v1 leaderboard score before adopting.
