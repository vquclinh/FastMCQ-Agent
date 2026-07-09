# BTC Final Compliance Matrix

Phase 2L.47G final static verification before Docker build.

Final image target: `vquclinh/fastmcq-agent:latest`

Final mode: offline local GPU inference with `Qwen/Qwen3-4B-Instruct-2507` through Hugging Face Transformers. No external API final path, no runtime internet, no API key, no vLLM, no `uv`, no `--torch-backend=cu128`, no `--ipc=host`, and no `--shm-size`.

## Summary

| BTC area | Status | Evidence | Remaining action |
|---|---:|---|---|
| Dockerfile 2.1 general principles | PASS | `Dockerfile:12`, `Dockerfile:44-48`, `README.md:192-210` | User must run final Docker build manually. |
| Dockerfile 2.2 CUDA configuration | PASS | `Dockerfile:12`, `Dockerfile:29-30`, `README.md:51-62` | User must validate on target GPU manually. |
| Dockerfile 2.3 template | PASS | `Dockerfile:21-38`, `Dockerfile:54-61` | User must run container manually. |
| Dockerfile 2.4 pre-submit checklist | PARTIAL | `DOCKER_SUBMISSION.md:23-110`, `README.md:71-111` | Commands are documented; build/run/push remain manual. |
| GitHub 2.1 README | PASS | `README.md:37-62`, `README.md:126-210` | None before manual Docker validation. |
| GitHub 2.2 library management | PASS | `requirements.txt:3-14`, `Dockerfile:29-34` | `pip check` should stay passing in the active env. |
| GitHub 2.3 source organization | PASS | `predict.py:40-44`, `predict.py:157-209`, `inference.sh:1-5` | User must run real GPU inference manually. |
| BTC clarification mapping | PASS | `predict.py`, `Dockerfile`, README and Docker docs listed below | User must verify final container on BTC-like host. |

## Dockerfile 2.1 - General Principles

Requirement: Dockerfile must build from a clean/base image, not a previous team image.

Status: PASS

Repository evidence:
- `Dockerfile:12` uses `FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- The Dockerfile does not use `FROM vquclinh/fastmcq-agent`, `FROM team_submission`, or a local/custom old image.

Why this satisfies BTC:
- The image starts from an official NVIDIA CUDA base image suitable for GPU inference rather than a team-prebuilt submission image.

Remaining manual action:
- Run `docker build -t vquclinh/fastmcq-agent:latest .` manually.

Requirement: Required resources such as model weights or database indexes should be downloaded or initialized during build.

Status: PASS

Repository evidence:
- `Dockerfile:44` sets `ARG SKIP_MODEL_DOWNLOAD=0`, so final builds download the model by default.
- `Dockerfile:45-48` runs `scripts/download_local_model.py --model Qwen/Qwen3-4B-Instruct-2507 --out /models/qwen3-4b-instruct-2507`.
- `README.md:194-204` documents that no vector database, index, or retrieval database is required, and that only Qwen model weights are initialized during Docker build.
- `Dockerfile:43` documents `SKIP_MODEL_DOWNLOAD=1` as smoke/CI only.

Why this satisfies BTC:
- The required Qwen weights are initialized during Docker build at `/models/qwen3-4b-instruct-2507`, and there is no separate vector database/index resource to initialize.

Remaining manual action:
- Final build must be run without `--build-arg SKIP_MODEL_DOWNLOAD=1`.

## Dockerfile 2.2 - CUDA Configuration

Requirement: GPU solutions should use a CUDA-supporting base image compatible with BTC hardware.

Status: PASS

Repository evidence:
- `Dockerfile:12` uses `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- `README.md:53-60`, `DOCKER_SUBMISSION.md:136-144`, `docs/FINAL_SYSTEM.md` (§2–§3), and `docs/BTC_SUBMISSION_COMPLIANCE.md:23-32` state BTC confirmed CUDA 12.8+ for the RTX 5060 Ti / Blackwell target environment.
- Mentions of the old CUDA 12.2 template are historical context only.

Why this satisfies BTC:
- BTC clarified the target GPU environment uses RTX 5060 Ti / Blackwell and should use CUDA 12.8+. This repository follows that confirmed requirement instead of downgrading to the old CUDA 12.2 template example.

Remaining manual action:
- User must run the final image on an NVIDIA GPU host with `--gpus all`.

Requirement: PyTorch should match the CUDA runtime and be pinned.

Status: PASS

Repository evidence:
- `Dockerfile:29-30` installs `torch==2.7.1` from `https://download.pytorch.org/whl/cu128`.
- `requirements.txt:3-5` explains torch is intentionally installed in the Dockerfile, not in `requirements.txt`, because it must come from the CUDA 12.8 wheel index.

Why this satisfies BTC:
- The Dockerfile uses an exact PyTorch pin from the CUDA 12.8 wheel index, avoiding an unpinned `pip install torch` and avoiding CUDA/PyTorch mismatch.

Remaining manual action:
- Validate CUDA visibility during manual Docker GPU test.

Requirement: vLLM-specific runtime and install flags should not be required for this non-vLLM solution.

Status: PASS

Repository evidence:
- `Dockerfile:10-11`, `README.md:61-62`, `DOCKER_SUBMISSION.md:143-144`, and `docs/BTC_SUBMISSION_COMPLIANCE.md:31-32` document that vLLM is not used and therefore `--ipc=host`, `--shm-size`, `uv`, and `--torch-backend=cu128` are not required.

Why this satisfies BTC:
- BTC's `uv --torch-backend=cu128` note applies to vLLM teams. This repository uses Hugging Face Transformers directly.

Remaining manual action:
- None beyond using the documented `--gpus all` run flag.

## Dockerfile 2.3 - Dockerfile Template

Requirement: Dockerfile should follow the BTC template shape.

Status: PASS

Repository evidence:
- CUDA base image: `Dockerfile:12`.
- System packages include `python3`, `python3-pip`, `python3-dev`, `git`, and `ca-certificates`: `Dockerfile:21-24`.
- Python symlink: `Dockerfile:24`.
- `WORKDIR /code`: `Dockerfile:18`.
- `COPY . /code`: `Dockerfile:38`.
- Installs final dependencies from `requirements.txt`: `Dockerfile:33-34`.
- Downloads Qwen model during build: `Dockerfile:44-48`.
- Offline runtime environment: `Dockerfile:54-56`.
- Default startup: `Dockerfile:61` uses `CMD ["bash", "inference.sh"]`.
- No final `ENTRYPOINT` is present.

Why this satisfies BTC:
- The image follows the BTC template while using the confirmed CUDA 12.8 base and the final local-Transformers inference path.

Remaining manual action:
- User must run the documented container commands after build.

## Dockerfile 2.4 - Pre-submit Checklist

Requirement: Teams should test Docker build/run, verify output files, and push the image.

Status: PARTIAL

Repository evidence:
- Final build command is documented in `DOCKER_SUBMISSION.md:23-25` and `README.md:71-73`.
- BTC sample-compatible `/app/data` run is documented in `DOCKER_SUBMISSION.md:38-41` and `README.md:81-86`.
- Official `/code/private_test.json` run with host-preserved outputs and `SUBMISSION_FILE` / `SUBMISSION_TIME_FILE` is documented in `DOCKER_SUBMISSION.md:49-54` and `README.md:95-101`.
- Offline `--network none` run is documented in `DOCKER_SUBMISSION.md:61-67` and `README.md:103-111`.
- Output validation script is documented in `DOCKER_SUBMISSION.md:72-92`.
- Docker Hub push command is documented in `DOCKER_SUBMISSION.md:110`.

Why this satisfies BTC:
- The repository contains the exact commands needed for BTC's pre-submit checklist without executing them during this static phase.

Remaining manual action:
- User must run the final Docker build, GPU run, offline run, CSV validation, and Docker Hub push manually.

## GitHub 2.1 - README.md

Requirement: README.md must describe Pipeline Flow, Data Processing, and Resource Initialization.

Status: PASS

Repository evidence:
- Final submission mode and constraints: `README.md:37-62`.
- Docker image/model/input/output summary: `README.md:47-49`.
- Official input `/code/private_test.json` and compatibility input `/app/data/private_test.json`: `README.md:39-40`, `README.md:165-174`, `README.md:213-214`.
- Official outputs `/code/submission.csv` and `/code/submission_time.csv`: `README.md:41`, `README.md:81-91`, `README.md:216-227`.
- Pipeline Flow section with text diagram: `README.md:126-156`.
- Data Processing section with input priority, choice normalization, parser, fallback, and output examples: `README.md:158-190`.
- Resource Initialization section: `README.md:192-210`.
- Docker reproduction flags: `README.md:71-115`.
- No `--ipc=host`, no `--shm-size`, no vLLM, no `uv`, no `--torch-backend=cu128`: `README.md:61-62`, `README.md:114-115`.

Why this satisfies BTC:
- README explains the full final pipeline, input/output contract, data handling, model resource initialization, and exact Docker usage for BTC.

Remaining manual action:
- None before Docker validation.

## GitHub 2.2 - Library Management

Requirement: `requirements.txt` should list libraries and specific versions with no obvious install conflicts.

Status: PASS

Repository evidence:
- `requirements.txt:6-14` exact-pins all final direct dependency lines.
- `requirements.txt:3-5` documents that torch is intentionally omitted from `requirements.txt` because `Dockerfile:29-30` installs `torch==2.7.1` from the CUDA 12.8 `cu128` index.
- `Dockerfile:33-34` installs only `requirements.txt`.
- `Dockerfile` installs only `requirements.txt`.
- The retired remote-provider requirement file is absent from the active repository.

Why this satisfies BTC:
- The final dependency set is pinned and the GPU-sensitive torch wheel is pinned in the only place where the CUDA 12.8 wheel index is configured.

Remaining manual action:
- Keep `pip check` passing after any later dependency change.

## GitHub 2.3 - Source Organization

Requirement: Repository must include root `predict.py` as the end-to-end entrypoint.

Status: PASS

Repository evidence:
- Root files exist: `Dockerfile`, `predict.py`, `inference.sh`, `README.md`, and `requirements.txt`.
- `predict.py:6-8` documents the official input and output contract.
- Input resolver includes `/code/private_test.json` and `/app/data/private_test.json`: `predict.py:40-44`.
- Default output resolver writes under `/code` when possible: `predict.py:74-82`.
- Output env overrides are supported: `predict.py:157-159`.
- Local model path default is set before predictor loading: `predict.py:176-177`.
- Samples and predictor are loaded once before the prediction loop: `predict.py:178-180`.
- Per-sample loop measures time around each single inference: `predict.py:182-196`.
- Exact CSV headers are written: `predict.py:201-209`.
- Invalid/empty outputs are coerced to valid labels with deterministic fallback: `predict.py:85-99`, `predict.py:186-193`.
- `inference.sh:1-5` has a shebang, strict mode, and runs `python predict.py "$@"`.

Why this satisfies BTC:
- `predict.py` is the official end-to-end pipeline entrypoint, reads BTC input paths, loads the model once, processes samples in a loop, records real per-sample timing, preserves qids, and writes the required CSV files.

Remaining manual action:
- User must run real model inference inside the built Docker image manually.

## BTC Clarification Mapping

### 1. Confirmed Mount and Filename

Requirement: BTC confirmed the official input is `/code/private_test.json` with filename `private_test.json`.

Status: PASS

Evidence:
- `predict.py:40` includes `/code/private_test.json`.
- `README.md:39`, `README.md:165-174`, and `DOCKER_SUBMISSION.md:49-54` document the official path and mount command.

Why this satisfies BTC:
- The default input resolver and docs match BTC's confirmed official input mount and filename.

Remaining manual action:
- Mount the real test file at `/code/private_test.json` during final validation.

### 2. Confirmed Output Location

Requirement: BTC confirmed outputs should be written directly inside `/code`.

Status: PASS

Evidence:
- `predict.py:141-144` documents default output paths as `/code/submission.csv` and `/code/submission_time.csv`.
- `predict.py:74-82` resolves default outputs under `/code` when possible.
- `README.md:216-227` and `DOCKER_SUBMISSION.md:15-18` document the official output paths.

Why this satisfies BTC:
- The final default output contract writes both CSV files directly inside `/code`.

Remaining manual action:
- Confirm both files exist after the manual Docker run.

### 3. Confirmed Docker Flags

Requirement: Teams should document Docker flags. This repo requires GPU access but not vLLM-specific shared-memory flags.

Status: PASS

Evidence:
- `README.md:71-115` documents `--gpus all` runs.
- `DOCKER_SUBMISSION.md:38-67` documents `/app/data`, `/code/private_test.json`, and `--network none` runs using `--gpus all`.
- `README.md:114-115` and `DOCKER_SUBMISSION.md:17-18` state no `--ipc=host` and no `--shm-size` are required.

Why this satisfies BTC:
- The required GPU flag is documented, and the omitted flags are justified by the non-vLLM Transformers backend.

Remaining manual action:
- Run the documented Docker commands manually.

### 4. Confirmed Timing

Requirement: BTC confirmed timing must be dumped per data point/sample, not averaged over the dataset.

Status: PASS

Evidence:
- `predict.py:182-196` starts timing before each single-sample inference and records elapsed time after that sample.
- `predict.py:207-209` writes `qid,answer,time`.
- `README.md:149-153`, `README.md:185-190`, and `DOCKER_SUBMISSION.md:97-104` document per-sample timing and the output example.

Why this satisfies BTC:
- Timing is measured inside the sample loop around the actual prediction call and is not computed as total time divided by sample count.

Remaining manual action:
- Inspect `submission_time.csv` after manual final run.

### 5. Confirmed Hardware and CUDA

Requirement: BTC confirmed NVIDIA RTX 5060 Ti, RAM 32GB, and CUDA 12.8+ base image.

Status: PASS

Evidence:
- `Dockerfile:12` uses CUDA 12.8.
- `Dockerfile:29-30` installs `torch==2.7.1` from `cu128`.
- `README.md:51-62`, `DOCKER_SUBMISSION.md:136-144`, and `docs/FINAL_SYSTEM.md` (§2–§3) document BTC's CUDA 12.8+ confirmation and the RTX 5060 Ti / Blackwell target.
- Final model is `Qwen/Qwen3-4B-Instruct-2507`: `Dockerfile:47`, `README.md:48`.

Why this satisfies BTC:
- The image and torch wheel match the confirmed hardware/CUDA setting, and the 4B Qwen model is the local GPU model selected for this target.

Remaining manual action:
- Run final image on the target GPU or comparable local GPU host.

### 6. vLLM Note

Requirement: BTC's vLLM-specific note says vLLM teams should use `uv --torch-backend=cu128`.

Status: PASS

Evidence:
- `Dockerfile:10-11`, `README.md:61-62`, `DOCKER_SUBMISSION.md:143-144`, and `docs/BTC_SUBMISSION_COMPLIANCE.md:31-32` state this repository does not use vLLM.
- No final Docker or README command requires `uv` or `--torch-backend=cu128`.

Why this satisfies BTC:
- The vLLM note is not applicable because this repository uses local Hugging Face Transformers, while still using CUDA 12.8 and the PyTorch `cu128` wheel.

Remaining manual action:
- None.

## Final Manual Next Steps

1. Build the final image:

```bash
docker build -t vquclinh/fastmcq-agent:latest .
```

2. Test official `/code/private_test.json` path and preserve outputs on host:

```bash
mkdir -p btc_data btc_output

docker run --rm --gpus all \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent:latest
```

3. Test BTC sample-compatible `/app/data` path:

```bash
docker run --rm --gpus all \
  -v "$PWD/btc_data:/app/data:ro" \
  vquclinh/fastmcq-agent:latest
```

4. Test offline runtime:

```bash
docker run --rm --gpus all --network none \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent:latest
```

5. Validate both CSV files:

```bash
head -5 btc_output/submission.csv
head -5 btc_output/submission_time.csv
python - <<'PY'
import csv, pathlib
sub = pathlib.Path("btc_output/submission.csv")
tim = pathlib.Path("btc_output/submission_time.csv")
assert sub.exists(), "missing submission.csv"
assert tim.exists(), "missing submission_time.csv"
with sub.open() as f:
    rows = list(csv.reader(f))
assert rows[0] == ["qid", "answer"], rows[0]
with tim.open() as f:
    rows_t = list(csv.reader(f))
assert rows_t[0] == ["qid", "answer", "time"], rows_t[0]
assert len(rows) == len(rows_t), (len(rows), len(rows_t))
for r in rows_t[1:]:
    assert len(r) == 3, r
    float(r[2])
print("BTC output files look valid.")
PY
```

6. Push Docker Hub image:

```bash
docker push vquclinh/fastmcq-agent:latest
```

7. Commit the final repository after successful validation.
