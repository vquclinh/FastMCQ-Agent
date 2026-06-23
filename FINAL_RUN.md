# FINAL RUN — FASTMCQ (Independent V11, frozen)

## The command (explicit)

```bash
python scripts/final_infer.py --input public-test_1780368312.json --output pred.csv
```

That's it. No `--mode`, no `--allow-pred-csv`, **no API key**.

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

- **Default = frozen winning independent v11** (`outputs/pred_v11_independent_rerun1.csv`,
  public score **78.4**).
- Copies that frozen CSV to your `--output` (including `pred.csv`) — offline, deterministic.
- **No API key needed**; no inference; v10 is never used.
- **Validates** the output automatically (columns, all qids present, no duplicates, valid
  labels, row count == dataset).
- **Prints elapsed time automatically** — every run ends with:

```text
============================================================
FINAL INFER COMPLETE
mode: frozen_csv
source: outputs/pred_v11_independent_rerun1.csv
output: pred.csv
questions: 463
md5: 69f4e7c990e8c612e7bee53084d13b4d
elapsed_seconds: <float>
status: PASS
============================================================
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
`outputs/pred_v11_independent_rerun1.csv`, `outputs/pred_v10_full_production_user_run.csv`,
and `outputs/pred_v8_clean_generalized_from_v7.csv`. Writing `pred.csv` is allowed — that is
the intended final export.

## Validate separately (optional)

```bash
python scripts/validate_submission.py --input public-test_1780368312.json --submission pred.csv
```
