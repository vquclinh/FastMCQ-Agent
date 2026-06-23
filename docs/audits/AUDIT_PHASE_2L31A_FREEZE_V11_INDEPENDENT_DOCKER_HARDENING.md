# Audit — Phase 2L.31A: Freeze Winning V11 Independent + Docker Hardening

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (for review)

## Final decision

**Independent v11 (`outputs/pred_v11_independent_rerun1.csv`, public 78.4) is the production
default.** v10 (`pred_v10_full_production_user_run.csv`, 77.75) is **fallback only** and is
never run by default. The image is offline and reproducible: it exports the frozen 78.4 CSV
and validates it, requiring no API key.

## Files changed

- **Updated:** `experiments/best_candidate_manifest.json` (current/previous best + default).
- **New:** `configs/production_v11_independent.json` (production config, no secrets).
- **New:** `scripts/final_infer.py` (frozen_csv default; v11_independent / v10 modes; output
  protection + full validation).
- **New:** `scripts/audit_production_candidate.py` (read-only candidate audit + recommendation).
- **New:** `scripts/docker_entrypoint_v11.sh` (offline frozen_csv entrypoint).
- **Updated:** `Dockerfile` (default → v11 frozen entrypoint, not the v10 pipeline).
- **New:** `.dockerignore`, `DOCKER_SUBMISSION.md`.
- **New:** `tests/test_final_package_2l31a.py` (+15).

## Manifest details and md5s

- current_best: `v11_independent_rerun1` → `outputs/pred_v11_independent_rerun1.csv`,
  public **78.4**, architecture `independent_v11`, `do_not_overwrite: true`,
  md5 **`69f4e7c990e8c612e7bee53084d13b4d`**, rows 463.
- previous_best: `v10_full_production` → `outputs/pred_v10_full_production_user_run.csv`,
  public **77.75**, architecture `v10`, `do_not_overwrite: true`,
  md5 **`c12e32fdf16ee5472e6a791c1e52e86a`**, rows 463.
- production_default: `independent_v11`; recommended_final_csv:
  `outputs/pred_v11_independent_rerun1.csv`. (Manifest md5 verified == file md5 by test.)

## Production config (`configs/production_v11_independent.json`)

`architecture=independent_v11`, `default_mode=frozen_csv`, `runnable_mode=v11_independent`,
`default_script=scripts/final_infer.py`,
`independent_runner=scripts/run_full_v11_independent_submission.py`,
`model=qwen/qwen3.5-9b-20260310`, `no_v10_base=true`, `v10_compare_only=true`,
`output_validation_required=true`, `model_policy_audit_required=true`, a `protected_outputs`
list, and notes (frozen_csv is the Docker default; v11_independent needs explicit
execute/budget). **No secrets/API keys.**

## final_infer design (Part C)

- **frozen_csv (default):** source priority `--source-csv` → config `current_best_csv` →
  fail; validates the source, copies to `--output`, re-validates, prints md5 + elapsed. No
  API, no v10.
- **v11_independent:** delegates to the independent runner (no v10 base); **requires
  `--execute` and explicit `--budget-usd`**; validates the output; `--compare-pred` is
  report-only.
- **v10:** explicit fallback only — copies the locked v10 CSV; no API.
- **Always validates:** required columns, all dataset qids present, no duplicates, no extra
  qids, row count == dataset, every label valid for its question.

## Output protection rules (Part D)

`final_infer` refuses to write any of `pred_v11_independent_rerun1.csv`,
`pred_v10_full_production_user_run.csv`, `pred_v8_clean_generalized_from_v7.csv` (by
basename, any directory), and `pred.csv` unless `--allow-pred-csv` (the explicit final
export used by the Docker entrypoint). Verified by tests.

## Dockerfile / .dockerignore design (Part E)

- `Dockerfile` CMD → `scripts/docker_entrypoint_v11.sh`, which detects the input under
  `/data` and runs `final_infer.py --mode frozen_csv --allow-pred-csv` → `/output/pred.csv`,
  then `validate_submission.py`. **Default never runs v10** (the v10 pipeline entrypoint is
  no longer the CMD) and needs no API key.
- `.dockerignore` excludes `.env`/secrets/keys, `scratch/`, `experiments/`, `docs/`, `.git/`,
  notebooks, `*.log`, `*.jsonl`, model weights/caches, and the non-final
  `outputs/pred.csv` + `outputs/pred_v11_full_adaptive_test.csv`; keeps the required frozen
  v11 best CSV and the v10 fallback CSV.

## Production candidate audit summary (Part F)

`scripts/audit_production_candidate.py` on the frozen candidate:
`candidate valid=True, qid_set_valid=True, changed_vs_v10=48, beats_v10=True,
md5_matches_manifest=True` → **recommendation: `freeze_as_default`**. Decision-source
breakdown (from the repaired decisions): consensus 259, api:calculation_solver 58,
api:option_elimination 58, api:route_specialist 31, direct_fallback 30, formula_bank 18,
direct_fallback_repair 9; fallback_used 39; last_resort 0.

## Smoke test result + md5 match (Part G)

```
final_infer.py --mode frozen_csv -> scratch/final_package_smoke/pred_final_smoke.csv (463 rows)
  output md5 = 69f4e7c990e8c612e7bee53084d13b4d  (== best md5)
validate_submission.py -> RESULT: PASS — submission is valid.
md5 compare: best == smoke -> same: True
```

## Tests run and results (Part H)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **592 passed** (was 577; +15 in `tests/test_final_package_2l31a.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: manifest freezes v11 (md5 verified); frozen_csv md5-identical + valid; explicit
  source; dry-run writes nothing; protected output names refused; pred.csv only with the
  flag; v11_independent needs execute+budget; v10 fallback copy; validation catches a bad
  source; production audit recommends freeze / do_not_freeze on md5 mismatch / refuses
  non-scratch; `.dockerignore` excludes secrets+scratch; Docker default uses the v11 frozen
  entrypoint (not v10); no qid hardcoding.

## Confirmations

- **Default mode is offline `frozen_csv`** using the current best independent v11 CSV
  (md5 `69f4e7c990e8c612e7bee53084d13b4d`); no API key required by default.
- **v10 is fallback only** — never the default, never a base for v11 generation.
- **No outputs overwritten**: `outputs/` still holds `pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v11_full_adaptive_test.csv`,
  `pred_v11_independent_rerun1.csv`, `pred_v8_clean_generalized_from_v7.csv`. The frozen
  best and v10 were not modified; the smoke wrote only under `scratch/`.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- No API call / no inference this phase; no secrets in config/Docker.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact final inference command

```bash
.venv/bin/python scripts/final_infer.py \
  --input public-test_1780368312.json \
  --output scratch/final_package_smoke/pred_final_smoke.csv \
  --mode frozen_csv
# -> exact copy of outputs/pred_v11_independent_rerun1.csv (md5 69f4e7c9…), validated.
```

## Exact Docker build / run commands

```bash
# build
docker build -t fastmcq-final .

# run (default: offline frozen current-best v11; no API key)
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final
#   -> writes /output/pred.csv (== pred_v11_independent_rerun1.csv) + validates

# run with explicit source CSV (still frozen_csv, offline)
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/final_infer.py --input /data/public-test.json \
    --output /output/pred.csv --allow-pred-csv --mode frozen_csv \
    --source-csv outputs/pred_v11_independent_rerun1.csv

# EXPERIMENTAL: regenerate via independent v11 (API key + budget REQUIRED; never v10)
docker run --rm -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/final_infer.py --input /data/public-test.json \
    --output /output/pred_v11_rerun.csv --mode v11_independent \
    --model qwen/qwen3.5-9b-20260310 --budget-usd 3.00 --execute --resume

# validate
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/validate_submission.py --input /data/public-test.json --submission /output/pred.csv
```

## git status (this phase)

```
 M Dockerfile
?? .dockerignore
?? DOCKER_SUBMISSION.md
?? configs/production_v11_independent.json
?? experiments/best_candidate_manifest.json   (untracked from a prior phase; rewritten here)
?? scripts/final_infer.py
?? scripts/audit_production_candidate.py
?? scripts/docker_entrypoint_v11.sh
?? tests/test_final_package_2l31a.py
?? docs/AUDIT_PHASE_2L31A_FREEZE_V11_INDEPENDENT_DOCKER_HARDENING.md
```
(`Dockerfile` is the only tracked-file modification; the manifest and v11 scripts are
untracked from earlier uncommitted phases. `outputs/` unchanged.)
