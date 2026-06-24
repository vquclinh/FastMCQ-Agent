# Audit — Phase 2L.41A: Official Full-System Command + `output/pred.csv` Contract

**Date:** 2026-06-24  **Branch:** `main`  **Status:** workflow enforcement + dir migration (no commit, no API)

## Files inspected

`scripts/final_infer.py`, all `scripts/run_*.sh`, `scripts/docker_entrypoint_v11.sh`,
`Dockerfile`, `.dockerignore`, `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`,
`configs/run_profiles.json`, the production configs, the manifest, and the tests/docs that
referenced `outputs/`.

## Files changed

**New:**
- `scripts/run_full_system.sh` — the one official end-to-end runner.
- `scripts/output_quality_report.py` — answer-distribution report + optional guard.
- `tests/test_full_system_output_contract_2l41a.py` — 12 integration tests.
- `docs/audits/AUDIT_PHASE_2L41A_…md` — this audit.

**Changed:**
- `configs/run_profiles.json` — added `production_full_system` (API) and
  `production_full_system_noapi` (offline) profiles.
- `src/fastmcq_system.py` — already supports the full pipeline; unchanged this phase except via
  the `outputs/`→`output/` migration. (`base_execute_api` from 2L.39D retained.)
- `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md` — lead with the official command; old
  per-layer/profile commands moved under **"Legacy / research diagnostics only"**.
- **Directory migration** `outputs/` → `output/` across configs, manifest, scripts, tests, root
  docs, and non-audit docs (the user renamed the dir). `.gitignore`/`.dockerignore` updated.

## Path migrations (`outputs/` → `output/`)

The local final dir was renamed `outputs/` → `output/`. Migrated every `outputs/` and
`"outputs"` directory reference (94 files) — configs (`current_best_csv`, `baseline_v10_csv`,
`protected_outputs`), `experiments/best_candidate_manifest.json`, all `run_*.sh`/`*.py` scripts,
all tests, root docs, and `docs/*.md` — **excluding** `docs/audits/` (historical records kept
verbatim) and `scratch/`. `.gitignore` now tracks the 5 official CSVs under `output/` and
ignores the generated `output/pred.csv`; `.dockerignore` excludes `output/pred.csv`.

> **Disclosure (collateral):** the broad replace also touched two **gitignored, unused** reranker
> vocab files (`models/qwen3-reranker-0.6b/{vocab,tokenizer}.json`) which happened to contain a
> BPE token `"outputs"`. They are not used by the dynamic system or any test (the 3 tests that
> name the reranker dir do not validate those tokens; full suite passes). A best-effort reversal
> restored `vocab.json` (1×`output` + 1×`outputs`, valid JSON) and `tokenizer.json` (valid JSON);
> byte-identical restoration of `tokenizer.json` can't be guaranteed. These files are
> `.gitignore`d + `.dockerignore`d, so the committed repo and Docker image are unaffected;
> re-download the reranker if it is ever needed.

## Exact final behavior

- **Local:** `bash scripts/run_full_system.sh <test_file>` → timestamped
  `scratch/runs/full_system_<ts>/pred.csv`, then **copied to `output/pred.csv`** on success.
  Prints `run_out`, `final`, `md5`, `status`. A failed run leaves an existing `output/pred.csv`
  untouched.
- **Docker:** the entrypoint runs `final_infer.py` which writes directly to **`/output/pred.csv`**
  (creating `/output` if missing); does not rely on the local `output/` dir.

## Official full-system command

```bash
bash scripts/run_full_system.sh <test_file>          # API run (needs OPENROUTER_API_KEY)
bash scripts/run_full_system.sh <test_file> --no-api # fully offline
```

## Production profile used by `run_full_system.sh`

`production_full_system` (or `production_full_system_noapi` when `--no-api` is passed):
`mode=dynamic_full`, `enable_v12b=true`, `enable_v13=true`, selector enabled, caps 463/463,
conservative policies, `max_overrides=100`, model `qwen/qwen3.5-9b-20260310`. No public replay,
no previous-best seed, arbitrary/private qids, output exactly the input qids, model policy
enforced. The API profile requires `OPENROUTER_API_KEY`; the `_noapi` profile runs base + the
deterministic V13 programmatic path with model layers reported `skipped_no_api`.

## Per-layer scripts no longer the main workflow

`run_public_replay/dynamic_noapi/public_api50/public_api100/public_layer_api50/private_*` and
the explicit `final_infer.py` form are now under **"Legacy / research diagnostics only"** in
README / FINAL_RUN / DOCKER_SUBMISSION. No V12B-only/V13-only/candidate-build command is
presented as primary.

## Quality report / guard behavior

After a successful run the wrapper runs `output_quality_report.py`, writing
`scratch/runs/full_system_<ts>/quality_report.json` (counts, ratios, top_label, top_ratio,
degenerate flag) and printing the distribution. If one label exceeds 70% it prints
`WARNING: degenerate answer distribution detected…`. **Promotion to `output/pred.csv` is NOT
blocked by default** (BTC needs the file to exist). With `--fail-on-quality-guard`, a degenerate
distribution makes the wrapper refuse to promote `output/pred.csv` (verified by test).

## Tests run / results

- `compileall -q src scripts tests`: **OK**
- `pytest -q tests/test_full_system_output_contract_2l41a.py`: **12 passed**
- `pytest -q` (full suite): **751 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Part H smoke (no API)

```
bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  profile=production_full_system_noapi  status: PASS
  run_out: scratch/runs/full_system_20260624_102654/pred.csv
  final  : output/pred.csv   md5 48c60045a4250d2d8bfb3fb6e7699058
  [QUALITY] total=5 dist: A=3(60%), B=1(20%), D=1(20%)  (not degenerate)
```
`output/pred.csv` exists; output qids = input qids exactly (`sm1..sm5`); `quality_report.json`
written; no API calls.

## Confirmations

- **No API calls** — all runs used `--no-api`; the production_full_system (API) profile was not
  executed; model policy enforced in the layers.
- **No qid/answer hardcoding** — wrapper/report/profiles regex-clean; system modules carry no
  public-CSV path.
- **Official historical artifacts preserved** — the 5 CSVs now live under `output/` with
  unchanged md5 (V13 `cb02fef5…`, V12B `075646ad…`, v11 `69f4e7c9…`, v10 `c12e32fd…`); the
  git-tracked `outputs/*` show as deletions to be recorded as a rename to `output/*` on commit.
- **Scratch run dirs untouched** — `scratch/runs/public_api50_20260624_005107/` and
  `scratch/runs/smoke_api50_patch_20260624_020447/` not modified/deleted.
- **No model-policy rules changed.**
- **Not committed.**

## Git status

```
 D outputs/{.gitkeep,pred_v8…,pred_v10…,pred_v11…,pred_v12b…,pred_v13…}.csv   (renamed -> output/)
 M ~99 files (outputs/ -> output/ migration: configs, manifest, scripts, tests, root+docs)
?? output/                          (the 5 official CSVs + .gitkeep; pred.csv ignored)
?? scripts/run_full_system.sh
?? scripts/output_quality_report.py
?? tests/test_full_system_output_contract_2l41a.py
?? docs/audits/AUDIT_PHASE_2L41A_FULL_SYSTEM_FINAL_OUTPUT_CONTRACT.md
```
(`scratch/`, `output/pred.csv`, `models/` remain gitignored.) Nothing committed.

## Recommended command to produce BTC-ready final output

```bash
# Local (full system, needs OPENROUTER_API_KEY) -> output/pred.csv
bash scripts/run_full_system.sh public-test_1780368312.json

# Docker (BTC): mounts /data and /output, writes /output/pred.csv
docker run --rm -v "$PWD/data:/data" -v "$PWD/output:/output" fastmcq-final
```
