# Audit — Phase 2L.36A: Freeze V12B 78.83 as Official Production Best

**Date:** 2026-06-23  **Branch:** `main`  **Status:** promotion (no commit, no API)

## Why V12B is being promoted

The V12B option-permutation debiaser candidate was validated on the public leaderboard and
**beats the previous v11 best**. It is now the official frozen production default, and the
V12B debiaser (module + scripts + tests) is promoted from experiment to official architecture.

## Leaderboard score improvement

| | CSV | public |
|---|---|---|
| previous best (v11) | `outputs/pred_v11_independent_rerun1.csv` | 78.40 |
| **new best (V12B)** | `outputs/pred_v12b_permutation_candidate_api30.csv` | **78.83** |
| delta | | **+0.43** |

## Exact official production default after this phase

- **Frozen CSV:** `outputs/pred_v12b_permutation_candidate_api30.csv`
- **Production config:** `configs/production_v12b_permutation_7883.json` (`default_mode=frozen_csv`)
- **Entry:** `scripts/final_infer.py` (`_DEFAULT_CONFIG` → new config) and
  `scripts/docker_entrypoint_v11.sh` (`--config` → new config). Docker/final path stays
  frozen-CSV and API-free.

## md5 values (Part A — verified, all matched expected)

```
075646adb4ec7d2db1b234186b091f70  outputs/pred_v12b_permutation_candidate_api30.csv   (NEW best)
69f4e7c990e8c612e7bee53084d13b4d  outputs/pred_v11_independent_rerun1.csv             (prev best)
c12e32fdf16ee5472e6a791c1e52e86a  outputs/pred_v10_full_production_user_run.csv       (fallback)
```
V12B candidate: 463 rows, qid set == public test, all labels valid, changed_vs_v11 = 4.

## Changed qids (V12B vs v11)

| qid | v11 → V12B |
|---|---|
| test_0232 | E → A |
| test_0244 | A → B |
| test_0246 | A → E |
| test_0397 | J → E |

## Files created / changed

**Created:**
- `configs/production_v12b_permutation_7883.json` — new official production config.
- `docs/audits/AUDIT_PHASE_2L36A_…md` — this audit.

**Changed:**
- `scripts/final_infer.py` — `_DEFAULT_CONFIG` → new config; added the V12B best to
  `_PROTECTED_NAMES` (refuses to overwrite it).
- `scripts/docker_entrypoint_v11.sh` — `--config` → new config.
- `experiments/best_candidate_manifest.json` — current_best=V12B 78.83, previous_best=v11
  78.40, fallback_v10=77.75; V13 marked experimental/not promoted.
- `configs/production_v11_independent.json` — marked `status: SUPERSEDED` + `superseded_by`.
- `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`, `README.md` — current best → V12B 78.83.
- `.gitignore` — official tracked outputs now include V12B api30 + v8 (plus v11, v10).
- Tests retargeted to the new default: `test_btc_short_2l31b.py`, `test_btc_noarg_2l32b.py`,
  `test_final_package_2l31a.py` (`_BEST` → V12B; manifest test → v12b), and the three
  `test_*_default_*` guards now assert the V12B config.

## Confirmation: V12B source layer is now official architecture

These remain official (not scratch), all present, all imported by the production-adjacent
tooling: `src/mcq_permutation_debiaser.py` (pure core, **no API client** — verified),
`scripts/build_v12b_permutation_plan.py`, `scripts/run_v12b_option_permutation.py`
(constructs the client only under `--execute`; dry-run = 0 calls),
`scripts/build_v12b_permutation_candidate.py`, `scripts/audit_v12b_permutation_candidate.py`,
`tests/test_v12b_permutation_2l34b.py`, `tests/test_mcq_permutation_debiaser_2l34c.py`,
`docs/audits/AUDIT_PHASE_2L34C_…md`. Model IDs are validated via `src/model_policy.py`.

## Confirmation: final/Docker path remains frozen CSV and API-free

`default_mode=frozen_csv`; `final_infer.py` copies the frozen V12B CSV and validates; no client
is constructed on the default path; the entrypoint forwards to `final_infer.py` with the new
config. No `OPENROUTER_API_KEY` required or used.

## Smoke test commands and results (Part E)

```
python scripts/final_infer.py --input public-test_1780368312.json --output scratch/v12b_freeze_smoke/pred.csv
  input detected: public-test_1780368312.json
  source: outputs/pred_v12b_permutation_candidate_api30.csv
  md5: 075646adb4ec7d2db1b234186b091f70   elapsed_seconds: 0.02   status: PASS
md5sum  -> scratch/v12b_freeze_smoke/pred.csv == outputs/pred_v12b_permutation_candidate_api30.csv (075646ad…)
validate_submission.py -> RESULT: PASS — submission is valid.
```
Default output is byte-identical to the V12B best. No API calls.

## Full tests and model-policy results (Part F)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **673 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Output artifact cleanup summary (Part D)

- **Now officially tracked** (`.gitignore` exceptions): `pred_v12b_permutation_candidate_api30.csv`,
  `pred_v11_independent_rerun1.csv`, `pred_v10_full_production_user_run.csv`,
  `pred_v8_clean_generalized_from_v7.csv`.
- **Archived to `scratch/archive_outputs/`** (old shadow candidates, not deleted):
  `pred_v12_delta_candidate.csv`, `pred_v12b_permutation_candidate.csv`,
  `pred_v12b_permutation_candidate_refactor.csv`, `pred_v13_multilayer_candidate_dryrun.csv`.
- `outputs/pred.csv` (runtime export) remains gitignored.

## Confirmations

- **No API calls** this phase (md5 verification + offline frozen copy + offline tests only).
- **No ground truth / answer table / hidden answers / external 3-LLM sheet** used.
- **No best artifacts overwritten** — V12B `075646ad…`, v11 `69f4e7c9…`, v10 `c12e32fd…` all
  unchanged on disk; `final_infer.py` now also protects the V12B best.
- **V13 not promoted** — its src/scripts/tests stay experimental; manifest marks them
  not-in-production; the V13 default-guard test asserts the default is still V12B.
- **Not committed.**

## Git status

```
 M .gitignore  DOCKER_SUBMISSION.md  FINAL_RUN.md  README.md
 M configs/production_v11_independent.json  experiments/best_candidate_manifest.json
 M scripts/docker_entrypoint_v11.sh  scripts/final_infer.py
 M tests/test_btc_noarg_2l32b.py  tests/test_btc_short_2l31b.py  tests/test_final_package_2l31a.py
?? configs/production_v12b_permutation_7883.json
?? outputs/pred_v12b_permutation_candidate_api30.csv   ?? outputs/pred_v8_clean_generalized_from_v7.csv
?? src/{mcq_permutation_debiaser,programmatic_solver_layer,content_first_answerer,least_to_most_constraint_solver}.py
?? scripts/{build,run,audit}_v12*/v13* .py   ?? tests/test_{mcq_permutation_debiaser_2l34c,v12_delta_2l34a,v12b_permutation_2l34b,v13_multilayer_2l35a}.py
?? docs/audits/AUDIT_PHASE_2L34A/2L34B/2L34C/2L35A/2L36A_*.md
```
(`outputs/pred.csv` and `scratch/` — incl. `scratch/archive_outputs/` — remain gitignored.)
Nothing committed.

## Next recommended phase

Run the **V13 Multi-Layer API pilot using V12B 78.83 as `--current`** (not v11): build the
V13 plan against `outputs/pred_v12b_permutation_candidate_api30.csv`, run the verifier with
`--execute` + budget, then build/audit a V13 candidate and compare on the leaderboard before
any promotion. V13 must beat 78.83 to be promoted.
