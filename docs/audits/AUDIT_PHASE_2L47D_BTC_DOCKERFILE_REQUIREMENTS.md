# Audit — Phase 2L.47D: BTC Dockerfile Requirement Compliance Check

**Date:** 2026-06-27  
**Scope:** BTC Dockerfile sections 2.1, 2.2, 2.3, 2.4 only.  
**Status:** PASS for static Dockerfile/docs contract; PARTIAL for manual Docker pre-submit checks
because Docker build/run/push were intentionally not executed in this phase.

## Summary

Final submission direction confirmed: offline local GPU inference with
`Qwen/Qwen3-4B-Instruct-2507` through Hugging Face Transformers. No OpenRouter final path, no
runtime internet, no API key, no vLLM, no `--ipc=host`, no `--shm-size`.

Key changes made in this phase:

- `Dockerfile`: switched from `ENTRYPOINT ["bash", "inference.sh"]` to strict BTC-template
  `CMD ["bash", "inference.sh"]`.
- `Dockerfile`: exact-pinned PyTorch CUDA 12.8 wheel install to `torch==2.7.1` from the `cu128`
  index.
- `README.md`, `DOCKER_SUBMISSION.md`, `docs/METHOD.md`: documented CUDA 12.8+ rationale,
  `CMD` behavior, environment-variable output overrides, no vector DB/index, no vLLM, no IPC/shm
  flags, and manual pre-submit commands.
- `docs/BTC_SUBMISSION_COMPLIANCE.md`: created stable BTC 2.1-2.4 checklist and manual command
  reference.
- `tests/integration/test_btc_submission_contract_2l47a.py`: added regression checks for Dockerfile
  CUDA/pinning/model-download/CMD shape and manual Docker command docs.

## BTC 2.1 — General Dockerfile Principles

**Status: PASS (manual final build still required).**

Evidence:

- Clean official base image: `Dockerfile:12`
  uses `FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- No old team/local base image: static grep found no `FROM vquclinh/fastmcq-agent`, no
  `FROM team_submission`, and no local custom base in `Dockerfile`.
- Required runtime model resource initialized during build: `Dockerfile:44-48` runs
  `python scripts/download_local_model.py --model Qwen/Qwen3-4B-Instruct-2507 --out /models/qwen3-4b-instruct-2507`.
- `SKIP_MODEL_DOWNLOAD` default: `Dockerfile:44` has `ARG SKIP_MODEL_DOWNLOAD=0`; the
  `SKIP_MODEL_DOWNLOAD=1` branch is documented as CI/smoke only at `Dockerfile:42-50`.
- Model path: `/models/qwen3-4b-instruct-2507` appears in `Dockerfile:48` and runtime env
  `Dockerfile:54`.
- Docs state no vector database/index: `README.md:53-57`, `DOCKER_SUBMISSION.md:113-117`,
  `docs/METHOD.md:241-245`, `docs/BTC_SUBMISSION_COMPLIANCE.md:17-19`.
- Git ignore proof:
  - `git check-ignore -v models` -> `.gitignore:25:models/ models`
  - `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$|^models/)'`
    -> no output.

Changes made:

- Kept the clean official NVIDIA CUDA base.
- Kept the build-time Qwen download and `SKIP_MODEL_DOWNLOAD=0`.
- Added/updated documentation that no vector database or indexing step is required.

Remaining manual checks:

- User must run the real Docker build later to verify the model download succeeds.

## BTC 2.2 — CUDA Configuration

**Status: PASS (manual GPU compatibility test still required).**

Evidence:

- CUDA 12.8+ base: `Dockerfile:12`.
- PyTorch CUDA 12.8 wheel index: `Dockerfile:29-30`.
- Exact torch pin: `Dockerfile:30` installs `torch==2.7.1`.
- `requirements.txt:3-5` documents why torch is not in `requirements.txt` and points to the exact
  Dockerfile install.
- CUDA 12.8+ rationale documented:
  - `DOCKER_SUBMISSION.md:124-129`
  - `docs/METHOD.md:247-250`
  - `docs/BTC_SUBMISSION_COMPLIANCE.md:23-27`
  - `README.md:267-269`
- Required runtime flag `--gpus all` documented:
  - `README.md:70-110`
  - `DOCKER_SUBMISSION.md:17-19`
  - `docs/BTC_SUBMISSION_COMPLIANCE.md:28`
- No IPC/shm/vLLM requirement documented:
  - `Dockerfile:10-11`
  - `README.md:109-110`, `README.md:148-149`
  - `DOCKER_SUBMISSION.md:17-19`
  - `docs/METHOD.md:244-245`
  - `docs/BTC_SUBMISSION_COMPLIANCE.md:29-30`

Decision:

- The original BTC Dockerfile template mentioned CUDA 12.2. The team later received BTC
  clarification that target hardware is RTX 5060 Ti / Blackwell and CUDA 12.8+ should be used to
  avoid CUDA/PyTorch mismatch. The final image therefore intentionally stays on CUDA 12.8+ and does
  not downgrade to CUDA 12.2.

Changes made:

- Exact-pinned the torch install to `torch==2.7.1` from `https://download.pytorch.org/whl/cu128`.
- Added explicit no `--shm-size` language where it was missing.
- Removed an old future-work vLLM mention from `docs/METHOD.md`; remaining vLLM mentions state
  that final submission does not use it.

Remaining manual checks:

- User must run the GPU container manually on target-compatible hardware.
- User must confirm the exact torch wheel and Qwen model load successfully in the built image.

## BTC 2.3 — Dockerfile Template

**Status: PASS.**

Evidence:

- Base image block: `Dockerfile:1-12`.
- System packages: `Dockerfile:21-24` installs `python3`, `python3-pip`, `python3-dev`, `git`,
  `ca-certificates`.
- Python symlink: `Dockerfile:24` links `/usr/bin/python` to `/usr/bin/python3`.
- Workdir: `Dockerfile:18` uses `WORKDIR /code`.
- Full repo copy command: `Dockerfile:38` uses `COPY . /code`.
- Dependencies: `Dockerfile:33-34` installs from `requirements.txt`; torch is separately installed
  from the CUDA 12.8 PyTorch index at `Dockerfile:29-30`.
- Model download: `Dockerfile:44-48`.
- Offline runtime env: `Dockerfile:54-56` sets `LOCAL_MODEL_PATH`, `TRANSFORMERS_OFFLINE=1`,
  `HF_HUB_OFFLINE=1`.
- Default startup: `Dockerfile:61` now uses `CMD ["bash", "inference.sh"]`.
- Tests enforce this contract:
  - `tests/integration/test_btc_submission_contract_2l47a.py:170-184`
  - `tests/integration/test_btc_submission_contract_2l47a.py:221-237`

CMD/ENTRYPOINT decision:

- The previous Dockerfile used `ENTRYPOINT ["bash", "inference.sh"]`.
- This phase switched to `CMD ["bash", "inference.sh"]` to match the stricter BTC template.
- Because `CMD` arguments are replaced by any command after the image name, docs now use
  `SUBMISSION_FILE` and `SUBMISSION_TIME_FILE` environment variables for Docker output overrides
  instead of relying on flags after the image name.

Changes made:

- Switched Docker startup from `ENTRYPOINT` to `CMD`.
- Updated README / DOCKER_SUBMISSION / BTC_SUBMISSION_COMPLIANCE command examples accordingly.

Remaining manual checks:

- User should verify that `docker run --rm --gpus all vquclinh/fastmcq-agent:latest` starts
  `bash inference.sh` after the final image is built.

## BTC 2.4 — Pre-Submit Docker Checklist

**Status: PARTIAL by instruction.**

Prepared but not executed:

- Final build command documented:
  `docker build -t vquclinh/fastmcq-agent:latest .`
  (`README.md:64-68`, `DOCKER_SUBMISSION.md:21-26`,
  `docs/BTC_SUBMISSION_COMPLIANCE.md:51-55`).
- BTC sample-compatible `/app/data` run documented:
  `docker run --rm --gpus all -v "$PWD/btc_data:/app/data:ro" vquclinh/fastmcq-agent:latest`
  (`README.md:76-82`, `DOCKER_SUBMISSION.md:34-42`,
  `docs/BTC_SUBMISSION_COMPLIANCE.md:57-63`).
- Official `/code/private_test.json` reproduction with host outputs documented:
  `README.md:84-96`, `DOCKER_SUBMISSION.md:44-55`,
  `docs/BTC_SUBMISSION_COMPLIANCE.md:65-76`.
- Offline runtime verification with `--network none` documented:
  `README.md:98-107`, `DOCKER_SUBMISSION.md:57-68`,
  `docs/BTC_SUBMISSION_COMPLIANCE.md:78-87`.
- Output validation commands documented:
  `DOCKER_SUBMISSION.md:70-93`, `docs/BTC_SUBMISSION_COMPLIANCE.md:89-112`.
- Docker Hub push command documented:
  `DOCKER_SUBMISSION.md:95-99`, `docs/BTC_SUBMISSION_COMPLIANCE.md:114-118`.

Not executed in this phase:

- No real Docker build.
- No Qwen weight download.
- No real model inference.
- No Docker Hub push.

Remaining manual checks:

1. User must run `docker build -t vquclinh/fastmcq-agent:latest .`.
2. User must run the GPU test manually.
3. User must run the `--network none` offline runtime test manually.
4. User must validate `submission.csv` and `submission_time.csv`.
5. User must push `vquclinh/fastmcq-agent:latest`.
6. User must commit the final repo after successful validation.

## Final Path Compliance Notes

- Final model: `Qwen/Qwen3-4B-Instruct-2507`.
- Final inference path: local Hugging Face Transformers via `predict.py` / `src/local_model`.
- No OpenRouter final mode: `DOCKER_SUBMISSION.md:3-7`, `README.md:48-51`,
  `docs/METHOD.md:223-226`; OpenRouter remains only in legacy/dev-only documentation.
- No API key required: `DOCKER_SUBMISSION.md:17-19`, `README.md:48-51`.
- No runtime internet: Dockerfile offline env at `Dockerfile:54-56`; docs include
  `--network none` verification command.
- Official input support: `/code/private_test.json` in `predict.py` and documented at
  `README.md:123-127`, `DOCKER_SUBMISSION.md:15-16`.
- Compatibility input support: `/app/data/private_test.json` documented at `README.md:126-128`,
  `DOCKER_SUBMISSION.md:34-42`, and tested through input priority.
- Official outputs: `/code/submission.csv` and `/code/submission_time.csv` documented at
  `README.md:131-136`, `DOCKER_SUBMISSION.md:15-16`.
- Per-sample timing: implemented around each sample in `predict.py`; tested in
  `test_per_sample_time_measured_around_each_sample`.
- `requirements-openrouter.txt` is a tracked legacy file, but the final Dockerfile does not use it:
  `Dockerfile:33-34` installs `requirements.txt`, and grep found no `requirements-openrouter`
  reference in `Dockerfile`, README, DOCKER_SUBMISSION, METHOD, or BTC compliance docs.

## Secret / Model Weight Tracking Proof

Commands run:

```text
git check-ignore -v .env
-> .gitignore:15:.env .env

git check-ignore -v Dockerfile.api
-> .gitignore:21:Dockerfile.api Dockerfile.api

git check-ignore -v models
-> .gitignore:25:models/ models

git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$|^models/)'
-> no output
```

Conclusion: `.env`, `Dockerfile.api`, and `models/` are ignored/untracked for final submission.

## Validation Results

Safe checks run with existing `.venv/bin/python`:

```text
.venv/bin/python -m compileall -q src scripts tests predict.py
-> PASS

.venv/bin/python -m pytest -q
-> 785 passed in 20.28s

.venv/bin/python scripts/audit_model_policy.py
-> RESULT: PASS — only competition-allowed models referenced.
```

Static checks:

```text
grep -nE '^(FROM|RUN|WORKDIR|COPY|CMD|ENTRYPOINT|ARG|ENV)' Dockerfile
-> shows FROM nvidia/cuda:12.8.0..., WORKDIR /code, COPY . /code, ARG SKIP_MODEL_DOWNLOAD=0,
   ENV LOCAL_MODEL_PATH/TRANSFORMERS_OFFLINE/HF_HUB_OFFLINE, CMD ["bash", "inference.sh"].

grep -nE 'nvidia/cuda|12\.8|12\.2|cu128|WORKDIR /code|COPY \. /code|requirements.txt|inference.sh|download_local_model|SKIP_MODEL_DOWNLOAD' Dockerfile
-> confirms CUDA 12.8 base, cu128 torch pin, requirements.txt install, model download, default
   SKIP_MODEL_DOWNLOAD=0, and inference.sh CMD.

grep -RIn 'OpenRouter|api-baked|OPENROUTER_API_KEY|--ipc=host|--shm-size|vLLM|vllm' README.md DOCKER_SUBMISSION.md docs/METHOD.md docs/BTC_SUBMISSION_COMPLIANCE.md 2>/dev/null || true
-> no output because the provided pattern is literal without -E.

grep -RInE 'OpenRouter|api-baked|OPENROUTER_API_KEY|--ipc=host|--shm-size|vLLM|vllm' ...
-> expected docs hits only: no-OpenRouter/no-API statements, no IPC/shm/vLLM statements, and
   legacy/dev-only OpenRouter notes. No final-path requirement for OpenRouter/API/vLLM found.
```

## Remaining Steps

1. Run final Docker build manually:
   `docker build -t vquclinh/fastmcq-agent:latest .`
2. Run GPU test manually with `--gpus all`.
3. Run network isolation test manually with `--network none`.
4. Validate `btc_output/submission.csv` and `btc_output/submission_time.csv`.
5. Push `vquclinh/fastmcq-agent:latest`.
6. Commit the final repository after successful validation.

No commit was made in this phase.
