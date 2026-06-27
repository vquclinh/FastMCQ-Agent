# Audit — Phase 2L.47B: Final Offline Local Qwen3-4B Docker Submission

**Date:** 2026-06-27  **Branch:** `main`  **Base commit:** `891db48`  **Status:** offline pivot
(no commit, no real API, no model build/run in this phase)

Pivots the final submission from API-based dynamic inference to a **fully offline, single
open-weight local model** to satisfy BTC's internet-isolated, no-external-API, ≤5B rule.

## BTC rule interpretation

Private-test runtime is internet-isolated → no OpenRouter / external API / web search / external
retrieval at runtime; one open-weight model with ≤5B params; official input `/code/private_test.json`;
outputs `/code/submission.csv` (`qid,answer`) + `/code/submission_time.csv` (`qid,answer,time`,
per-sample); GPU solutions target CUDA 12.8+ on an RTX 5060 Ti / 32 GB. Local Transformers (not
vLLM) → requires `--gpus all`, not `--ipc=host`.

## Chosen model & why it is the strongest compliant choice

`Qwen/Qwen3-4B-Instruct-2507` — a dense **4.0B-parameter** (< 5B) instruct model from the open
Qwen3 family, **Apache-2.0** (per Qwen model card / docs). It is the strongest option under the
≤5B cap (stronger than 0.5B/1.5B/3B variants) while remaining a single open-weight model suitable
for instruction-following MCQ reasoning. Parameter count / license should be reconfirmed against
the model card at build time; the audit records the basis for the choice.

## Files changed

- **`src/local_model/__init__.py`, `src/local_model/qwen_mcq_predictor.py`** (new) — local backend.
- **`predict.py`** — default path is now offline local inference (per-sample loop + real timing);
  `--legacy-dynamic-full` keeps the old API pipeline as dev-only.
- **`scripts/download_local_model.py`** (new) — build-time `snapshot_download` of the model.
- **`Dockerfile`** — CUDA 12.8 base + torch(cu128) + deps + model download + offline env +
  `ENTRYPOINT inference.sh`.
- **`Dockerfile.api`** (local-only, git-ignored) — mirrored; adds build-arg key for the dev path.
- **`requirements.txt`** — transformers/accelerate/safetensors/huggingface_hub/sentencepiece +
  PyYAML/pytest/httpx(legacy); torch installed in the Dockerfile (CUDA 12.8 index).
- **`README.md`, `DOCKER_SUBMISSION.md`, `docs/METHOD.md`** — offline contract, model, flags.
- **Tests:** new `test_btc_submission_contract_2l47a.py` (local backend stubbed); updated
  `test_final_package_2l31a` (Dockerfile/default), `test_btc_noarg_2l32b` / `test_btc_short_2l31b`
  / `test_run_profiles_2l38c` (doc guardrails → offline contract).
- **`.gitignore` / `.dockerignore`** — BTC smoke dirs (from 2L.47A).

## Final `predict.py` behavior

Input priority `--input`/`$INPUT_FILE` → `/code/private_test.json` → `/code/public_test.json` →
`/app/data/*.json` → `/data/*.json` → `/data/*.csv`. Loads the local model **once**, then per
question: time → `predict_one` → coerce to a valid label (or deterministic fallback `A`) → record
real elapsed seconds. Writes `/code/submission.csv` (`qid,answer`) and `/code/submission_time.csv`
(`qid,answer,time`, fixed-decimal seconds), and mirrors to `/output/pred.csv` (+ `--output`).
Does **not** call any API by default; `--no-api` is a compatibility no-op;
`--legacy-dynamic-full` is the only path that touches `final_infer.py` (dev only).

## Local model backend behavior

`QwenMCQPredictor(model_path, device="auto", max_new_tokens=64)`: lazy `torch`/`transformers`
imports in `load()` (module importable without them, so tests stub it); single load; GPU + bf16
when CUDA is available, else fp32; deterministic generation (`do_sample=False`, `num_beams=1`);
answer-only Vietnamese prompt with labeled choices; robust label parsing (first valid `A–K`).
`model_path` from CLI `--model-path` → `$LOCAL_MODEL_PATH` → `/models/qwen3-4b-instruct-2507`.

## Dockerfile CUDA 12.8+ behavior

`FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`; installs python3/pip/git; installs torch from
`https://download.pytorch.org/whl/cu128`; installs `requirements.txt`; copies code; downloads the
model (`ARG SKIP_MODEL_DOWNLOAD=0`, default builds the real model); sets `LOCAL_MODEL_PATH`,
`TRANSFORMERS_OFFLINE=1`, `HF_HUB_OFFLINE=1`; `ENTRYPOINT ["bash", "inference.sh"]` (forwards
flags; no-arg runs the BTC default). No vLLM; no `--ipc=host`.

## Model download behavior

`scripts/download_local_model.py` uses `huggingface_hub.snapshot_download` (no HF token needed for
this public model) into `/models/qwen3-4b-instruct-2507`, fetching safetensors + tokenizer/config
and skipping `.bin`/docs; warns if no `.safetensors` are found.

## Exact model path

`/models/qwen3-4b-instruct-2507` (`DEFAULT_MODEL_PATH`; `ENV LOCAL_MODEL_PATH`).

## requirements changes

Pinned/constrained direct deps: `transformers>=4.51.0` (Qwen3 support), `accelerate>=0.30.0`,
`safetensors>=0.4.3`, `huggingface_hub>=0.23.0`, `sentencepiece>=0.2.0`, `PyYAML==6.0.3`,
`httpx==0.28.1` (legacy/dev only), `pytest==9.1.0`. **torch is installed in the Dockerfile** from
the CUDA 12.8 wheel index (cannot encode the index URL cleanly in requirements). These were not
locally importable (no GPU/torch in the dev env) and will be validated at the real Docker build
(remaining step).

## Docs changes

README, DOCKER_SUBMISSION, METHOD now lead with the offline local-model contract, the
`Qwen3-4B-Instruct-2507` model, `--gpus all` (no `--ipc=host`), build-time model download, offline
env, and "no API / no internet at runtime." `api-baked` / OpenRouter are demoted to clearly
labeled **legacy/dev-only** notes (e.g. a collapsed `<details>` block), never advertised as the
final mode.

## Tests added/updated

`test_btc_submission_contract_2l47a.py` (local backend stubbed): both files written with exact
headers; qids match input; per-sample time measured around each sample (≥ 8 ms with a sleeping
stub → not an average); deterministic fallback when the model returns nothing; default model path
`/models/qwen3-4b-instruct-2507`; env output overrides; legacy `/output` mirror; input priority
`/code` first; Dockerfile offline shape (CUDA 12.8, download, offline env, no baked key); download
script targets Qwen3-4B; `predict.py` default is offline-local; `.env`/`Dockerfile.api`/weights
not tracked. Updated legacy doc-guardrail tests to the offline contract.

## Confirmations

- **No external API in the final path** — default `predict.py` runs the local model; the only API
  code path is the explicit dev `--legacy-dynamic-full` flag.
- **No OpenRouter final mode** — docs advertise offline local only; `OPENROUTER_API_KEY` is not
  required and not baked into the committed image.
- **Designed for network isolation** — weights baked at build; `TRANSFORMERS_OFFLINE=1` /
  `HF_HUB_OFFLINE=1`; no vector DB; verifiable with `--network none`.
- **Single model** — exactly one LLM (`Qwen3-4B-Instruct-2507`).
- **No qid/answer/`463`/public-test-size hardcoding**; fallback is the deterministic first label.
- **No secret / model weights tracked** — `.env`, `Dockerfile.api`, `models/` git-ignored;
  `git ls-files models/` empty.

## Required Docker run flags

`--gpus all` (local Transformers GPU inference). **`--ipc=host` not required** (no vLLM). No
`-e OPENROUTER_API_KEY`, no network.

## Secret / model-weight tracking proof

- `git check-ignore -v .env | Dockerfile.api | models` → all ignored.
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|^models/…weights)'` → none.
- key-like scan over tracked files: only allowed shell placeholders / legacy `<details>` notes;
  no real key.

## Validation results

- `compileall -q src scripts tests predict.py` → **OK**
- `pytest -q` → **784 passed** (local backend stubbed; no download/network/API)
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**
  (the scanner flags banned vendors / Qwen>9B; `Qwen3-4B` is clean and the root `predict.py` /
  `Dockerfile` are outside the scan dirs). **Model policy was NOT modified.**
- Docker image **not built** this phase (CUDA base + torch + 4B download is multi-GB; per Part I
  it is a remaining step). Dockerfile verified statically (download cmd, offline env, CUDA base).

## Known risks

- torch/transformers/model versions are **unvalidated in the dev env** (no GPU/torch installed);
  the real Docker build must confirm `transformers>=4.51` loads Qwen3-4B and the cu128 torch wheel
  matches the runtime driver. Qwen3-4B param-count/license to be reconfirmed from the model card.
- The model download needs network **at build time** (only); the final image is offline.
- Image size: CUDA runtime + torch + 4B weights ≈ several GB — expected for a local-model GPU
  submission.

## Git status (this phase)

```
 M .dockerignore   .gitignore   DOCKER_SUBMISSION.md   Dockerfile   README.md
 M docs/METHOD.md   requirements.txt
 M tests/integration/{test_btc_noarg_2l32b,test_btc_short_2l31b,test_final_package_2l31a,test_run_profiles_2l38c}.py
?? predict.py   inference.sh   scripts/download_local_model.py   src/local_model/
?? tests/integration/test_btc_submission_contract_2l47a.py
?? docs/audits/AUDIT_PHASE_2L47A_… .md   docs/audits/AUDIT_PHASE_2L47B_… .md
# Dockerfile.api present on disk, git-ignored (NOT shown).
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E / 2L.45A–C / 2L.46A–D / 2L.47A changes.) Nothing committed.

## Remaining steps

1. **Build the real image with the model** (network available at build):
   `docker build -t vquclinh/fastmcq-agent:latest .`
2. **Test with `--gpus all`** on a tiny `private_test.json` → check `submission.csv` /
   `submission_time.csv` (headers, qids, positive per-sample time).
3. **Test with `--network none`** to confirm true offline operation.
4. **Push** `vquclinh/fastmcq-agent:latest` to Docker Hub.
5. **Commit** the accumulated phases — review `git status`; never `git add -f` `.env` /
   `Dockerfile.api` / model weights.
