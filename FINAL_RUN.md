# FINAL RUN — FASTMCQ (dynamic system; V12B + V13 official layers)

> **The official system is a DYNAMIC full pipeline that runs over any input** (public, private,
> unseen, larger sets) and outputs predictions for exactly the input qids:
> dynamic base predictor → **V12B** option-permutation debiaser → **V13** multi-layer
> (programmatic / content-first / least-to-most) → unified selector. The frozen public CSV
> (`pred_v13_multilayer_candidate_api30_from_v12b.csv`, public **79.7**) is the current
> public-best **artifact** for leaderboard reproducibility — it is **not** the universal
> private solution.

## Modes

- `dynamic_full` (**default**) — the real production/BTC system. Runs the dynamic base predictor
  + official **V12B** and **V13** layers over the given input. Works for any qids. API-free by
  default (`--no-api`); add `--execute-api` to call the allowed model.
- `public_replay` — reproducibility only. Copies the frozen **V13 79.7** CSV, **but only if the
  input qid set exactly matches** the public artifact; fails clearly otherwise.
- `auto` — resolves to `public_replay` only with `--allow-public-replay` **and** an exact public
  qid match; otherwise `dynamic_full`. Never replays public answers onto unseen qids.

## Short commands (run profiles — recommended)

Profiles live in `configs/run_profiles.json`; the wrappers create a timestamped run dir under
`scratch/runs/`, tee a `run.log`, and print elapsed time + output path + md5.

```bash
bash scripts/run_public_replay.sh public-test_1780368312.json   # reproduce the 79.7 public artifact
bash scripts/run_dynamic_noapi.sh public-test_1780368312.json   # full dynamic system, no API
bash scripts/run_public_api100.sh public-test_1780368312.json   # quick API system check (caps 100 qids)
bash scripts/run_private_api200.sh private_test.json            # recommended BTC/private API run
bash scripts/run_private_noapi.sh private_test.json             # private, no API
```

Profile meanings: **public_replay** = reproduce the 79.7 artifact for the exact public qids;
**dynamic_noapi** = full dynamic system (V12B+V13) without API; **public_api100** = quick API
system check; **private_api200** = recommended private/BTC API run. CLI flags after the input
override the profile (e.g. `… --no-api`). Equivalent `python scripts/final_infer.py
--profile <name> --input … --output …`.

## The full command (default = dynamic_full, API-free)

```bash
python scripts/final_infer.py --input <test>.json --output pred.csv
```

No `--mode` needed. Runs the dynamic pipeline (V12B + V13 enabled by default); **no API key**
required (deterministic parts run; model-dependent layers reported skipped). Add `--execute-api`
for the full layers (see below).

## Reproduce the public 79.7 artifact (leaderboard only)

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv --mode public_replay
```

## No-argument command (BTC style)

`--input` and `--output` are optional. With the test file in the current directory
(`doc_public_test.csv`, `private_test.csv`, `public-test_1780368312.json`, or
`public-test.json`), just run:

```bash
python scripts/final_infer.py
```

Resolution order — **input**: `--input` → `$FASTMCQ_INPUT` →
`/data/doc_public_test.csv` → `/data/private_test.csv` → `/data/public-test*.json` →
the same names in the current directory → a lone `.csv`/`.json` in `/data`. **output**:
`--output` → `$FASTMCQ_OUTPUT` → `/output/pred.csv` (if `/output` exists/creatable) →
`./pred.csv`. A qid-only CSV (BTC `doc_public_test.csv`) is supported; when the input has
no choices, answers are validated against the global label space `A–K`.

## What it does

- **Default = `dynamic_full`** — runs the real pipeline (dynamic base → V12B → V13 → unified
  selector) over your input and writes predictions for **exactly the input qids**. Works on
  arbitrary/private/unseen test sets.
- **No API key needed** by default: deterministic parts run (incl. the V13 programmatic
  arithmetic path); model-dependent V12B/V13 layers are reported `skipped_no_api`. Add
  `--execute-api --model qwen/qwen3.5-9b-20260310 --budget-usd <N>` for the full layers.
- **Validates** the output automatically (columns, all qids present, no duplicates, valid
  labels, row count == input).
- The current public-best artifact is **V13 79.7**
  (`outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv`); reproduce it with
  `--mode public_replay` on the public test.
- **Prints the resolved mode, V12B/V13 targets+overrides, and elapsed time** — every run ends with:

```text
============================================================
FINAL INFER COMPLETE
mode: dynamic_full
source: src.fastmcq_system
output: pred.csv
questions: <N input qids>
md5: <md5 of this run's output>
elapsed_seconds: <float>
status: PASS
============================================================
```

### Official architecture layers (both enabled by default)

The dynamic system combines two official layers via a unified conservative selector
(`src/system_candidate_selector.py`):
- **V12B** option-permutation debiaser (`src/v12b_dynamic_layer.py`) — promoted at 78.83.
- **V13** multi-layer reasoning (`src/v13_dynamic_layer.py`): **programmatic solver**,
  **content-first normalizer**, **least-to-most constraint table** — promoted at **79.7**.

Both are **enabled by default** in `dynamic_full`. Without API, model-dependent layers report
`skipped_no_api`, but the **deterministic V13 programmatic arithmetic path still runs** (e.g.
"2 + 2" → option with value 4, offline). Legacy `scripts/*_v13_multilayer_*.py` remain offline
experimental wrappers; the preferred path is `final_infer.py --mode dynamic_full`.

## Recommended private/BTC command WITH API (full V12B + V13 system)

```bash
python scripts/final_infer.py \
  --input private_test.json --output pred.csv \
  --mode dynamic_full --execute-api \
  --model qwen/qwen3.5-9b-20260310 --budget-usd 5.00 \
  --enable-v12b --v12b-max-qids 200 --v12b-permutations 6 --v12b-policy conservative \
  --enable-v13 --v13-max-qids 200 --system-policy conservative --max-overrides 50 \
  --work-dir scratch/private_dynamic_full_v13 --resume
```

## Safe API-free private command

```bash
python scripts/final_infer.py --input private_test.json --output pred.csv --mode dynamic_full --no-api
```

## Other modes (explicit only)

- **v10 fallback** (offline copy of the 77.75 baseline; never the default):
  ```bash
  python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv --mode v10
  ```
- **Regenerate via independent v11** (EXPERIMENTAL; needs an API key + budget; never v10):
  ```bash
  python scripts/final_infer.py --input public-test_1780368312.json --output pred_v11_rerun.csv \
    --mode v11_independent --model qwen/qwen3.5-9b-20260310 --budget-usd 3.00 --execute --resume
  ```

## Protections

`final_infer.py` refuses to overwrite the frozen/locked artifacts
`outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv` (current best, 79.7),
`outputs/pred_v12b_permutation_candidate_api30.csv` (previous best, 78.83),
`outputs/pred_v11_independent_rerun1.csv`,
`outputs/pred_v10_full_production_user_run.csv`, and
`outputs/pred_v8_clean_generalized_from_v7.csv`. Writing `pred.csv` is allowed — that is
the intended final export.

## Validate separately (optional)

```bash
python scripts/validate_submission.py --input public-test_1780368312.json --submission pred.csv
```
