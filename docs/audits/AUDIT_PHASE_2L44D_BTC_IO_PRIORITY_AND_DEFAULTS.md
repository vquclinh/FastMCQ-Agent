# Audit — Phase 2L.44D: BTC Input/Output Priority and Default Fallback Contract

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** I/O contract
(no commit, no API)

Goal: make Docker and local full-system execution follow the EXACT input/output priority, with
an explicit input always overriding the `/data/*` defaults.

## Files inspected

- `scripts/run_full_system.sh`
- `scripts/docker_entrypoint_v11.sh` (Dockerfile ENTRYPOINT)
- `scripts/docker_entrypoint.sh` (legacy pipeline entry — not the active ENTRYPOINT)
- `scripts/tools/final_infer.py` (the real module; `scripts/final_infer.py` is a shim)
- `Dockerfile`, `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`
- I/O tests: `tests/integration/test_btc_noarg_2l32b.py`,
  `tests/integration/test_full_system_output_contract_2l41a.py`,
  `tests/integration/test_final_package_2l31a.py`, `configs/profiles/run_profiles.json`

## Files changed

- `scripts/tools/final_infer.py` — input/output priority, early-fail message, `auto` max-qid.
- `scripts/docker_entrypoint_v11.sh` — API-key-based profile selection; priority banner; lets
  `final_infer.py` own the I/O resolution.
- `scripts/run_full_system.sh` — optional positional input; API-key-based profile fallback.
- `tests/integration/test_btc_noarg_2l32b.py` — local-default assertion updated to
  `output/pred.csv`; output env cleared.
- `tests/integration/test_btc_io_priority_2l44d.py` — **new** (18 tests, no API).
- `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md` — documented exact priority + overrides.

## Exact input priority (implemented)

```
1. --input <path>            (CLI argument)            — wins over everything
2. $INPUT_FILE               (then legacy $FASTMCQ_INPUT), if set and non-empty
3. /data/private_test.csv
4. /data/public_test.csv
5. /data/private_test.json
6. /data/public_test.json
   then other known names (doc_public_test.*, public-test*.json), cwd equivalents,
   then a lone .csv/.json under /data.
```
An explicit input (CLI `--input` **or** `$INPUT_FILE`) overrides the `/data/*` defaults even
when `/data/private_test.csv` exists. `_INPUT_CANDIDATES` reordered to private.csv → public.csv
→ private.json → public.json. Empty `$INPUT_FILE` (set but blank) is ignored.

## Exact output priority (implemented)

```
1. --output <path>           (CLI argument)
2. $OUTPUT_FILE              (then legacy $FASTMCQ_OUTPUT), if set and non-empty
3. /output/pred.csv          (Docker default, when /output exists or is creatable)
4. output/pred.csv           (local default)
```
Local default changed from `pred.csv` → `output/pred.csv`.

## Early-fail on missing input

`_resolve_input` raises a clear `SystemExit` listing all six expected defaults in priority order
and stating that `--input` or `$INPUT_FILE` overrides the `/data` defaults. Verified by
`test_missing_input_fails_early_with_clear_message` and the no-arg timing test (prints
`status: FAIL`).

## API-key behavior (no secret baked in)

- `docker_entrypoint_v11.sh` and `run_full_system.sh`: `OPENROUTER_API_KEY` present →
  `production_full_system` (API); absent → `production_full_system_noapi` (offline, still writes
  `pred.csv`). `--no-api` always forces offline.
- No key is ever baked into the image (Dockerfile has no `ENV/ARG OPENROUTER_API_KEY=`; verified
  by `test_no_secret_baked_in_dockerfile`). The key is supplied by the evaluator's container env.

## Max-qid default

`_resolve_maxq(v, n_input)` accepts: `None`/`''`/`'all'` → None (every qid); `'auto'` (the new
CLI default) → `ceil(n_input / 8)`, minimum 1; int/numeric → that int. The `--v12b-max-qids` /
`--v13-max-qids` argparse defaults are now `'auto'`. The frozen production profiles still set
`'all'` explicitly (CLI/profile values override the default), so `run_full_system.sh` and the
Docker entrypoint keep `'all'` — the bare `final_infer.py` CLI is the only path that defaults to
`auto`. **No hardcoded count (no `463`)** anywhere in `final_infer.py`.

## Tests run / results

- `.venv/bin/python -m compileall -q src scripts tests` → **OK**
- `.venv/bin/python -m pytest -q` → **756 passed** (738 baseline + 18 new in 2L.44D; legacy
  deselected)
- `.venv/bin/python scripts/audit_model_policy.py` → **RESULT: PASS — only competition-allowed
  models referenced**

New `test_btc_io_priority_2l44d.py` covers: CLI input > `/data/private_test.csv`; `$INPUT_FILE` >
`/data/private_test.csv`; empty `$INPUT_FILE` ignored; private default used only without explicit
input; private > public; csv > json; missing-input clear early-fail; CLI `--output` >
`$OUTPUT_FILE`; `$OUTPUT_FILE` > `/output/pred.csv`; Docker → local default; legacy aliases;
INPUT_FILE+OUTPUT_FILE end-to-end (no API); `auto` max-qid math; no baked secret; entrypoint &
wrapper profile selection; `run_full_system.sh` resolves input from `$INPUT_FILE` end-to-end.

## Docker smoke (no API performed)

Run via the shell entrypoint and the official wrapper (no Docker daemon needed for the I/O
contract; no real API):

```
# entrypoint, no OPENROUTER_API_KEY, INPUT_FILE override:
INPUT_FILE=<sandbox>/data/private_test.csv OUTPUT_FILE=<sandbox>/ep_out.csv \
  bash scripts/docker_entrypoint_v11.sh
  -> profile: production_full_system_noapi ; api: off ; input: <INPUT_FILE> ; status: PASS
  -> ep_out.csv = qid,answer / z1,B / z2,A   (private input honored; public_test.csv ignored)

# official wrapper, no key, optional input via $INPUT_FILE:
FASTMCQ_FINAL_DIR=<sandbox>/final INPUT_FILE=<sandbox>/data/private_test.csv \
  bash scripts/run_full_system.sh --no-api
  -> status: PASS ; final/pred.csv = z1,z2 (NOT public p1)
```
Confirms: explicit input overrides `/data/*` defaults; no-key → no-api fallback still writes
`pred.csv`; production profile keeps `max_qids=all`.

## Confirmations

- **No API calls** — all smokes ran with `OPENROUTER_API_KEY` unset / `--no-api`; tests stub
  `SelectiveAPIClient` to throw if called.
- **No secret baked into the image** — Dockerfile/entrypoint/wrapper carry no key value
  (`test_no_secret_baked_in_dockerfile`, content assertions).
- **No hardcoded `463` / public-test dependency / qids / answers** — `"463" not in final_infer.py`
  (test); production logic never depends on `public-test_1780368312.json` (only a last-resort
  autodetect candidate); no `test_####` literals in changed scripts/configs.
- **Model-policy rules unchanged** — audit PASS.
- **Official artifacts preserved** — repo `output/` untouched; V13 md5
  `cb02fef569b31e7fb544abab46c0e282`.
- **`run_full_system.sh` and Docker `/data` → `/output/pred.csv` contract intact.**
- **Not committed.**

## Final BTC Docker command

```bash
docker run --rm \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  <dockerhub_username>/fastmcq-final:latest
```

### Advanced override examples

```bash
# Custom input/output via env (overrides the /data defaults):
docker run --rm \
  -e INPUT_FILE=/data/custom_test.csv \
  -e OUTPUT_FILE=/output/custom_pred.csv \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  <dockerhub_username>/fastmcq-final:latest

# CLI input path (overrides all /data/* defaults AND $INPUT_FILE):
docker run --rm \
  -v "$PWD/data:/data:ro" -v "$PWD/output:/output" \
  <dockerhub_username>/fastmcq-final:latest --input /data/custom_test.csv
```

## Git status (this phase)

```
 M DOCKER_SUBMISSION.md
 M FINAL_RUN.md
 M README.md
 M scripts/docker_entrypoint_v11.sh
 M scripts/run_full_system.sh
 M scripts/tools/final_infer.py
 M tests/integration/test_btc_noarg_2l32b.py
?? tests/integration/test_btc_io_priority_2l44d.py
?? docs/audits/AUDIT_PHASE_2L44D_BTC_IO_PRIORITY_AND_DEFAULTS.md
```
Nothing committed.
