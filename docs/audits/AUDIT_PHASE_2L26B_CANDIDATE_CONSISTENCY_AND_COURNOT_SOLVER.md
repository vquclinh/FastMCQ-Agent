# Audit — Phase 2L.26B: Candidate Consistency Guard + Cournot Solver

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Fixed the answer/evidence-mismatch weakness in the selective multi-candidate system
and added a qid-free deterministic Cournot duopoly solver. With both, the offline v11
proposals now **reject the two bad 20-qid review items** (placeholder-evidence consensus
and a numeric mismatch) and instead surface **one correct deterministic proposal**
(test_0457 C→D, q=6). No API call, no inference, no final prediction, no outputs
overwritten, no qid hardcoding.

## Files changed

**New**
- `src/candidate_consistency.py` — placeholder detection + numeric answer/evidence
  consistency guard.
- `tests/test_candidate_consistency.py` — guard + ranker-integration tests.

**Modified**
- `src/answer_ranker.py` — consensus path now validates each candidate with the guard;
  inconsistent candidates do not count toward consensus; decision record carries
  `inconsistent_candidates`.
- `src/formula_bank_solver.py` — added `try_cournot_duopoly` (registered first in
  `_NEW_RULES`).
- `src/tool_solvers/finance_econ_solver.py` — delegates to `try_cournot_duopoly`.
- `tests/test_formula_bank_solver.py` — Cournot positive + decline tests.

## Consistency guard design (`candidate_consistency.py`)

- `detect_placeholder_evidence` — rejects empty / `"r"` / `"some evidence"` / `"n/a"` /
  too-short / single-char-repeat evidence.
- `extract_numeric_claims`, `extract_option_numeric_values`, `strong_claim` — parse
  numbers; `strong_claim` returns the value after the LAST `=` (the derived result).
- `candidate_matches_option` — if a candidate states a strong numeric result, the
  selected option must contain that value (tolerance). `q=6` cannot select `q=4`.
- `validate_candidate_consistency` → `ConsistencyRecord(ok, severity, reason,
  detected_claims, option_values)`. Severity: `numeric_mismatch` (decisive, any
  source) > `placeholder` (non-deterministic only) > `ok`. Deterministic tool
  candidates (source `tool:*`/`formula_bank`/`concept`/`calc:`) are trusted (they
  already matched the option) but still fail on a numeric mismatch.

**Policy in the ranker:** a candidate counts toward `multi_agent_consensus` only if it
passes the guard; placeholder-evidence or numeric-mismatch candidates are excluded, so
three agents agreeing on a wrong-but-unsupported answer no longer override. Deterministic
proof overrides are unaffected.

## Cournot solver design (`try_cournot_duopoly`)

Symmetric linear Cournot, n=2: `q_i = (a − c) / (b·(n+1)) = (a − c)/(3b)`. Fires only
when: Cournot/"cạnh tranh về lượng" **and** two firms detected; inverse demand
`P = a − bQ` parsed (b optional = 1); a single symmetric marginal cost `C(q)=c·q`;
`a>c`, `b>0`; and exactly one option's symmetric pair equals `q_i`. Declines on >2
firms, nonlinear demand (`Q^2`), asymmetric costs (`C_X`/`C_Y`), or no unique option.
Example: `P=20−Q, C(q)=2q → (20−2)/3 = 6 → q_X=q_Y=6`.

## Old proposals (before the guard)

```
test_0001  A→B  multi_agent_consensus  medium   (3 agents, evidence "some evidence" = placeholder)
test_0457  C→B  multi_agent_consensus  medium   (agents derived q=6 but B is q=4 -> mismatch)
```

## New proposals (after the guard + Cournot)

```
test_0457  C→D  formula_bank (cournot_duopoly)  low   proof: q_i=(20-2)/(1·3)=6 -> q_X=q_Y=6
```
- `test_0001` is **rejected** (placeholder evidence → not counted → no consensus → keep v10).
- `test_0457` B/C API picks are **rejected** (numeric mismatch); the deterministic
  Cournot solver proposes **D** (q=6), which the ranker applies as a low-risk proof.
- Reviewer recommendation: **submit_candidate** (1 deterministic, low-risk change).

## Whether a qid-free deterministic proposal remains

Yes — exactly one: `test_0457 C→D` from `cournot_duopoly`, derived generically from the
question text (P=20−Q, C(q)=2q), with no qid reference. Verified by the solver on the
real sample and by synthetic unit tests.

## Test results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **462 passed** (was 446; +16).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- New coverage: placeholder detection; numeric-claim/option extraction; numeric
  mismatch rejected & match accepted; deterministic trusted; ranker rejects
  placeholder/mismatch consensus, overrides on consistent consensus, deterministic
  proof still works; Cournot positive + 4 decline cases.

## Confirmations

- **No OpenRouter/API call**; no inference run.
- **No final prediction generated**; `outputs/pred.csv` and
  `outputs/pred_v10_full_production_user_run.csv` untouched; proposals under `scratch/` only.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth.
- No disallowed model introduced (policy audit PASS).
- Nothing committed.

## Recommended next step

The single deterministic proposal (`test_0457 C→D`, Cournot, low-risk) is a safe,
qid-free upgrade candidate. If desired, run the selective API on the remaining planned
qids (Phase 2L.26A commands), rebuild v11 with this guard, review, and — only for a
`submit_candidate`/reviewed result — build a v11 CSV into a NEW file and A/B vs v10.
v10 (77.75) remains the submission until then.

Do not commit until a result is accepted.
