# Audit — Phase 2L.39D: Layer-Only API Profiles

**Date:** 2026-06-24  **Branch:** `main`  **Status:** profile/flag addition (no commit, no API)

## Root reason for adding a layer-only profile

`public_api50` (and the other API profiles) let the **base predictor** call the model for every
qid the deterministic formula bank does not solve (~445/463 on the public test). That is the
bulk of the API cost and is not where V12B/V13 add value. We want a profile where **API is used
ONLY by the V12B/V13 verifier layers** on a capped set of high-risk qids, while the base
predictor stays fully deterministic/no-API — full output for every input qid, no public replay,
no previous-best seed.

## Files changed

- **`src/fastmcq_system.py`** — `FastMCQSystemConfig.base_execute_api: bool | None = None`; the
  base predictor now runs with `base_api = execute_api if base_execute_api is None else
  base_execute_api` (independent of the layer API gate). The `[FASTMCQ]` start log now prints
  `base_execute_api`, `layer_execute_api`, `v12b_max_qids`, `v13_max_qids`, and
  `public_replay=disabled`; `progress.json` `base_start` records both API flags.
- **`scripts/final_infer.py`** — `--base-execute-api` / `--no-base-api` flags (tri-state, default
  None → inherit `--execute-api`); profile mapping for `base_execute_api`; passes it into the
  config.
- **`configs/run_profiles.json`** — new `public_layer_api50` profile.
- **`scripts/run_public_layer_api50.sh`** — short wrapper.
- **`FINAL_RUN.md`** — documents the new short command.

## Exact profile semantics (`public_layer_api50`)

```json
{ "mode": "dynamic_full", "execute_api": true, "base_execute_api": false,
  "model": "qwen/qwen3.5-9b-20260310", "budget_usd": 1.50,
  "enable_v12b": true, "enable_v13": true,
  "v12b_max_qids": 50, "v12b_permutations": 6, "v12b_policy": "conservative",
  "v13_max_qids": 50, "system_policy": "conservative", "max_overrides": 30 }
```
- `base_execute_api=false` → base predictor uses **formula/deterministic/fallback only** (no API,
  no `dynamic_api` sources).
- `execute_api=true` → the **V12B/V13 layers** may call the allowed model on capped high-risk
  qids (`assert_allowed_llm_model` still enforced at call time).
- Full output for **every** input qid; `public_replay` never triggers (dynamic_full); no
  previous-best seed; works on arbitrary/private qids.
- CLI flags override the profile (e.g. `--no-api` for a fully offline dry run; `--base-execute-api`
  to re-enable base API). `base_execute_api=None` (unset) inherits `execute_api` → existing
  profiles behave exactly as before (no public-replay behavior change).

## Run-start log (Part 6)

```
[FASTMCQ] input_count=<N> output=<path> work_dir=<path> mode=dynamic_full profile=<profile> \
          base_execute_api=<bool> layer_execute_api=<bool> v12b_max_qids=<n> v13_max_qids=<n> \
          public_replay=disabled
```

## Tests run and results (Part 8)

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_layer_only_api_profile_2l39d.py`: **8 passed**
- `pytest -q` (full suite): **739 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

Coverage: profile exists with expected values; wrapper exists + `bash -n` valid;
`base_execute_api=false` keeps the base offline (no `[BASE] source=api` lines) while layers run
(fake client called > 0); `base_execute_api=None` inherits `execute_api`; arbitrary private qid
(`weird_qid_!42`) outputs exactly that qid; system modules carry no public-CSV dependency; no
qid/answer hardcoding. No real API (fake client injected / offline paths).

## Confirmations

- **No API calls** — fake client / offline `--no-api` paths only; model policy enforced before
  any (mocked) layer call.
- **No qid/answer hardcoding** — profile + wrapper + system modules regex-clean (tested).
- **Official V13 79.7 artifact unchanged** — `outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`
  md5 still `cb02fef569b31e7fb544abab46c0e282`.
- **Old run dirs untouched** — `scratch/runs/public_api50_20260624_005107/` and
  `scratch/runs/smoke_api50_patch_20260624_020447/` not modified/deleted.
- **No model-policy rules changed.**
- **Not committed.**

## Git status

```
 M configs/run_profiles.json  scripts/final_infer.py  src/fastmcq_system.py  FINAL_RUN.md
?? scripts/run_public_layer_api50.sh
?? tests/test_layer_only_api_profile_2l39d.py
?? docs/audits/AUDIT_PHASE_2L39D_LAYER_ONLY_API_PROFILES.md
```
(`scratch/` and `outputs/pred.csv` remain gitignored.) Nothing committed.

## Recommended small smoke command (offline, no API)

```bash
python scripts/final_infer.py --profile public_layer_api50 --no-api \
  --input public-test_1780368312.json --output scratch/layer_smoke/pred.csv \
  --work-dir scratch/layer_smoke/work
# -> base_execute_api=False layer_execute_api=False (overridden), exactly-input qids, PASS
```

## Recommended full public layer-api50 command (requires OPENROUTER_API_KEY)

```bash
bash scripts/run_public_layer_api50.sh public-test_1780368312.json
# base predictor deterministic (no API); only V12B/V13 call the model on up to 50 high-risk
# qids each; budget $1.50; logs + incremental JSONL + progress.json under scratch/runs/.
```
