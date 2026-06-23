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

## Final submission (production default)

The official system is a **dynamic full pipeline** (`--mode dynamic_full`, the default) that
runs over any input — public, private, unseen, or larger sets — and outputs predictions for
exactly the input qids: dynamic base predictor → official **V12B** option-permutation debiaser →
official **V13** multi-layer reasoning (programmatic / content-first / least-to-most) → unified
selector. **Both V12B and V13 are enabled by default.** The frozen public artifact
`outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv` (public **79.7**; +0.87 over V12B
78.83, +1.30 over v11 78.40) is the current public-best CSV for **leaderboard reproducibility
only** (`--mode public_replay`), not the universal private solution. The default command is
API-free, validates automatically, and prints the resolved mode + V12B/V13 targets/overrides +
elapsed time.

**Short commands (run profiles — recommended):**

```bash
bash scripts/run_public_replay.sh public-test_1780368312.json   # reproduce the 79.7 public artifact
bash scripts/run_dynamic_noapi.sh public-test_1780368312.json   # full dynamic system, no API
bash scripts/run_public_api100.sh public-test_1780368312.json   # quick API system check
bash scripts/run_private_api200.sh private_test.json            # recommended BTC/private API run
```

Each wrapper logs to `scratch/runs/<profile>_<ts>/` and prints elapsed time + output md5.
Full/explicit form:

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
```

`--input`/`--output` are optional — with the test file in the current directory (or under
`/data`) and `/output` available, the no-arg form works too (BTC/Docker style):

```bash
python scripts/final_infer.py          # auto-detects input, writes /output/pred.csv or ./pred.csv
```

No `--mode` or `--allow-pred-csv` needed. v10 is fallback only (`--mode v10`); regenerating
via the independent v11 runner is explicit/experimental (`--mode v11_independent --execute
--budget-usd ...`). See [FINAL_RUN.md](FINAL_RUN.md) and [DOCKER_SUBMISSION.md](DOCKER_SUBMISSION.md).

## Quick start (local, historical baseline)

> The commands below run the earlier Phase-1/2 `run.py` pipeline and are kept for reference.
> For the competition submission use the **Final submission** command above.

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
model, install the optional LLM deps and point the solver at a **local** model
directory. **Nothing is downloaded** and no external API is called —
`--model-path` must already exist on disk.

### Optional LLM environment setup

```bash
# Optional deps (torch, transformers, accelerate, sentencepiece, safetensors)
pip install -r requirements-llm.txt

# Check the environment (torch/transformers, CUDA, GPU/VRAM) — no downloads
python scripts/check_llm_env.py
python scripts/check_llm_env.py --model-path /path/to/local/model --load-tokenizer

# Check the model is within the allowed families BEFORE running it
python scripts/check_model_compliance.py --model-path /path/to/local/model
python scripts/check_model_compliance.py --model-name "Qwen3.5-7B" --strict
```

See [docs/MODEL_COMPLIANCE.md](docs/MODEL_COMPLIANCE.md) for which model families
are allowed (provisional: Qwen3.5 ≤ 9B, Gemma-4; BGE-m3 / Qwen-Rerank for
retrieval) and what still needs organizer confirmation.

Two solvers are available:

- **`hf_generate`** — prompts the model and parses a single answer label out of
  its short generated reply. Simple; quality depends on the model following the
  "output only the label" instruction.
- **`hf_option_score`** *(preferred)* — scores every candidate answer as a
  continuation and picks the highest length-normalised log-probability. More
  stable than generation, and it handles any number of choices (2, 3, 4, 10, 11).
  Falls back to generation, then `A`.

**Score modes** (`--score-mode`, default `label_plus_choice`):

| Mode | Scores continuation | Notes |
|---|---|---|
| `label_only` | `" A"` | Cleanest if the tokenizer cooperates; can be brittle. |
| `label_plus_choice` | `" A. <choice text>"` | **Default**, most robust. |
| `choice_only` | `" <choice text>"` | Label-free content likelihood. |

Both solvers return a **dynamic label** sized to the question's actual choice
count and keep the same valid-or-fallback-to-`A` guarantee via `postprocess.py`.

```bash
# 1) Smoke test on the first 10 samples (confirms the model loads + parses)
bash scripts/run_llm_smoke.sh /path/to/local/model [SCORE_MODE]
#    -> outputs/pred_llm_smoke.csv  + validation

# 2) Full public inference with the option-scoring solver
bash scripts/run_llm_full.sh /path/to/local/model [SCORE_MODE]
#    -> outputs/pred_llm.csv  + validation + reminder to upload & log the score

# Equivalent explicit command:
python run.py --solver hf_option_score --model-path /path/to/local/model \
  --score-mode label_plus_choice \
  --input public-test_1780368312.json --output outputs/pred_llm.csv \
  --save-raw --log-path outputs/run_debug.jsonl

# 3) Validate any submission
python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_llm.csv

# 4) Benchmark runtime from the debug log
python scripts/benchmark_runtime.py --log-path outputs/run_debug.jsonl
```

Useful flags: `--score-mode`, `--limit N` (first N samples), `--resume FILE`
(skip qids already predicted), `--save-raw` (log raw outputs/scores),
`--max-input-tokens`, `--max-new-tokens`, `--temperature`, `--device`,
`--trust-remote-code`. CLI flags override `configs/default.yaml` (`hf:` section).

### Recommended leaderboard experiment order

Run these in order and record each score in `experiments/leaderboard_log.csv`:

1. `hf_generate` (baseline LLM)
2. `hf_option_score --score-mode label_only`
3. `hf_option_score --score-mode label_plus_choice` (default)
4. `hf_option_score --score-mode choice_only`

Keep whichever scoring mode wins on the leaderboard.

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
