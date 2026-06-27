# Audit — Phase 2L.47A: Official BTC Submission Contract

**Date:** 2026-06-27  **Branch:** `main`  **Base commit:** `891db48`  **Status:** submission
contract (no commit, no real API)

Implements the confirmed Vietnamese Student HackAIthon — Bảng C Innovator submission contract
(input `/code/private_test.json` → `/code/submission.csv` + `/code/submission_time.csv`) via a new
root `predict.py` / `inference.sh`, a BTC-shaped `Dockerfile`, while preserving the legacy
`/data` → `/output/pred.csv` behaviour.

## BTC requirement summary

- Input: `/code/private_test.json` (filename exactly `private_test.json`).
- Outputs in `/code`: `submission.csv` (`qid,answer`) and `submission_time.csv`
  (`qid,answer,time`); time dumped **per sample**.
- Repo must contain `Dockerfile`, `predict.py` (end-to-end entry), `inference.sh`, `README.md`
  (pipeline flow, data processing, resource init, Docker reproduction).
- Docker default runs the pipeline (`inference.sh`).
- BTC HW: RTX 5060 Ti / 32 GB. CUDA 12.8+ only matters for GPU/vLLM teams — **this repo needs no
  local GPU/vLLM**, so no CUDA/vLLM deps were introduced.

## Gaps from the previous contract

- Old contract was `/data/private_test.csv|public_test.csv` → `/output/pred.csv` via
  `scripts/docker_entrypoint_v11.sh`. No `/code` JSON input, no `submission.csv` /
  `submission_time.csv`, no per-sample timing, no `predict.py` / `inference.sh`, Dockerfile
  `WORKDIR /app` + entrypoint script. All addressed below; legacy path preserved.

## Files changed

- **`predict.py`** (new, root) — official BTC entry point.
- **`inference.sh`** (new, root, executable) — `python predict.py "$@"`.
- **`Dockerfile`** — `WORKDIR /code`, `COPY . /code`, install `requirements.txt`,
  `ENTRYPOINT ["bash", "inference.sh"]`; lightweight `python:3.11-slim` base.
- **`Dockerfile.api`** (local-only, git-ignored) — mirrored to `/code` + `inference.sh`, keeps
  `ARG/ENV OPENROUTER_API_KEY`.
- **`requirements.txt`** — pinned (`PyYAML==6.0.3`, `httpx==0.28.1`, `pytest==9.1.0`).
- **`README.md`**, **`DOCKER_SUBMISSION.md`**, **`docs/METHOD.md`** — BTC contract documented.
- **`tests/integration/test_btc_submission_contract_2l47a.py`** (new, 9 tests).
- **`tests/integration/test_final_package_2l31a.py`** — `test_docker_default_not_v10` updated to
  the new Dockerfile shape.
- **`.dockerignore` / `.gitignore`** — added BTC smoke/output scratch dirs.

## `predict.py` behavior

- **Input resolution** (BTC-first): `--input` → `$INPUT_FILE` → `/code/private_test.json` →
  `/code/public_test.json` → `/app/data/*.json` → `/data/*.json` → `/data/private_test.csv` →
  `/data/public_test.csv`; clear early-fail otherwise.
- **Output resolution**: `--submission` / `$SUBMISSION_FILE` → `/code/submission.csv` (cwd
  fallback if `/code` unwritable); same for `--submission-time` / `$SUBMISSION_TIME_FILE` →
  `/code/submission_time.csv`.
- **Pipeline**: delegates to `scripts/tools/final_infer.py::main` (the SAME dynamic full-system
  pipeline) with `--input … --output <submission> --profile <production_full_system|_noapi>` — no
  prediction logic duplicated or altered. Profile chosen by `OPENROUTER_API_KEY` presence;
  `--no-api` forces offline. Extra flags (`--model`, `--budget-usd`, …) are forwarded.
- **Outputs**: `submission.csv` is the pipeline's `qid,answer` artifact directly;
  `submission_time.csv` is built from it + the per-sample time; predictions are mirrored to
  `/output/pred.csv` (when writable) and to `--output`/`$OUTPUT_FILE` if given.

## `inference.sh` behavior

`set -euo pipefail; python predict.py "$@"` — forwards all flags. Executable; `bash -n` clean.

## Dockerfile behavior

`FROM python:3.11-slim`, `WORKDIR /code`, install deps, `COPY . /code`, `chmod +x inference.sh`,
`ENTRYPOINT ["bash", "inference.sh"]`. ENTRYPOINT (not bare `CMD`) is used so the documented
`docker run <image> --submission … --no-api` flag-override commands forward args to
`inference.sh`, while `docker run <image>` with no args runs the BTC default — fulfilling the
"default runs inference.sh" requirement. No baked key; lightweight base, no CUDA/vLLM.

## Local `Dockerfile.api`

Updated on disk to mirror the new Dockerfile (`/code` + `inference.sh` + `ARG/ENV
OPENROUTER_API_KEY`); **kept git-ignored and untracked** (`git check-ignore` →
`.gitignore:21`; `git ls-files` empty). No real key in it.

## Output files supported

- `/code/submission.csv` (`qid,answer`) — official.
- `/code/submission_time.csv` (`qid,answer,time`) — official, per-sample time.
- `/output/pred.csv` (`qid,answer`) — legacy compatibility mirror.

## Timing strategy

The production system is a single dynamic full-set selective run (NOT one call per question — by
design, to preserve the selective budget and avoid cost blow-up). Per Part A's documented
fallback, `predict.py` measures the **total wall-time** of the pipeline and writes a **positive
per-sample value** = `total / N` (rounded, ≥ 1e-6) for every qid in `submission_time.csv`.
Predictions are unchanged (no instrumentation inside the core system). This is documented in the
README and METHOD: timing is dumped per sample while inference stays a full-set run.

## requirements.txt changes / pinning decision

Pinned the direct runtime deps to the validated environment: `PyYAML==6.0.3`, `httpx==0.28.1`
(critical — the real OpenRouter path), and `pytest==9.1.0` (test-only). `torch` /
`transformers` / `sentence-transformers` / `numpy` are imported only by OPTIONAL local HF solvers
and are intentionally **not** listed (the dynamic_full pipeline doesn't need them; those paths
fail closed) — keeps the image lightweight and CPU-only. Documented inline.

## Tests added/updated

New `test_btc_submission_contract_2l47a.py` (9): both files written with exact headers
(`qid,answer` / `qid,answer,time`); qids match input in order; answer columns consistent; time
numeric and > 0; BTC input priority (`/code/private_test.json` first); env overrides
(`SUBMISSION_FILE` / `SUBMISSION_TIME_FILE`); legacy `--output` mirror; `run_full_system.sh` still
works; Dockerfile shape (`WORKDIR /code`, `inference.sh`, `COPY . /code`, no CUDA base, no baked
key); `inference.sh` calls `predict.py`; `predict.py` compiles; `.env`/`Dockerfile.api` untracked.
Updated `test_docker_default_not_v10` for the inference.sh/predict.py Dockerfile.

## Docker no-API smoke results (image `:btc-contract-test`)

- **Official BTC JSON contract** (explicit `--submission`/`--submission-time`, `--no-api`):
  `submission.csv` = `qid,answer` / `btc_json_001,B` / `btc_json_002,A`; `submission_time.csv` =
  `qid,answer,time` with `time=0.027` (> 0); `profile=production_full_system_noapi` (api off);
  **status PASS**.
- **Default `/code` write** (no output override, `--no-api`): logs `wrote /code/submission.csv` and
  `wrote /code/submission_time.csv`; **status PASS**.
- **Legacy `/data`** (`private_test.csv`, `--no-api`): input detected `/data/private_test.csv`;
  mirrored → host `/output/pred.csv` = `qid,answer` / `compat_001,B` / `compat_002,A`;
  **status PASS**.

All smokes ran with no API. Test image and smoke dirs were removed afterward.

## Secret-safety proof

- `git check-ignore -v .env` → `.gitignore:15`; `git check-ignore -v Dockerfile.api` →
  `.gitignore:21`.
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$)'` → **none tracked**.
- key-like scan over new/changed tracked files (excl audits) → only the allowed shell placeholder
  `-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"` in README/DOCKER_SUBMISSION. **No real key.**

## Validation results

- `compileall -q src scripts tests predict.py` → **OK**
- `pytest -q` → **780 passed** (771 prior + 9 new; 1 updated)
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**

## Confirmations

- **No real API calls** — smokes `--no-api`; tests stub `SelectiveAPIClient` to throw if called.
- **No core model logic changed** — `predict.py` is a wrapper around the existing pipeline; no
  timing instrumentation was added inside the core system (wrapper-level total-time fallback).
  Model policy unchanged.
- **No qid/answer/`463`/public-test-size hardcoding** in the new code.
- **No secret committed**; `.env` / `Dockerfile.api` git-ignored/local-only.
- **Not committed.**

## Git status (this phase)

```
 M .dockerignore
 M .gitignore
 M DOCKER_SUBMISSION.md
 M Dockerfile
 M README.md
 M docs/METHOD.md
 M requirements.txt
 M tests/integration/test_final_package_2l31a.py
?? inference.sh
?? predict.py
?? tests/integration/test_btc_submission_contract_2l47a.py
?? docs/audits/AUDIT_PHASE_2L47A_BTC_OFFICIAL_SUBMISSION_CONTRACT.md
# Dockerfile.api present on disk, git-ignored (NOT shown).
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E / 2L.45A–C / 2L.46A–D changes.) Nothing committed.

## Remaining steps

1. **Rebuild `:no-key`** from the new Dockerfile:
   `docker build -t vquclinh/fastmcq-agent:no-key .`
2. **Rebuild local `:api-baked`** (git-ignored Dockerfile.api, disposable key):
   `set -a; source .env; set +a; docker build -f Dockerfile.api --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" -t vquclinh/fastmcq-agent:api-baked .`
3. **Tag/push `:latest`**: `docker tag vquclinh/fastmcq-agent:api-baked vquclinh/fastmcq-agent:latest`
   then push `:no-key`, `:api-baked`, `:latest`.
4. Optionally run one **tiny real-API Docker smoke** to confirm live V12B/V13 end-to-end.
5. **Commit** the accumulated phases — review `git status`; never `git add -f` `.env` /
   `Dockerfile.api`.
