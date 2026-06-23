# Audit — Project Overview

**Date:** 2026-06-19
**Purpose:** Produce a complete project status report and roadmap before deciding
the next implementation phase. **No solver features were added or changed.**

## Files inspected

- **Top level:** `README.md`, `run.py`, `Dockerfile`, `requirements.txt`,
  `.gitignore`, `configs/default.yaml`.
- **`src/`:** `data_io.py`, `labels.py`, `solver_base.py`, `baseline_solver.py`,
  `postprocess.py`, `utils.py`, `prompting.py`, `output_parser.py`,
  `hf_common.py`, `hf_generate_solver.py`, `hf_option_score_solver.py`,
  `solver_factory.py`, `run_logger.py`.
- **`scripts/`:** `validate_submission.py`, `inspect_dataset.py`,
  `profile_dataset.py`, `run_local.sh`, `run_llm_smoke.sh`, `run_llm_full.sh`,
  `benchmark_runtime.py`.
- **`tests/`:** `test_labels.py`, `test_data_io.py`, `test_prompting.py`,
  `test_output_parser.py`, `test_solver_factory.py`.
- **`docs/`:** `METHOD.md`, `DATASET_PROFILE.md`, `hackaithon.pdf`, and the four
  prior audits (initial setup, Phase 1.1, Phase 2A, Phase 2B/C).
- **`experiments/`:** `leaderboard_log.csv`, `README.md`.
- **Data:** `public-test_1780368312.json` (463 samples), `submission_1780332147.csv`
  (4-row illustrative sample), `outputs/run_debug.jsonl` (empty).

## Files created / modified

- **Created:** `docs/PROJECT_STATUS_AND_ROADMAP.md`, `docs/AUDIT_PROJECT_OVERVIEW.md`.
- **Modified:** none.
- **Generated (git-ignored):** `outputs/pred_overview_check.csv` (from the safe
  baseline run below).

## Commands run

```bash
git status
git log --oneline --decorate -8
find . -maxdepth 3 -type f | sort
cat outputs/run_debug.jsonl            # confirm no prior LLM run (empty)
python3 run.py --input public-test_1780368312.json --output outputs/pred_overview_check.csv
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_overview_check.csv
python3 -m pytest -q                   # -> "No module named pytest"
python3 tests/test_labels.py tests/test_data_io.py tests/test_prompting.py \
        tests/test_output_parser.py tests/test_solver_factory.py   # standalone fallback
```

(Also read `docs/hackaithon.pdf`, pages 1–6.)

## Git branch and commit info

- **Branch:** `deployment`
- **HEAD:** `137269d add competitive local LLM solver framework`
- Recent commits: `137269d` (Phase 2B/C) → `ad1f477` (Phase 2A) →
  `8e63cee` (Phase 1/1.1 baseline) → `ce11a26` (initial commit, = `origin/main`).
- **Note:** `origin/main` / `main` still point at `ce11a26` (bare initial commit).
  All real work is on `deployment` — flagged as a reproducibility blocker.

## Git status

`On branch deployment — nothing to commit, working tree clean` (before this
audit). The two new docs are the only additions; no tracked source changed.

## Validation commands run

- **Baseline run:** 463 samples, solver `always_a`, 463 rows written.
- **Submission validation:** **RESULT: PASS**.
- **Tests:** `pytest` not installed (`No module named pytest`); standalone
  runners → **33/33 passed** (labels 6, data_io 8, prompting 7, output_parser 8,
  solver_factory 4).
- **LLM inference:** **not run** — no local model, no torch/transformers, and
  downloads are forbidden. `outputs/run_debug.jsonl` is empty, confirming no
  prior real run.

## Was any code changed?

**No.** This task was inspection + documentation only. No `src/`, `run.py`,
config, Dockerfile, or test files were modified.

## Key conclusions

1. **Infrastructure is mature and verified.** Baseline + Docker produce a valid
   submission; 33/33 tests pass.
2. **The LLM framework is built but unproven.** No real-model run has occurred;
   no leaderboard score exists. No accuracy claims can be made yet.
3. **Two non-code blockers dominate risk:** (a) all work is on `deployment` while
   `main` is empty; (b) the bundled PDF is the *general* HackAIthon rules and does
   **not** specify the MCQA accuracy/speed weighting, time budget, or submission/
   packaging format — these must be confirmed externally.
4. **The dataset is well-characterised** structurally (463 samples, 2–11 choices,
   ~29% >4 choices, 21.6% long-context); category heuristics are rough and should
   not be over-trusted.

## Recommended next step

Before any model work: **publish the work to the branch graders will clone** and
**confirm the real scoring rubric / time budget / submission format.** Then run
**Phase 2C.1** (optional `requirements-llm.txt`) and **Phase 2D** (smoke test +
first full run on a real local model, logged to the leaderboard CSV). Full
rationale and phase plan in
[`docs/PROJECT_STATUS_AND_ROADMAP.md`](PROJECT_STATUS_AND_ROADMAP.md).
