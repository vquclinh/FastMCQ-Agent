# Audit — Phase 2L.20: Hidden-Test General Production Pipeline + Expanded Formula Bank

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Resume context — what was incomplete after the interruption

The previous 2L.20 run was interrupted mid-response. On resume the filesystem had:
- **kept & valid:** `src/production_policy.py` (complete) and the 2L.19
  `src/formula_bank_solver.py` (suite green, 337 tests).
- **missing (never created):** `scripts/run_production_pipeline.py`,
  `scripts/audit_hidden_generalization_readiness.py`, `scripts/docker_entrypoint.sh`,
  the formula-bank expansion, tests, and this audit.

Action taken: kept `production_policy.py` as-is (verified it imports and is
self-consistent), then completed the missing pieces cleanly. Nothing had to be
reverted.

## Files created / changed

**New**
- `scripts/run_production_pipeline.py` — production runner (preset + explicit flags;
  `--detect-only` for the entrypoint; protected-output guard).
- `scripts/audit_hidden_generalization_readiness.py` — no-API dry-run scanner.
- `scripts/docker_entrypoint.sh` — input auto-detection + production preset run.
- `tests/test_production_pipeline.py` — runner/policy/detection tests.

**Modified**
- `src/formula_bank_solver.py` — +13 conservative rule families (Phase 2L.20).
- `tests/test_formula_bank_solver.py` — +13 new-rule tests.
- `Dockerfile` — CMD now runs `scripts/docker_entrypoint.sh`.

**Kept from interrupted run**
- `src/production_policy.py` — branch routing + safe-override decision (unchanged).

## production_policy.py — kept (not reverted)

It implements the decision policy: **deterministic safe rule > base LLM**; medium/
high-risk detections, verifiers, and self-consistency are **log-only** and never
auto-override. `decide(sample, base_answer, labels)` returns `(final, record)`;
`apply_safe_overrides(...)` maps it across a batch. Verified by tests (overrides on a
safe rule that differs, keeps base when no rule or when the rule agrees).

## Production runner design

`scripts/run_production_pipeline.py`:
1. resolves a `--preset` (or explicit flags; explicit wins);
2. loads the FRESH input via `src.data_io.load_dataset` (JSON or CSV) — **the only
   file it reads**; it never reads v7/v8/v9 predictions (`read_predictions` is not
   imported/used; v7/v8/v9 names appear only in the protected-overwrite guard set);
3. builds the base solver via `src.solver_factory.build_solver` and runs
   `predict_batch` (this is the only OpenRouter step — NOT run in this phase/CI);
4. applies safe deterministic overrides via `production_policy.apply_safe_overrides`
   (calc → concept → formula bank, surfaced by `solve_formula_bank_sample`);
5. writes `qid,answer` via `write_predictions` + a per-sample JSONL log (base answer,
   final answer, branch, rule id, override reason).
- **Protected-output guard:** refuses to overwrite a protected LOCAL prediction
  (`outputs/pred.csv`, v2/v6/v6b/v7/v8/v9) unless `--allow-overwrite-protected`.
- Preset `competition_qwen35_9b` → qwen/qwen3.5-9b, temp 0, max_tokens 512,
  `configs/verifier_selective.yaml`, calc + reranker(`models/qwen3-reranker-0.6b`,
  candidate_top_k 12, batch 8) + concept + formula bank, safe-overrides-only.

## Branch / layer architecture

`production_policy.branch_of` maps the router's route to a branch:
calculation / long_context / short_knowledge / law_admin / ambiguous (+ a
`formula_bank` logical layer). Final policy: deterministic safe rule wins; otherwise
keep the base LLM answer. long_context keeps the reranker but does not override on
evidence; short_knowledge/law_admin/ambiguous get no automatic verifier/adjudicator
override in production (those remain proposal-only from earlier phases).

## Docker entrypoint design

`scripts/docker_entrypoint.sh`: `mkdir -p /output`; detect input under `/data` via
`run_production_pipeline.py --detect-only` (priority: `private_test.csv` →
`public_test.csv` → `*-test.csv` → `*_test.json`/`*-test.json` → any `*.csv`/`*.json`);
clear error + exit 1 if none; then `exec` the production pipeline with the preset and
a JSONL log. `OPENROUTER_API_KEY` is NOT baked into the image (evaluator env). If the
local neural reranker is unavailable, the pipeline fails closed to lexical. Dockerfile
`CMD` updated to run the entrypoint.

## Formulas / concepts added (Phase 2L.20)

Conservative, qid-free, unique-match-only, with synthetic tests:
`kinetic_energy`, `potential_energy`, `uniform_motion` (s=vt), `density` (m/V),
`pressure` (F/A), `frequency_period` (f=1/T), `circle_area`/`circle_circumference`,
`triangle_area`, `profit` (rev−cost), `roi`, `straight_line_depreciation`, `moles`
(m/M), `concentration` (n/V). These join the existing electricity/wave/geometry/
linear-algebra/economics/CS rules from 2L.19. Each declines when values are missing.

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **363 passed** (was 337; +26: production pipeline + new formula rules).
- Coverage: preset expansion + unknown-preset rejection; runner reads no prediction
  files; protected-output refusal; Docker input-detection priority + empty-dir + generic
  fallback; safe-override policy (override on differing safe rule, keep base otherwise,
  keep base when rule agrees, batch); deterministic branch routing; new formula rules
  (positive + decline); no qid hardcoding / no external sheet / no API-key/.env in source.

## Dry-run readiness audit summary (no API)

`scripts/audit_hidden_generalization_readiness.py` on public test (diagnostic only):
- 463 questions; branches: short_knowledge 190, calculation 159, long_context 100,
  ambiguous 7, law_admin 7.
- **17** fireable safe deterministic rules total (calc 13, short_knowledge 2,
  ambiguous 1, law_admin 1); top families include the new `pythagorean_distance` and
  `resistor_series_parallel_basic`.
- **146** calculation-route questions have NO safe deterministic rule (coverage-gap
  signal — these rely on the base LLM, as expected).
- A separate re-run of the formula bank over v8_clean still yields exactly **1** change
  (the verified `pythagorean_distance` fix) — the 2L.20 additions introduced **no new
  misfires** on the public set.

## Confirmations

- **No final prediction generated**; no `pred_v10`; `outputs/pred.csv` not created or
  overwritten (protected-output guard + this phase did not run the producer).
- **No API call** in this phase (the base-solver step was never executed; tests inject
  no client and never reach the OpenRouter path).
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used.
- No protected outputs overwritten; `outputs/*` are gitignored (untracked).
- No API key baked into Docker; `.env` not read by the new code.

## Final command for the human operator (manual; contacts OpenRouter)

```bash
.venv/bin/python scripts/run_production_pipeline.py \
  --input public-test_1780368312.json \
  --output outputs/pred_production_user_run.csv \
  --preset competition_qwen35_9b
```
(Competition/container path: the Docker entrypoint runs the same pipeline with
`--input <auto-detected /data file> --output /output/pred.csv --preset
competition_qwen35_9b`.)

## git status

```
 M Dockerfile
?? scripts/run_production_pipeline.py
?? scripts/audit_hidden_generalization_readiness.py
?? scripts/docker_entrypoint.sh
?? src/production_policy.py
?? src/formula_bank_solver.py
?? scripts/apply_formula_bank_to_predictions.py   (from 2L.19)
?? tests/test_production_pipeline.py
?? tests/test_formula_bank_solver.py              (from 2L.19, extended)
?? docs/AUDIT_PHASE_2L19_FORMULA_BANK_V9.md        (from 2L.19)
?? docs/AUDIT_PHASE_2L20_HIDDEN_GENERAL_PRODUCTION_PIPELINE.md
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*` and `scratch/*`
are gitignored, so the readiness-audit CSV is untracked.)

## Next step

The operator runs the manual command above (or builds/runs the Docker image) to
produce a fresh full prediction, validates it, and — if accepted — promotes it to
`outputs/pred.csv` via the explicit archive-first finalization step (as in 2L.18).
Then commit the accepted code/docs/audits. Do not commit now.
