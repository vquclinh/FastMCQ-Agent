# FASTMCQ final submission image — OFFLINE local-model (Phase 2L.47B).
#
# Vietnamese Student HackAIthon — Bảng C Innovator. Internet-isolated runtime: ONE open-weight
# local model (Qwen/Qwen3-4B-Instruct-2507, 4.0B < 5B, Apache-2.0) via Hugging Face Transformers.
# NO OpenRouter / external API / web retrieval at runtime.
#
# Container runs predict.py (via inference.sh): reads /code/private_test.json and writes
# /code/submission.csv (qid,answer) + /code/submission_time.csv (qid,answer,time, REAL per-sample).
#
# GPU: local Transformers inference (not vLLM) -> requires `--gpus all`, no `--ipc=host` or
# `--shm-size` required.
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

# System deps: Python 3.10 (ubuntu22.04), pip, git (for HF), and basic build tooling.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-dev git ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3 /usr/bin/python

# PyTorch with CUDA 12.8 wheels (matches BTC's CUDA 12.8+ environment). Installed here (not in
# requirements.txt) because it needs the PyTorch CUDA index URL. Exact-pinned for reproducible
# final builds.
RUN python -m pip install --upgrade pip && \
    python -m pip install --index-url https://download.pytorch.org/whl/cu128 torch==2.7.1

# Remaining Python dependencies (transformers, accelerate, safetensors, huggingface_hub, ...).
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

# Application code + frozen assets. .dockerignore keeps .env/secrets, scratch, caches, .git,
# notebooks, large logs and model weights OUT of the build context.
COPY . /code

RUN chmod +x inference.sh 2>/dev/null || true

# Download the single open-weight model into the image at BUILD time so inference is fully
# offline. SKIP_MODEL_DOWNLOAD is for CI/smoke ONLY — the final build uses the default (=0).
ARG SKIP_MODEL_DOWNLOAD=0
RUN if [ "$SKIP_MODEL_DOWNLOAD" = "0" ]; then \
        python scripts/download_local_model.py \
            --model Qwen/Qwen3-4B-Instruct-2507 \
            --out /models/qwen3-4b-instruct-2507 ; \
    else \
        echo "[build] SKIP_MODEL_DOWNLOAD=1 — model NOT downloaded (CI/smoke only)" ; \
    fi

# Offline runtime: point at the baked model and forbid any network calls to the HF hub.
ENV LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1

# Default action: BTC template shape. Runtime output overrides use SUBMISSION_FILE /
# SUBMISSION_TIME_FILE environment variables; passing arguments after the image name overrides
# this CMD, as standard Docker behavior.
CMD ["bash", "inference.sh"]
