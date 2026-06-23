# Audit — Phase 2L.31B: BTC Short Command Polish + Default Timing Output

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (for review)

## What changed from 2L.31A

- **`pred.csv` is no longer protected by basename.** `final_infer.py` now allows writing
  `pred.csv` as the explicit final output, so the short command works without
  `--allow-pred-csv`. The frozen best / v10 / v8 remain protected.
- **`--allow-pred-csv` is now a deprecated no-op** (kept for backward compatibility).
- **Every run prints a standard timing block** (`FINAL INFER COMPLETE … elapsed_seconds …
  status: PASS|FAIL`) by default — no flag required; failures print elapsed + `status: FAIL`
  before re-raising.
- The Docker entrypoint no longer passes `--allow-pred-csv`.
- New `FINAL_RUN.md`; `DOCKER_SUBMISSION.md` now leads with the simple local command.

## Confirmation: the short command works

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
```
Runs with no `--mode` and no `--allow-pred-csv`: default mode `frozen_csv`, default source
`outputs/pred_v11_independent_rerun1.csv`, writes the explicit `--output` (incl. `pred.csv`),
validates source + output, no API, no v10, and prints elapsed time. (Verified via the
smoke run and tests.)

## Default behaviour confirmations

- **Default is still the winning v11 frozen CSV** — mode `frozen_csv`, source
  `outputs/pred_v11_independent_rerun1.csv` (md5 `69f4e7c990e8c612e7bee53084d13b4d`).
- **v10 is fallback only** — requires explicit `--mode v10`; never the default; output md5
  differs from v10 by construction (the default copies v11).
- **`pred.csv` can be written** as the explicit final output (no flag).
- **Frozen best / v10 / v8 are still protected** — refused as `--output` with a clear error.
- **No API by default; no API key required** (frozen_csv constructs no client — verified by
  a monkeypatched client that raises if instantiated).

## Default timing block (Part B)

Every successful run prints:
```text
============================================================
FINAL INFER COMPLETE
mode: frozen_csv
source: outputs/pred_v11_independent_rerun1.csv
output: pred.csv
questions: 463
md5: 69f4e7c990e8c612e7bee53084d13b4d
elapsed_seconds: <float>
status: PASS
============================================================
```
Failures print the same block with `status: FAIL (<error>)` and `elapsed_seconds` before the
exception propagates (verified by attempting to write a protected name).

## Smoke test result (Part D)

```
final_infer.py --input public-test_1780368312.json --output scratch/final_default_short_smoke/pred.csv
  -> FINAL INFER COMPLETE  mode: frozen_csv  questions: 463
     md5: 69f4e7c990e8c612e7bee53084d13b4d  elapsed_seconds: 0.022  status: PASS
validate_submission.py -> RESULT: PASS — submission is valid.
```

## md5 match result

```
best  (outputs/pred_v11_independent_rerun1.csv)        : 69f4e7c990e8c612e7bee53084d13b4d
smoke (scratch/final_default_short_smoke/pred.csv)     : 69f4e7c990e8c612e7bee53084d13b4d
same: True
```

## Tests run and results (Part E)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **605 passed** (was 592; +13 in `tests/test_btc_short_2l31b.py`; two 2L.31A
  assertions updated for the new `pred.csv` policy).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: short command works with no `--mode`/flag; default mode frozen_csv; default
  source is the frozen best; output md5 == winning CSV; `elapsed_seconds` + `status: PASS`
  printed by default; `pred.csv` basename allowed; frozen best/v10/v8 still refused; v10 not
  default; no API call on the default path; failure prints elapsed + `status: FAIL`;
  `--allow-pred-csv` harmless backward-compat; docs contain the short BTC command near the
  top; no qid hardcoding.

## Confirmations

- **No OpenRouter/API call** this phase; no inference; no full run.
- **No outputs/best artifacts overwritten** — `outputs/` still holds `pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v11_full_adaptive_test.csv`,
  `pred_v11_independent_rerun1.csv` (md5 `69f4e7c9…` unchanged),
  `pred_v8_clean_generalized_from_v7.csv`. Smoke wrote only under `scratch/`.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact BTC command

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
```

## Exact Docker command

```bash
docker build -t fastmcq-final .
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final
# -> /output/pred.csv (== frozen v11 best), validated; no API key required.
```

## git status (this phase)

```
 M Dockerfile                                   (from 2L.31A)
?? .dockerignore
?? DOCKER_SUBMISSION.md                          (updated this phase)
?? FINAL_RUN.md                                  (new this phase)
?? configs/production_v11_independent.json
?? experiments/best_candidate_manifest.json
?? scripts/final_infer.py                        (edited this phase)
?? scripts/audit_production_candidate.py
?? scripts/docker_entrypoint_v11.sh              (edited this phase)
?? tests/test_final_package_2l31a.py             (two assertions updated this phase)
?? tests/test_btc_short_2l31b.py                 (new this phase)
?? docs/AUDIT_PHASE_2L31B_BTC_SHORT_COMMAND_TIMING.md
```
(`final_infer.py`, the manifest, configs, and the 2L.31A docs/scripts/tests are untracked
from the prior uncommitted phase and were edited in place. `Dockerfile` is the only tracked
modification. `outputs/` unchanged.)
