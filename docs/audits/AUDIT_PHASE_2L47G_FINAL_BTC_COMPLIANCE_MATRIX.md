# Audit Phase 2L.47G - Final BTC Compliance Matrix

Date: 2026-06-27

Scope: static/documentation verification before the user runs the final Docker build and Docker Hub push.

## Files Inspected

- `Dockerfile`
- `predict.py`
- `inference.sh`
- `requirements.txt`
- `README.md`
- `DOCKER_SUBMISSION.md`
- `docs/METHOD.md`
- `docs/BTC_SUBMISSION_COMPLIANCE.md`
- `docs/audits/AUDIT_PHASE_2L47D_BTC_DOCKERFILE_REQUIREMENTS.md`
- `docs/audits/AUDIT_PHASE_2L47E_BTC_REPOSITORY_REQUIREMENTS.md`
- `docs/audits/AUDIT_PHASE_2L47F_BTC_CUDA128_CONFIRMATION.md`

## Files Changed

- Added `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`
- Added `docs/audits/AUDIT_PHASE_2L47G_FINAL_BTC_COMPLIANCE_MATRIX.md`

No code changes were made in this phase.

## Final BTC Compliance Status

### Dockerfile 2.1 - General Principles

Status: PASS

Evidence:
- `Dockerfile:12` uses official base image `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- `Dockerfile:44` sets `ARG SKIP_MODEL_DOWNLOAD=0`.
- `Dockerfile:45-48` downloads `Qwen/Qwen3-4B-Instruct-2507` during build to `/models/qwen3-4b-instruct-2507` through `scripts/download_local_model.py`.
- `README.md:192-210` documents that no vector database, external index, or retrieval database is required.
- `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` records these checks in the Dockerfile 2.1 section.

Why it matches BTC:
- The final image starts from a clean official NVIDIA base image, not a previous team image.
- The only required runtime resource is the Qwen model, and the Dockerfile initializes it during build by default.

Remaining manual check:
- User must run `docker build -t vquclinh/fastmcq-agent:latest .` without `SKIP_MODEL_DOWNLOAD=1`.

### Dockerfile 2.2 - CUDA Configuration

Status: PASS

Evidence:
- `Dockerfile:12` uses `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- `Dockerfile:29-30` installs exact-pinned `torch==2.7.1` from `https://download.pytorch.org/whl/cu128`.
- `README.md:51-62`, `DOCKER_SUBMISSION.md:136-144`, `docs/METHOD.md:247-251`, and `docs/BTC_SUBMISSION_COMPLIANCE.md:23-32` document BTC's CUDA 12.8+ confirmation.
- These docs also state that vLLM is not used and that `--ipc=host`, `--shm-size`, `uv`, and `--torch-backend=cu128` are not required.

Why it matches BTC:
- BTC confirmed RTX 5060 Ti / Blackwell target hardware with CUDA 12.8+ base images. The Dockerfile and torch wheel index match that confirmed environment.

Remaining manual check:
- User must validate the final image on a GPU host with `--gpus all`.

### Dockerfile 2.3 - Dockerfile Template

Status: PASS

Evidence:
- `Dockerfile:21-24` installs `python3`, `python3-pip`, `python3-dev`, `git`, and `ca-certificates`, and creates `/usr/bin/python -> /usr/bin/python3`.
- `Dockerfile:18` sets `WORKDIR /code`.
- `Dockerfile:38` copies the repository with `COPY . /code`.
- `Dockerfile:33-34` installs final dependencies from `requirements.txt`.
- `Dockerfile:54-56` sets `LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507`, `TRANSFORMERS_OFFLINE=1`, and `HF_HUB_OFFLINE=1`.
- `Dockerfile:61` uses BTC-template-compatible `CMD ["bash", "inference.sh"]`.

Why it matches BTC:
- The Dockerfile follows the BTC template structure while using the confirmed CUDA 12.8 base and local Transformers path.

Remaining manual check:
- User must run the built image and confirm it starts through `inference.sh`.

### Dockerfile 2.4 - Pre-submit Checklist

Status: PARTIAL

Evidence:
- `DOCKER_SUBMISSION.md:23-25` documents the final build command.
- `DOCKER_SUBMISSION.md:38-41` documents the BTC sample-compatible `/app/data` run.
- `DOCKER_SUBMISSION.md:49-54` documents the official `/code/private_test.json` run with `SUBMISSION_FILE` and `SUBMISSION_TIME_FILE`.
- `DOCKER_SUBMISSION.md:61-67` documents the offline `--network none` run.
- `DOCKER_SUBMISSION.md:72-92` documents CSV validation commands.
- `DOCKER_SUBMISSION.md:110` documents Docker Hub push.
- `README.md:71-111` documents the same operational run commands.

Why it matches BTC:
- The repository prepares all required BTC pre-submit commands and output validation steps.

Remaining manual check:
- User must execute build, GPU run, offline run, output validation, and Docker Hub push manually. This phase intentionally did not run Docker.

### GitHub 2.1 - README

Status: PASS

Evidence:
- `README.md:37-62` states the final offline local Qwen model mode, no API/OpenRouter/runtime internet, no API key, CUDA 12.8+, torch `cu128`, and no vLLM-specific flags/tools.
- `README.md:126-156` contains the Pipeline Flow section and text diagram.
- `README.md:158-190` contains Data Processing, input priority, choice normalization, label parsing, deterministic fallback, and output examples.
- `README.md:192-210` contains Resource Initialization and states no vector DB/index/retrieval database is required.
- `README.md:212-227` documents official input/output contracts.

Why it matches BTC:
- README contains the required repository explanation: full pipeline, data processing, and resource initialization.

Remaining manual check:
- None before Docker validation.

### GitHub 2.2 - Requirements

Status: PASS

Evidence:
- `requirements.txt:6-14` exact-pins all non-comment direct dependency lines.
- `requirements.txt:3-5` documents that torch is intentionally installed in the Dockerfile for the CUDA 12.8 `cu128` wheel index.
- `Dockerfile:29-30` exact-pins `torch==2.7.1`.
- `Dockerfile:33-34` installs `requirements.txt`, not `requirements-openrouter.txt`.
- Safe validation `python -m pip check` reported `No broken requirements found.`

Why it matches BTC:
- Final direct dependencies are pinned, and the GPU-sensitive PyTorch dependency is pinned in the Dockerfile where the correct CUDA wheel index is specified.

Remaining manual check:
- Re-run `pip check` if dependencies change later.

### GitHub 2.3 - Source Organization

Status: PASS

Evidence:
- Root files exist: `Dockerfile`, `predict.py`, `inference.sh`, `README.md`, and `requirements.txt`.
- `predict.py:40-44` supports `/code/private_test.json` and `/app/data/private_test.json`.
- `predict.py:141-144` documents default official outputs `/code/submission.csv` and `/code/submission_time.csv`.
- `predict.py:157-159` supports `SUBMISSION_FILE` and `SUBMISSION_TIME_FILE`.
- `predict.py:178-180` loads samples and the local model predictor before the loop.
- `predict.py:182-196` measures timing around each individual sample prediction.
- `predict.py:201-209` writes exact CSV headers `qid,answer` and `qid,answer,time`.
- `predict.py:85-99` validates/coerces answers without hardcoded qids or answers.
- `inference.sh:1-5` has a shebang, strict mode, and calls `python predict.py "$@"`.

Why it matches BTC:
- Root `predict.py` is the end-to-end entrypoint, root `inference.sh` launches it, and per-sample timing is real loop timing rather than an average.

Remaining manual check:
- User must run real Qwen inference manually inside the final Docker image.

### BTC Clarification Mapping

Status: PASS

Evidence:
- Confirmed mount `/code/private_test.json`: `predict.py:40`, `README.md:39`, `DOCKER_SUBMISSION.md:49-54`.
- Confirmed output location inside `/code`: `predict.py:74-82`, `predict.py:141-144`, `README.md:216-227`.
- Confirmed Docker flags: `README.md:71-115` and `DOCKER_SUBMISSION.md:38-67` document `--gpus all`; `README.md:114-115` and `DOCKER_SUBMISSION.md:17-18` document no `--ipc=host` and no `--shm-size`.
- Confirmed timing per data point: `predict.py:182-196` and `predict.py:207-209`.
- Confirmed hardware/CUDA: `Dockerfile:12`, `Dockerfile:29-30`, `README.md:51-62`, `DOCKER_SUBMISSION.md:136-144`.
- vLLM note: `README.md:61-62`, `DOCKER_SUBMISSION.md:143-144`, and `docs/BTC_SUBMISSION_COMPLIANCE.md:31-32` state vLLM is not used, so `uv --torch-backend=cu128` is not applicable.
- Full mapping is recorded in `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`.

Why it matches BTC:
- Repository docs and implementation match the confirmed BTC input path, output location, timing contract, hardware/CUDA setting, and non-vLLM toolchain.

Remaining manual check:
- User must run final Docker build/run tests on a GPU machine.

## Validation Results

Commands run:

```bash
.venv/bin/python -m compileall -q src scripts tests predict.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/audit_model_policy.py
.venv/bin/python -m pip check
grep -nE '^(FROM|ARG|RUN|WORKDIR|COPY|ENV|CMD|ENTRYPOINT)' Dockerfile
grep for truncated SUBMISSION_TIME_FILE typo pattern in README.md DOCKER_SUBMISSION.md docs/METHOD.md docs/BTC_SUBMISSION_COMPLIANCE.md docs/BTC_FINAL_COMPLIANCE_MATRIX.md
grep -RInE "Pipeline Flow|Data Processing|Resource Initialization|/code/private_test.json|/app/data/private_test.json|submission_time.csv|CUDA 12.8|RTX 5060|cu128|--gpus all|--ipc=host|--shm-size|vLLM|uv|--torch-backend=cu128" README.md DOCKER_SUBMISSION.md docs/METHOD.md docs/BTC_SUBMISSION_COMPLIANCE.md docs/BTC_FINAL_COMPLIANCE_MATRIX.md
git check-ignore -v .env || true
git check-ignore -v Dockerfile.api || true
git check-ignore -v models || true
git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$|^models/)' || true
```

Results:
- `compileall`: PASS.
- `pytest`: PASS, `790 passed in 20.13s`.
- `scripts/audit_model_policy.py`: PASS, only competition-allowed models referenced.
- `pip check`: PASS, `No broken requirements found.` A non-fatal warning reported that the pip cache directory was not writable.
- Dockerfile structure grep: PASS, showed CUDA 12.8 base, requirements install, model download arg, offline env, and `CMD ["bash", "inference.sh"]`.
- Truncated `SUBMISSION_TIME_FILE` typo grep: PASS, no matches.
- Documentation contract grep: PASS, required terms found in README/Docker docs/method/compliance matrix.
- `git check-ignore`: PASS, `.env`, `Dockerfile.api`, and `models/` are ignored.
- tracked secret/legacy/model-weight grep: PASS, no tracked `.env`, `Dockerfile.api`, `Dockerfile.api.local`, or `models/` files found.

## Prohibited Actions Confirmation

This phase did not run:
- Docker build.
- Docker container.
- Model weight download.
- Real Qwen inference.
- Docker Hub push.
- Git commit.

This phase did not edit:
- `Dockerfile.api`.

This phase did not add:
- OpenRouter final mode.
- External API final mode.
- API key requirement.
- Runtime internet requirement.
- vLLM.
- `uv`.
- `--torch-backend=cu128`.
- `--ipc=host`.
- `--shm-size`.

## Final Manual Next Steps

1. Build final image:

```bash
docker build -t vquclinh/fastmcq-agent:latest .
```

2. Test official `/code/private_test.json` path:

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
