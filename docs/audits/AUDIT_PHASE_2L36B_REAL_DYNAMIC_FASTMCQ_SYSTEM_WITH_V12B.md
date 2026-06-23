# Audit — Phase 2L.36B: Real Dynamic FASTMCQ System with Official V12B Layer

**Date:** 2026-06-23  **Branch:** `main`  **Status:** architecture build (no commit, no API)

## Problem corrected

The previous default was effectively a **public-frozen replay**: it copied the 78.83 public CSV
and validated it. That is only valid for the public test's exact qids — useless for private/
unseen qids or larger inputs (~2000 questions). This phase makes the **default a real dynamic
pipeline** (`dynamic_full`) that processes ANY input and outputs predictions for exactly the
given qids, with the official **V12B** debiaser integrated as an architecture layer. The public
frozen CSV is now reachable only via the explicit `public_replay` mode (leaderboard reproduction).

## Files created / changed

**Created (src architecture):**
- `src/fastmcq_system.py` — orchestrator (`FastMCQSystemConfig`, `FastMCQSystemReport`,
  `run_fastmcq_system`).
- `src/dynamic_base_predictor.py` — `BasePrediction`, `predict_base_answers` (arbitrary qids;
  deterministic formula/concept bank + conservative fallback; optional guarded API).
- `src/v12b_dynamic_layer.py` — `V12BTarget`, `V12BLayerResult`, `select_v12b_targets`
  (feature-based), `run_v12b_layer` (uses `src.mcq_permutation_debiaser`; API only under
  `execute_api`).
- `src/v13_layer_registry.py` — `available_v13_layers`, `run_v13_layers_if_enabled` (disabled
  by default, never applied).
- `tests/test_fastmcq_dynamic_system_2l36b.py` — 16 tests.
- `docs/audits/AUDIT_PHASE_2L36B_…md` — this audit.

**Changed:**
- `scripts/final_infer.py` — new modes `dynamic_full` (default) / `public_replay` / `auto`
  (kept `frozen_csv`/`v11_independent`/`v10`); new flags (`--allow-public-replay`,
  `--execute-api`/`--no-api`, `--enable/disable-v12b`, `--v12b-max-qids/-permutations/-policy`,
  `--enable/disable-v13`, `--work-dir`); delegates dynamic modes to `run_fastmcq_system`; richer
  logs.
- `scripts/docker_entrypoint_v11.sh` — header/behavior now dynamic_full default.
- `experiments/best_candidate_manifest.json` — documents the dynamic production_system and that
  the public-best artifact is **not** universal.
- `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`, `README.md` — explain dynamic_full vs public_replay,
  V12B as official layer, API-free vs API mode, recommended private command.
- Tests retargeted to the new default (`test_btc_short_2l31b.py`, `test_btc_noarg_2l32b.py`,
  `test_final_package_2l31a.py`): reproduction asserts moved to `--mode public_replay`; default
  asserts now expect `dynamic_full`.

## Architecture overview

`final_infer.py` → resolves mode → for dynamic modes calls `src.fastmcq_system.run_fastmcq_system`:
1. validate input (qids present/unique);
2. `dynamic_base_predictor.predict_base_answers` — one valid label per sample
   (deterministic `solve_formula_bank_sample` → conservative `dynamic_fallback`; guarded API
   only under `execute_api`);
3. per-qid metadata via base-prediction fields (route, risk_reason, source, confidence);
4. `v12b_dynamic_layer.select_v12b_targets` — feature-based (weak/fallback source, low
   confidence, ≥5 options, multi-condition, long, route);
5. `v12b_dynamic_layer.run_v12b_layer` — official debiaser; API only under `execute_api`,
   else every target reported `skipped_no_api`;
6. `v13_layer_registry.run_v13_layers_if_enabled` — visible, disabled by default, never applied;
7. assemble (base → apply valid V12B overrides), validate (exact input qids, valid labels), write.

## Official mode behavior

- **dynamic_full** (default): runs the full dynamic architecture; output = exactly input qids;
  V12B included (skipped without API, applied with `--execute-api`). Verified on unseen qids.
- **public_replay**: copies `pred_v12b_permutation_candidate_api30.csv` only when the input qid
  set exactly matches the public artifact; **fails clearly** otherwise.
- **auto**: `public_replay` only with `--allow-public-replay` AND exact public match; else
  `dynamic_full`. Never silently replays public answers onto unseen qids.

## How V12B is included in the official dynamic path

`run_fastmcq_system` always (when `enable_v12b`, default true) selects feature-based V12B targets
and runs `run_v12b_layer`, which uses the official `src/mcq_permutation_debiaser` core
(permutations → map-back → vote summary → conservative/balanced override). Overrides are applied
to the dynamic base predictions when valid. Without API the layer reports targets and applies 0
overrides (`skipped_no_api`).

## V13 registry status

`available_v13_layers()` exposes `programmatic_solver`, `content_first`, `least_to_most` — all
`enabled_by_default=False`, `promoted=False`. `run_v13_layers_if_enabled` returns `[]` unless
explicitly enabled, and even then applies nothing to predictions. Not wired into the default.

## Fake private smoke result (Part I)

```
final_infer.py --input scratch/dynamic_system_smoke/private_test.json --mode dynamic_full --no-api
  resolved mode: dynamic_full (api=off)
  base predictions : 2
  V12B enabled=True executed=False targets=2 overrides=0   (skipped_no_api)
  V13 enabled=False executed=False (registered, not applied)
  questions: 2  status: PASS
  output qids: private_smoke_0001, private_smoke_0002  (exactly the input; NOT public replay)
```

## Public replay smoke result (Part I)

```
final_infer.py --input public-test_1780368312.json --mode public_replay
  source: outputs/pred_v12b_permutation_candidate_api30.csv
  md5: 075646adb4ec7d2db1b234186b091f70   status: PASS
md5 == outputs/pred_v12b_permutation_candidate_api30.csv  ✓
public_replay on a private input -> REFUSED clearly (qid set mismatch).
auto on private -> resolved dynamic_full; auto + --allow-public-replay on public -> public_replay.
```

## Tests and model-policy results (Part H)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **689 passed** (16 new dynamic-system tests; updated btc/final-package tests)
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Confirmations

- **No API calls** during coding or smokes — dynamic_full ran with `--no-api`; V12B/base
  construct no client unless `--execute-api`; disallowed-model attempt raises via `model_policy`
  before any call (unit-tested).
- **No ground truth / hidden answers / answer tables / external 3-LLM sheet.**
- **No qid/answer hardcoding** — system modules regex-clean and contain no frozen-CSV path
  dependency (unit-tested `test_no_qid_hardcoding_in_system_modules`).
- **Public-best artifact retained** — `pred_v12b_permutation_candidate_api30.csv` md5
  `075646ad…` unchanged; v11 `69f4e7c9…`, v10 `c12e32fd…` unchanged.
- **Output artifacts protected/archived** — official CSVs (v8/v10/v11/v12b) tracked; old shadow
  candidates archived under `scratch/archive_outputs/`; `pred.csv` gitignored.
- **Docker/BTC behavior** — no-arg = dynamic_full (API-free), writes `/output/pred.csv` for
  exactly the input qids; args forwarded (`--mode public_replay`, `--execute-api`, etc.).
- **Not committed.**

## Git status

```
 M .gitignore  DOCKER_SUBMISSION.md  FINAL_RUN.md  README.md
 M configs/production_v11_independent.json  experiments/best_candidate_manifest.json
 M scripts/docker_entrypoint_v11.sh  scripts/final_infer.py
 M tests/test_btc_noarg_2l32b.py  tests/test_btc_short_2l31b.py  tests/test_final_package_2l31a.py
?? configs/production_v12b_permutation_7883.json
?? src/fastmcq_system.py  src/dynamic_base_predictor.py  src/v12b_dynamic_layer.py  src/v13_layer_registry.py
?? src/mcq_permutation_debiaser.py  src/{programmatic_solver_layer,content_first_answerer,least_to_most_constraint_solver}.py
?? scripts/{build,run,audit}_v12*/v13* .py
?? tests/test_fastmcq_dynamic_system_2l36b.py  tests/test_{mcq_permutation_debiaser_2l34c,v12_delta_2l34a,v12b_permutation_2l34b,v13_multilayer_2l35a}.py
?? outputs/pred_v12b_permutation_candidate_api30.csv  outputs/pred_v8_clean_generalized_from_v7.csv
?? docs/audits/AUDIT_PHASE_2L34A..2L36B_*.md
```
(`outputs/pred.csv` and `scratch/` — incl. `scratch/archive_outputs/` — remain gitignored.)
Nothing committed.

## Next phase

1. Run **dynamic_full with V12B API** on the public test (`--execute-api --budget-usd …`) as a
   full-system check — compare its output to the 78.83 public_replay artifact.
2. Then run the **V13 multilayer API pilot** *through this dynamic architecture* (V13 enabled),
   using V12B 78.83 as the comparison baseline; promote V13 only if it beats 78.83.
