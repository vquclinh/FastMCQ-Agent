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

## Official command (use this)

One command runs the full production system end-to-end (base → V12B → V13 → selector) over any
test set and writes the final local artifact to **`output/pred.csv`**:

```bash
bash scripts/run_full_system.sh <test_file>          # API run (needs OPENROUTER_API_KEY)
bash scripts/run_full_system.sh <test_file> --no-api # fully offline
```

- Final local artifact: **`output/pred.csv`**. Docker final artifact: **`/output/pred.csv`**.
- Timestamped logs/records live under `scratch/runs/full_system_<ts>/` (run.log,
  work/progress.json, work/v12b_dynamic_records.jsonl, work/v13_dynamic_records.jsonl,
  pred.csv) — these are NOT the official artifact.
- Profile: `production_full_system` (API; `--no-api` → `production_full_system_noapi`). Prints an
  answer-distribution quality report and warns on a degenerate (>70% one label) distribution;
  add `--fail-on-quality-guard` to refuse promoting `output/pred.csv` when degenerate.
- A failed run never overwrites an existing `output/pred.csv`.

## Short commands (run profiles — research diagnostics)

Profiles live in `configs/run_profiles.json`; the wrappers create a timestamped run dir under
`scratch/runs/`, tee a `run.log`, and print elapsed time + output path + md5.

```bash
bash scripts/run/run_public_replay.sh public-test_1780368312.json   # reproduce the 79.7 public artifact
bash scripts/run/run_dynamic_noapi.sh public-test_1780368312.json   # full dynamic system, no API
bash scripts/run/run_public_api50.sh public-test_1780368312.json    # medium API pilot (caps 50 qids, $2.50)
bash scripts/run/run_public_layer_api50.sh public-test_1780368312.json  # layer-only API: base no-API, V12B/V13 API ($1.50)
bash scripts/run/run_public_api100.sh public-test_1780368312.json   # quick API system check (caps 100 qids)
bash scripts/run/run_private_api200.sh private_test.json            # recommended BTC/private API run
bash scripts/run/run_private_noapi.sh private_test.json             # private, no API
```

Profile meanings: **public_replay** = reproduce the 79.7 artifact for the exact public qids;
**dynamic_noapi** = full dynamic system (V12B+V13) without API; **public_api50** = medium API
pilot over the full input file, sending up to 50 high-risk qids through the V12B/V13 API layers
(a middle option between a manual `public_api30`-style override and `public_api100`);
**public_api100** = quick API system check; **private_api200** = recommended private/BTC API
run. CLI flags after the input override the profile (e.g. `… --no-api` or `… --budget-usd
3.00`). Equivalent `python scripts/final_infer.py --profile <name> --input … --output …`.

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

Resolution order (exact BTC contract, Phase 2L.44D) — **input**: `--input` (CLI) →
`$INPUT_FILE` (then legacy `$FASTMCQ_INPUT`) → `/data/private_test.csv` →
`/data/public_test.csv` → `/data/private_test.json` → `/data/public_test.json` → other known
names in the current directory → a lone `.csv`/`.json` in `/data`. An explicit input (CLI
`--input` or `$INPUT_FILE`) always wins over the `/data/*` defaults, even when
`/data/private_test.csv` exists. **output**: `--output` (CLI) → `$OUTPUT_FILE` (then legacy
`$FASTMCQ_OUTPUT`) → `/output/pred.csv` (Docker default, when `/output` exists/creatable) →
`output/pred.csv` (local default). If no input is found the run fails early with a clear message
listing the expected defaults and the `--input`/`$INPUT_FILE` overrides. A qid-only CSV (BTC
`doc_public_test.csv`) is supported; when the input has no choices, answers are validated
against the global label space `A–K`.

**Layer budget (default):** without explicit `--v12b-max-qids`/`--v13-max-qids` flags, the
V12B/V13 caps default to `auto = ceil(input_count / 8)` (minimum 1) — e.g. 3 → 1, 463 → 58,
2000 → 250 — shown in logs as `auto(<cap>/<N>)`. This is the production default used by
`run_full_system.sh` and the Docker entrypoint. Pass an integer to cap explicitly, or `all` to
process every input qid.

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
  (`output/pred_v13_multilayer_candidate_api30_from_v12b.csv`); reproduce it with
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
(`src/selector/system_candidate_selector.py`):
- **V12B** option-permutation debiaser (`src/layers/v12b_dynamic_layer.py`) — promoted at 78.83.
- **V13** multi-layer reasoning (`src/layers/v13_dynamic_layer.py`): **programmatic solver**,
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
`output/pred_v13_multilayer_candidate_api30_from_v12b.csv` (current best, 79.7),
`output/pred_v12b_permutation_candidate_api30.csv` (previous best, 78.83),
`output/pred_v11_independent_rerun1.csv`,
`output/pred_v10_full_production_user_run.csv`, and
`output/pred_v8_clean_generalized_from_v7.csv`. Writing `pred.csv` is allowed — that is
the intended final export.

## Validate separately (optional)

```bash
python scripts/validate_submission.py --input public-test_1780368312.json --submission pred.csv
```
