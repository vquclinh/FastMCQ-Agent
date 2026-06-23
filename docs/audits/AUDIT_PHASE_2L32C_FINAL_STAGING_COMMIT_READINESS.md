# Audit — Phase 2L.32C: Final Staging Audit + Commit Readiness

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (ready to commit)

## Final default confirmation

Production default unchanged: **independent v11**, `outputs/pred_v11_independent_rerun1.csv`,
public **78.4**, offline `frozen_csv`, no API key; v10 is fallback only. Default command
(`python scripts/final_infer.py`) and BTC Docker no-arg both resolve to this frozen CSV.

## No-arg local smoke result (Part B)

```
(cd scratch/final_commit_smoke/json_auto && python ../../../scripts/final_infer.py)
  input detected: public-test_1780368312.json   output: pred.csv
  md5: 69f4e7c990e8c612e7bee53084d13b4d   elapsed_seconds: 0.022   status: PASS
```

## No-arg Docker smoke result (Part C)

`docker build -t fastmcq-final .` — SUCCESS. No-arg run with a qid-only
`/data/doc_public_test.csv`:
```
[final_infer] input detected: /data/doc_public_test.csv
[final_infer] output: /output/pred.csv
md5: 69f4e7c990e8c612e7bee53084d13b4d   elapsed_seconds: 0.008   status: PASS
```

## validate_submission result

Both the local and Docker outputs: `RESULT: PASS — submission is valid.`

## md5 match result

```
best   : 69f4e7c990e8c612e7bee53084d13b4d
local  : 69f4e7c990e8c612e7bee53084d13b4d  (same: True)
docker : 69f4e7c990e8c612e7bee53084d13b4d  (same: True)
```

## Tests result (Part D)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **618 passed**
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**

## Production candidate audit summary

`candidate valid=True, qid_set_valid=True, changed_vs_v10=48, beats_v10=True,
md5_matches_manifest=True` → **recommendation: `freeze_as_default`**
(report under `scratch/production_candidate_audit_commit/`).

## Safe-file audit summary (Part A)

`git add -A` dry-run was inspected: **98 files** would be staged, and a filter for
`.env`/`.venv`/`scratch`/`__pycache__`/`.pytest_cache`/`.key`/`.pem`/`models`/`.bin`/
`.safetensors`/`.ipynb`/`.log` matched **nothing**. Secret scan of `src`/`scripts`/`configs`
found **no hardcoded API keys**.

**Confirmed NOT staged (ignored):**
- `.env` — exists (contains the real `OPENROUTER_API_KEY=sk-or-v***`); matched by
  `.gitignore:15:.env` → never staged.
- `scratch/` (incl. `scratch/full_v11_independent_rerun1/v11_independent_candidates.jsonl`)
  → `.gitignore:55:scratch/*`.
- `.venv/`/`venv/`/`env/`, `.pytest_cache/`, `__pycache__/`, `models/`, weights/caches,
  notebooks/logs → all ignored.
- `outputs/pred.csv` (runtime export), `outputs/pred_v8_clean_generalized_from_v7.csv`
  (old candidate) → ignored.

**Confirmed stage-able / should be committed:**
- `outputs/pred_v11_independent_rerun1.csv` (winning 78.4) and
  `outputs/pred_v10_full_production_user_run.csv` (fallback) — un-ignored via the
  `.gitignore` exceptions (lines 37–38); both appear as `??`.
- `scripts/final_infer.py`, `scripts/docker_entrypoint_v11.sh`, `Dockerfile`,
  `.dockerignore`, `.gitignore`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`,
  `configs/production_v11_independent.json`, `experiments/best_candidate_manifest.json`.
- All v11 independent scripts/`src`/`tests` and the `docs/AUDIT_PHASE_2L25..2L32C_*.md`.
- Pre-existing tracked modifications (`scripts/run_production_pipeline.py`,
  `src/formula_bank_solver.py`, `src/knowledge_cards.py`, `src/openrouter_client.py`,
  `tests/test_candidate_lab.py`, `tests/test_formula_bank_solver.py`) — part of the v11
  pipeline work; scanned clean (no secrets).

**Suspicious files that should not be committed:** none found.

Note: `outputs/pred_v11_full_adaptive_test.csv` (an experimental, gitignored artifact from an
earlier human run) is no longer present in `outputs/`; it is not a required/best artifact and
was not modified or deleted by this phase.

## Ignored / staged recommendation

`git add -A` is **safe** (verified by the dry-run above — no secrets/venv/scratch/caches/
weights/notebooks get staged; only the two required `outputs/` CSVs are added).

## Confirmations

- **No OpenRouter/API call** this phase; no inference (frozen_csv + offline Docker only).
- **No best outputs overwritten** — `outputs/pred_v11_independent_rerun1.csv` md5 still
  `69f4e7c990e8c612e7bee53084d13b4d`; v10 untouched; smokes wrote only under `scratch/`.
- v10 not made default; required final files all present.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Exact recommended `git add` command

```bash
git add -A
git status --short    # verify: 2 outputs/ CSVs staged, NO .env / scratch / .venv / caches
```

## Exact recommended `git commit` command

```bash
git checkout -b v11-independent-freeze   # avoid committing straight to main
git commit -m "Freeze winning independent v11 (78.4) as production default + BTC final package

- final_infer.py: frozen_csv default, optional no-arg I/O (/data -> /output/pred.csv),
  CSV qid input, global A-K label validation, elapsed timing block, output protection
- Docker ENTRYPOINT no-arg (auto-detect input, forward args); .dockerignore excludes
  .venv/secrets/scratch; .gitignore tracks the required final CSVs (v11 winner + v10 fallback)
- full independent v11 runner + repair + integrity/production audits
- docs: FINAL_RUN.md, DOCKER_SUBMISSION.md, README final-submission pointer
- 618 tests passing; model-policy audit PASS"
```
(Do not commit until you have reviewed `git status --short` after staging.)

## Final `git status --short`

(Unchanged from the safe-file audit, plus this new audit doc as `??`.)
```
 M .gitignore
 M Dockerfile
 M README.md
 M scripts/run_production_pipeline.py
 M src/formula_bank_solver.py
 M src/knowledge_cards.py
 M src/openrouter_client.py
 M tests/test_candidate_lab.py
 M tests/test_formula_bank_solver.py
?? .dockerignore
?? DOCKER_SUBMISSION.md
?? FINAL_RUN.md
?? configs/production_v11_independent.json
?? docs/AUDIT_PHASE_2L25..2L32C_*.md   (audit docs, incl. this one)
?? experiments/best_candidate_manifest.json
?? outputs/pred_v10_full_production_user_run.csv
?? outputs/pred_v11_independent_rerun1.csv
?? scripts/*.py  (final_infer, docker_entrypoint_v11.sh, run_full_v11_independent_submission,
                  repair_v11_independent_run, audit_*, build_*, run_*, etc.)
?? src/*.py  (independent_answer_selector, calculation_first_planner, answer_factory,
              answer_ranker, api_candidate_agents, model_policy, …) + src/tool_solvers/
?? tests/test_*.py  (btc_noarg_2l32b, btc_short_2l31b, final_package_2l31a, independent_v11_2l30b,
                     repair_v11_2l30c, v11_hardening_2l30d, …)
```
(`.env`, `scratch/`, `.venv/`, caches remain ignored and absent from the list above.)
