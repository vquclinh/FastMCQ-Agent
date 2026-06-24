# FASTMCQ Agent

A Vietnamese multiple-choice question-answering (MCQ) system. The final submission is delivered
as a **Docker image**: the container reads a test file from `/data` and writes predictions to
`/output/pred.csv` (`qid,answer`). It runs a dynamic pipeline (base predictor → selective V12B /
V13 reasoning layers → conservative selector) and works on any input — public, private, or
unseen — producing one answer per input question.

## Official Docker Submission

| | |
|---|---|
| **Image** | `vquclinh/fastmcq-agent:latest` |
| **Explicit equivalent** | `vquclinh/fastmcq-agent:api-baked` |
| **Safe fallback** | `vquclinh/fastmcq-agent:no-key` |

`latest` / `api-baked` is the API-enabled image (a contest key is baked in for evaluation
convenience). `no-key` is the safe image that runs offline by default and accepts a key at run
time. **No API key is stored in this repository.**

## Quick Start

```bash
mkdir -p data output
# Place private_test.csv (or public_test.csv) inside ./data

docker run --rm \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  vquclinh/fastmcq-agent:latest
```

The prediction file is written to:

```text
output/pred.csv
```

## Input and Output Contract

- **Input priority** (first match wins):
  1. `/data/private_test.csv`
  2. `/data/public_test.csv`
  3. `/data/private_test.json`
  4. `/data/public_test.json`

  Override with `-e INPUT_FILE=/data/<file>` or a CLI argument `--input <path>`.
- **Output:** `/output/pred.csv` (override with `-e OUTPUT_FILE=/output/<file>` or `--output`).
- **CSV format:** `qid,answer` — one row per input `qid`.
- **`answer`** is a single option label (`A`, `B`, `C`, `D`, …) sized to the question's number of
  choices. Most questions are 4-choice (`A`–`D`); the public test ranges up to 11 choices, so
  labels can extend to `K`.

## Runtime Modes

- **`latest` / `api-baked`** — API-enabled image for final evaluation convenience; runs the API
  production profile (key baked into the image layer).
- **`no-key`** — safe image with no baked key; runs offline by default, or with a key supplied at
  run time:

  ```bash
  docker run --rm \
    -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
    -v "$PWD/data:/data:ro" \
    -v "$PWD/output:/output" \
    vquclinh/fastmcq-agent:no-key
  ```

  With no key present, the container runs the offline profile and still writes a complete, valid
  `/output/pred.csv`.

Notes:
- No real API key is stored in GitHub. `.env` and the local-only `Dockerfile.api` are
  git-ignored.
- The API-baked image is a Docker Hub convenience artifact only; the committed repository ships
  the normal safe `Dockerfile`.

## System Overview

- **Base predictor** answers **every** input question (guarantees full coverage).
- **V12B** option-permutation / debiasing layer is applied **selectively** to higher-risk
  questions.
- **V13** multi-layer reasoning (programmatic / content-first / least-to-most) is applied
  **selectively**.
- **Unified selector** merges the candidates conservatively and writes predictions for **all**
  input `qid`s.
- **Default layer budget:** the V12B/V13 layers default to `auto = ceil(input_count / 8)`,
  **minimum 1** (e.g. 3 → 1, 463 → 58). The budget only limits how many questions the layers may
  revise — never how many appear in the output.

Public-leaderboard checkpoints observed during development: 78.40 → 78.83 → **79.7**. No
private-test performance is claimed.

## Repository Structure

```text
src/                    core inference system (system/ base/ layers/ api/ selector/ solvers/ evidence/ utils/)
scripts/                CLI / Docker entrypoints and tools (run_full_system.sh, tools/, run/, legacy/)
configs/                production profiles and the allowed-model policy
docs/METHOD.md          method description
DOCKER_SUBMISSION.md    Docker-specific submission details
docs/audits/            development and validation audit trail
tests/                  unit and integration tests
```

## Reproducibility and Validation

The suite passes and the model-policy audit is clean; the Docker image was tested across the I/O
matrix (default detection and explicit `--input`/`--output`).

```bash
.venv/bin/python -m compileall -q src scripts tests
.venv/bin/python -m pytest -q
.venv/bin/python scripts/audit_model_policy.py
```

## Documentation

- [DOCKER_SUBMISSION.md](DOCKER_SUBMISSION.md) — Docker build/run details and the I/O contract.
- [docs/METHOD.md](docs/METHOD.md) — method and architecture description.
- [docs/audits/](docs/audits/) — development and validation audit trail.

## Notes

Prepared for the Vietnamese Student HackAIthon / BTC Docker-based evaluation. No license file is
included.
