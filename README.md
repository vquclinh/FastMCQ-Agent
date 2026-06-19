# FastMCQ-Agent

A multiple-choice QA (MCQ) inference system for **HackAIthon 2026 — Board C / Innovator**.

Given a set of questions, each with a list of choices, the system predicts one
answer label (`A`, `B`, `C`, ...) per question and writes a submission CSV.

> **Phase 1 status: baseline infrastructure only.**
> The current solver (`AlwaysASolver`) predicts `A` for every question. It is a
> **format-check baseline** that exercises the full pipeline (load → solve →
> validate → write) and guarantees a structurally valid submission. Real LLM
> inference arrives in Phase 2 — see [docs/METHOD.md](docs/METHOD.md).

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

## Tests

```bash
# With pytest
pytest -q

# Or standalone, without pytest installed
python tests/test_labels.py
python tests/test_data_io.py
```

## Roadmap

- **Phase 1 (this commit):** repo skeleton, data contract, baseline solver,
  validation, Docker, docs. ✅
- **Phase 2:** real LLM inference — swap `AlwaysASolver` for an LLM-backed
  solver behind the same `BaseSolver` interface. See
  [docs/METHOD.md](docs/METHOD.md).
