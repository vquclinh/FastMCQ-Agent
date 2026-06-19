# Audit — Phase 2E.1: Architecture Hardening Before Implementation

**Date:** 2026-06-19
**Branch:** `main` @ `9b371dc`
**Scope:** Documentation-only hardening of the architecture before coding Phase 2F.
Added a Minimal Viable Agent v1 scope, logging schema, compressor/confidence v1
policies, and reconciled phase naming across all planning docs.
**No core code changed; no LLM inference run.**

## 1. Files inspected

`docs/ARCHITECTURE.md`, `docs/METHOD.md`, `docs/RESEARCH_STRATEGY.md`,
`docs/PROJECT_STATUS_AND_ROADMAP.md`, `experiments/leaderboard_log.csv`,
and `git status`.

## 2. Files modified

### Created
| Path | Purpose |
|---|---|
| `docs/AUDIT_PHASE_2E1_ARCHITECTURE_HARDENING.md` | This audit. |

### Modified (documentation only)
| Path | Change |
|---|---|
| `docs/ARCHITECTURE.md` | Added **§14 Minimal Viable Agent v1** with three subsections: *Agent JSONL logging schema*, *Passage compressor v1 policy*, *Confidence v1 policy*. Defines the exact 5-module v1 scope and an explicit NOT-in-v1 exclusion list. |
| `docs/PROJECT_STATUS_AND_ROADMAP.md` | Replaced the stale §I/§J draft phase numbering with the canonical roadmap table (2C.1→3, with statuses) and a Phase-2F-focused immediate action. |
| `docs/RESEARCH_STRATEGY.md` | Rewrote §9 "What is planned" to the canonical phase names (2F–2J). |
| `docs/METHOD.md` | Relabeled "Future improvements (Phase 2D+)" → "(Phases 2I–2J)" and tied each item to a phase, noting they are **not** in v1 (links to `ARCHITECTURE.md` §14). |

## 3. Was any core code changed?

**No.** `git status` confirms `src/`, `run.py`, `configs/`, `scripts/`, and
`tests/` are all clean. Only `docs/` files were touched. Default solver remains
`always_a`; the I/O contract is unchanged.

## 4. Validation commands and results

```bash
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_architecture_hardening_check.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_architecture_hardening_check.csv
.venv/bin/python -m pytest -q
```

- Baseline run: 463 samples, solver `always_a`, 463 rows. **Validate: PASS.**
- Tests: **47 passed** (pytest in `.venv`).
- `.venv` was available and used (no `python3` fallback needed).

## 5. Roadmap inconsistencies fixed

The pre-architecture draft in `PROJECT_STATUS_AND_ROADMAP.md` used an **older,
conflicting** phase scheme:

| Old (draft) meaning | Reconciled to canonical |
|---|---|
| 2D = real smoke test + first submission | folded into **2H** (real model ablation) |
| 2E = compare score modes & prompts | folded into **2H** |
| 2F = speed optimization / quantization | now **2I** |
| 2G = adaptive routing / passage compression / math helper | split into **2F** (modules), **2G** (adaptive solver), **2J** (math/advanced) |

All four docs now use one canonical scheme: **2C.1 → 2D.1 → 2E → 2E.1 → 2F → 2G →
2H → 2I → 2J → 3**. A grep confirmed no old-scheme phase definitions remain
(the only `Phase 2G — Adaptive…` match is the correct `AdaptiveAgentSolver v1`).

## 6. New implementation constraints added (anti-over-engineering)

- **Minimal Viable Agent v1 = exactly 5 modules:** `question_profiler.py`,
  `question_router.py`, `passage_compressor.py`, `confidence.py`,
  `adaptive_agent_solver.py`.
- **v1 must be:** deterministic profiling, deterministic routing, pure-Python
  (lexical) passage compression, `hf_option_score` backbone, margin-based
  confidence, simple alternate-mode/generation fallback.
- **Explicitly NOT in v1:** PAL-lite, multi-agent debate, ToT-lite, GoT-style
  reasoning, unrestricted code execution, external retrieval, always-on
  self-consistency.
- **Agent JSONL logging schema** fixed (18 fields incl. route, profile_features,
  budget_tier, strategy, margin, fallback, compression stats) — mandatory because
  there is no local ground truth.
- **Compressor v1:** lexical / BM25-lite, preserve title+question, never touch
  choices, log kept/dropped; **no BGE-m3 / Qwen-Rerank** in v1.
- **Confidence v1:** config-driven margin thresholds (not hard-coded, not claimed
  optimal pre-leaderboard); deterministic duplicate-choice handling.

## 7. Risks / caveats

- **Still design-only:** the 5 v1 modules are specified but not implemented; risk
  is scope creep — mitigated by the explicit NOT-in-v1 list and config-driven
  thresholds.
- **No ground truth:** thresholds and routing quality cannot be validated locally;
  the JSONL logging schema exists precisely to enable leaderboard-driven tuning.
- **No accuracy is claimed.** All effectiveness statements remain hypotheses until
  Phase 2H leaderboard runs.
- **Model/runtime constraints carry over:** 7.6 GB VRAM and transformers 5.x
  (from 2D.1) still pending real validation; `MODEL_PATH` still required for 2H.

## 8. Recommended next phase

**Phase 2F — Lightweight agent modules.** Implement `question_profiler.py`,
`question_router.py`, `passage_compressor.py`, `confidence.py` (pure Python, no
torch, fully testable now) with unit tests, per `ARCHITECTURE.md` §14. This is the
highest-value work available without a `MODEL_PATH` and unblocks the
AdaptiveAgentSolver (2G).

## 9. Git status

```
 M docs/METHOD.md
 M docs/PROJECT_STATUS_AND_ROADMAP.md
 M docs/RESEARCH_STRATEGY.md
?? docs/ARCHITECTURE.md
?? docs/AUDIT_PHASE_2E1_ARCHITECTURE_HARDENING.md
?? docs/AUDIT_PHASE_2D1_VENV_AND_FIRST_LLM_SMOKE.md
?? docs/AUDIT_PHASE_2D_REAL_MODEL_SMOKE.md
?? docs/AUDIT_PHASE_2E_RESEARCH_GROUNDED_MULTIAGENT_ARCHITECTURE.md
```

All changes are documentation; uncommitted, pending review. `outputs/*` and
`.venv` remain git-ignored.
