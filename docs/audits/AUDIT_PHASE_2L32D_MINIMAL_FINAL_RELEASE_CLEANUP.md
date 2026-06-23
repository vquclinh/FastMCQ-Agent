# Audit — Phase 2L.32D: Minimal Final Release Cleanup

**Date:** 2026-06-23  **Branch:** `main`  **Status:** uncommitted (commit-ready, minimal plan)

## Final default confirmation

Production default unchanged: **independent v11 frozen** —
`outputs/pred_v11_independent_rerun1.csv` (public **78.4**), offline `frozen_csv`, no API key;
v10 fallback only. Docker no-arg + local no-arg + local explicit all resolve to this CSV.

## File classification

### 1. Required final package (must commit — the BTC frozen path depends on these)
- `scripts/final_infer.py` — entrypoint (frozen_csv default, no-arg I/O, validation, timing).
- `scripts/docker_entrypoint_v11.sh` — no-arg Docker entrypoint.
- `scripts/validate_submission.py` — output validator *(already committed, unmodified)*.
- `src/data_io.py`, `src/labels.py` — the **only** project modules imported by the frozen
  path *(already committed, unmodified)*.
- `configs/production_v11_independent.json` — production config.
- `outputs/pred_v11_independent_rerun1.csv` — the winning 78.4 CSV.
- `Dockerfile`, `.dockerignore`, `.gitignore`, `requirements.txt` *(reqs already committed)*.
- `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`.

### 2. Useful fallback / reproducibility (should commit)
- `outputs/pred_v10_full_production_user_run.csv` — v10 fallback (`--mode v10`).
- `experiments/best_candidate_manifest.json` — best-candidate manifest (scores + md5s).
- `docs/audits/AUDIT_PHASE_2L32D_…md` (this file) + the release/freeze audits.

### 3. Development / experimental pipeline (leave UNCOMMITTED — not needed for frozen run)
- v11/adaptive runners & builders: `run_full_v11_independent_submission.py`,
  `repair_v11_independent_run.py`, `run_full_adaptive_submission.py`,
  `run_adaptive_selective_api.py`, `run_adaptive_pilot.py`,
  `run_selective_multicandidate_api.py`, `build_*` / `audit_*` / `plan_*` / `select_*` /
  `analyze_*` / `review_*` scripts.
- experimental `src/` modules: `independent_answer_selector.py`, `calculation_first_planner.py`,
  `answer_factory.py`, `answer_ranker.py`, `api_candidate_agents.py`, `candidate_answer.py`,
  `candidate_consistency.py`, `evidence_pack.py`, `option_grounding.py`, `rag_lite.py`,
  `model_policy.py`, `selective_api_client.py`, `adaptive_accuracy_planner.py`,
  `src/tool_solvers/` *(only reached by `--mode v11_independent`, which is opt-in)*.
- phase tests (`tests/test_*_2l2*.py`, etc.) — 16 untracked development test files.
- pre-existing tracked **modifications** from the v11 work: `src/formula_bank_solver.py`,
  `src/knowledge_cards.py`, `src/openrouter_client.py`, `scripts/run_production_pipeline.py`,
  `tests/test_candidate_lab.py`, `tests/test_formula_bank_solver.py` — left modified-but-
  uncommitted (not part of the frozen BTC path).
- the 18 untracked dev-cycle audit docs (2L.25–2L.32C) under `docs/` — development evidence.

### 4. Do not commit (ignored, verified absent from `git status`)
- `.env` (holds the real `OPENROUTER_API_KEY`; `.gitignore:15`), `.venv/`, `scratch/`,
  `__pycache__/`, `.pytest_cache/`, model weights/caches, notebooks/logs,
  `outputs/pred.csv` (runtime export), `outputs/pred_v8_*` (old candidate), any external sheet.

## Files moved / removed

- **Created** `docs/audits/` and moved **all 72 `docs/AUDIT_*.md` files** into it (per user
  request for a cleaner repo): 54 already-committed audits via `git mv` (staged renames,
  history preserved) + 18 untracked dev-cycle audits via plain `mv`. `docs/audits/` now holds
  73 files (incl. this audit). `docs/` root retains only the 13 non-audit reference docs
  (ARCHITECTURE, METHOD, CALCULATION_*, DATASET_PROFILE, etc.).
- No code/test/README path referenced the audit docs (only self-references inside the audits),
  so the move broke nothing — **618 tests still pass** after the move.
- **No files removed.** No required/best artifact deleted. `scratch/` (12M, fully gitignored)
  left as-is by user decision; the 16 untracked dev-phase test files kept (uncommitted).

## Final package dependency list (Part B)

Static + lazy-import trace of `scripts/final_infer.py`:
- top-level project imports: **`src.data_io`, `src.labels`** (and stdlib only).
- the v11 runner is loaded **lazily** via `importlib` only under `--mode v11_independent`, so
  the **frozen_csv default does not import any experimental module**. No refactor needed.
- `scripts/validate_submission.py` also imports only `src.data_io` + `src.labels`.
- `scripts/docker_entrypoint_v11.sh` calls only `scripts/final_infer.py` (no
  `run_production_pipeline.py`). Output md5 unchanged: `69f4e7c990e8c612e7bee53084d13b4d`.

## Docker smoke result (Part E)

`docker build -t fastmcq-final .` — SUCCESS. No-arg run with `/data/doc_public_test.csv`:
```
input detected: /data/doc_public_test.csv   output: /output/pred.csv
md5: 69f4e7c990e8c612e7bee53084d13b4d   elapsed_seconds: 0.008   status: PASS
```
`validate_submission` → `RESULT: PASS`; md5 == winning: **True**.

## Tests / model-policy result (Part F)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **618 passed** (28 tracked test files + 16 untracked dev-cycle test files).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**

Committed vs development tests: the **minimal commit does not include the 16 untracked phase
test files**; they remain development artifacts. All 618 tests were run green *before*
cleanup, so the frozen path + validator are verified.

## Recommended commit strategy

**Option 1 — Minimal final commit (RECOMMENDED).** Commit only the final BTC package +
winning/fallback CSVs + final docs + this release audit. Leave the experimental v11/adaptive
pipeline, phase tests, dev-cycle audit docs, and the 6 pre-existing tracked source
modifications as uncommitted development artifacts. Rationale: the frozen Docker path depends
only on `final_infer.py` + `data_io` + `labels` + config + the winning CSV, so a minimal,
auditable package is sufficient and easiest for BTC to understand.

(Option 2 — full reproducibility commit — would add the whole v11 pipeline + tests + audits;
defer unless reproducibility of the `--mode v11_independent` rerun must ship.)

## Staging plan (Part G) — updated for the audit reorganization

`git add -A` is **not** used (it would also stage the full experimental pipeline). The repo
now also carries the **audit reorganization** (all `docs/AUDIT_*.md` → `docs/audits/`): 54
staged renames + 18 moved untracked dev-cycle audits. To realize the clean `docs/audits/`
layout in git, commit the whole audit folder alongside the minimal BTC package.

- `outputs/pred_v11_independent_rerun1.csv` → **COMMIT** (winning 78.4).
- `outputs/pred_v10_full_production_user_run.csv` → **COMMIT** (fallback).
- `docs/audits/` (the reorg: 54 renames + 18 moved docs) → **COMMIT** (documentation only;
  realizes the clean layout the user requested).
- v11 experimental runner scripts + experimental `src/` modules → **DO NOT COMMIT** (dev
  artifacts; the frozen path doesn't import them).
- 16 untracked dev-phase tests → **DO NOT COMMIT** (kept on disk per user; still pass).
- 6 pre-existing tracked source modifications → **DO NOT COMMIT** (not on the frozen path).

## Exact recommended `git add` command

```bash
# minimal BTC package
git add \
  scripts/final_infer.py \
  scripts/docker_entrypoint_v11.sh \
  configs/production_v11_independent.json \
  experiments/best_candidate_manifest.json \
  outputs/pred_v11_independent_rerun1.csv \
  outputs/pred_v10_full_production_user_run.csv \
  Dockerfile .dockerignore .gitignore \
  README.md FINAL_RUN.md DOCKER_SUBMISSION.md
# audit reorganization (renames already staged by git mv; this adds the 18 moved dev-cycle docs)
git add docs/audits/
git status --short    # verify: no .env/scratch/.venv and no experimental scripts/src/tests
```

## Exact recommended `git commit` command

```bash
git checkout -b v11-independent-final
git commit -m "BTC final package: frozen independent v11 (78.4) as production default

- scripts/final_infer.py: offline frozen_csv default (no API key), no-arg /data->/output,
  CSV qid input, A-K label validation, elapsed timing, output protection
- Docker ENTRYPOINT no-arg (auto-detect input; args forwarded); .dockerignore excludes
  .venv/secrets/scratch; .gitignore tracks the winning v11 CSV + v10 fallback
- configs/production_v11_independent.json + best_candidate_manifest.json
- README/FINAL_RUN/DOCKER_SUBMISSION docs; all audits reorganized under docs/audits/
Frozen path depends only on src/data_io + src/labels (already committed). Output md5
69f4e7c990e8c612e7bee53084d13b4d. Experimental v11 pipeline + phase tests left uncommitted."
```
(Do not commit until `git status --short` after staging is reviewed.)

## Final `git status` (relevant subset after the recommended staging)

Staged (13 paths): the files in the `git add` list above — incl. both required `outputs/`
CSVs. Left unstaged/untracked: the experimental v11 scripts/`src` modules, 16 phase tests,
dev-cycle audit docs, and the 6 pre-existing tracked source modifications. Ignored & absent:
`.env`, `.venv/`, `scratch/`, caches, `outputs/pred.csv`, `outputs/pred_v8_*`.

## Confirmations

- **No OpenRouter/API call** this phase; no inference (frozen_csv + offline Docker only).
- **No best outputs overwritten** — winning CSV md5 still `69f4e7c990e8c612e7bee53084d13b4d`;
  v10 untouched; root `pred.csv` not written; smokes wrote only under `scratch/`.
- v10 not made default; required final files all present.
- No qid hardcoding; no answer tables / ground truth; external 3-LLM sheet not used.
- No files deleted; only `docs/audits/` created.
- Nothing committed.
