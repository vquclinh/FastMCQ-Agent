# Audit — Phase 2L.38A: Promote V13 Multi-Layer 79.7 as Official Dynamic Production System

**Date:** 2026-06-24  **Branch:** `main`  **Status:** promotion (no commit, no API)

## Why V13 is promoted

The V13 multi-layer candidate (built from the V12B base) improved the public leaderboard to
**79.7**, beating V12B 78.83 by +0.87 (9 qids changed). V13 is now the official public-best
artifact, and its three methods are official, default-on architecture layers in the dynamic
system.

## Leaderboard score progression

| version | file | public |
|---|---|---|
| v11 | `pred_v11_independent_rerun1.csv` | 78.40 |
| V12B | `pred_v12b_permutation_candidate_api30.csv` | 78.83 |
| **V13** | `pred_v13_multilayer_candidate_api30_from_v12b.csv` | **79.7** |

## Official public-best artifact and md5 (Part A — verified, all matched expected)

```
cb02fef569b31e7fb544abab46c0e282  outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv  (NEW best)
075646adb4ec7d2db1b234186b091f70  outputs/pred_v12b_permutation_candidate_api30.csv          (prev best)
69f4e7c990e8c612e7bee53084d13b4d  outputs/pred_v11_independent_rerun1.csv
c12e32fdf16ee5472e6a791c1e52e86a  outputs/pred_v10_full_production_user_run.csv
```
V13: 463 rows, qid set == public test, all labels valid, changed_vs_V12B = 9
(test_0034 A→B, 0082 B→D, 0103 E→A, 0123 B→F, 0155 F→A, 0251 I→H, 0269 A→I, 0388 A→C, 0420 B→A).

## Official dynamic architecture after promotion

```
input arbitrary test set
 → src/dynamic_base_predictor.py        (one valid label per qid; deterministic + optional API)
 → src/v12b_dynamic_layer.py            (official V12B option-permutation debiaser)
 → src/v13_dynamic_layer.py             (official V13: programmatic_solver / content_first / least_to_most)
 → src/system_candidate_selector.py     (unified conservative override selector)
 → validated output (exactly the input qids)
```
`dynamic_full` is the default and the real production/BTC mode; **V12B and V13 are both enabled
by default**; API only under `--execute-api` (model validated via `src/model_policy.py`).

## Files created / changed

**Created:** `configs/production_v13_multilayer_7970.json`,
`docs/audits/AUDIT_PHASE_2L38A_…md`.
**Changed:**
- `scripts/final_infer.py` — `_DEFAULT_CONFIG` → V13 config; V13 best added to `_PROTECTED_NAMES`;
  `--enable-v13` default **True**.
- `src/fastmcq_system.py` — `FastMCQSystemConfig.enable_v13` default **True**.
- `scripts/docker_entrypoint_v11.sh` — `--config` → V13 config.
- `configs/production_v12b_permutation_7883.json` — `status: SUPERSEDED`, `superseded_by` V13.
- `experiments/best_candidate_manifest.json` — current_best = V13 79.7; v12b/v11 demoted;
  score_progression + official_layers.
- `.gitignore` — official tracked outputs now include the V13 CSV.
- `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`, `README.md` — V13 79.7 current best; both layers
  official + default-on; dynamic_full vs public_replay; API-free vs API; recommended commands.
- Tests retargeted to V13 (`_BEST`/`_V12B` → V13 file + md5 `cb02fef5…`; manifest test → V13).

## Production config updates

`configs/production_v13_multilayer_7970.json`: `current_best_csv` = V13 CSV, score 79.7, md5
`cb02fef5…`; `enable_v12b_default`/`enable_v13_default` = true; previous bests + fallback +
protected_outputs recorded. V12B config marked SUPERSEDED.

## Docs / manifest updates

README / FINAL_RUN / DOCKER_SUBMISSION now state: current best is V13 79.7; V12B + V13 are
official default-on layers; `public_replay` reproduces the V13 79.7 artifact (public qids only);
`dynamic_full` is the real system for arbitrary/private/BTC inputs; API-free vs API commands.

## Smoke test results (Part H, no API)

- **dynamic_full --no-api** on 3 unseen private qids → `resolved mode: dynamic_full`,
  V12B enabled targets=3 overrides=0, V13 enabled targets=3 **overrides=1** (deterministic
  programmatic solved "2 + 2" → B), output exactly 3 qids, valid labels, **no None**, PASS.
- **public_replay** on public test → `source: …pred_v13_multilayer_candidate_api30_from_v12b.csv`,
  md5 **cb02fef569b31e7fb544abab46c0e282** == artifact, PASS.
- **auto** on private → `auto -> dynamic_full`, PASS.

## Full tests and model-policy result (Part G)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **705 passed**
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

## Confirmations

- **dynamic_full handles arbitrary/private qids** — smoke + tests output exactly the input qids
  for unseen ids; no public-frozen replay on private input.
- **V12B + V13 are both official architecture layers** — enabled by default in
  `FastMCQSystemConfig` and the CLI; reported in the system log/report.
- **public_replay is explicit-only** — default is dynamic_full; auto needs
  `--allow-public-replay` + exact public-qid match; refuses mismatched qids.
- **No API calls** during promotion/smokes (`--no-api`; clients only under `--execute-api`,
  model-policy guarded).
- **No ground truth / hidden answers / answer tables / external 3-LLM sheet.**
- **No qid/answer hardcoding** in the dynamic system modules (regex-clean; no frozen-CSV path).
- **No best artifacts overwritten** — V13 `cb02fef5…`, V12B `075646ad…`, v11 `69f4e7c9…`,
  v10 `c12e32fd…` all unchanged on disk.
- **Not committed.**

## Git status

```
 M .gitignore  FINAL_RUN.md  DOCKER_SUBMISSION.md  README.md
 M configs/production_v12b_permutation_7883.json  experiments/best_candidate_manifest.json
 M scripts/docker_entrypoint_v11.sh  scripts/final_infer.py  src/fastmcq_system.py
 M tests/test_btc_short_2l31b.py  tests/test_final_package_2l31a.py
   tests/test_fastmcq_dynamic_system_2l36b.py  tests/test_v13_dynamic_integration_2l37a.py
?? configs/production_v13_multilayer_7970.json
?? outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv
?? docs/audits/AUDIT_PHASE_2L38A_PROMOTE_V13_7970_OFFICIAL_DYNAMIC_SYSTEM.md
   (plus untracked 2L.34–2L.37A src/scripts/tests/docs/outputs from prior phases;
    `scratch/` and `outputs/pred.csv` remain gitignored)
```
Nothing committed.

## Next step

Commit all official architecture files and artifacts (dynamic system src, V13/V12B layers,
configs, the V13 79.7 CSV + prior official CSVs, docs, tests). Then, if time remains, run a
larger private/public `dynamic_full --execute-api --enable-v12b --enable-v13` run with a limited
budget to exercise the full model-backed pipeline end-to-end.
