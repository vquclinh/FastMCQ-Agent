# Audit — Phase 2F/G: Full Core Adaptive Multi-Agent Solver Implementation

**Date:** 2026-06-19
**Branch:** `main` @ `9b371dc` (working changes uncommitted)
**Scope:** Implement the core `adaptive_agent` solver and its supporting modules
per `docs/ARCHITECTURE.md` (Minimal Viable Agent v1). Default solver stays
`always_a`; advanced reasoning methods are gated off. **No real LLM inference was
run** (`MODEL_PATH` empty).

## 1. Files inspected

`docs/ARCHITECTURE.md`, `docs/METHOD.md`, `docs/RESEARCH_STRATEGY.md`, `run.py`,
`configs/default.yaml`, `src/solver_base.py`, `src/solver_factory.py`,
`src/prompting.py`, `src/hf_generate_solver.py`, `src/hf_option_score_solver.py`,
`src/output_parser.py`, `src/run_logger.py`, `src/postprocess.py`,
`src/data_io.py`, `src/labels.py`, existing tests, and `git status`.

## 2. Files created

| Path | Purpose |
|---|---|
| `src/question_profiler.py` | Deterministic `QuestionProfile` (length, choices, context/numeric/legal/safety signals, duplicate choices, difficulty). No torch. |
| `src/question_router.py` | Deterministic `RouteDecision` over 7 routes with budget tier + primary/fallback strategy. |
| `src/passage_compressor.py` | Pure-Python BM25-lite long-context compressor; preserves title/question, never touches choices, never returns empty or longer-than-input text. |
| `src/confidence.py` | `ConfidenceDecision` from top-2 margin + structural signals; configurable thresholds. |
| `src/adaptive_agent_solver.py` | `AdaptiveAgentSolver` orchestration + `AdaptiveConfig`; rich JSONL trace; gated advanced-method guard. |
| `tests/test_question_profiler.py` | 8 tests. |
| `tests/test_question_router.py` | 7 tests. |
| `tests/test_passage_compressor.py` | 6 tests (incl. never-drops-choices, never-longer-than-input). |
| `tests/test_confidence.py` | 8 tests (high/medium/low/unknown). |
| `tests/test_adaptive_agent_solver.py` | 9 tests via injected fakes (no model). |
| `docs/AUDIT_PHASE_2FG_FULL_CORE_ADAPTIVE_AGENT_IMPLEMENTATION.md` | This audit. |

## 3. Files modified

| Path | Change |
|---|---|
| `src/hf_option_score_solver.py` | Added `score_sample()` (rich metadata, no logging) and parameterized `_score_options`/`_score_detail` by `score_mode`. **`predict_one` behavior unchanged** (verified by existing tests). |
| `src/run_logger.py` | Added `record_event(dict)` for the adaptive solver's richer JSONL schema. Existing `record`/`record_summary` unchanged. |
| `src/solver_factory.py` | Added `adaptive_agent` (lazy import; builds `AdaptiveConfig` from known keys); kept `always_a`/`hf_generate`/`hf_option_score`. |
| `run.py` | Resolve `hf.adaptive` config into `adaptive_config`; `--score-mode` overrides the adaptive primary mode; pass through to `build_solver`. All existing CLI preserved. |
| `configs/default.yaml` | Added `hf.adaptive` block with safe defaults; advanced flags off; default solver still `always_a`. |
| `docs/METHOD.md`, `docs/RESEARCH_STRATEGY.md`, `docs/PROJECT_STATUS_AND_ROADMAP.md`, `docs/ARCHITECTURE.md` | Marked Phase 2F/G implemented; reiterated gating and "no real inference yet". |

## 4. Architecture pieces implemented

- **Profiler → Router → Budget tier → (Context compression for long_context) →
  Option-scoring backbone → Confidence → Selective fallback → Final valid label.**
- Reuses `HFOptionScoreSolver` as the backbone and shares its loaded model with
  the generation fallback (no double model load).
- Long-context compression injects a compressed `question` into a copied sample,
  so no prompt-building code is duplicated.
- Rich per-sample JSONL trace via `RunLogger.record_event` with all required
  fields (qid, route, profile_features, num_choices, question_length, budget_tier,
  strategy, score_mode, best_label, second_label, margin, confidence_level,
  fallback_used, fallback_reason, compressed_context_used,
  compressed_context_stats, duplicate_choice_groups, elapsed_sec, final_answer);
  robust to missing fields (defaults to null).

## 5. Architecture pieces intentionally gated / not implemented

- `enable_self_consistency`, `enable_pal_lite`, `enable_debate`, `enable_tot_lite`
  exist as config flags but are **off by default**; enabling any raises
  `NotImplementedError` (clear failure, no silent no-op). Tested.
- No neural rerank (BGE-m3 / Qwen-Rerank) in the compressor — lexical only.
- No external retrieval, no external APIs, no internet, no model download.
- Tier-2 budget for `ambiguous` is clamped to Tier 1 unless `allow_tier2_ambiguous`.

## 6. Was any LLM inference run? / MODEL_PATH

- **No LLM inference was run.** `MODEL_PATH` is **empty**.
- The adaptive solver's orchestration (routing, confidence, fallback, logging) is
  validated with **injected fakes** in `tests/test_adaptive_agent_solver.py` — no
  torch/model required. Real-model behavior is deferred to Phase 2H.

## 7. Validation commands and results

```bash
.venv/bin/python -m pytest -q
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_adaptive_code_check_baseline.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_adaptive_code_check_baseline.csv
```

- **pytest: 84 passed** (47 prior + 37 new across the 5 new test files).
- Baseline run: 463 samples, solver `always_a`, 463 rows. **Validate: PASS.**
- `adaptive_agent` without `--model-path` → clean `ERROR ... requires --model-path`
  (exit 2), no fabricated output.
- Pure modules import without torch (confirmed).

## 8. Test results detail

| Suite | Tests |
|---|---|
| test_question_profiler | 8 |
| test_question_router | 7 |
| test_passage_compressor | 6 |
| test_confidence | 8 |
| test_adaptive_agent_solver | 9 (incl. gated-method `NotImplementedError`, factory recognizes `adaptive_agent`, default stays `always_a`) |
| (existing) labels/data_io/prompting/output_parser/solver_factory/model_compliance/score_mode | 46 |

A real bug was caught and fixed during testing: `_extract_head` could capture an
entire newline-free passage as the "title", making compressed output longer than
the input. Fixed by bounding the title regex **and** adding a hard invariant that
compressed length never exceeds the original.

## 9. Risks / caveats

- **Unproven on a real model.** Routing/compression/confidence are deterministic
  and unit-tested, but end-to-end quality and latency are unknown until Phase 2H.
- **Confidence thresholds (0.30 / 0.10) are conservative placeholders**, not
  tuned — they are config values and must be set from leaderboard evidence.
- **Compression may drop a decisive sentence** if lexical overlap misses it; the
  final question and choices are always preserved as mitigation.
- **transformers 5.x / 7.6 GB VRAM** constraints (Phase 2D.1) still apply to any
  real run; the adaptive path does extra forward passes on fallback (cost-capped
  by `max_fallbacks_per_sample`).
- **Backward compatibility:** `hf_option_score` behavior is preserved (existing
  tests pass); the refactor only added an optional `score_mode` parameter and a
  non-logging `score_sample` method.

## 10. Git status

```
 M configs/default.yaml
 M docs/METHOD.md
 M docs/PROJECT_STATUS_AND_ROADMAP.md
 M docs/RESEARCH_STRATEGY.md
 M run.py
 M src/hf_option_score_solver.py
 M src/run_logger.py
 M src/solver_factory.py
?? docs/ARCHITECTURE.md
?? docs/AUDIT_PHASE_2D_REAL_MODEL_SMOKE.md
?? docs/AUDIT_PHASE_2D1_VENV_AND_FIRST_LLM_SMOKE.md
?? docs/AUDIT_PHASE_2E_RESEARCH_GROUNDED_MULTIAGENT_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2E1_ARCHITECTURE_HARDENING.md
?? docs/AUDIT_PHASE_2FG_FULL_CORE_ADAPTIVE_AGENT_IMPLEMENTATION.md
?? src/adaptive_agent_solver.py
?? src/confidence.py
?? src/passage_compressor.py
?? src/question_profiler.py
?? src/question_router.py
?? tests/test_adaptive_agent_solver.py
?? tests/test_confidence.py
?? tests/test_passage_compressor.py
?? tests/test_question_profiler.py
?? tests/test_question_router.py
```

`outputs/*` and `.venv` remain git-ignored. All changes uncommitted, pending review.

## 11. Recommended next phase

**Phase 2H — Real model ablation and leaderboard logging.** With a compliant
local `MODEL_PATH` (Qwen3.5 ≤ 9B, quantized to fit 7.6 GB), run a smoke test of
`adaptive_agent` (and compare against `hf_generate` / `hf_option_score` score
modes), validate, benchmark, and log the first real leaderboard scores. Use the
JSONL traces to tune the confidence thresholds and routing before considering any
Phase 2J advanced reasoning.
