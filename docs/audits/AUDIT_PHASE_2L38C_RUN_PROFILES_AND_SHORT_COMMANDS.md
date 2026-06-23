# Audit — Phase 2L.38C: Run Profiles and Short Commands

**Date:** 2026-06-24  **Branch:** `main`  **Status:** packaging convenience (no commit, no API)

> The V13 79.7 dynamic system was committed in `0a7b9d6` before this phase. This phase adds
> run profiles + short wrapper scripts on top — no behavior change to the pipeline.

## Files created / changed

**Created:**
- `configs/run_profiles.json` — 7 named profiles.
- `scripts/run_public_replay.sh`, `run_dynamic_noapi.sh`, `run_public_api100.sh`,
  `run_private_noapi.sh`, `run_private_api200.sh` — short wrappers.
- `tests/test_run_profiles_2l38c.py` — 12 tests.
- `docs/audits/AUDIT_PHASE_2L38C_…md` — this audit.

**Changed:**
- `scripts/final_infer.py` — `--profile` flag + `_load_profiles`/`_apply_profile`; profile name
  printed in logs and the completion/failure blocks. CLI flags always override profile values;
  unknown profile fails clearly; profiles never bypass model-policy.
- `FINAL_RUN.md`, `README.md`, `DOCKER_SUBMISSION.md` — short commands shown first; full command
  kept as the explicit/advanced form.

## Profiles added (`configs/run_profiles.json`)

`public_replay`, `dynamic_noapi`, `public_noapi`, `public_api100`, `public_api463`,
`private_noapi`, `private_api200`. API profiles set `execute_api: true` + the allowed model
`qwen/qwen3.5-9b-20260310` + budget + V12B/V13 caps + system policy.

## Wrapper scripts added

Five `scripts/run_*.sh`: each `set -euo pipefail`, makes a timestamped `scratch/runs/<profile>_<ts>/`
dir, runs `final_infer.py --profile <name>` (forwarding extra flags), tees `run.log`, and prints
profile, output path, **md5**, **elapsed (s + m:s)**, log path, and PASS/FAIL. They use the repo
`.venv` python if present. No hardcoded qids/answers.

## Timing output behavior (Part C)

`final_infer.py` always prints `resolved mode`, `profile` (if used), `output`, `md5`,
`elapsed_seconds`, and `status` (success and failure paths). Wrappers additionally print
wall-clock elapsed in `s` and `m:s`.

## Smoke results (Part E, no API)

```
run_public_replay.sh public-test… -> md5 cb02fef569b31e7fb544abab46c0e282  status PASS
run_dynamic_noapi.sh public-test… -> dynamic_full V12B+V13 enabled (no api)  status PASS
run_private_noapi.sh <fake private> -> exactly the input qids, valid labels   status PASS
```
Also verified directly: `--profile public_replay` → md5 `cb02fef5…`; `--profile dynamic_noapi`
→ dynamic_full no-api; unknown profile → clear `REFUSING: unknown profile …`; CLI `--no-api`
overrides `public_api100`'s `execute_api`.

## Tests and model-policy results (Part D)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_run_profiles_2l38c.py`: **12 passed**
- `pytest -q` (full suite): **717 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

Coverage incl.: profile loading; CLI override; unknown-profile failure; public_replay →
public_replay; dynamic_noapi → dynamic_full + no API (client patched to fail); public_api100
caps; **profile cannot bypass model_policy** (disallowed `--model gpt-4o` over an API profile
still raises); api-profile models all allowed; final_infer works without a profile; wrappers
exist + `bash -n` valid + reference their profiles; public_replay md5 == V13 79.7; dynamic
private no-api outputs exact qids; no qid/answer hardcoding.

## Confirmations

- **No API calls** during coding or smokes — only `public_replay` (copy) and `--no-api`
  dynamic runs; API profiles were not executed; model-policy guards remain in the layers.
- **No qid/answer hardcoding** — profiles + wrappers regex-clean; no public qids embedded.
- **Official V13 79.7 artifact unchanged** — `outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`
  md5 still `cb02fef569b31e7fb544abab46c0e282`.
- **No model-policy rules changed.**
- **Not committed.**

## Recommended short commands

```bash
bash scripts/run_public_replay.sh public-test_1780368312.json
bash scripts/run_dynamic_noapi.sh public-test_1780368312.json
bash scripts/run_public_api100.sh public-test_1780368312.json
bash scripts/run_private_api200.sh private_test.json
```

## Git status

```
 M DOCKER_SUBMISSION.md  FINAL_RUN.md  README.md  scripts/final_infer.py
?? configs/run_profiles.json
?? scripts/run_public_replay.sh  run_dynamic_noapi.sh  run_public_api100.sh
?? scripts/run_private_noapi.sh  run_private_api200.sh
?? tests/test_run_profiles_2l38c.py
?? docs/audits/AUDIT_PHASE_2L38C_RUN_PROFILES_AND_SHORT_COMMANDS.md
```
(`scratch/` incl. `scratch/runs/` and `outputs/pred.csv` remain gitignored.) Nothing committed.
