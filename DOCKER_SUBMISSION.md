# Docker Submission — FASTMCQ Final (dynamic system; V12B + V13 official layers)

The image runs the real **dynamic_full** system by default (dynamic base → V12B → V13 →
unified selector) over the mounted input and writes `/output/pred.csv` for exactly the input
qids. **No API key is required by default** (deterministic parts run; model-dependent layers are
`skipped_no_api`). The current public-best artifact is **V13 multi-layer 79.7**
(`output/pred_v13_multilayer_candidate_api30_from_v12b.csv`, +0.87 over V12B 78.83, +1.30 over
v11 78.40); reproduce it exactly with `--mode public_replay` on the public test.

## Official local command (use this)

```bash
bash scripts/run_full_system.sh <test_file>          # full system; needs OPENROUTER_API_KEY
bash scripts/run_full_system.sh <test_file> --no-api # fully offline
```
Runs base → V12B → V13 → selector end-to-end and writes the final local artifact to
**`output/pred.csv`** (Docker writes **`/output/pred.csv`**). Logs/records under
`scratch/runs/full_system_<ts>/`.

### Legacy / research diagnostics only (not the main workflow)

```bash
bash scripts/run/run_public_replay.sh public-test_1780368312.json   # reproduce the 79.7 artifact
bash scripts/run/run_dynamic_noapi.sh public-test_1780368312.json   # full dynamic system, no API
bash scripts/run/run_public_api50.sh public-test_1780368312.json    # medium API pilot (caps 50 qids)
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv  # explicit form
```
Runs `dynamic_full` (V12B + V13, API-free) and writes validated `pred.csv` for exactly the
input qids; prints resolved mode + V12B/V13 overrides + `elapsed_seconds` + `status: PASS`. To
reproduce the public 79.7 artifact exactly add `--mode public_replay`.

## What ships in the image

- Source (`src/`, `scripts/`), `configs/production/default.json`, `requirements.txt`.
- Required final CSVs under `output/`: `pred_v13_multilayer_candidate_api30_from_v12b.csv`
  (current best, 79.7), `pred_v12b_permutation_candidate_api30.csv` (previous best, 78.83),
  `pred_v11_independent_rerun1.csv`, and `pred_v10_full_production_user_run.csv` (fallback only).
- **Excluded** by `.dockerignore`: `.env`/secrets/keys, `scratch/`, `experiments/`, `docs/`,
  `.git/`, notebooks, `*.log`, `*.jsonl`, model weights/caches, and the non-final
  `output/pred.csv` / `output/pred_v11_full_adaptive_test.csv`.

## Build

```bash
docker build -t fastmcq-final .
```

## Official submission image (Docker Hub)

- **Image:** `vquclinh/fastmcq-agent:latest` — explicit equivalent tag
  `vquclinh/fastmcq-agent:api-baked`.
- **Run (BTC):**
  ```bash
  docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/output:/output" vquclinh/fastmcq-agent:latest
  ```
- Reads `/data/private_test.csv` (else `/data/public_test.csv`, else the `.json` equivalents) and
  writes `/output/pred.csv` (`qid,answer`).

**The submitted `:latest`/`:api-baked` image is built locally with the contest OpenRouter key
baked in** (so BTC needs no env wiring); it runs the API `production_full_system` profile. This
secret lives **only inside that Docker Hub image layer — never in GitHub**: `Dockerfile.api` is
git-ignored, `.env` is never committed, and no key appears in any tracked file. Use a
disposable/limited-credit key and revoke it after the contest. If you prefer no secret in the
image, use the `:no-key` image below and pass the key at run time.

## Safe image (Docker Hub: `vquclinh/fastmcq-agent:no-key`)

The committed repo ships **one** Docker build — the normal safe image (`Dockerfile`). It contains
**no API key**. Build and run:

```bash
docker build -t vquclinh/fastmcq-agent:no-key .

docker run --rm \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  vquclinh/fastmcq-agent:no-key
```

With no `OPENROUTER_API_KEY` in the env it runs the offline `production_full_system_noapi`
profile (still writes `/output/pred.csv`). To enable the API production profile, supply the key
**at run time** (the key never enters the image or the repo):

```bash
docker run --rm \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  vquclinh/fastmcq-agent:no-key
```

The entrypoint selects `production_full_system` when `OPENROUTER_API_KEY` is present, else
`production_full_system_noapi`. **Prefer this image** — runtime env injection exposes no secret.

> An *optional* secret-bearing `:api-baked` image (key baked at build time) can be built
> **locally** for convenience, but it is intentionally **not part of this GitHub repo** (its
> Dockerfile is git-ignored as local-only) and must never receive a real key in any committed
> file. Build only a disposable/limited-credit key into it and never publish it.

## Input / output priority (BTC contract)

The entrypoint and `final_infer.py` resolve I/O in this **exact** order:

**Input**
1. `--input <path>` (CLI argument) — wins over everything
2. `$INPUT_FILE` env var (if set and non-empty)
3. `/data/private_test.csv`
4. `/data/public_test.csv`
5. `/data/private_test.json`
6. `/data/public_test.json`

**Output**
1. `--output <path>` (CLI argument)
2. `$OUTPUT_FILE` env var (if set and non-empty)
3. Docker default: `/output/pred.csv`
4. Local default: `output/pred.csv`

An explicitly provided input (CLI `--input` **or** `$INPUT_FILE`) always overrides the
`/data/*` defaults, even when `/data/private_test.csv` exists.

**API key:** if `OPENROUTER_API_KEY` is present in the container env the entrypoint uses the
API production profile (`production_full_system`); if missing it falls back to no-api
(`production_full_system_noapi`) and still writes `pred.csv`. **No key is baked into the image.**

**Layer budget (default):** when no `--v12b-max-qids`/`--v13-max-qids` flags are passed, the
V12B/V13 caps default to `auto = ceil(input_count / 8)` (minimum 1) — e.g. 3 → 1, 463 → 58,
2000 → 250. Logs show the resolved value as `auto(<cap>/<N>)`. Pass an integer to cap explicitly
(`--v12b-max-qids 50`) or `all` to process every input qid.

## Run — default, no arguments (BTC)

The harness mounts the dataset into `/data` and reads `/output`. **No flags needed.**
The container resolves the input by the priority above (defaulting to `/data/private_test.csv`,
else `/data/public_test.csv`, else the `.json` equivalents) and runs the **dynamic_full** system,
writing `/output/pred.csv` for exactly the input qids:

```bash
docker run --rm \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  <dockerhub_username>/fastmcq-final:latest
# (locally built image: use `fastmcq-final` in place of <dockerhub_username>/fastmcq-final:latest)
# -> resolved mode: dynamic_full; /output/pred.csv has one row per input qid;
#    prints resolved mode + V12B/V13 targets/overrides + elapsed_seconds + status: PASS; validated.
```

### Advanced — override input/output via env

Point the run at a custom input and/or output without changing the command shape:

```bash
docker run --rm \
  -e INPUT_FILE=/data/custom_test.csv \
  -e OUTPUT_FILE=/output/custom_pred.csv \
  -v "$PWD/data:/data:ro" \
  -v "$PWD/output:/output" \
  <dockerhub_username>/fastmcq-final:latest
```

If the runner passes a CLI input path instead (`docker run ... <image> --input /data/custom.csv`),
that path overrides all default `/data/*` paths and `$INPUT_FILE`.

This is the **real system** (works on private/unseen qids), not a public-frozen replay. **V12B
and V13 are both official layers, enabled by default.** With `OPENROUTER_API_KEY` set the full
model layers run; without it the deterministic parts run and model-dependent layers are
`skipped_no_api`. To reproduce the public **79.7** artifact exactly, pass `--mode public_replay`
(only valid when input qids match the public set).

Any args passed to `docker run ... <image> <args>` are forwarded to `final_infer.py`
(e.g. `... <image> --mode v10`). To run an arbitrary command, override the entrypoint
with `--entrypoint bash`.

## Run — explicit source CSV (still frozen_csv, offline)

```bash
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/final_infer.py \
    --input /data/public-test.json \
    --output /output/pred.csv --allow-pred-csv \
    --mode frozen_csv --source-csv output/pred_v13_multilayer_candidate_api30_from_v12b.csv
```

## Run — v11_independent rerun (EXPERIMENTAL; API key + budget REQUIRED)

Not the default. Regenerates answers from the independent v11 system (never uses v10):

```bash
docker run --rm -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/final_infer.py \
    --input /data/public-test.json \
    --output /output/pred_v11_rerun.csv \
    --mode v11_independent --model qwen/qwen3.5-9b-20260310 \
    --budget-usd 3.00 --execute --resume
```

## Validate the output

```bash
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/validate_submission.py \
    --input /data/public-test.json --submission /output/pred.csv
```

## Notes

- Default = `dynamic_full`: the real pipeline (V12B + V13) over the input. `public_replay`
  reproduces the frozen **79.7** CSV (`pred_v13_multilayer_candidate_api30_from_v12b.csv`, md5
  `cb02fef569b31e7fb544abab46c0e282`) — same md5 every run, public qids only.
- v10 mode (`--mode v10`) is an explicit fallback only; it is never the default and never a
  base for v11 generation.
- `final_infer.py` refuses to overwrite protected/locked files
  (`pred_v13_multilayer_candidate_api30_from_v12b.csv`, `pred_v12b_permutation_candidate_api30.csv`,
  `pred_v11_independent_rerun1.csv`, `pred_v10_full_production_user_run.csv`,
  `pred_v8_clean_generalized_from_v7.csv`).
