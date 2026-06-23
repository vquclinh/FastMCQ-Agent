# Audit — Phase 2L.38B: Final Pre-Commit Packaging Audit (V13 79.7 Dynamic System)

**Date:** 2026-06-24  **Branch:** `main`  **Status:** pre-commit verification (no commit, no API)

## Verdict

The V13 79.7 dynamic production system is **complete, clean, and safe to commit.** `git add -A`
is safe (verified by dry-run): it stages no secrets/venv/scratch/caches/weights/notebooks/logs,
only official source/scripts/tests/configs/docs and the 3 new official CSVs.

## 1. File classification

**Official — commit (modified, tracked):** `.gitignore`, `DOCKER_SUBMISSION.md`, `FINAL_RUN.md`,
`README.md`, `configs/production_v11_independent.json` (superseded marker),
`experiments/best_candidate_manifest.json`, `scripts/docker_entrypoint_v11.sh`,
`scripts/final_infer.py`, `tests/test_btc_noarg_2l32b.py`, `tests/test_btc_short_2l31b.py`,
`tests/test_final_package_2l31a.py`.

**Official — commit (new, untracked):**
- configs: `production_v12b_permutation_7883.json`, `production_v13_multilayer_7970.json`.
- dynamic system src: `fastmcq_system.py`, `dynamic_base_predictor.py`, `v12b_dynamic_layer.py`,
  `v13_dynamic_layer.py`, `v13_layer_registry.py`, `system_candidate_selector.py`,
  `mcq_permutation_debiaser.py`, `programmatic_solver_layer.py`, `content_first_answerer.py`,
  `least_to_most_constraint_solver.py`.
- scripts: `build/run/audit_v12_delta*`, `build/run/audit_v12b_*`, `build/run/audit_v13_multilayer*`.
- tests: `test_mcq_permutation_debiaser_2l34c.py`, `test_v12_delta_2l34a.py`,
  `test_v12b_permutation_2l34b.py`, `test_v13_multilayer_2l35a.py`,
  `test_fastmcq_dynamic_system_2l36b.py`, `test_v13_dynamic_integration_2l37a.py`.
- audit docs: `AUDIT_PHASE_2L34A … 2L38B_*.md`.
- official CSVs: `outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`,
  `outputs/pred_v12b_permutation_candidate_api30.csv`,
  `outputs/pred_v8_clean_generalized_from_v7.csv`
  (v10/v11 already tracked from a prior commit).

**Ignored / generated — DO NOT commit:** `outputs/pred.csv` (runtime export), `outputs/pred_v12_delta_candidate.csv`,
`outputs/pred_v12b_permutation_candidate.csv`, `outputs/pred_v13_multilayer_candidate_dryrun.csv`
(archived under `scratch/archive_outputs/`), `.env`, `.venv/`, `scratch/`, `__pycache__/`,
`.pytest_cache/`, model weights/caches, notebooks/logs — all gitignored.

**Suspicious needing review:** none found.

## 2. Official artifacts and md5 (all matched expected)

```
cb02fef569b31e7fb544abab46c0e282  outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv
075646adb4ec7d2db1b234186b091f70  outputs/pred_v12b_permutation_candidate_api30.csv
69f4e7c990e8c612e7bee53084d13b4d  outputs/pred_v11_independent_rerun1.csv
c12e32fdf16ee5472e6a791c1e52e86a  outputs/pred_v10_full_production_user_run.csv
```

## 3. Old shadow outputs not tracked

`git check-ignore` confirms ignored: `pred_v12_delta_candidate.csv`,
`pred_v12b_permutation_candidate.csv`, `pred_v13_multilayer_candidate_dryrun.csv`, `pred.csv`.
None appear in `git status`; the dryrun/delta/refactor shadows live in `scratch/archive_outputs/`.

## 4. Secrets / env / caches

`.env` exists but is gitignored (not staged/tracked). `git add -A` dry-run staged **no**
`.env`/`.venv`/`scratch`/`__pycache__`/`.pytest_cache`/`models`/`.ipynb`/`.log`/weights. Secret
scan (`sk-or-v1-…`) of `src`/`scripts`/`configs`/`tests` and the committed tree: **no key literal**.

## 5. Validation results

- `git diff --check`: **clean** (no whitespace errors / conflict markers).
- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **705 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## 6. Public replay smoke result

```
final_infer.py --input public-test_1780368312.json --mode public_replay
  resolved mode: public_replay   md5: cb02fef569b31e7fb544abab46c0e282   status: PASS
md5 == outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv  ✓
```

## 7. Dynamic private no-api smoke result

```
final_infer.py --input scratch/final_precommit_smoke/private.json --mode dynamic_full --no-api
  resolved mode: dynamic_full   V12B enabled=True executed=False targets=2 overrides=0
  V13 enabled=True executed=False targets=2 overrides=1 (deterministic programmatic: 2+2 -> B)
  questions: 2   status: PASS
output: private_commit_0001=B, private_commit_0002=A  (exactly the 2 input qids; valid; no None)
```

## Confirmations

- **No API calls** — both smokes ran `--no-api` / offline replay; no client constructed.
- **No secrets / generated scratch files to commit** — `.env`, `scratch/`, caches, `pred.csv`,
  shadow CSVs all ignored; `git add -A` dry-run is clean.
- **No ground truth / hidden answers / answer tables / external 3-LLM sheet; no qid/answer
  hardcoding** (system modules regex-clean; carry no frozen-CSV path).
- **No official output artifacts overwritten** — all four md5s unchanged.

## Recommended `git add` command

`git add -A` is safe (verified). Explicit form if preferred:
```bash
git add -A
git status --short    # confirm: 3 official CSVs + src/scripts/tests/configs/docs; NO .env/scratch/.venv/pred.csv
```

## Recommended commit message

```
Promote V13 multi-layer 79.7 as official dynamic production system

- dynamic_full (src/fastmcq_system.py) = real system for arbitrary inputs:
  dynamic base -> V12B debiaser -> V13 (programmatic/content-first/least-to-most)
  -> unified system_candidate_selector; outputs exactly the input qids.
- V12B + V13 official, enabled by default; API only under --execute-api (model-policy guarded).
- public_replay reproduces the frozen public best: V13 79.7
  (outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv, md5 cb02fef5…); explicit-only.
- configs/production_v13_multilayer_7970.json (current best); V12B config superseded.
- track official CSVs (v13/v12b/v8; v10/v11 already tracked); manifest + docs updated.
- 705 tests passing; model-policy PASS; no secrets committed.
```

## Final git status

11 modified (tracked) + 40 untracked (official src/scripts/tests/configs/docs + 3 official CSVs).
`.env`, `scratch/` (incl. `archive_outputs/`), `outputs/pred.csv`, and shadow candidates remain
gitignored. Nothing committed.
