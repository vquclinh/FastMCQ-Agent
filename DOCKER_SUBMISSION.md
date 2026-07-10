# Docker Submission — FASTMCQ Final (offline local model)

This is the one authoritative Docker build/run/retrieve guide for FASTMCQ-Agent. Other Markdown
files that mention Docker (`docs/BTC_SUBMISSION_COMPLIANCE.md`, `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`)
link back here rather than duplicating commands.

The final image is **fully offline**: it runs a single open-weight local model
(`Qwen/Qwen3-4B-Instruct-2507`, 4.0B < 5B, Apache-2.0) via Hugging Face Transformers. **No external
API and no internet are used at runtime.** By default the container runs the full
**confidence-routed pipeline** (Base generation → one-forward confidence scoring → confidence
router → V12B → V13 → deterministic selector; architecture detail in
[`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md)) — **no CLI flag is required to get this behavior.**
It reads `/code/private_test.json` and writes `/code/submission.csv` (`qid,answer`) and
`/code/submission_time.csv` (`qid,answer,time`, a real per-sample time).

## Official submission image

- **Image:** `vquclinh/fastmcq-agent-final:latest`
- **Docker Hub:** <https://hub.docker.com/r/vquclinh/fastmcq-agent-final>
- **Model:** `Qwen/Qwen3-4B-Instruct-2507` (downloaded into the image at **build time**; the only
  generation model, shared by Base, V12B, and V13)
- **Default command / ENTRYPOINT contract:** there is no `ENTRYPOINT`; `CMD ["bash", "inference.sh"]`
  runs `python predict.py "$@"` with `WORKDIR /code`. With no extra arguments, `predict.py` receives
  zero CLI flags and resolves to the full confidence pipeline (the no-flag default).
- **BTC contract:** in `/code/private_test.json` → out `/code/submission.csv` +
  `/code/submission_time.csv`.
- **Required Docker flags:** `--gpus all` (local Transformers GPU inference). `--ipc=host` and
  `--shm-size` are **not required** (no vLLM). No network access is needed at runtime.

### Pull

```bash
docker pull vquclinh/fastmcq-agent-final:latest
```

### Build (only needed if building from source instead of pulling)

```bash
docker build -t vquclinh/fastmcq-agent-final:latest .
```

### Run — BTC default (no flags, full confidence pipeline)

Default host/container mount contract: mount the private-test file read-only at
`/code/private_test.json` inside the container. Do **not** mount a host directory at `/code` itself
(e.g. `-v "$PWD:/code"`) — that would overwrite the application directory inside the image (source,
`predict.py`, `inference.sh`) with whatever is on the host.

This example does not mount an output directory, so the outputs land only inside the container's
`/code/`. Do **not** use `--rm` here — it would delete the container, and the outputs with it,
before they can be copied out. Keep the container (named, no `--rm`) and copy the files out with
`docker cp`:

```bash
docker rm -f fastmcq_btc_test 2>/dev/null || true

docker run \
  --name fastmcq_btc_test \
  --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent-final:latest

docker cp fastmcq_btc_test:/code/submission.csv ./submission.csv
docker cp fastmcq_btc_test:/code/submission_time.csv ./submission_time.csv

docker rm fastmcq_btc_test
```

This already runs the full pipeline described in `docs/FINAL_SYSTEM.md` — no
`--confidence-full-pipeline` flag is necessary for a normal submission; it is provided only as an
explicit, equivalent alias (see "Execution modes" below).

### Run — custom input/output paths (outputs kept on the host)

Real, currently supported flags/env vars: `--input`/`$INPUT_FILE` for the input path,
`--submission`/`$SUBMISSION_FILE` and `--submission-time`/`$SUBMISSION_TIME_FILE` for the output
paths (CLI flag takes priority over the env var, which takes priority over the default
`/code/submission*.csv`).

```bash
mkdir -p btc_data btc_output
# put private_test.json in ./btc_data/private_test.json

docker run --rm --gpus all \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent-final:latest
```

### Windows PowerShell equivalent

```powershell
docker run --rm --gpus all `
  -v "${PWD}\btc_data\private_test.json:/code/private_test.json:ro" `
  -v "${PWD}\btc_output:/code/btc_output" `
  -e SUBMISSION_FILE=/code/btc_output/submission.csv `
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv `
  vquclinh/fastmcq-agent-final:latest
```

### Run — offline runtime verification

The model is already baked in, so this should still work with no runtime network.

```bash
docker run --rm --gpus all --network none \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent-final:latest
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
docker push vquclinh/fastmcq-agent-final:latest
```

## Execution modes

| Flag | Use case |
|---|---|
| *(none)* | **Normal submission.** Full confidence pipeline — this is the default. |
| `--confidence-full-pipeline` | Explicit, equivalent alias of the default. Not needed for normal submission. |
| `--base-only` | Emergency/control run only: disables the router/V12B/V13/selector, Base answers stand as-is. |
| `--legacy-dynamic-full` | Isolated legacy development path (pre-confidence-pipeline prototype). Not used for submission. |

```bash
# Emergency/control run, e.g. to isolate whether an issue is in the router/V12B/V13 layer.
# Also writes the default /code/submission*.csv, so retrieve it the same way as above (no --rm):
docker rm -f fastmcq_base_only 2>/dev/null || true

docker run \
  --name fastmcq_base_only \
  --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent-final:latest \
  python predict.py --base-only

docker cp fastmcq_base_only:/code/submission.csv ./submission.csv
docker cp fastmcq_base_only:/code/submission_time.csv ./submission_time.csv
docker rm fastmcq_base_only
```

Full architecture, the `ceil(N/20)` router budget, and per-stage detail:
[`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md).

### Legacy compatibility (old `/data` → `/output/pred.csv`)

```bash
docker run --rm --gpus all -v "$PWD/data:/data:ro" -v "$PWD/output:/output" \
  vquclinh/fastmcq-agent-final:latest
```

Reads `/data/private_test.csv` (else `/data/public_test.csv`, else the `.json` equivalents) and
mirrors predictions to the mounted `/output/pred.csv`, which is what `--rm` is safe to use with
here — `/output` is a host-mounted directory, so `pred.csv` persists after the container is
removed. The run still also writes the standard `/code/submission.csv` /
`/code/submission_time.csv` internally (same default confidence pipeline as above), but since
`/code` is not mounted in this example, those two copies are **not** persisted when the container
is removed — use `/output/pred.csv` as the retrieved artifact in this mode, or additionally mount
`/code/submission.csv` / `/code/submission_time.csv` (or drop `--rm` and `docker cp` them, as
above) if you need both artifacts.

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

- Source (`src/`, `scripts/`, `predict.py`, `inference.sh`), `requirements.txt`, `configs/`, the
  baked model weights under `/models/` (built in, **never committed to git**).
- **Excluded** by `.dockerignore`: `.env`/secrets/keys, `scratch/`, `experiments/`, `docs/`,
  `.git/`, notebooks, `*.log`, `*.jsonl`, host `models/` and caches.

## Notes

- Default = the confidence-routed pipeline running on the offline local model
  (`Qwen/Qwen3-4B-Instruct-2507`); no external API or internet at runtime.
- Docker startup uses BTC-template `CMD ["bash", "inference.sh"]`. With `CMD`, use
  `SUBMISSION_FILE` and `SUBMISSION_TIME_FILE` for Docker output overrides.
- `.env`, local-only Docker variants, and `models/` are git-ignored and are not part of the
  submission image.
