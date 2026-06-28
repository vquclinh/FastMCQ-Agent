# FASTMCQ Agent

<div align="center">

### Vietnamese Multiple-Choice Reasoning Agent for Student HackAIthon 2026

Docker-first MCQ answering system for the BTC private-test evaluation.<br>
Reads `/code/private_test.json` (or `/app/data/private_test.json` for compatibility), runs one
offline local Qwen model, and writes `/code/submission.csv` plus `/code/submission_time.csv`.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Docker](https://img.shields.io/badge/Docker-Hub-blue)
![Status](https://img.shields.io/badge/Status-Final%20Submission-success)
![Model Policy](https://img.shields.io/badge/Model%20Policy-PASS-brightgreen)
![Output](https://img.shields.io/badge/Output-qid%2Canswer-orange)

</div>

## Table of Contents

- [Competition Context](#competition-context)
- [Official Docker Submission](#official-docker-submission)
- [Quick Start](#quick-start)
- [Pipeline Flow](#pipeline-flow)
- [Data Processing](#data-processing)
- [Resource Initialization](#resource-initialization)
- [Input and Output Contract](#input-and-output-contract)
- [System Architecture](#system-architecture)
- [Runtime Modes](#runtime-modes)
- [Repository Structure](#repository-structure)
- [Validation](#validation)
- [Documentation](#documentation)
- [Security & Compliance](#security--compliance)

## Competition Context

Built for the **Vietnamese Student HackAIthon 2026 — Bảng C Innovator** Docker-based evaluation,
which runs in an **internet-isolated** environment. The submitted **Docker Hub container** reads
`/code/private_test.json` and writes `/code/submission.csv` (`qid,answer`) and
`/code/submission_time.csv` (`qid,answer,time`). The pipeline uses **one open-weight local model**
(≤ 5B) with **no external API and no internet** at runtime.

## Official Docker Submission

| | |
|---|---|
| **Official submission image** | `vquclinh/fastmcq-agent:latest` |
| **Model (single, open-weight)** | `Qwen/Qwen3-4B-Instruct-2507` (4.0B < 5B, Apache-2.0) |
| **Mode** | **fully offline** — local Hugging Face Transformers inference; **no API, no internet at runtime** |

The final image is **offline / local-model only**: the model weights are downloaded **at Docker
build time** into `/models/qwen3-4b-instruct-2507` and the container runs with
`TRANSFORMERS_OFFLINE=1` / `HF_HUB_OFFLINE=1`. There is no OpenRouter, no external API, and no web
retrieval during evaluation. **No API key exists in the image or in GitHub.**

BTC confirmed CUDA 12.8+ base images for the target GPU environment. This repository follows that
confirmed target with the clean official NVIDIA base
`nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`, installs an exact-pinned CUDA 12.8 PyTorch wheel
(`torch==2.7.1` from the `cu128` index), installs the remaining dependencies from
`requirements.txt`, and initializes only the Qwen model. No vector database is required, and no
indexing step is required. This solution does not use vLLM, so `--ipc=host`, `--shm-size`, `uv`,
and `--torch-backend=cu128` are not required.

## Quick Start

The Docker image entrypoint is **`inference.sh`**, which runs **`predict.py`** automatically.
The official/default BTC contract is:

```text
Host input file      -> mounted to container as /code/private_test.json
Container output     -> /code/submission.csv
Container time file  -> /code/submission_time.csv
```

`/code` is the Linux filesystem path **inside the Docker container**. If the evaluator wants to
inspect the output files on the host machine after the container finishes, keep the container with
`--name` and copy the files out with `docker cp`.

### 1. Pull the final image from DockerHub

```bash
docker pull vquclinh/fastmcq-agent:latest
```

### 2. Default BTC run

Place the private test file on the host machine as `private_test.json`, then mount it into the
container at `/code/private_test.json`.

Linux / Bash:

```bash
docker rm -f fastmcq_btc_test 2>/dev/null || true

docker run --name fastmcq_btc_test --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent:latest
```

Windows PowerShell:

```powershell
$IMAGE = "vquclinh/fastmcq-agent"

docker rm -f fastmcq_btc_test 2>$null

docker run --name fastmcq_btc_test --gpus all `
  -v "${PWD}\private_test.json:/code/private_test.json:ro" `
  "${IMAGE}:latest"
```

After the run finishes, the default output files are created inside the container:

```text
/code/submission.csv
/code/submission_time.csv
```

### 3. Copy default outputs from the container

Linux / Bash:

```bash
docker cp fastmcq_btc_test:/code/submission.csv ./submission.csv
docker cp fastmcq_btc_test:/code/submission_time.csv ./submission_time.csv

cat ./submission.csv
cat ./submission_time.csv
```

Windows PowerShell:

```powershell
docker cp fastmcq_btc_test:/code/submission.csv .\submission.csv
docker cp fastmcq_btc_test:/code/submission_time.csv .\submission_time.csv

Get-Content .\submission.csv
Get-Content .\submission_time.csv
```

Clean up the named test container after copying the outputs:

```bash
docker rm fastmcq_btc_test
```

### 4. Equivalent minimal run command

If the evaluator has another mechanism to collect files from the container filesystem, the minimal
run command is:

```bash
docker run --gpus all \
  -v /path/to/private_test.json:/code/private_test.json:ro \
  vquclinh/fastmcq-agent:latest
```

Do **not** use `--rm` if you need to copy `/code/submission.csv` and
`/code/submission_time.csv` from the container after it exits.

### 5. Optional offline verification

The final image is designed to run without runtime internet. After pulling the image, this can be
checked locally by adding `--network none`:

```bash
docker rm -f fastmcq_btc_test 2>/dev/null || true

docker run --name fastmcq_btc_test --gpus all --network none \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent:latest
```

### 6. Build from source

Build the final image from this repository. The real Qwen weights are downloaded during Docker
build and stored inside the image.

```bash
docker build -t vquclinh/fastmcq-agent:latest .
```

### 7. Compatibility runs

The official path is `/code/private_test.json`. The image also supports older compatibility paths.

BTC sample-compatible `/app/data` run:

```bash
docker run --rm --gpus all \
  -v "$PWD/btc_data:/app/data:ro" \
  vquclinh/fastmcq-agent:latest
```

Legacy `/data` -> `/output/pred.csv` run:

```bash
docker run --rm --gpus all \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  vquclinh/fastmcq-agent:latest
```

**Required Docker flag:** `--gpus all` for local Transformers GPU inference. **`--ipc=host` is not
required** and **`--shm-size` is not required** because this solution does not use vLLM.

## Pipeline Flow

`inference.sh` launches `predict.py`, which is the end-to-end BTC entrypoint. The local Qwen model
is loaded once, then the input items are processed one by one. Timing is measured around each
single item inference inside that loop and written to `submission_time.csv`.

```text
private_test.json
   |
   v
Input resolver
   |
   v
Question/choice normalization
   |
   v
Prompt construction
   |
   v
Offline Qwen3-4B local inference
   |
   v
Answer label parser / fallback validator
   |
   v
submission.csv + submission_time.csv
```

The default final path is offline local Transformers inference with
`Qwen/Qwen3-4B-Instruct-2507`. It does not call OpenRouter, does not call any external API, does
not require `OPENROUTER_API_KEY`, and is designed to run without runtime internet.

## Data Processing

The accepted BTC input is a JSON test list. Each item is normalized into the internal shape
`qid`, `question`, and `choices`; legacy CSV input remains supported only as a compatibility
fallback. Input priority is:

1. CLI `--input <path>` or `$INPUT_FILE`
2. `/code/private_test.json`
3. `/code/public_test.json`
4. `/app/data/private_test.json`
5. `/app/data/public_test.json`
6. `/data/private_test.json`
7. `/data/public_test.json`
8. `/data/private_test.csv`
9. `/data/public_test.csv`

Choices are converted into dynamic labels `A`, `B`, `C`, ... based on the number of options in
that item. The model prompt includes all normalized choices and asks for one label. The generated
text is parsed back into a valid answer label; invalid or empty output falls back
deterministically to the first valid label for that item. The fallback is generic and does not
hardcode qids, answers, public-test size, or any private-test assumption.

Official output examples:

```text
submission.csv:
qid,answer
test_0001,A

submission_time.csv:
qid,answer,time
test_0001,A,1.2345
```

## Resource Initialization

No vector database is used. No external index is used. No retrieval database is required. The
only required runtime resource is the Qwen model snapshot, downloaded during Docker build into:

```text
/models/qwen3-4b-instruct-2507
```

At runtime the image uses:

```text
LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507
TRANSFORMERS_OFFLINE=1
HF_HUB_OFFLINE=1
```

Because the model is baked into the image and Hugging Face offline mode is enabled, the final
container is intended to pass a `--network none` runtime check after the image has been built.

## Input and Output Contract

**Official BTC input:** `/code/private_test.json`. **Input priority** (first match wins):

1. `--input <path>` (CLI) / `$INPUT_FILE`
2. `/code/private_test.json`  ·  `/code/public_test.json`  *(official)*
3. `/app/data/private_test.json`  ·  `/app/data/public_test.json`  *(compat)*
4. `/data/private_test.json`  ·  `/data/public_test.json`
5. `/data/private_test.csv`  ·  `/data/public_test.csv`  *(legacy)*

**Official BTC outputs** (written under `/code`; override with `$SUBMISSION_FILE` /
`$SUBMISSION_TIME_FILE` in Docker, or `--submission` / `--submission-time` when running
`predict.py` directly):

- `/code/submission.csv` — header `qid,answer`
- `/code/submission_time.csv` — header `qid,answer,time` (numeric seconds per sample)

`answer` is an option label such as `A`/`B`/`C`/`D`; the parser supports wider choice sets when
the input provides more options. For backward compatibility, predictions are also mirrored to
`/output/pred.csv` (and to `--output`/`$OUTPUT_FILE` if given).

**Pipeline flow & resources.** `inference.sh` → `predict.py` loads and normalizes the test file
(CSV/JSON), loads the single local model **once**, answers each question with deterministic
(greedy, answer-only) generation, and writes the two output files. `submission_time.csv` records a
**real per-sample** time measured around each question's inference. The model weights are baked
into the image **at build time**; **no vector database, no internet, and no external API** is used
at runtime. No vector database is required, no indexing step is required, and only the Qwen model
is initialized during Docker build. GPU is used via `--gpus all`; **`--ipc=host` is not required**,
**`--shm-size` is not required**, and no vLLM is used. If the model cannot answer a sample, that
sample falls back to a deterministic label so the output always covers every input qid.

## System Architecture

**Final offline pipeline (the submitted image).** `inference.sh` → `predict.py` loads the single
local model **once** (`Qwen/Qwen3-4B-Instruct-2507`), then for each question builds an answer-only
MCQ prompt, runs deterministic greedy generation, parses the option label, and (on any failure)
falls back to a deterministic label. It writes `submission.csv` (`qid,answer`) and
`submission_time.csv` (`qid,answer,time`, measured per sample). No API, no internet, no vector DB.

> The diagram and tables below describe the earlier **dynamic API reasoning system** (base → V12B
> → V13 → selector). It remains in the repo as a **dev-only** path (`predict.py
> --legacy-dynamic-full`) and is **not** used by the offline submission.

<div align="center">

![FASTMCQ Agent architecture (legacy dynamic pipeline)](assets/archi.png)

</div>

### Modules

| Area | Package | Role |
|---|---|---|
| System Orchestration | `src/system/` | Full dynamic pipeline, production profiles, Docker-facing inference flow |
| Base Prediction | `src/base/` | Produces complete all-qid coverage before selective reasoning |
| Dynamic Layers | `src/layers/` | V12B/V13 selective reasoning, routing, permutation debiasing, least-to-most / content-first passes |
| API Runtime | `src/api/` | OpenRouter client, selective API execution, allowed-model policy integration |
| Final Selection | `src/selector/` | Candidate consistency, ranking, conservative override decisions |
| Solvers | `src/solvers/` | Symbolic/programmatic/formula-based MCQ solvers and heuristic reasoning |
| Evidence | `src/evidence/` | Evidence packing, reranking, sufficiency checks, option grounding |
| Utilities | `src/utils/` | Data I/O, label handling, output parsing, logging, postprocessing |

### Reasoning stages

| Stage | Coverage | Purpose |
|---|---:|---|
| Base Predictor | all qids | Guarantees every input question receives an answer |
| V12B | `ceil(N/8)` qids by default | Option-permutation reasoning to reduce ordering bias |
| V13 | `ceil(N/8)` qids by default | Multi-layer targeted reasoning: programmatic, content-first, least-to-most |
| Final Selector | all qids | Merges base/layer candidates and only overrides when confidence is sufficient |

The selective budget is **`auto = ceil(input_count / 8)`**, minimum 1 (e.g. 3 → 1, 463 → 58). It
limits only how many questions the V12B/V13 reasoning layers may call — the **output always
contains all input qids**.

### Design Principles

- **All-qid coverage first:** never rely on selective layers to produce complete output.
- **Selective reasoning budget:** reserve expensive API reasoning for high-value qids.
- **Permutation debiasing:** test answer stability across option orderings.
- **Conservative selection:** prefer safe overrides over noisy changes.
- **Docker-first reproducibility:** one command reads `/data` and writes `/output/pred.csv`.

See [`docs/METHOD.md`](docs/METHOD.md) for the full method description.

## Runtime Modes

The submission runs in a **single offline mode**: local `Qwen/Qwen3-4B-Instruct-2507` inference
with the model baked into the image and `TRANSFORMERS_OFFLINE=1` / `HF_HUB_OFFLINE=1`. No API key,
no internet, no `--ipc=host`, and no `--shm-size` are needed — only `--gpus all`.

| Path | Trigger | Behavior |
|---|---|---|
| **Offline local model** (default) | — | loads `Qwen3-4B-Instruct-2507`, answers each qid locally |
| Legacy dynamic API | `--legacy-dynamic-full` (dev only) | the older base→V12B→V13 pipeline; **not** used for submission |

`predict.py` flags: `--model-path` (default `/models/qwen3-4b-instruct-2507` or `$LOCAL_MODEL_PATH`),
`--max-new-tokens`, `--device` (default `auto`), `--submission` / `--submission-time`. `--no-api`
is accepted as a compatibility no-op (the offline path never uses an API).

## Repository Structure

```text
src/                    core inference system
  system/               full-system orchestration
  base/                 base predictors and solver factory
  layers/               V12B/V13 dynamic reasoning layers
  api/                  OpenRouter and selective API clients
  selector/             candidate merging and final selection
  solvers/              symbolic/programmatic MCQ solvers
  evidence/             evidence packing and reranking
  utils/                IO, labels, logging, parsing

scripts/                CLI/Docker entrypoints and validation tools
configs/                production profiles and model-policy configuration
tests/                  unit and integration tests
docs/METHOD.md          method description
DOCKER_SUBMISSION.md    Docker-specific submission details
docs/audits/            audit trail of major changes and validations
```

## Validation

```bash
.venv/bin/python -m compileall -q src scripts tests
.venv/bin/python -m pytest -q
.venv/bin/python scripts/audit_model_policy.py
```

- The Docker contract (BTC JSON in / `submission.csv` + `submission_time.csv` out) and the legacy
  `/data` → `/output/pred.csv` path have been validated with the local backend stubbed (no
  download/network in tests).
- Detailed logs are kept out of the repository; see `docs/audits/` for the validation trail.

## Documentation

- [DOCKER_SUBMISSION.md](DOCKER_SUBMISSION.md) — Docker build/run details and the I/O contract.
- [docs/METHOD.md](docs/METHOD.md) — method and architecture description.
- [docs/audits/](docs/audits/) — audit trail of major changes and validations.

## Security & Compliance

- **Offline at runtime:** the final image uses **no OpenRouter, no external API, and no internet**
  — a single local open-weight model (`Qwen/Qwen3-4B-Instruct-2507`, 4.0B < 5B, Apache-2.0).
- Model weights are downloaded **at build time** and are **never committed** — `models/` is
  git-ignored.
- CUDA choice: BTC confirmed CUDA 12.8+ base images for the target environment. This final GPU
  image uses CUDA 12.8+ accordingly. The older CUDA 12.2 template is only historical context and
  is not used here.
- **No API key anywhere:** `.env` is git-ignored; `Dockerfile.api` (a dev-only API-capable build)
  is local-only and git-ignored — neither is part of the committed repository.
- Resource initialization: no vector database / index; no model-weight init at runtime beyond
  loading the baked weights; runs under `TRANSFORMERS_OFFLINE=1` / `HF_HUB_OFFLINE=1`.

---

<div align="center">

Prepared for the Vietnamese Student HackAIthon 2026 / BTC Docker-based evaluation.

</div>
