# Docker Submission — FASTMCQ Final (offline local model)

The final image is **fully offline**: it runs a single open-weight local model
(`Qwen/Qwen3-4B-Instruct-2507`, 4.0B < 5B, Apache-2.0) via Hugging Face Transformers and answers
each MCQ deterministically. **No OpenRouter, no external API, no internet at runtime.** The
container reads `/code/private_test.json` and writes `/code/submission.csv` (`qid,answer`) and
`/code/submission_time.csv` (`qid,answer,time`, a real per-sample time).

## Official submission image

- **Image:** `vquclinh/fastmcq-agent:latest`
- **Model:** `Qwen/Qwen3-4B-Instruct-2507` (downloaded into the image at **build time**)
- **Default command:** `predict.py` via `inference.sh` (`CMD ["bash", "inference.sh"]`,
  `WORKDIR /code`)
- **BTC contract:** in `/code/private_test.json` → out `/code/submission.csv` +
  `/code/submission_time.csv`
- **Required Docker flags:** `--gpus all` (local Transformers GPU inference). **`--ipc=host` is
  NOT required** and **`--shm-size` is NOT required** (no vLLM). No
  `-e OPENROUTER_API_KEY` and no network access are needed.

### Build

```bash
# Final build: downloads the model into the image (no HF token needed for this public model).
docker build -t vquclinh/fastmcq-agent:latest .
```

### Run — BTC default (no flags)

```bash
docker run --rm --gpus all vquclinh/fastmcq-agent:latest
```

### Run — BTC sample-compatible `/app/data`

This reads `/app/data/private_test.json`.

```bash
docker run --rm --gpus all \
  -v "$PWD/btc_data:/app/data:ro" \
  vquclinh/fastmcq-agent:latest
```

### Run — reproducible local (outputs kept on the host)

```bash
mkdir -p btc_data btc_output
# put private_test.json in ./btc_data/private_test.json
docker run --rm --gpus all \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent:latest
```

### Run — offline runtime verification

The model is already baked in, so this should still work with no runtime network.

```bash
docker run --rm --gpus all --network none \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent:latest
```

### Validate output files

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

Expected output shape:

```text
submission.csv:
qid,answer
test_0001,A

submission_time.csv:
qid,answer,time
test_0001,A,1.2345
```

### Push after manual validation

```bash
docker push vquclinh/fastmcq-agent:latest
```

### Legacy compatibility (old `/data` → `/output/pred.csv`)

```bash
docker run --rm --gpus all -v "$PWD/data:/data:ro" -v "$PWD/output:/output" \
  vquclinh/fastmcq-agent:latest
```

Reads `/data/private_test.csv` (else `/data/public_test.csv`, else the `.json` equivalents) and
mirrors predictions to `/output/pred.csv`.

## Resource initialization & timing

- Model weights are fetched by `scripts/download_local_model.py` **during `docker build`** into
  `/models/qwen3-4b-instruct-2507`; runtime sets `LOCAL_MODEL_PATH`, `TRANSFORMERS_OFFLINE=1`,
  `HF_HUB_OFFLINE=1`.
- **No vector database is required. No indexing step is required. Only the Qwen model is
  initialized during Docker build.** No internet is used at runtime.
- `submission_time.csv` records a **real per-sample** time measured around each question's local
  inference. Per-sample failures fall back to a deterministic label so the output always covers
  every input qid.

## Base image

BTC confirmed CUDA 12.8+ base images for the target GPU environment. This final
GPU/local-Transformers image uses the clean official
`nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04` base accordingly. The original BTC Dockerfile
template mentioned CUDA 12.2, but that is only historical context for this repository. PyTorch is
installed as exact-pinned `torch==2.7.1` from the CUDA 12.8 (`cu128`) wheel index inside the
Dockerfile; other deps come from `requirements.txt`.

This solution does not use vLLM. Therefore `--ipc=host`, `--shm-size`, `uv`, and
`--torch-backend=cu128` are not required for the final image.

## What ships in the image

- Source (`src/`, `scripts/`, `predict.py`, `inference.sh`), `requirements.txt`, the baked model
  weights under `/models/` (built in, **never committed to git**).
- **Excluded** by `.dockerignore`: `.env`/secrets/keys, `scratch/`, `experiments/`, `docs/`,
  `.git/`, notebooks, `*.log`, `*.jsonl`, host `models/` and caches.

## Optional dev image (`Dockerfile.api`, local-only, git-ignored)

`Dockerfile.api` mirrors the offline image but bakes an `OPENROUTER_API_KEY` (build arg) so the
**dev-only** `predict.py --legacy-dynamic-full` path can exercise the older API pipeline. It is
**not** the submission, **never committed**, and must use a disposable key.

<!-- legacy OpenRouter notes retained below for development reference only -->
<details>
<summary>Legacy dev-only OpenRouter pipeline (NOT the submission)</summary>

The earlier dynamic API pipeline (base → V12B → V13 → conservative selector) is reachable only
via `predict.py --legacy-dynamic-full` and is used for development only — never in the offline
submission. It read `/data/private_test.csv|public_test.csv` (or the BTC `/code` paths) and, when
`OPENROUTER_API_KEY` was present, called the allowed model via OpenRouter
(`production_full_system`); without a key it ran `production_full_system_noapi`. Its selective
V12B/V13 budget defaulted to `auto = ceil(input_count / 8)` (min 1). The local helper
`bash scripts/run_full_system.sh <test_file> --no-api` still runs it offline and writes
`output/pred.csv`. None of this is required for, or used by, the final offline image.

</details>

## Notes

- Default = offline local model (`Qwen/Qwen3-4B-Instruct-2507`); no OpenRouter / external API /
  internet at runtime.
- Docker startup uses BTC-template `CMD ["bash", "inference.sh"]`. With `CMD`, use
  `SUBMISSION_FILE` and `SUBMISSION_TIME_FILE` for Docker output overrides.
- `final_infer.py` still refuses to overwrite protected/locked historical CSVs under `output/`.
- No real API key is stored in GitHub; `.env`, `Dockerfile.api`, and `models/` are git-ignored.
