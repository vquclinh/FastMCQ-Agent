# Audit — Phase 2L.32B: BTC No-Argument Default I/O + Timing

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (for review)

## What changed from 2L.32A

- `final_infer.py` `--input` and `--output` are now **optional** with autodetect/defaults.
- BTC CSV input supported: a qid-only `doc_public_test.csv` / `private_test.csv` loads, and
  when the input carries **no choices** answers are validated against the global label space.
- `final_infer.py` resolves its config + frozen/v10 source CSVs against the **repo root**, so
  it can be invoked from any working directory (needed for the BTC no-arg/local cases).
- `docker_entrypoint_v11.sh` is now **no-arg** (`python scripts/final_infer.py`) and forwards
  any `docker run` args to `final_infer.py`; the Dockerfile uses **ENTRYPOINT** (not CMD) so
  arg-forwarding works.
- Docs (`FINAL_RUN.md`, `DOCKER_SUBMISSION.md`, `README.md`) show the no-arg BTC commands.

## Input autodetect order

`--input` → `$FASTMCQ_INPUT` → `/data/doc_public_test.csv` → `/data/private_test.csv` →
`/data/public-test.json` → `/data/public-test_1780368312.json` → `doc_public_test.csv`
(cwd) → `private_test.csv` (cwd) → `public-test_1780368312.json` (cwd) → `public-test.json`
(cwd) → a lone `.csv`/`.json` in `/data` → else **fail early** with a clear error (and the
timing block still prints).

## Output default order

`--output` → `$FASTMCQ_OUTPUT` → `/output/pred.csv` (if `/output` exists or is creatable) →
`./pred.csv`.

## CSV input support

`src.data_io.load_dataset` reads a CSV with a `qid` column (extra columns ignored; no `qid`
column → clear failure). For frozen-output validation: qid set + row count must match the
input; columns must be `qid,answer`; labels valid. **When choices are present** → strong
per-sample validation; **when absent** (BTC qid-only CSV) → global label validation.

### Global label space note (deviation from the brief's "A–H")

The phase text said "validate globally against A-H", but the public test has **2–11 choices
(labels A–K)** and the frozen winner legitimately contains `J`/`K`. Validating against A–H
would wrongly reject those valid answers, so the global set is **A–K** (`ABCDEFGHIJK`). This
is the faithful interpretation of "don't require choice-specific validation" for this dataset.

## Docker no-arg behavior

`ENTRYPOINT ["bash", "scripts/docker_entrypoint_v11.sh"]`. With **no args** the entrypoint
runs `final_infer.py` (frozen_csv), which auto-detects `/data/doc_public_test.csv` (or the
other candidates) and writes `/output/pred.csv`, printing its timing block + validating.
With args, they are forwarded to `final_infer.py` (e.g. `--mode v10`). Arbitrary commands:
`docker run --entrypoint bash ...`. Exits nonzero on inference/validation failure (`set -e`).

## Exact commands

- **BTC Docker (no args):**
  ```bash
  docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final
  ```
- **Local no-arg** (input file in cwd or `/data`):
  ```bash
  python scripts/final_infer.py
  ```
- **Local explicit** (still supported):
  ```bash
  python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
  ```

## Smoke test results (Part E)

All three local runs printed `status: PASS` + `elapsed_seconds` and produced **md5 ==
winning** (`69f4e7c990e8c612e7bee53084d13b4d`):

| run | input detected | output | md5 == best | validate |
|---|---|---|---|---|
| explicit | `public-test_1780368312.json` | `…/pred_explicit.csv` | True | PASS |
| json auto | `public-test_1780368312.json` (cwd) | `pred.csv` (cwd) | True | PASS |
| csv auto | `doc_public_test.csv` (cwd, qid-only) | `pred.csv` (cwd) | True | PASS |

## Docker smoke result (Part F)

`docker build -t fastmcq-final .` — SUCCESS. No-arg `docker run` with a qid-only
`/data/doc_public_test.csv`:
```
[final_infer] input detected: /data/doc_public_test.csv
[final_infer] output: /output/pred.csv
md5: 69f4e7c990e8c612e7bee53084d13b4d   elapsed_seconds: 0.009   status: PASS
```
Host validation of `scratch/docker_noarg_smoke/output/pred.csv`: `RESULT: PASS`;
md5 == winning: **True**.

## md5 match results

All local + Docker outputs: `69f4e7c990e8c612e7bee53084d13b4d` (== the frozen winning CSV).

## Elapsed-time confirmation

Every successful run prints `FINAL INFER COMPLETE … elapsed_seconds: <float> … status: PASS`.
A failure (e.g. no detectable input, or a protected output name) prints the same block with
`status: FAIL (<error>)` and `elapsed_seconds` before raising.

## Tests run and results (Part G)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **618 passed** (was 605; +13 in `tests/test_btc_noarg_2l32b.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: no-arg run (json + csv autodetect) → md5 == best; no-arg uses v11 frozen best;
  no-arg makes no API call; elapsed + status PASS printed; no-detectable-input prints timing
  + clear error; input autodetect prefers `doc_public_test.csv` over `private_test.csv`;
  explicit/env input resolution; output default order (explicit/env/`/output`/`./pred.csv`);
  global A–K label validation when choices absent (rejects out-of-range); frozen best/v10
  still protected; docs contain the BTC no-arg Docker command; no qid hardcoding.

## Confirmations

- **Default uses the frozen v11 78.4 CSV** (`outputs/pred_v11_independent_rerun1.csv`,
  md5 `69f4e7c990e8c612e7bee53084d13b4d`).
- **No API dependency on the default path**; no API key required (verified by a monkeypatched
  client that raises if instantiated, and by the offline Docker run).
- **v10 is fallback only** (`--mode v10` / forwarded arg); never the default.
- **No best artifacts overwritten** — `outputs/` still holds `pred.csv`,
  `pred_v10_full_production_user_run.csv`, `pred_v11_full_adaptive_test.csv`,
  `pred_v11_independent_rerun1.csv` (md5 unchanged), `pred_v8_clean_generalized_from_v7.csv`.
  Smoke + Docker wrote only under `scratch/`.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## git status (this phase)

```
 M .gitignore        (2L.32A: outputs exceptions)
 M Dockerfile        (CMD -> ENTRYPOINT for no-arg + arg forwarding)
 M README.md         (no-arg note added)
 M scripts/run_production_pipeline.py / src/*.py / tests/* (pre-existing, earlier phases)
?? DOCKER_SUBMISSION.md, FINAL_RUN.md          (updated this phase)
?? scripts/final_infer.py                       (optional I/O + global-label validation)
?? scripts/docker_entrypoint_v11.sh             (no-arg + arg forwarding)
?? tests/test_btc_noarg_2l32b.py                (new this phase)
?? docs/AUDIT_PHASE_2L32B_BTC_NOARG_DEFAULT_IO_TIMING.md
?? (other untracked v11 pipeline files + audits from phases 2L.25–2L.32A)
?? outputs/pred_v11_independent_rerun1.csv / pred_v10_full_production_user_run.csv (trackable)
```
(`Dockerfile`, `.gitignore`, `README.md` are the tracked-file modifications; the v11
scripts/docs/tests are untracked from the prior uncommitted phases. `outputs/` CSV contents
unchanged.)
