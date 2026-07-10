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

![FASTMCQ-Agent offline local Qwen confidence-routed architecture](assets/archi.png)

Pipeline: input resolver → MCQ normalizer → Base generation → confidence scoring → confidence
router → V12B (option-permutation majority vote) → V13 (deterministic reasoning) → selector →
output writer. At most `ceil(N / 20)` records are ever escalated past Base; a record not selected
by the router keeps its Base answer; only V12B-unresolved records reach V13; any failure anywhere
in this chain falls back to the already-computed Base answer.

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
[`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md) §3 and
`tests/unit/test_confidence_shadow_router_2l48d.py`.

## Offline / no external API

No OpenRouter, no external LLM API, no web retrieval at runtime — a single local open-weight model
loaded once per process. Verified by static import analysis and by direct observation of container
network activity across every real-model validation run.

## Documentation

- [`docs/FINAL_SYSTEM.md`](docs/FINAL_SYSTEM.md) — full architecture, component-by-component
  detail, execution-mode table, and known limitations (source of truth).
- [`DOCKER_SUBMISSION.md`](DOCKER_SUBMISSION.md) — the authoritative Docker build/run/retrieve guide.

## Evidence and limitations — stated honestly

All accuracy figures anywhere in this repository come from **self-authored synthetic diagnostic
sets**, never organizer ground truth — true competition accuracy is not known in-repo. The
confidence-routed default was promoted deliberately, with explicit disclosure of the evidence
behind that decision — it is not presented as a guaranteed accuracy improvement. GPU peak memory
across all real-model validation runs has stayed at
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

## Research acknowledgements

FASTMCQ-Agent builds on ideas developed by the broader language-model reasoning, uncertainty, and
selective-prediction research communities. We gratefully acknowledge the authors of the following
works:

- **Option-order robustness:** Chujie Zheng et al., [*Large Language Models Are Not Robust Multiple
  Choice Selectors*](https://arxiv.org/abs/2309.03882). This work motivated our attention to
  answer-position sensitivity in MCQ systems. FASTMCQ-Agent's V12B addresses a related failure mode
  with its own deterministic permutation-and-vote procedure and does not implement PriDe.
- **Consistency and structured reasoning:** Xuezhi Wang et al., [*Self-Consistency Improves Chain of
  Thought Reasoning in Language Models*](https://arxiv.org/abs/2203.11171); Jason Wei et al.,
  [*Chain-of-Thought Prompting Elicits Reasoning in Large Language Models*](https://arxiv.org/abs/2201.11903);
  and Denny Zhou et al., [*Least-to-Most Prompting Enables Complex Reasoning in Large Language
  Models*](https://arxiv.org/abs/2205.10625). Their work informed the broader majority-voting,
  structured-reasoning, and decomposition design space: V12B varies option order rather than
  sampling multiple free-form reasoning chains, the Base prediction path does not depend on
  free-form chain-of-thought output, and `least_to_most` takes inspiration from constraint
  decomposition without reproducing the paper's method exactly.
- **Program-aided reasoning:** Luyu Gao et al., [*PAL: Program-aided Language
  Models*](https://arxiv.org/abs/2211.10435). Our `programmatic_solver` follows the general
  principle of separating model-produced calculation specifications from deterministic computation,
  using a narrower safe-AST implementation rather than a complete PAL system.
- **Uncertainty and selective escalation:** Dan Hendrycks and Kevin Gimpel, [*A Baseline for
  Detecting Misclassified and Out-of-Distribution Examples in Neural
  Networks*](https://arxiv.org/abs/1610.02136); Saurav Kadavath et al., [*Language Models (Mostly)
  Know What They Know*](https://arxiv.org/abs/2207.05221); and Amita Kamath, Robin Jia, and Percy
  Liang, [*Selective Question Answering under Domain Shift*](https://arxiv.org/abs/2006.09462).
  Their research on output-distribution uncertainty and calibration informed our decision to rely
  on token-level confidence and entropy signals — rather than asking the model to verbally report
  its own confidence — to selectively escalate uncertain records.
- **Bounded cascades:** Lingjiao Chen, Matei Zaharia, and James Zou, [*FrugalGPT: How to Use Large
  Language Models While Reducing Cost and Improving Performance*](https://arxiv.org/abs/2305.05176).
  Their work informed the general bounded-routing and cascade perspective; FASTMCQ-Agent reuses one
  fully local model with multiple reasoning strategies rather than routing across external LLM
  services.

> These works inspired parts of the design space; FASTMCQ-Agent does not claim to reproduce their
> methods exactly. Any implementation differences and errors are our own.

---

<div align="center">

Prepared for the Vietnamese Student HackAIthon 2026 / BTC Docker-based evaluation.

</div>
