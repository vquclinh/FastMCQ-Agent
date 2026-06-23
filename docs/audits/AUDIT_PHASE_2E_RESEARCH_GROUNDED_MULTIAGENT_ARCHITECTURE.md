# Audit — Phase 2E: Research-Grounded Multi-Agent Architecture Design

**Date:** 2026-06-19
**Branch:** `main` @ `9b371dc`
**Scope:** Design-only phase. Produced `docs/ARCHITECTURE.md` (the target
multi-agent system) and summarized it into `METHOD.md` / `RESEARCH_STRATEGY.md`.
**No solver code was written or changed; no LLM inference was run.**

## 1. Files inspected

`run.py`, `configs/default.yaml`, `src/solver_base.py`, `src/solver_factory.py`,
`src/prompting.py`, `src/output_parser.py`, `src/hf_generate_solver.py`,
`src/hf_option_score_solver.py`, `src/run_logger.py`,
`scripts/validate_submission.py`, `docs/DATASET_PROFILE.md`,
`docs/PROJECT_STATUS_AND_ROADMAP.md`, `docs/METHOD.md`,
`docs/RESEARCH_STRATEGY.md`, `docs/MODEL_COMPLIANCE.md`,
`experiments/leaderboard_log.csv`, and `git status`. (Most were already known
from prior phases; re-confirmed current state on `main`.)

## 2. Files created / modified

### Created
| Path | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | **FastMCQ-Agent++** full design: 13 sections incl. system diagram, agent roles, routing policy table, strategy policy table, research mapping, budget tiers, confidence/fallback policy, ablation plan, implementation roadmap (2F–3), and immediate recommendation. |
| `docs/AUDIT_PHASE_2E_RESEARCH_GROUNDED_MULTIAGENT_ARCHITECTURE.md` | This audit. |

### Modified
| Path | Change |
|---|---|
| `docs/METHOD.md` | Added "Target architecture — FastMCQ-Agent++" summary section linking to `ARCHITECTURE.md`. |
| `docs/RESEARCH_STRATEGY.md` | Added section 12 "Multi-agent architecture (FastMCQ-Agent++)". |

## 3. Was core code changed?

**No.** `git status` confirms only `docs/` changed; `src/`, `run.py`, `configs/`,
`scripts/`, and `tests/` are untouched. The default solver remains `always_a` and
the I/O contract is unchanged.

## 4. Validation commands and results

```bash
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_architecture_check.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_architecture_check.csv
.venv/bin/python -m pytest -q
```

- Baseline run: 463 samples, solver `always_a`, 463 rows. **Validate: PASS.**
- Tests: **47 passed** (pytest in `.venv`).
- Baseline intact; design work changed no behaviour.

## 5. Key architecture decisions

- **Backbone = likelihood-based option scoring**; generation is a fallback /
  comparison baseline.
- **Cheap-by-default routing:** a deterministic, no-LLM profiler + router sends
  most samples through a single Tier-0 scoring pass.
- **Three compute tiers** with a budget controller; expensive reasoning (Tier 2)
  is rationed to low-confidence / high-value cases so a ~2000-sample private test
  stays within time.
- **Confidence via the option-scoring top-2 margin** drives accept-vs-fallback.
- **Specialist agents** (knowledge, long-context, calculation, law/admin,
  safety/ethics, ambiguity) instead of one fixed prompt.
- **Evidence-gated adoption:** advanced techniques ship only if a leaderboard
  ablation shows real gains at acceptable cost.

## 6. Research ideas mapped into modules

| Research idea | Practical module | Default? |
|---|---|---|
| Likelihood option scoring | Candidate Scoring Engine | **yes (backbone)** |
| Chain-of-Thought | calculation-route internal reasoning prompt (label-only output) | route-only |
| RAG | in-question passage selection (Reading Agent) | long-context route |
| Lost-in-the-Middle | evidence positioning + compression (Context Builder) | long-context route |
| ReAct | module separation (router / builder / scorer / verifier / fallback) | structural |
| Self-Consistency | low-confidence Tier-2 fallback | gated |
| PAL / PoT | PAL-lite numeric helper (sandboxed) | gated, future |
| Reflexion / Self-Refine | single selective revision + logged error analysis | gated |
| Multi-agent debate | rare hard-case consensus | gated, optional |
| Tree/Graph-of-Thought | rare deliberation; GoT research-only | gated, maybe never |

All are specified as **lightweight, gated** versions — not full reimplementations.

## 7. Runtime / accuracy trade-offs

- **10-choice questions cost ~10 scoring passes**; 135 such samples make naive
  Tier-2-everywhere infeasible. The budget controller keeps mean latency near
  Tier 0 by escalating only the minority of hard cases.
- **GPU VRAM is 7.6 GB** (from Phase 2D.1) — too small for a 7B model in fp16;
  the roadmap front-loads quantization (Phase 2I) and a fits-in-VRAM model choice.
- Accuracy claims are deferred to leaderboard ablations (Phase 2H); the design
  asserts no accuracy numbers.

## 8. Risks / caveats

- **Design, not code:** most modules (profiler, router, compressor, confidence,
  adaptive solver) are planned, not implemented. Risk of scope creep — mitigated
  by the explicit phase plan and "what not to implement yet" list.
- **Routing/compression are heuristic** and can misroute or drop decisive
  evidence; the verifier and a safe default route are the guards.
- **No ground truth:** all thresholds must be tuned conservatively on the
  leaderboard, not locally — risk of overfitting if rushed.
- **transformers 5.x / 7.6 GB VRAM** constraints (from 2D.1) still pending real
  validation.
- **Model compliance** remains provisional pending organizer confirmation.

## 9. Recommended next implementation phase

**Phase 2F — Lightweight agent modules.** Build `src/question_profiler.py`,
`src/question_router.py`, `src/passage_compressor.py`, `src/confidence.py` with
tests. These are pure-Python, need no model, are fully testable now, and unblock
the AdaptiveAgentSolver (2G). Run the first real model ablation (2H) once a
compliant `MODEL_PATH` is available; add expensive reasoning (2J) only on
leaderboard evidence.

## 10. Git status

```
 M docs/METHOD.md
 M docs/RESEARCH_STRATEGY.md
?? docs/ARCHITECTURE.md
?? docs/AUDIT_PHASE_2E_RESEARCH_GROUNDED_MULTIAGENT_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2D1_VENV_AND_FIRST_LLM_SMOKE.md
?? docs/AUDIT_PHASE_2D_REAL_MODEL_SMOKE.md
```

All changes are documentation; uncommitted, pending review. `outputs/*` and
`.venv` remain git-ignored.
