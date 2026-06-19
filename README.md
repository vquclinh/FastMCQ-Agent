# FastMCQ-Agent

A multiple-choice QA (MCQ) inference system for **HackAIthon 2026 — Board C / Innovator**.

Given a set of questions, each with a list of choices, the system predicts one
answer label (`A`, `B`, `C`, ...) per question and writes a submission CSV.

> **Status:** the default solver is still the dependency-free `AlwaysASolver`
> **format-check baseline** (predicts `A`), so the container always produces a
> valid submission out of the box. Phase 2B/C adds **local-LLM solvers**
> (`hf_generate`, `hf_option_score`) behind the same interface — opt in with
> `--solver` + a **local** model path. No model is bundled or downloaded.
> See [docs/METHOD.md](docs/METHOD.md).

## Competition I/O contract

| | |
|---|---|
| **Input** | Mounted at `/data`. May be **JSON** (a list of objects) or **CSV**. |
| **Output** | Written to `/output/pred.csv`. |
| **Columns** | `qid,answer` |
| **Labels** | `A, B, C, ...` — sized to each question's number of choices (the public test has 2–11 choices, so labels are **not** hard-coded to A–D). |

Input auto-detection priority inside `/data`:
`private_test.csv` → `private-test.json` → `public_test.csv` → `public-test.json`
→ any other `.csv`/`.json` file (sorted). Override with `--input`.

## Project layout

```
FASTMCQ-AGENT/
├── run.py                 # entry point: detect input -> solve -> write pred.csv
├── configs/default.yaml   # config (Phase 1 reads `solver`; rest are placeholders)
├── src/
│   ├── data_io.py         # load JSON/CSV, normalise, read/write predictions
│   ├── labels.py          # index<->label, validity (supports >4 choices)
│   ├── solver_base.py     # BaseSolver interface
│   ├── baseline_solver.py # AlwaysASolver (Phase 1 baseline)
│   ├── postprocess.py     # validate, fallback to A, one answer per qid
│   └── utils.py           # logging + config loading
├── scripts/
│   ├── run_local.sh       # run + validate end-to-end locally
│   ├── inspect_dataset.py # dataset stats and detected schema
│   └── validate_submission.py
├── tests/                 # label + data_io tests (pytest or standalone)
├── data/                  # (runtime) harness mounts dataset here
├── outputs/               # (runtime) local prediction outputs
└── docs/                  # hackaithon.pdf, METHOD.md, AUDIT_INITIAL_SETUP.md
```

## Quick start (local)

```bash
# Optional: install deps (core pipeline needs only the stdlib + PyYAML)
pip install -r requirements.txt

# Run the baseline on the bundled public test
python run.py --input public-test_1780368312.json --output outputs/pred.csv

# Or do run + validate in one step
bash scripts/run_local.sh
```

### Inspect the dataset

```bash
python scripts/inspect_dataset.py --input public-test_1780368312.json
```

### Validate a submission

```bash
python scripts/validate_submission.py \
  --input public-test_1780368312.json \
  --submission outputs/pred.csv
```

### Profile the dataset

Generate a deep dataset analysis (choice-count distribution, long-context vs.
standalone questions, rough category breakdown, template/edge-case detection,
and sample-submission inspection). Writes a Markdown report and a JSON dump.

```bash
python scripts/profile_dataset.py \
  --input public-test_1780368312.json \
  --sample-submission submission_1780332147.csv
# -> docs/DATASET_PROFILE.md  and  outputs/dataset_profile.json
```

See [docs/DATASET_PROFILE.md](docs/DATASET_PROFILE.md) for the current report.

### Experiment logging

Leaderboard-driven development is tracked in [experiments/](experiments/).
Append one row per attempt to `experiments/leaderboard_log.csv` and fill in the
score after submitting — see [experiments/README.md](experiments/README.md).

## Docker

```bash
# Build
docker build -t fastmcq-agent .

# Run — mount the dataset into /data and collect /output/pred.csv.
# The default CMD targets /data/public-test.json.
docker run --rm \
  -v "$PWD/data:/data" \
  -v "$PWD/outputs:/output" \
  fastmcq-agent

# BTC may mount a different file; auto-detect by overriding the command
# with no --input:
docker run --rm -v /path/to/data:/data -v /path/to/out:/output \
  fastmcq-agent python run.py --output /output/pred.csv
```

## Local LLM solver (Phase 2B/C)

The baseline above always works with **no extra dependencies**. To run a real
model, install `torch` + `transformers` locally and point the solver at a
**local** model directory. **Nothing is downloaded** and no external API is
called — `--model-path` must already exist on disk.

Two solvers are available:

- **`hf_generate`** — prompts the model and parses a single answer label out of
  its short generated reply. Simple; quality depends on the model following the
  "output only the label" instruction.
- **`hf_option_score`** *(preferred)* — scores every candidate answer as a
  continuation (`A. <text>`, `B. <text>`, ...) and picks the highest
  length-normalised log-probability. More stable than generation, and it handles
  any number of choices (2, 3, 4, 10, 11). Falls back to generation, then `A`.

Both return a **dynamic label** sized to the question's actual choice count and
keep the same valid-or-fallback-to-`A` guarantee via `postprocess.py`.

```bash
# 1) Smoke test on the first 10 samples (confirms the model loads + parses)
bash scripts/run_llm_smoke.sh /path/to/local/model
#    -> outputs/pred_llm_smoke.csv  + validation

# 2) Full public inference with the option-scoring solver
bash scripts/run_llm_full.sh /path/to/local/model
#    -> outputs/pred_llm.csv  + validation + reminder to upload & log the score

# Equivalent explicit command:
python run.py --solver hf_option_score --model-path /path/to/local/model \
  --input public-test_1780368312.json --output outputs/pred_llm.csv \
  --log-path outputs/run_debug.jsonl

# 3) Validate any submission
python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_llm.csv

# 4) Benchmark runtime from the debug log
python scripts/benchmark_runtime.py --log-path outputs/run_debug.jsonl
```

Useful flags: `--limit N` (first N samples), `--resume FILE` (skip qids already
predicted), `--save-raw` (log raw outputs/scores), `--max-input-tokens`,
`--max-new-tokens`, `--temperature`, `--device`, `--trust-remote-code`. CLI flags
override `configs/default.yaml` (see its `hf:` section).

### Recommended workflow

1. `run_llm_smoke.sh` — sanity-check the model on 10 samples.
2. `run_llm_full.sh` — full run + validate.
3. Validate the submission CSV.
4. Upload `outputs/pred_llm.csv` to the leaderboard.
5. Record the score in [`experiments/leaderboard_log.csv`](experiments/leaderboard_log.csv).

## Tests

```bash
# With pytest
pytest -q

# Or standalone, without pytest installed
python tests/test_labels.py
python tests/test_data_io.py
python tests/test_prompting.py
python tests/test_output_parser.py
python tests/test_solver_factory.py
```

HF-solver tests skip the heavy model-loading paths gracefully when
torch/transformers are not installed.

## Roadmap

- **Phase 1 / 1.1:** repo skeleton, data contract, baseline solver, validation,
  hardened Docker. ✅
- **Phase 2A:** dataset profiling + experiment tracking. ✅
- **Phase 2B/C:** local-LLM solvers (`hf_generate`, `hf_option_score`) behind the
  `BaseSolver` interface, with prompting, output parsing, runtime logging. ✅
- **Phase 2D (next):** batching, quantization, faster backends (vLLM/llama.cpp),
  adaptive routing, prompt ensembles. See [docs/METHOD.md](docs/METHOD.md).
