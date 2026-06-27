# Audit — Phase 2L.47F: BTC CUDA 12.8 Confirmation Documentation

**Date:** 2026-06-27  
**Scope:** Documentation-only CUDA 12.8+ confirmation pass.  
**Status:** PASS for documentation/static checks. Docker build/run/push and real Qwen inference
were intentionally not run.

## Summary

BTC confirmed CUDA 12.8+ base images for the target GPU environment. This repository already uses
the correct final CUDA setup:

- Docker base image: `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- PyTorch install: `torch==2.7.1` from the PyTorch CUDA 12.8 `cu128` wheel index.
- Final inference backend: local Hugging Face Transformers, not vLLM.

No Dockerfile downgrade was made. No vLLM, `uv`, or `--torch-backend=cu128` path was added.

## Files Updated

- `README.md`
- `DOCKER_SUBMISSION.md`
- `docs/METHOD.md`
- `docs/BTC_SUBMISSION_COMPLIANCE.md`
- `tests/integration/test_btc_submission_contract_2l47a.py` (tiny doc guardrail update)

## Evidence

### Dockerfile CUDA / Torch State

Dockerfile was not changed in this phase. It remains on CUDA 12.8+ and cu128:

- `Dockerfile:12` — `FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`
- `Dockerfile:30` — installs `torch==2.7.1` from
  `https://download.pytorch.org/whl/cu128`
- `Dockerfile:10-11` — documents local Transformers inference, no vLLM, no `--ipc=host`, no
  `--shm-size`

### README.md

Updated CUDA wording:

- `README.md:56-62` says BTC confirmed CUDA 12.8+ base images, this repo follows that confirmed
  target, PyTorch is installed from `cu128`, vLLM is not used, and `--ipc=host`, `--shm-size`,
  `uv`, and `--torch-backend=cu128` are not required.
- `README.md:358-360` keeps CUDA 12.2 only as historical context and states CUDA 12.8+ is used
  accordingly.

### DOCKER_SUBMISSION.md

Updated base-image section:

- `DOCKER_SUBMISSION.md:136-141` says BTC confirmed CUDA 12.8+ base images and the final image
  uses `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04` with exact-pinned `torch==2.7.1` from
  `cu128`.
- `DOCKER_SUBMISSION.md:143-144` states vLLM is not used and therefore `--ipc=host`,
  `--shm-size`, `uv`, and `--torch-backend=cu128` are not required.

### docs/METHOD.md

Updated final submission method:

- `docs/METHOD.md:247-252` says BTC confirmed CUDA 12.8+ base images, the final
  GPU/local-Transformers image uses the CUDA 12.8 base and `torch==2.7.1` from `cu128`, CUDA 12.2
  is historical context only, and vLLM-specific flags/tools are not required.

### docs/BTC_SUBMISSION_COMPLIANCE.md

Updated CUDA checklist:

- `docs/BTC_SUBMISSION_COMPLIANCE.md:23-28` says BTC confirmed CUDA 12.8+ base images, the final
  base is `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`, CUDA 12.2 is historical context only,
  and PyTorch is exact-pinned from `cu128`.
- `docs/BTC_SUBMISSION_COMPLIANCE.md:30-32` says vLLM is not used and no `--ipc=host`,
  `--shm-size`, `uv`, or `--torch-backend=cu128` is required.

### Tests

Updated tiny documentation guardrail:

- `tests/integration/test_btc_submission_contract_2l47a.py:251-252` now requires
  `BTC confirmed CUDA 12.8+`, `uv`, and `--torch-backend=cu128` in the documentation contract.

## Validation Results

Safe checks run:

```text
.venv/bin/python -m compileall -q src scripts tests predict.py
-> PASS

.venv/bin/python -m pytest -q
-> 790 passed in 19.94s

.venv/bin/python scripts/audit_model_policy.py
-> RESULT: PASS — only competition-allowed models referenced.
```

Static confirmation:

```text
grep -RInE "later BTC clarification|later clarification|risky|uncertain|CUDA 12\.2|CUDA 12\.8\+|cu128|vLLM|--ipc=host|--shm-size|\buv\b|--torch-backend=cu128" ...
-> no leftover uncertain/risky wording; CUDA 12.2 appears only as historical context.

grep -nE "^FROM |torch==|cu128|vLLM|--ipc=host|--shm-size" Dockerfile
-> confirms CUDA 12.8 base and torch cu128 pin.
```

## Confirmations

- Did not downgrade to CUDA 12.2.
- Kept CUDA 12.8+ base image.
- Kept `torch==2.7.1` from the `cu128` PyTorch wheel index.
- Did not add vLLM.
- Did not add `uv`.
- Did not add `--torch-backend=cu128`.
- Did not require `--ipc=host`.
- Did not require `--shm-size`.
- Did not run Docker build.
- Did not download model weights.
- Did not run real Qwen inference.
- Did not push Docker Hub.
- Did not commit.

## Remaining Manual Steps

1. User must run the final Docker build manually.
2. User must run the GPU test manually.
3. User must run the network-none test manually.
4. User must push `vquclinh/fastmcq-agent:latest`.
5. User must commit the final repo after successful validation.
