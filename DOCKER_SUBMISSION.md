# Docker Submission — FASTMCQ Final (dynamic system; V12B + V13 official layers)

The image runs the real **dynamic_full** system by default (dynamic base → V12B → V13 →
unified selector) over the mounted input and writes `/output/pred.csv` for exactly the input
qids. **No API key is required by default** (deterministic parts run; model-dependent layers are
`skipped_no_api`). The current public-best artifact is **V13 multi-layer 79.7**
(`outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`, +0.87 over V12B 78.83, +1.30 over
v11 78.40); reproduce it exactly with `--mode public_replay` on the public test.

## Simplest local commands (run profiles — no Docker)

```bash
bash scripts/run_public_replay.sh public-test_1780368312.json   # reproduce the 79.7 artifact
bash scripts/run_dynamic_noapi.sh public-test_1780368312.json   # full dynamic system, no API
bash scripts/run_public_api50.sh public-test_1780368312.json    # medium API pilot (caps 50 qids)
bash scripts/run_private_api200.sh private_test.json            # recommended private/BTC API run
```
Each prints elapsed time + output md5 and logs under `scratch/runs/`. Full/explicit form:

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
```
Runs `dynamic_full` (V12B + V13, API-free) and writes validated `pred.csv` for exactly the
input qids; prints resolved mode + V12B/V13 overrides + `elapsed_seconds` + `status: PASS`. To
reproduce the public 79.7 artifact exactly add `--mode public_replay`. See `FINAL_RUN.md`.

## What ships in the image

- Source (`src/`, `scripts/`), `configs/production_v13_multilayer_7970.json`, `requirements.txt`.
- Required final CSVs under `outputs/`: `pred_v13_multilayer_candidate_api30_from_v12b.csv`
  (current best, 79.7), `pred_v12b_permutation_candidate_api30.csv` (previous best, 78.83),
  `pred_v11_independent_rerun1.csv`, and `pred_v10_full_production_user_run.csv` (fallback only).
- **Excluded** by `.dockerignore`: `.env`/secrets/keys, `scratch/`, `experiments/`, `docs/`,
  `.git/`, notebooks, `*.log`, `*.jsonl`, model weights/caches, and the non-final
  `outputs/pred.csv` / `outputs/pred_v11_full_adaptive_test.csv`.

## Build

```bash
docker build -t fastmcq-final .
```

## Run — default, no arguments (BTC)

The harness mounts the dataset into `/data` and reads `/output`. **No flags, no API key.**
The container auto-detects the input (`/data/private_test.csv|json`, `/data/doc_public_test.csv`,
then `/data/public-test*.json`) and runs the **dynamic_full** system, writing `/output/pred.csv`
for exactly the input qids:

```bash
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final
# -> resolved mode: dynamic_full (API-free by default); /output/pred.csv has one row per input qid;
#    prints resolved mode + V12B/V13 targets/overrides + elapsed_seconds + status: PASS; validated.
```

This is the **real system** (works on private/unseen qids), not a public-frozen replay. **V12B
and V13 are both official layers, enabled by default.** To call the model for the full layers,
pass `--execute-api --model qwen/qwen3.5-9b-20260310 --budget-usd <N>` (requires
`OPENROUTER_API_KEY`); without API the deterministic parts run and model-dependent layers are
`skipped_no_api`. To reproduce the public **79.7** artifact exactly, pass `--mode public_replay`
(only valid when input qids match the public set).

Any args passed to `docker run ... fastmcq-final <args>` are forwarded to `final_infer.py`
(e.g. `... fastmcq-final --mode v10`). To run an arbitrary command, override the entrypoint
with `--entrypoint bash`.

## Run — explicit source CSV (still frozen_csv, offline)

```bash
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final \
  python scripts/final_infer.py \
    --input /data/public-test.json \
    --output /output/pred.csv --allow-pred-csv \
    --mode frozen_csv --source-csv outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv
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
