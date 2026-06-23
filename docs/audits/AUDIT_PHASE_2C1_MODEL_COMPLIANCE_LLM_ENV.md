# Audit — Phase 2C.1: Model Compliance + LLM Environment + Option-Scoring Hardening

**Date:** 2026-06-19
**Branch:** `deployment` (Phase 2B/C committed at `137269d`; this work uncommitted)
**Scope:** Prepare for a real local-LLM run — optional deps, environment check,
model-compliance guardrail, and selectable option-scoring modes.
**Out of scope (by constraint):** real LLM inference (no local model / no
torch/transformers present), model downloads, external APIs. Baseline + I/O
contract unchanged; default solver remains `always_a`.

## 1. Files inspected

`README.md`, `run.py`, `configs/default.yaml`, `src/hf_common.py`,
`src/hf_generate_solver.py`, `src/hf_option_score_solver.py`,
`src/solver_factory.py`, `scripts/run_llm_smoke.sh`, `scripts/run_llm_full.sh`,
`docs/PROJECT_STATUS_AND_ROADMAP.md`, `docs/METHOD.md`,
`experiments/leaderboard_log.csv`, plus `git status` / `git log`.

## 2. Files created / modified

### Created
| Path | Purpose |
|---|---|
| `requirements-llm.txt` | Optional LLM deps (torch, transformers, accelerate, sentencepiece, safetensors); baseline/Docker do not need it. |
| `scripts/check_llm_env.py` | Reports torch/transformers, CUDA, GPU/VRAM; validates a model path; optional `--load-tokenizer`/`--load-model`; never downloads. |
| `configs/allowed_models.yaml` | Allowed/expected patterns: Qwen3.5 ≤ 9B, Gemma-4, BGE-m3, Qwen-Rerank; disallowed families list. |
| `scripts/check_model_compliance.py` | PASS/WARNING/FAIL checker; `--model-name`/`--model-path`; `--strict`; size-cap aware; never downloads. |
| `docs/MODEL_COMPLIANCE.md` | Allowed families, safe vs risky interpretation, recommended models, open questions for BTC, provenance, why unapproved models are dangerous. |
| `docs/RESEARCH_STRATEGY.md` | Polished strategy (option-scoring backbone, CoT, self-consistency, PAL-lite, passage compression; implemented vs planned vs avoided). |
| `tests/test_model_compliance.py` | 9 tests for the compliance logic. |
| `tests/test_score_mode.py` | 5 tests for score-mode continuations + invalid-mode rejection. |
| `docs/AUDIT_PHASE_2C1_MODEL_COMPLIANCE_LLM_ENV.md` | This audit. |

### Modified
| Path | Change |
|---|---|
| `src/hf_option_score_solver.py` | Added `score_mode` (`label_only`/`label_plus_choice`/`choice_only`, default `label_plus_choice`); `_continuation()` helper; richer debug detail (mode, labels, scores, best, second-best, margin). |
| `src/solver_factory.py` | Thread `score_mode` into `HFOptionScoreSolver`. |
| `run.py` | New `--score-mode` flag (argparse-validated choices); resolved via CLI>config>default; passed to `build_solver`. |
| `configs/default.yaml` | Added `hf.score_mode: label_plus_choice`. |
| `scripts/run_llm_smoke.sh`, `scripts/run_llm_full.sh` | Optional `SCORE_MODE` arg; print the full command; remind to run the compliance check first. |
| `README.md` | Optional LLM env setup, `check_llm_env.py` / `check_model_compliance.py` usage, score-mode table, recommended leaderboard experiment order. |
| `docs/METHOD.md` | Option-scoring variants, model-compliance & LLM-env section, note that the leaderboard decides the retained scoring mode. |

No files deleted or moved. Dataset, sample submission, and PDF untouched.

## 3. Exact commands run

```bash
git status ; git log --oneline --decorate -8
python3 run.py --input public-test_1780368312.json --output outputs/pred.csv
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred.csv
python3 scripts/check_llm_env.py
python3 scripts/check_model_compliance.py --model-name "Qwen3.5-7B"
python3 scripts/check_model_compliance.py --model-name "DeepSeek-7B"
python3 scripts/check_model_compliance.py --model-name "Qwen3.5-14B"      # size cap
python3 scripts/check_model_compliance.py --model-name "SomeModel-3B" --strict
python3 -m pytest -q                                                       # not installed
# standalone test runners for all 7 suites
# Docker baseline rebuild + run + validate
```

## 4. Validation results

- **Baseline run:** 463 samples, solver `always_a`, 463 rows. **Validate: PASS.**
- **Docker baseline:** rebuilt, ran (auto-detected mounted file), **validate PASS** — baseline intact.
- **Tests:** `python -m pytest -q` → **"No module named pytest"** (declared in
  `requirements.txt`, not installed here). Standalone runners: **47/47 passed**
  (labels 6, data_io 8, prompting 7, output_parser 8, solver_factory 4,
  **model_compliance 9**, **score_mode 5**).

## 5. LLM environment check result

`scripts/check_llm_env.py` reports **torch: NOT installed**, **transformers: NOT
installed**, **LLM-ready: NO**. CUDA/GPU therefore not probed. This is expected —
the optional deps are not installed in this environment, and we did not install
them (no model to run). To enable: `pip install -r requirements-llm.txt`.

## 6. Model compliance check examples

| Command | Verdict | Exit |
|---|---|---|
| `--model-name "Qwen3.5-7B"` | **PASS** (allowed family, within 9B) | 0 |
| `--model-name "gemma-4-9b-it"` | **PASS** (allowed family) | 0 |
| `--model-name "bge-m3"` | **PASS** (allowed embedding/rerank) | 0 |
| `--model-name "DeepSeek-7B"` | **FAIL** (disallowed family) | 1 |
| `--model-name "Qwen3.5-14B"` | **FAIL** (size 14B > 9B cap) | 1 |
| `--model-name "SomeModel-3B" --strict` | **FAIL** (unrecognized, strict) | 1 |
| `--model-name "MysteryModel-3B"` (non-strict) | **WARNING** (unrecognized) | 0 |

The checker is deliberately not brittle: name/path-basename substring + regex
matching, a parameter-size cap for Qwen, and a clear distinction between FAIL
(disallowed / over-cap) and WARNING (merely unrecognized).

## 7. Option-scoring changes

- Three selectable continuation styles: `label_only` (`" A"`),
  `label_plus_choice` (`" A. <text>"`, **default**), `choice_only` (`" <text>"`).
- Invalid `score_mode` raises `ValueError` **before** any model load (unit-tested).
- Debug log (`--save-raw`) now records `score_mode`, candidate `labels`, per-label
  `scores`, `best_label`, `second_label`, and `margin`, plus any `fallback_reason`.
- Scoring math, fallback chain (generation → `A`), and `torch.no_grad()` usage
  are unchanged from Phase 2B/C.

## 8. Was real LLM inference run?

**No.** No local model is available and torch/transformers are not installed;
downloading is forbidden. All LLM-dependent code paths were exercised only at the
non-tensor level (continuation strings, mode validation, compliance, env check).
A real run requires `pip install -r requirements-llm.txt` and a compliant local
`--model-path`, then `bash scripts/run_llm_smoke.sh <model> [score_mode]`.

## 9. Git branch / status

Branch `deployment`. New/changed files are uncommitted (see §2). `outputs/*`
remain git-ignored. The Phase-2-overview docs
(`PROJECT_STATUS_AND_ROADMAP.md`, `AUDIT_PROJECT_OVERVIEW.md`) were already
present and uncommitted from the prior task.

## 10. Risks / caveats

- **Allowed-model list is provisional.** `configs/allowed_models.yaml` encodes our
  *safe interpretation*, not confirmed organizer policy. Gemma-4 has no size cap
  recorded. Open questions are tracked in `docs/MODEL_COMPLIANCE.md`.
- **Compliance is heuristic.** It matches names/paths, not actual weights — a
  mislabeled directory could pass. It is a guardrail, not proof of provenance.
- **Option-scoring modes are unverified on a real model.** Which mode wins is an
  open empirical question for the leaderboard.
- **`pytest` not installed locally**; standalone runners were used (honestly
  reported). torch/transformers also absent by design.

## 11. Recommended next step

Proceed to **Phase 2D** once a compliant local model is available: install
`requirements-llm.txt`, run `check_llm_env.py` and `check_model_compliance.py`,
then `run_llm_smoke.sh <model>` → full run → validate → record the first real
leaderboard score. Before that, still resolve the two non-code blockers from the
project overview (publish work to the graded branch; confirm the real scoring
rubric / time budget / packaging format with BTC).
