# FASTMCQ Agent

<div align="center">

### Vietnamese Multiple-Choice Reasoning Agent for Student HackAIthon 2026

Docker-first, fully offline MCQ answering system for the BTC private-test evaluation.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Docker](https://img.shields.io/badge/Docker-Hub-blue)
![Status](https://img.shields.io/badge/Status-Final%20Submission-success)
![Model Policy](https://img.shields.io/badge/Model%20Policy-PASS-brightgreen)
![Output](https://img.shields.io/badge/Output-qid%2Canswer-orange)

</div>

## What FASTMCQ-Agent is

FASTMCQ-Agent answers Vietnamese multiple-choice questions using **one local, open-weight model**
(`Qwen/Qwen3-4B-Instruct-2507`, 4.0B parameters, Apache-2.0) with no external API and no internet
at runtime. By default it wraps that model in a **confidence-routed pipeline**: every question is
answered once and scored once; only the small, budget-capped fraction of questions the model is
genuinely unsure about are escalated to two independent verification stages before a conservative
selector decides the final answer. Every stage falls back safely to the plain single-pass answer on
any failure. See [`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md) for the full architecture.

## Competition / runtime constraints

Built for the **Vietnamese Student HackAIthon 2026 — Bảng C Innovator** Docker-based evaluation,
which runs in an **internet-isolated** environment with a **single open-weight model ≤ 5B
parameters** and no external API. The submitted Docker Hub container reads
`/code/private_test.json` and writes `/code/submission.csv` (`qid,answer`) and
`/code/submission_time.csv` (`qid,answer,time`).

## Final architecture

```text
private_test.json
   |
   v
Base Qwen3-4B generation (every record, once)
   |
   v
One-forward confidence scoring (top1 / top2 / logit margin / normalized entropy)
   |
   v
Confidence router  --------------------------->  not selected (most records) --\
   | selected: at most ceil(N / 20) records                                    |
   v                                                                            |
V12B: option-permutation majority vote                                         |
   | valid_unique_majority --------------------------------------------------->|
   | otherwise, unresolved                                                     |
   v                                                                            |
V13: programmatic_solver / content_first / least_to_most (one layer, chosen    |
     automatically) --------------------------------------------------------->|
   | on failure -----------------------------------------------------------\  |
   v                                                                        v  v
                                                              Deterministic selector
                                                                       |
                                                                       v
                                                  submission.csv + submission_time.csv
                                                  + privacy-safe diagnostics (optional)
```

Full per-stage detail, the execution-mode table, safety/fallback design, and known limitations
live in [`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md).

## Official Docker submission

| | |
|---|---|
| **Image** | `vquclinh/fastmcq-agent-final:latest` |
| **Docker Hub** | <https://hub.docker.com/r/vquclinh/fastmcq-agent-final> |
| **Model (single, open-weight)** | `Qwen/Qwen3-4B-Instruct-2507` (4.0B < 5B, Apache-2.0) |
| **Mode** | fully offline — no external API, no internet at runtime |

Model weights are downloaded **at Docker build time** into `/models/qwen3-4b-instruct-2507`; the
container runs with `TRANSFORMERS_OFFLINE=1` / `HF_HUB_OFFLINE=1`. No API key exists in the image
or in GitHub.

### Default BTC run — no pipeline flag required

The confidence-routed pipeline described above is the **no-flag default**. The evaluator does not
need to pass any pipeline-selection flag — the same plain command below already runs the full
pipeline:

```bash
docker pull vquclinh/fastmcq-agent-final:latest

docker rm -f fastmcq_btc_test 2>/dev/null || true

docker run --name fastmcq_btc_test --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent-final:latest
```

### Retrieve the output files

`/code` is the path **inside the container**. Since no output directory was mounted above, copy the
files out after the container finishes (kept alive because `--rm` was not used and `--name` was
set):

```bash
docker cp fastmcq_btc_test:/code/submission.csv ./submission.csv
docker cp fastmcq_btc_test:/code/submission_time.csv ./submission_time.csv
docker rm fastmcq_btc_test
```

Alternatively, mount a host output directory and override the output env vars so the files land on
the host directly (see [`DOCKER_SUBMISSION.md`](DOCKER_SUBMISSION.md) for the full example).

### Custom input/output paths

```bash
mkdir -p btc_data btc_output

docker run --rm --gpus all \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent-final:latest
```

### Escape hatch: Base-only

`--base-only` reproduces the pre-pipeline Base-only behavior exactly (no confidence router, no
V12B, no V13, no selector) — useful as an emergency/control run, not needed for normal submission.
This also writes to the default `/code/submission*.csv`, so retrieve it the same way (named
container, no `--rm`, then `docker cp`):

```bash
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

## Router budget

The confidence router escalates at most `ceil(N / 20)` records to V12B — a hard, predictable
ceiling, not a target. **N = 2000 → maximum 100 records escalated**, N = 120 → 6, N = 30 → 2. The
cap never backfills with high-confidence records to reach the budget; if fewer questions are
genuinely uncertain, fewer are escalated. Only the subset V12B leaves unresolved proceeds to V13 —
V12B and V13 do not both run on every selected record. Full derivation and test evidence:
[AUDIT 96](docs/audits/96-default-full-pipeline-and-budget-divisor20.md).

## Offline / no external API

No OpenRouter, no external LLM API, no web retrieval at runtime — a single local open-weight model
loaded once per process. Verified by static import analysis and by direct observation of container
network activity across every real-model validation run (AUDIT 92, 94, 95, 96).

## Documentation

- [`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md) — full architecture, component-by-component
  detail, execution-mode table, and known limitations (source of truth).
- [`DOCKER_SUBMISSION.md`](DOCKER_SUBMISSION.md) — the authoritative Docker build/run/retrieve guide.
- [`docs/audits/`](docs/audits/) — the full audit trail of every validated change, including
  real-model/GPU evidence (AUDIT 92, 94, 95, 96 are the current governing state).

## Evidence and limitations — stated honestly

All accuracy figures anywhere in this repository come from **self-authored synthetic diagnostic
sets**, never organizer ground truth — true competition accuracy is not known in-repo. The
confidence-routed default was promoted deliberately, with explicit disclosure of the evidence
behind that decision (see AUDIT 94/95/96) — it is not presented as a guaranteed accuracy
improvement. GPU peak memory across all real-model validation runs has stayed at
**≈6.2–6.4 GiB**, comfortably inside an 8 GiB card, but this is not a guarantee for arbitrarily
large inputs. See [`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md) §5 for the full, current
limitations list.

## Security & Compliance

- **Offline at runtime:** no external API, no internet — a single local open-weight model.
- Model weights are downloaded **at build time** and are **never committed** — `models/` is
  git-ignored.
- CUDA 12.8+ base image (`nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`), exact-pinned
  `torch==2.7.1` (`cu128`); no vLLM, so `--ipc=host`/`--shm-size` are not required — only
  `--gpus all`.
- No provider key required: `.env` is git-ignored.
- No vector database, no retrieval index; only the Qwen model is initialized during Docker build.

---

<div align="center">

Prepared for the Vietnamese Student HackAIthon 2026 / BTC Docker-based evaluation.

</div>
