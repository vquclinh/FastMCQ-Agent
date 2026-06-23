# Docker Submission — FASTMCQ Final (Independent V11, frozen)

The final image is **offline and reproducible by default**: it exports the current best
**independent v11** submission (`outputs/pred_v11_independent_rerun1.csv`, public **78.4**)
to `/output/pred.csv` and validates it. **No API key is required by default**, no inference
runs, and **v10 is never run** (it ships only as an explicit fallback CSV).

## Simplest local command (no Docker, no API key)

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
```
Writes the frozen 78.4 CSV to `pred.csv`, validates it, and prints `elapsed_seconds` +
`status: PASS`. See `FINAL_RUN.md`.

## What ships in the image

- Source (`src/`, `scripts/`), `configs/production_v11_independent.json`, `requirements.txt`.
- Required final CSVs under `outputs/`: `pred_v11_independent_rerun1.csv` (frozen best) and
  `pred_v10_full_production_user_run.csv` (fallback only).
- **Excluded** by `.dockerignore`: `.env`/secrets/keys, `scratch/`, `experiments/`, `docs/`,
  `.git/`, notebooks, `*.log`, `*.jsonl`, model weights/caches, and the non-final
  `outputs/pred.csv` / `outputs/pred_v11_full_adaptive_test.csv`.

## Build

```bash
docker build -t fastmcq-final .
```

## Run — default, no arguments (BTC)

The harness mounts the dataset into `/data` and reads `/output`. **No flags, no API key.**
The container auto-detects the input (`/data/doc_public_test.csv` or
`/data/private_test.csv`, then `/data/public-test*.json`) and writes `/output/pred.csv`:

```bash
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final
# -> /input detected under /data; /output/pred.csv (== pred_v11_independent_rerun1.csv);
#    prints elapsed_seconds + status: PASS; validated automatically.
```

Any args passed to `docker run ... fastmcq-final <args>` are forwarded to `final_infer.py`
(e.g. `... fastmcq-final --mode v10`). To run an arbitrary command, override the entrypoint
with `--entrypoint bash`.

## Run — explicit source CSV (still frozen_csv, offline)

```bash
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/final_infer.py \
    --input /data/public-test.json \
    --output /output/pred.csv --allow-pred-csv \
    --mode frozen_csv --source-csv outputs/pred_v11_independent_rerun1.csv
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

- Default = `frozen_csv`: a reproducible copy of the frozen 78.4 CSV — same md5 every run.
- v10 mode (`--mode v10`) is an explicit fallback only; it is never the default and never a
  base for v11 generation.
- `final_infer.py` refuses to overwrite protected/locked files
  (`pred_v11_independent_rerun1.csv`, `pred_v10_full_production_user_run.csv`,
  `pred_v8_clean_generalized_from_v7.csv`, and `pred.csv` unless `--allow-pred-csv`).
