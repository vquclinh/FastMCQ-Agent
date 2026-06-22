# Audit — Phase 2L.24C: Built-in Timing for the Formula Bank Script

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added runtime reporting to `scripts/apply_formula_bank_to_predictions.py` (printed
summary + a JSONL `event:"summary"` record), so the operator no longer needs to wrap
the command with `/usr/bin/time`. **Prediction logic, formula-bank rules, and answer
selection are unchanged** — regenerating v9 produces a byte-identical CSV.

## Files changed

- `scripts/apply_formula_bank_to_predictions.py` — `import time`; `run_start =
  time.perf_counter()` at the start of `main()`; computed `elapsed`/`samples_per_second`/
  `avg_seconds_per_sample`; printed them in the existing summary; added the timing
  fields + `event:"summary"` to the JSONL summary line.
- `tests/test_formula_bank_solver.py` — +1 test for the timing report + JSONL event.

## Exact timing fields added

Printed summary now also shows:
```
elapsed_seconds        : <float, 3dp>
samples_per_second     : <float, 2dp>
avg_seconds_per_sample : <float, 6dp>
```
(kept fields: samples, answers changed, changes by rule, per-change lines, prediction
CSV, log JSONL, diff CSV, no-API note.)

JSONL summary line (final record) now includes:
```json
{"_summary": true, "event": "summary", "base_pred": "...", "samples": N,
 "num_samples": N, "answers_changed": C, "changed_vs_base": C, "by_rule": {...},
 "elapsed_seconds": ..., "samples_per_second": ..., "avg_seconds_per_sample": ...}
```
(`samples`/`answers_changed` added per spec; legacy `num_samples`/`changed_vs_base`
kept for backward compatibility.)

## Verification (no API)

Regenerated v9 from `outputs/pred.csv` to scratch paths:
```
samples 463; answers changed 1; elapsed_seconds 0.302;
samples_per_second 1531.31; avg_seconds_per_sample 0.000653
JSONL event:"summary" → {elapsed_seconds, samples=463, answers_changed=1,
                         samples_per_second, avg_seconds_per_sample}
```
`diff -q` of the regenerated CSV vs `outputs/pred_v9_formula_bank_from_v8_clean.csv`
→ **IDENTICAL** (prediction logic unchanged).

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **411 passed** (was 410; +1).
- New test asserts: timing fields printed; JSONL `event:"summary"` present with all
  timing keys; predictions unchanged (no rule fires on the synthetic input → answers
  stay equal to the base).

## Confirmations

- **No OpenRouter/API call** (deterministic timing only).
- **Prediction logic unchanged** — no formula-bank rule, override gate, or
  answer-selection code touched; regenerated v9 is byte-identical.
- **No final prediction generated**; `outputs/pred.csv` not modified or overwritten
  (timing run wrote only to scratch paths).
- No qid hardcoding; nothing committed.

## git status (relevant)

```
?? scripts/apply_formula_bank_to_predictions.py
?? tests/test_formula_bank_solver.py
?? docs/AUDIT_PHASE_2L24C_FORMULA_BANK_TIMING.md
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*` and `scratch/*`
are gitignored.)

## Final command to run v9 (manual; no API; now self-times)

```bash
.venv/bin/python scripts/apply_formula_bank_to_predictions.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred.csv \
  --output outputs/pred_v9_formula_bank_from_v8_clean.csv \
  --log-path outputs/run_v9_formula_bank_from_v8_clean.jsonl \
  --diff outputs/pred_v9_formula_bank_diff.csv \
  --max-expected-changes 10
```
The runtime summary now prints automatically (elapsed_seconds / samples_per_second /
avg_seconds_per_sample) and is recorded in the JSONL `event:"summary"`.

Do not commit until a result is accepted.
