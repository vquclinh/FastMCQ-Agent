# Audit — Phase 2FG.1: Adaptive Agent Hardening + Commit Checkpoint

**Date:** 2026-06-19
**Branch:** `main`
**Scope:** Harden the Phase 2F/G adaptive multi-agent core, verify integration
safety against a defined risk list, and commit the completed Phase 2D/2E/2F/G
work. No new features; no model download; no real LLM inference (`MODEL_PATH`
empty).

## 1. Files inspected

`src/adaptive_agent_solver.py`, `src/hf_option_score_solver.py`,
`src/question_profiler.py`, `src/question_router.py`,
`src/passage_compressor.py`, `src/confidence.py`, `src/solver_factory.py`,
`src/run_logger.py`, `run.py`, `configs/default.yaml`, the five Phase 2F/G test
files, `.gitignore`, and `git status`.

## 2. Risk review

| Risk | Finding |
|---|---|
| Baseline default changed | **OK** — `configs/default.yaml` `solver: always_a`; `run.py` resolves default `always_a`. |
| Adaptive runs silently without model | **OK** — factory raises `ValueError` (exit 2); confirmed no output file written. |
| Double model load | **OK** — generation fallback shares `self.scorer._loaded`. |
| Fallback exceeds `max_fallbacks_per_sample` | **OK** — `attempts[: max_fallbacks_per_sample]` bounds it; verified with `max=0` edge case (no fallback, no crash). |
| Compression empty / longer than input | **OK** — invariant clamps to input length; never-empty fallback; unit-tested. |
| Choices modified/dropped | **OK** — compressor returns only `compressed_question`; adaptive copies sample with new question; choices untouched (test asserts list unchanged). |
| Missing score metadata crashes logging | **OK** — `.get()` defaults everywhere; `_emit` wrapped in try/except. |
| Score-mode override breaks `hf_option_score` | **OK** — optional `score_mode` param defaults to `self.score_mode`; `predict_one` unchanged; `test_score_mode` + `test_solver_factory` pass. |
| Advanced flags silently no-op | **OK** — enabling any raises `NotImplementedError` (tested for all four). |
| Public-test-answer hardcoding / overfitting | **OK** — grep for `test_0###` / `answer_key` / `gold` / `ground_truth` in `src/` found nothing. |
| `.venv` / `outputs` staged | **OK** — both git-ignored; staged set contains neither. |

## 3. Bugs found and fixes made

**None requiring a fix in this phase.** The review confirmed the Phase 2F/G code
already handles every item on the risk list (the compressor length/empty bug was
already found and fixed during 2F/G). No code changes were made here beyond
adding this audit; the implementation was committed as-is after verification.

## 4. Validation commands and results

```bash
.venv/bin/python -m compileall -q src tests          # OK
.venv/bin/python -m pytest -q                        # 84 passed
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_phase2fg1_baseline.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_phase2fg1_baseline.csv  # PASS
```

- **compileall:** OK (all `src/` and `tests/` modules byte-compile).
- **pytest:** **84 passed.**
- **Baseline:** 463 samples, solver `always_a`, 463 rows, **validate PASS**.

## 5. adaptive_agent-without-model behavior

```bash
.venv/bin/python run.py --solver adaptive_agent --input public-test_1780368312.json \
  --output outputs/pred_should_not_exist_without_model.csv --limit 3
# -> "ERROR: solver 'adaptive_agent' requires --model-path ... never downloads anything."
# adaptive_agent_without_model_exit=2
```

Exit code **2** (non-zero), clear error message, and **no output file created**
(`ls` confirmed absence). It does **not** fabricate predictions.

## 6. .venv and outputs ignored

```
git check-ignore -v .venv      -> .gitignore:10:.venv/   .venv
git check-ignore -v outputs/.. -> .gitignore:22:outputs/*  outputs/pred_phase2fg1_baseline.csv
```

Both ignored. The staged set (`git diff --cached --name-only`) contained no paths
under `.venv/` or `outputs/`.

## 7. Commit

Created. Staged exactly: `configs/default.yaml`, `run.py`, all new/modified
`src/`, the five new `tests/`, and `docs/` (architecture, research/method/roadmap
updates, and Phase 2D–2FG audits).

- **Commit message:** `Implement adaptive multi-agent MCQA solver`
- **Commit hash:** `4c2ac00` (this audit's hash-record line was committed in a
  small follow-up so the implementation commit hash stays accurate).

Post-commit:

```
$ git log --oneline -3
4c2ac00 Implement adaptive multi-agent MCQA solver
9b371dc add model compliance and LLM environment setup
f1181ea Merge pull request #1 from vquclinh/deployment
```

## 8. Remaining blocker for Phase 2H

A **compliant local model** at `MODEL_PATH` (Qwen3.5 ≤ 9B, quantized to fit the
7.6 GB GPU) plus the already-installed LLM deps. Until then no real inference,
accuracy, or leaderboard score is possible. Confidence thresholds and routing
remain conservative placeholders pending leaderboard tuning.

## 9. Risks / caveats

- The adaptive solver is verified structurally and with fakes, but **unproven on a
  real model**; latency of multi-pass scoring + fallback is unmeasured.
- `transformers` 5.x and the 7.6 GB VRAM ceiling (from Phase 2D.1) still apply.
- Model-compliance remains provisional pending organizer confirmation.

## 10. Recommended next phase

**Phase 2H — Real model ablation and leaderboard logging:** with a compliant
`MODEL_PATH`, smoke-test `adaptive_agent` and the `hf_option_score` modes,
validate, benchmark, and record the first real leaderboard scores; tune
confidence/routing from the JSONL traces before any Phase 2J work.

## 11. Final git status

After the implementation commit (`4c2ac00`), `git status --short` was **clean**
(empty). This audit's hash-record update is committed as a small follow-up; after
it, the working tree is clean again. `.venv/` and `outputs/` remain untracked and
git-ignored throughout.
