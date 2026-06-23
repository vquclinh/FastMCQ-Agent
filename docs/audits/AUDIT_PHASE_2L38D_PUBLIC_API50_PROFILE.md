# Audit — Phase 2L.38D: Add `public_api50` Run Profile and Short Wrapper

**Date:** 2026-06-24  **Branch:** `main`  **Status:** packaging convenience (no commit, no API)

## Files created / changed

**Created:**
- `scripts/run_public_api50.sh` — short wrapper for the `public_api50` profile.
- `docs/audits/AUDIT_PHASE_2L38D_…md` — this audit.

**Changed:**
- `configs/run_profiles.json` — added the `public_api50` profile (between `dynamic_noapi`/
  `public_noapi` and `public_api100`).
- `tests/test_run_profiles_2l38c.py` — added `run_public_api50.sh` to the wrapper list + 5
  focused tests.
- `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md` — documented the new short command.

## Profile values (`public_api50`)

```json
{ "mode": "dynamic_full", "execute_api": true, "model": "qwen/qwen3.5-9b-20260310",
  "budget_usd": 2.50, "enable_v12b": true, "enable_v13": true,
  "v12b_max_qids": 50, "v12b_permutations": 6, "v12b_policy": "conservative",
  "v13_max_qids": 50, "system_policy": "conservative", "max_overrides": 30 }
```
A middle option between a manual `public_api30`-style override and `public_api100`: it runs the
full dynamic system over the **entire** input file (predictions for all qids) but only sends up
to **50** high-risk qids through the V12B/V13 API layers. CLI flags still override the profile
(verified: `--no-api`, `--budget-usd` win).

## Wrapper behavior (`scripts/run_public_api50.sh`)

`set -euo pipefail`; usage `bash scripts/run_public_api50.sh <input> [extra flags...]`; creates
`scratch/runs/public_api50_<ts>/`; calls
`final_infer.py --profile public_api50 --input … --output …/pred.csv --work-dir …/work --resume`
(forwarding extra args); tees `run.log`; prints profile, output path, md5, elapsed seconds +
m:s, log path, PASS/FAIL. Uses repo `.venv` python if present. No hardcoded qids/answers.

## Tests run and results (Part C)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **722 passed** (5 new `public_api50` tests + existing profile suite)
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

New tests assert: profile exists with the exact values (execute_api, allowed model, v12b/v13
max_qids=50, permutations=6, conservative policies, budget 2.50); model passes model-policy;
`_apply_profile` sets the caps; wrapper exists + `bash -n` valid + uses `--resume`; all three
docs mention `run_public_api50.sh`.

## Model policy result

**PASS** — `public_api50` uses `qwen/qwen3.5-9b-20260310` (allowed ≤9B Qwen3.5); no model-policy
rules changed; the layers still validate via `assert_allowed_llm_model` at call time.

## Confirmations

- **No API calls** this phase — only offline profile-loading/`_apply_profile` checks and the
  test suite ran; the API profile was not executed.
- **No qid/answer hardcoding** — profile + wrapper regex-clean.
- **Official V13 79.7 artifact unchanged** — `outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`
  md5 still `cb02fef569b31e7fb544abab46c0e282`.
- **Not committed.**

## Git status

```
 M configs/run_profiles.json
 M tests/test_run_profiles_2l38c.py
 M README.md  FINAL_RUN.md  DOCKER_SUBMISSION.md
?? scripts/run_public_api50.sh
?? docs/audits/AUDIT_PHASE_2L38D_PUBLIC_API50_PROFILE.md
```
(`scratch/` incl. `scratch/runs/` and `outputs/pred.csv` remain gitignored.) Nothing committed.

## Exact command to run API50 after this phase

```bash
# requires OPENROUTER_API_KEY in the environment / .env (this phase did NOT run it)
bash scripts/run_public_api50.sh public-test_1780368312.json
# or to raise the budget:
bash scripts/run_public_api50.sh public-test_1780368312.json --budget-usd 3.00
```
