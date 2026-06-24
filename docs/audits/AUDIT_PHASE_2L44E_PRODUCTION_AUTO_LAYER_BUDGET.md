# Audit — Phase 2L.44E: Fix Production Docker Default Layer Budget to Auto 1/8

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** config/logging
fix (no commit, no API)

Resolves the gap flagged by 2L.44D: the `argparse` default for `--v12b-max-qids` /
`--v13-max-qids` was `auto`, but the `production_full_system` / `production_full_system_noapi`
profiles still set `"all"`, so `run_full_system.sh` and Docker used `all` instead of the desired
`auto`. The final-submission policy is now enforced everywhere: with no explicit flags,
V12B/V13 caps default to `auto = ceil(input_count / 8)` (minimum 1).

## Files changed

- `configs/profiles/run_profiles.json` — `production_full_system` and
  `production_full_system_noapi`: `v12b_max_qids`/`v13_max_qids` `"all"` → `"auto"`.
- `src/fastmcq_system.py` — added `v12b_max_qids_source`/`v13_max_qids_source` to
  `FastMCQSystemConfig` and a `_fmt_cap()` helper; the `[FASTMCQ]` log now renders
  `auto(<cap>/<N>)` / `all(<N>)` / `<int>`.
- `scripts/tools/final_infer.py` — passes the raw flag spec (`v12b/v13_max_qids_source`) into the
  system config so the log can show `auto(...)`.
- `tests/integration/test_production_auto_budget_2l44e.py` — **new** (9 tests, no API).
- `README.md` / `FINAL_RUN.md` / `DOCKER_SUBMISSION.md` — documented the default layer budget.
- `scratch/smoke_api/smoke5_arbitrary_qids.json` — recreated (gitignored smoke fixture, was
  cleaned).

Files inspected (unchanged): `configs/production/default.json`, `configs/production/noapi.json`
(neither carries max-qid keys — caps come from the profile), `scripts/run_full_system.sh`,
`scripts/docker_entrypoint_v11.sh`.

## Exact default max-qid behavior

`_resolve_maxq(v, n_input)` (in `scripts/tools/final_infer.py`):
- `None` / `''` / `'all'` → `None` → **every input qid** (logged `all(N)`)
- `'auto'` (**the default**, set by the production profiles and the bare CLI) →
  `ceil(n_input / 8)`, **minimum 1** (logged `auto(<cap>/<N>)`)
- an int / numeric string → that int (logged as the int)

Verified examples: **3 → 1**, **463 → 58**, **2000 → 250**, 1 → 1, 8 → 1, 9 → 2. No hardcoded
size anywhere (the formula derives the cap from the resolved input count).

Required behaviors confirmed:
- `bash scripts/run_full_system.sh <test_file>` → `auto` (default profile is
  `production_full_system` with key, `production_full_system_noapi` without).
- Docker no-flag run → `auto` (entrypoint selects the same profiles).
- `--v12b-max-qids 50 --v13-max-qids 50` → still `50`.
- `--v12b-max-qids all --v13-max-qids all` → still all input qids (`all(N)`).

## run_full_system default now uses auto

```
bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  [FASTMCQ] ... profile=production_full_system_noapi ... v12b_max_qids=auto(1/5) v13_max_qids=auto(1/5)
  status  : PASS ; final -> output/pred.csv (via FASTMCQ_FINAL_DIR in the smoke)
```
(Test `test_run_full_system_default_uses_auto_no_api` asserts `auto(1/3)` for N=3;
`test_explicit_cap_overrides_auto_no_api` asserts `=5`; `test_explicit_all_overrides_auto_no_api`
asserts `all(10)`.)

## Docker default now uses auto

```
docker build -t fastmcq-final .
# data/private_test.csv with 3 qids; run WITHOUT OPENROUTER_API_KEY:
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/docker_output:/output" fastmcq-final
  [entrypoint] profile: production_full_system_noapi
  [entrypoint] api    : off (no OPENROUTER_API_KEY -> no-api fallback)
  [FASTMCQ] input_count=3 ... v12b_max_qids=auto(1/3) v13_max_qids=auto(1/3)
  [FASTMCQ] output_written path=/output/pred.csv ; status: PASS
  docker_output/pred.csv:
    qid,answer
    z1,B
    z2,A
    z3,A
```
`docker_output/pred.csv` exists with the `qid,answer` header. (Temp `data/` + `docker_output/`
were removed after the smoke; `data/.gitkeep` restored.)

## Tests run / results

- `.venv/bin/python -m compileall -q src scripts tests` → **OK**
- `.venv/bin/python -m pytest -q` → **765 passed** (756 baseline + 9 new in 2L.44E; legacy
  deselected)
- `.venv/bin/python scripts/audit_model_policy.py` → **RESULT: PASS — only competition-allowed
  models referenced**
- `bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api` →
  **status PASS**, `v12b_max_qids=auto(1/5)`

New `test_production_auto_budget_2l44e.py` covers: production profiles default to `auto` (and not
`all`); auto formula (3→1, 463→58, 2000→250, min 1); explicit int / `all` overrides;
`_fmt_cap` rendering (`auto(1/3)`, `auto(250/2000)`, `all(N)`, int); end-to-end default uses auto
(no API); explicit int and `all` overrides end-to-end (no API); no hardcoded 463 in production
code/config.

## Confirmations

- **No API calls** — smoke and Docker run with `OPENROUTER_API_KEY` unset / `--no-api`; tests
  stub `SelectiveAPIClient` to throw if invoked.
- **No secret baked into Docker** — Dockerfile/entrypoint carry no key value; the no-key Docker
  run took the `production_full_system_noapi` fallback.
- **No hardcoded 463 / public-test / qids** — `test_no_hardcoded_463_in_production` scans
  `final_infer.py`, `fastmcq_system.py`, both production configs, `run_full_system.sh`, and the
  entrypoint (the only `463` is the cosmetic profile NAME `public_api463`, never a value); no
  dependency on `public-test_1780368312.json` in production logic.
- **Model-policy rules unchanged** — audit PASS.
- **Official artifacts preserved** — repo `output/` untouched; V13 md5
  `cb02fef569b31e7fb544abab46c0e282`.
- **Not committed.**

## Git status (this phase, cumulative with uncommitted 2L.44D)

```
 M DOCKER_SUBMISSION.md
 M FINAL_RUN.md
 M README.md
 M configs/profiles/run_profiles.json
 M scripts/docker_entrypoint_v11.sh
 M scripts/run_full_system.sh
 M scripts/tools/final_infer.py
 M src/fastmcq_system.py
 M tests/integration/test_btc_noarg_2l32b.py
?? docs/audits/AUDIT_PHASE_2L44D_BTC_IO_PRIORITY_AND_DEFAULTS.md
?? docs/audits/AUDIT_PHASE_2L44E_PRODUCTION_AUTO_LAYER_BUDGET.md
?? tests/integration/test_btc_io_priority_2l44d.py
?? tests/integration/test_production_auto_budget_2l44e.py
```
(2L.44D and 2L.44E are both uncommitted on top of `891db48`.) Nothing committed.

## Remaining final-submission steps

1. Commit the uncommitted 2L.44D + 2L.44E changes when ready (this phase does not commit).
2. Push the rebuilt `fastmcq-final` image to Docker Hub as
   `<dockerhub_username>/fastmcq-final:latest` (the image was rebuilt locally this phase).
3. Optionally run one budgeted `production_full_system` **API** check (none performed here) to
   confirm live V12B/V13 behavior end-to-end before submission.
