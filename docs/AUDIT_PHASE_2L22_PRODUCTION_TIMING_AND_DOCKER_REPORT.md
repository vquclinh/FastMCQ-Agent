# Audit — Phase 2L.22: Production Timing + Docker Runtime Report

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added clear runtime reporting to the production runner and Docker entrypoint. The
runner now times the whole run and prints throughput + writes an `event:"summary"`
JSONL record; the entrypoint prints input/output/preset and start/end timestamps +
wall seconds. **Prediction logic, prompts, and answer selection are unchanged.**

## Files changed

- `scripts/run_production_pipeline.py` — whole-run `time.perf_counter()` timer; a
  printed "PRODUCTION RUN SUMMARY" block; an `event:"summary"` record in the JSONL.
- `scripts/docker_entrypoint.sh` — prints detected input, output path, log path,
  preset, UTC start/end timestamps, wall seconds, and exit code; runs (not `exec`) so
  it can report the end timestamp; forwards `--skip-existing --checkpoint-every 50`.
- `tests/test_production_timing.py` — 5 new tests (fake solver, no API).

No changes to `production_policy`, `production_inference`, `production_prompts`,
`option_evidence`, `formula_bank_solver`, or any solver — answer selection untouched.

## Exact timing fields added

Printed report and `event:"summary"` JSONL record both include:
`elapsed_seconds` (whole run), `predict_loop_seconds`, `total_samples`,
`newly_predicted`, `resumed_skipped`, `samples_per_second`, `avg_seconds_per_sample`,
`overrides_applied`, plus `input`, `output`, `log_path`, `preset`. The printed block
also shows the output and log paths. Throughput uses `newly_predicted / elapsed`
(guards against divide-by-zero).

Verified output (fake solver, 5 samples, no API):
```
PRODUCTION RUN SUMMARY
elapsed_seconds        : 0.001
total_samples          : 5
newly_predicted        : 5
resumed/skipped        : 0
samples_per_second     : 7323.87
avg_seconds_per_sample : 0.0001
safe overrides applied : 0
```
JSONL: `{"event":"summary","elapsed_seconds":...,"total_samples":5,"newly_predicted":5,
"samples_per_second":...,"avg_seconds_per_sample":...,"overrides_applied":0, ...}`

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `bash -n scripts/docker_entrypoint.sh`: **OK** (valid shell syntax)
- `pytest -q`: **391 passed** (was 386; +5).
- New tests: timing report printed; JSONL `event:"summary"` present with all timing
  keys; prediction logic unchanged (fixed-answer fake solver → all outputs == base
  "A"); Docker entrypoint detection + metadata tokens present; no qid hardcoding.

## Confirmations

- **No OpenRouter/API call** (base solver monkeypatched to a fake in tests; the
  visual check used a fake solver too). No full inference run.
- **No prediction logic changed** — only timing/reporting added; a fixed-answer fake
  solver passes through unchanged (test asserts every output equals the base answer).
- No `outputs/pred.csv` created or overwritten (protected-output guard intact).
- No qid hardcoding; nothing committed.

## Final human-run command (manual; contacts OpenRouter)

```bash
.venv/bin/python scripts/run_production_pipeline.py \
  --input public-test_1780368312.json \
  --output outputs/pred_production_user_run.csv \
  --preset competition_qwen35_9b \
  --log-path outputs/run_production_user_run.jsonl \
  --skip-existing --checkpoint-every 50
```
The runtime report prints at the end; the Docker entrypoint runs the same preset on
the auto-detected `/data` input into `/output/pred.csv` and prints start/end/wall time.

## git status

```
 M Dockerfile                         (from 2L.20)
?? scripts/run_production_pipeline.py
?? scripts/docker_entrypoint.sh
?? tests/test_production_timing.py
?? docs/AUDIT_PHASE_2L22_PRODUCTION_TIMING_AND_DOCKER_REPORT.md
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*` and `scratch/*`
are gitignored.)

## Next step

Operator runs the manual command (or the Docker image) and reads the runtime report
to confirm throughput/elapsed time meets the competition's inference-time budget.
Do not commit until a result is accepted.
