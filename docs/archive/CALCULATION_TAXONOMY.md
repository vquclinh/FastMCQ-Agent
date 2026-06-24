# Generic Calculation Taxonomy

The deterministic solver (`src/calculation_solver.py`) is a **registry of generic
formula families**. Each family keys off generic wording + numbers + formulas —
never a question id or a memorized answer. This file catalogues the implemented
families, the ones intentionally **declined**, and future candidates.

> Design rule (correctness-first, conservative): a family fires only when its
> pattern is unambiguous AND the computed value maps to exactly one label (exact
> match, or nearest-numeric with a clear margin). On any ambiguity it returns
> `matched=False` and the LLM path runs. **Prefer no answer over a risky answer.**

## Implemented families

| Family | Domain | Trigger (generic) | Formula | Match type |
|---|---|---|---|---|
| exponential_decay/growth | calculus | `dX/dt=±kX` | `X0·e^{±kt}` | symbolic |
| hess_law | thermochemistry | sequential `ΔH` steps | `ΣΔH_i` | exact numeric |
| cylinder_rate | related rates | cylinder, `dV/dt`, `r` | `dh/dt=(dV/dt)/(πr²)` | nearest |
| sphere_rate | related rates | sphere `V=4/3πr³`, `dr/dt`, `r` | `dV/dt=4πr²·dr/dt` | nearest |
| gdp_inflation | economics | nominal/real GDP, prev deflator | deflator + inflation | nearest |
| price_elasticity_midpoint | economics | two `(P,Q)` points | midpoint `E` | nearest |
| expected_distinct | probability | uniform `{1..k}`, distinct in `n` | `k(1-(1-1/k)^n)` | symbolic |
| resistor_cut_parallel | circuits | `R` halved, parallel | `I'=4I` | symbolic |
| **kepler_third_law** | astronomy | Kepler III, radius ×k | `T'=T·k^(3/2)` | nearest |
| **relativistic_gamma** | physics | speed as fraction of `c` | `γ=1/√(1−β²)` | nearest |
| **money_multiplier** | economics | reserve ratio `rr` | `m=1/rr` | nearest |
| **t_statistic** | statistics | `x̄,μ₀,s,n` | `(x̄−μ₀)/(s/√n)` | nearest |
| **acid_base_neutralization** | chemistry | 1:1 acid/base volume | `V_b=(M_a·V_a)/M_b` | nearest |
| **supply_demand_gap** | economics | linear `Qd/Qs` at controlled price | shortage/surplus | nearest |
| **cobb_douglas_isoquant** | economics | `Q=A√(KL)`, `(K,L)` choices | unique pair with `A√(KL)=Q` | exact |
| **modular_arithmetic** | number theory | `base^exp mod n` / `a mod n` | `pow(base,exp,n)` / `a%n` | exact |
| ‡relativistic_momentum | physics | "động lượng" + speed `βc` | `p=γβ·m₀c` (options as ×m₀c) | nearest |
| ‡cobb_douglas_isoquant_scaling | economics | `Q=A·K^a·L^b`, `(K0,L0)`, fraction | pick `(K,L)` hitting `Q1=frac·Q0` | exact |
| ‡t_statistic_one_sample | statistics | t-test, **interval** options | `t=(x̄−μ₀)/(s/√n)`, pick interval | interval |
| ‡z_score_one_sample | statistics | **population** σ given | `z=(x̄−μ₀)/(σ/√n)` | nearest |
| ‡supply_demand_price_control | economics | general linear `Qd/Qs` (incl. `cP−d`) | shortage/surplus at controlled P | nearest |
| ‡henderson_hasselbalch_buffer | chemistry | buffer pKa + [base],[acid] | `pH=pKa+log10([base]/[acid])` | nearest |
| ‡linear_total_equation | algebra | ≥2 linear eqs summed to a total | `y=(T−ΣC)/ΣK` | abs-nearest |
| ‡nuclear_binding_energy_release | physics | fission, BE/nucleon before/after | `ΔE=A·Δ(BE/nucleon)` | nearest |
| ‡accrued_simple_interest | finance | principal, rate %, two dates | `I=P·r·(months/12)` | nearest |
| ‡operating_margin_asset_turnover | finance | gross, opex, sales, assets | margin=(gross−opex)/sales; turnover=sales/assets | combined |

(**bold** = Phase 2L.8; ‡ = Phase 2L.14B.)

## Phase 2L.14B — relativity bug fix + new families

- **`relativistic_gamma` tightened**: previously fired on generic relativity wording
  (e.g. "0.6c") and answered γ even for momentum/energy questions. It now fires
  **only** when γ itself is the asked quantity ("hệ số Lorentz" / "hệ số giãn nở thời
  gian" / …) and **declines** if "động lượng"/"năng lượng"/"động năng" is asked.
- **`relativistic_momentum` added**: `p = γβ·m₀c`, matched against options written as
  multiples of `m₀c`. Example: `v=0.6c → γ=1.25 → p=0.75·m₀c`.
- **Public-set check (external sheet is NOT ground truth, only a risk signal):** on
  `test_0085` the deterministic momentum gives the physically-correct `0.75·m₀c`
  (label **C**); on `test_0099` the operating margin `=(400k−150k)/800k = 31.25%`
  with turnover `800k/2M = 0.40` (label **B**). Both are arithmetically correct and
  both **agree with the external 3/3 majority** (C and B respectively).
  > Correction (Phase 2L.15B): an earlier draft of this note claimed the external
  > majority disagreed (0.6·m₀c / 25%). That was a **sheet-read bug** — an ad-hoc
  > line-by-line read drifted by one row after an embedded-newline record (row 80,
  > `'C\n'`). The authoritative `csv.reader` alignment (used by the audit scripts)
  > gives C and B, matching the deterministic answers. The leaderboard remains the
  > only ground truth.

## Extraction examples (generic, not public-test answers)

- Kepler: `"bán kính quỹ đạo gấp 4 lần"` → k=4 → ratio `4^1.5 = 8`.
- Gamma: `"0,6c"`, `"60% tốc độ ánh sáng"`, `"0,6 lần tốc độ ánh sáng"` → β=0.6 → γ=1.25.
- Money multiplier: `"tỷ lệ dự trữ bắt buộc là 10%"` → rr=0.10 → m=10.
- t-statistic: `"trung bình mẫu 52, độ lệch chuẩn 5, cỡ mẫu 25, giả thuyết 50"` → t=2.
- Acid-base: `"50 mL HCl 0,2 M ... NaOH 0,1 M"` → `V_b=(0.2·50)/0.1=100 mL`.
- Supply-demand: `"Qd=100-2P, Qs=20+3P, giá trần 10"` → shortage = 80−50 = 30.
- Cobb-Douglas: `"Q=2√(KL)"`, target 12 → pick `(K=4,L=9)` (2·√36=12).
- Modular: `"chia 2^10 cho 7"` → `pow(2,10,7)=2`.

## Intentionally declined (not implemented)

| Candidate | Why declined |
|---|---|
| **Polynomial/function substitution** (`g(x)=f(x−a)`, coefficient extraction) | Robust, safe (no `eval`) symbolic parsing of arbitrary polynomials and substitution is fragile; a wrong override is worse than deferring to the LLM. |
| pH **titration-curve / mixed weak-acid** | Multi-branch logic (titration mixtures, ICE tables) stays error-prone; only the clean **buffer** case (`henderson_hasselbalch_buffer`, 2L.14B) and the 1:1 neutralization-volume case are implemented. |
| General Cobb-Douglas `K^a L^b` **cost-min / Lagrange optimisation** | Requires prices + a constrained optimisation; the isoquant / output-scaling cases (`cobb_douglas_isoquant`, `cobb_douglas_isoquant_scaling`) are implemented, not the optimiser. |
| Free-form arithmetic via expression `eval` | Forbidden by design — no `eval`/`exec`. Only integer `pow`/`%` on parsed integers is used (modular family). |
| **Legal / admin count questions** (e.g. "Theo Luật … có bao nhiêu nguyên tắc…") | **NOT a deterministic formula** — this is legal/admin knowledge. No public-test-specific numeric rule is added; it stays LLM/verifier territory. A test asserts the solver does not fire on such questions. |

A declined family is better left to the LLM than implemented with shaky parsing.

## Route interaction (consideration, not enabled)

The calc node runs only on the `calculation`/`ambiguous` routes. On the public set
all 12 safe matches route to `calculation`, so none are blocked. For the private
test, a prose-phrased physics/stat formula question could route to
`short_knowledge` and miss the override. A future option is a configurable
`calc_apply_routes` that also runs the (conservative, override-only-when-safe) calc
helper on `short_knowledge`. This is **not enabled by default** because it changes
behavior on the largest route bucket without public-set evidence of benefit; it
should be A/B-validated before adoption.

## Safety invariants (all families)

- No `qid` is read for any decision; same content under any qid → same result.
- No public-test answer table; no `if qid == ...`.
- No `eval`/`exec`/`__import__`/`open`/network — regex + arithmetic only.
- Output is always a label from the sample's choices, or no override.
- `safe_to_override` requires `confidence ≥ calc_min_confidence` (default 0.95).

## Future candidates (would need robust, safe parsing first)

Compound interest / annuity; ideal gas `PV=nRT`; projectile range; combinatorics
`nCr/nPr`; simple Bayesian update; unit-conversion chains; arithmetic/geometric
series sums. Each should ship with ≥2 positive + ≥1 decline synthetic test and a
no-qid test, matching the existing pattern.
