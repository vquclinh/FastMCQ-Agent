# Audit — Phase 2L.38D: `public_api50` JSONL Location Check (read-only diagnostic)

**Date:** 2026-06-24  **Branch:** `main`  **Status:** read-only diagnostic on a LIVE run
(the API job was not touched). No API called by this diagnostic. No files modified except this audit.

## Question

Where are the `.jsonl` intermediate files for the in-progress
`bash scripts/run_public_api50.sh public-test_1780368312.json` run being written?

## Commands run (all read-only)

```bash
pwd
ls -td scratch/runs/public_api50_* | head -5
RUN_DIR=$(ls -td scratch/runs/public_api50_* | head -1)
find "$RUN_DIR" -type f -name "*.jsonl" | sort
find "$RUN_DIR" -type f -name "*.jsonl" -printf "%T@ %p\n" | sort -nr | head -20
find "$RUN_DIR" -type f -name "*.jsonl" -print -exec wc -l {} \;
find "$RUN_DIR/work" -maxdepth 4 -type f | sort | head -200
tail -80 "$RUN_DIR/run.log"
ls -la "$RUN_DIR" "$RUN_DIR/work"; wc -l "$RUN_DIR/run.log"; grep -c "openrouter ok" "$RUN_DIR/run.log"
grep -n "_dynamic_records.jsonl|work_dir" src/v12b_dynamic_layer.py src/v13_dynamic_layer.py
```

## Discovered paths

- **Exact run directory:** `scratch/runs/public_api50_20260624_005107/`
  - `run.log` (302 KB, actively growing — last write 01:18 vs dir created 00:51)
  - `work/` (exists, **empty**)
  - no `pred.csv` yet

## Whether `.jsonl` exists

**No `.jsonl` files exist yet** — neither under the run dir nor anywhere in `scratch/runs/`.
`work/` is empty. 542 `openrouter ok` calls have completed so far (run still in progress).

This is expected: the dynamic layers **buffer their records in memory and write the JSONL once,
at the END of each layer**, not incrementally. From the source (read-only):
- `src/v12b_dynamic_layer.py` → writes `<work_dir>/v12b_dynamic_records.jsonl` after its target
  loop completes.
- `src/v13_dynamic_layer.py` → writes `<work_dir>/v13_dynamic_records.jsonl` at the end (only if
  ≥1 API result was produced).

For this run, `--work-dir = scratch/runs/public_api50_20260624_005107/work`, so when each layer
finishes the intermediates will appear at:
- `scratch/runs/public_api50_20260624_005107/work/v12b_dynamic_records.jsonl`
- `scratch/runs/public_api50_20260624_005107/work/v13_dynamic_records.jsonl`

The empty `work/` means the run is still inside the base-predictor / V12B phase (neither layer
has reached its end-of-function write). The base predictor returns in-memory predictions and
writes **no** JSONL of its own.

## What is being written instead (during the run)

Only `scratch/runs/public_api50_20260624_005107/run.log` — the tee'd stdout (per-call
`[fastmcq] openrouter ok …` usage lines). The final `pred.csv` is written by
`run_fastmcq_system` after both layers + the unified selector finish.

## Latest updated file

`scratch/runs/public_api50_20260624_005107/run.log` (the only file currently changing).

## Final CSV status

`scratch/runs/public_api50_20260624_005107/pred.csv` — **does not exist yet** (run in progress).

## Answers (summary)

1. Run directory: `scratch/runs/public_api50_20260624_005107/`
2. `.jsonl` paths: **none yet**; will be `work/v12b_dynamic_records.jsonl` and
   `work/v13_dynamic_records.jsonl` under that run dir on layer completion.
3. Most recently updated: `run.log` (no `.jsonl` exists to compare).
4. No `.jsonl` yet because layers write them only at completion; meanwhile only `run.log` grows.
5. `pred.csv`: not yet written.
6. No files modified by this diagnostic.

## Confirmations

- **No API calls** made by this diagnostic — only `pwd`/`ls`/`find`/`tail`/`wc`/`grep`/`cat` on
  existing files.
- **The running job was not stopped, killed, restarted, or modified.**
- **No files modified** except this audit; no source/config/output/scratch/run files touched.
- `scratch/runs/` is gitignored (the live run is invisible to git).

## Git status

`git status --short`: no tracked modifications; only this new audit file is untracked
(`scratch/` incl. `scratch/runs/` remains gitignored). Nothing committed.
