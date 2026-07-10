# BTC Submission Compliance

Scope: Vietnamese Student HackAIthon — Bảng C Innovator final Docker submission,
`vquclinh/fastmcq-agent-final:latest`
(<https://hub.docker.com/r/vquclinh/fastmcq-agent-final>).

By default the image runs the confidence-routed pipeline (Base → confidence scoring → router →
V12B → V13 → selector); see [`docs/FINAL_SYSTEM.md`](FINAL_SYSTEM.md) for architecture and
[`../DOCKER_SUBMISSION.md`](../DOCKER_SUBMISSION.md) for the canonical, up-to-date run commands.
The commands below verify Dockerfile-level compliance (base image, CUDA, offline env) and remain
correct; treat `../DOCKER_SUBMISSION.md` as authoritative if the two ever appear to diverge.

## Dockerfile Requirements

### 2.1 General Dockerfile Principles

- Base image: clean official `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- The Dockerfile does not derive from `vquclinh/fastmcq-agent`, `team_submission`, or any local
  previously built image.
- Required runtime model resources are initialized during Docker build:
  `scripts/download_local_model.py --model Qwen/Qwen3-4B-Instruct-2507 --out /models/qwen3-4b-instruct-2507`.
- `ARG SKIP_MODEL_DOWNLOAD=0` defaults to the real model download. `SKIP_MODEL_DOWNLOAD=1` is only
  for CI/smoke checks.
- `models/` is git-ignored; model weights must not be committed.
- No vector database is required. No indexing step is required. Only the Qwen model is initialized
  during Docker build.

### 2.2 CUDA Configuration

- BTC confirmed CUDA 12.8+ base images for the target GPU environment.
- Final base image uses CUDA 12.8+ accordingly:
  `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`.
- The original BTC template mentioned CUDA 12.2, but that is historical context only for this
  repository.
- PyTorch is exact-pinned in the Dockerfile as `torch==2.7.1` from the CUDA 12.8 `cu128` index.
- Runtime flag required: `--gpus all`.
- vLLM is not used.
- Runtime flags/tools not required for this solution: no `--ipc=host`, no `--shm-size`, no `uv`,
  and no `--torch-backend=cu128`.

### 2.3 Dockerfile Template

- `WORKDIR /code`.
- `COPY . /code`.
- Dependencies install from `requirements.txt`; PyTorch is installed separately from the `cu128`
  PyTorch index.
- `/usr/bin/python` is linked to `/usr/bin/python3`.
- Offline runtime environment:
  `LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507`, `TRANSFORMERS_OFFLINE=1`,
  `HF_HUB_OFFLINE=1`.
- Default startup uses the stricter BTC template shape:
  `CMD ["bash", "inference.sh"]`.
- With `CMD`, Docker output overrides use environment variables:
  `SUBMISSION_FILE` and `SUBMISSION_TIME_FILE`.

## Manual Pre-Submit Commands

Do not run these as part of static audit work; they are for the final manual GPU/Docker check.

Build final image:

```bash
docker build -t vquclinh/fastmcq-agent-final:latest .
```

BTC sample-compatible run using `/app/data` (no output mount, so `--rm` is not used here —
keep the named container and copy the default `/code/submission*.csv` out with `docker cp`):

```bash
docker rm -f fastmcq_app_data_test 2>/dev/null || true

docker run \
  --name fastmcq_app_data_test \
  --gpus all \
  -v "$PWD/btc_data:/app/data:ro" \
  vquclinh/fastmcq-agent-final:latest

docker cp fastmcq_app_data_test:/code/submission.csv ./submission.csv
docker cp fastmcq_app_data_test:/code/submission_time.csv ./submission_time.csv
docker rm fastmcq_app_data_test
```

Official `/code/private_test.json` reproduction with outputs preserved on host:

```bash
mkdir -p btc_data btc_output

docker run --rm --gpus all \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent-final:latest
```

Offline runtime verification:

```bash
docker run --rm --gpus all --network none \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent-final:latest
```

Output validation:

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

Push after successful manual validation:

```bash
docker push vquclinh/fastmcq-agent-final:latest
```
