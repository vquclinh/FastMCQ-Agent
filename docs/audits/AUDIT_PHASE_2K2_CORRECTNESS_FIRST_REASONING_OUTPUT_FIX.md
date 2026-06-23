# Audit — Phase 2K.2: Correctness-First Qwen Reasoning Output Fix

**Date:** 2026-06-19
**Branch:** `main` @ `200bf0a` (+ uncommitted 2K.2 changes)
**Result:** **Blocker fixed.** A clean, correctness-first config was found and
verified on live limit-3 and limit-20 smokes: **reasoning explicitly disabled +
minimal-output prompt + answer-key parser recovery**. No full inference, no
leaderboard upload, no commit.

## 1. Repo / key guard

Branch `main`; `OPENROUTER_API_KEY` **present** (never printed); `.env`
git-ignored + untracked. Recovered from a prior interrupted run — the reasoning
CLI/config wiring was present, but the parser hardening and prompt changes were
not yet applied; completed them this phase.

## 2. Files inspected

`src/openrouter_client.py`, `src/openrouter_graph_solver.py`,
`src/openrouter_prompts.py`, `src/structured_answer.py`, `src/solver_factory.py`,
`run.py`, `configs/default.yaml`, the OpenRouter tests, `docs/OPENROUTER_ROUND1_STRATEGY.md`,
and the Phase 2K.1 audit + prior 2K.2 outputs/logs.

## 3. Files modified / created

| Path | Change |
|---|---|
| `src/openrouter_client.py` | Reasoning controls; `build_payload` **always sends `reasoning.enabled`** (default `false` = truly off) + configured exclude/max_tokens/effort when enabled. |
| `src/openrouter_prompts.py` | **Minimal-output contract**: answer first, JSON only, no chain-of-thought, evidence ≤2 items / ~80 chars, short result clue for calculations. |
| `src/structured_answer.py` | Schema tightened (answer `maxLength`, evidence array `maxItems:2`/`maxLength:120`); parser adds **explicit answer-key recovery** from truncated JSON (`source="partial_answer_key"`) and **removed** the unreliable first-standalone-letter fallback. |
| `src/openrouter_graph_solver.py`, `run.py`, `configs/default.yaml` | Reasoning config + CLI (`--openrouter-reasoning-*`) wired through (from the recovered prior run). |
| `tests/test_openrouter_client.py`, `tests/test_structured_answer.py` | Updated/added tests (see §5). |
| `docs/OPENROUTER_ROUND1_STRATEGY.md` | Added the 2K.1/2K.2 blocker + chosen-config section. |
| `docs/AUDIT_PHASE_2K2_CORRECTNESS_FIRST_REASONING_OUTPUT_FIX.md` | This audit. |

## 4. Reasoning config (final, evidence-based)

`reasoning_enabled` (+ effort/max_tokens/exclude), default **false**. **Deviation
from the task's literal "omit when false" rule, justified by evidence:** for
`qwen/qwen3.5-9b`, *omitting* `reasoning` lets it reason by default → empty
content (0/3 parseable). The client therefore sends `reasoning.enabled`
**explicitly**; default `{"enabled": false}` truly disables reasoning. Correctness
(non-empty parseable answers for every sample) takes priority over the literal
schema, per this phase's stated priority order.

## 5. Prompt/schema + parser changes

- **Prompt:** JSON-only, `answer` first, no step-by-step reasoning, evidence ≤2
  short items; calculation = short result clue, not a derivation essay.
- **Schema:** `answer` short; `evidence` array capped (`maxItems:2`, item
  `maxLength:120`) so verbose output can't truncate the JSON.
- **Parser order:** strict JSON → fenced → embedded → **explicit `"answer":"X"`
  recovery** (degraded, `needs_review`, marked `partial_answer_key`) → failure.
  No recovery from a random standalone letter / letters in evidence / option text.
  Recovered answers are validated against the sample's labels.

## 6. Tests added/updated

`pytest`: **141 passed**. New/changed: default payload disables reasoning
(`{"enabled": false}`); enabled payload includes exclude/max_tokens/effort;
partial-JSON answer-key recovery; **no** recovery from standalone letters or prose;
recovered label validated; existing 1-call / repair-cap / no-key-in-logs tests
retained.

## 7. Validation before live calls

`compileall` OK; `pytest -q` → **141 passed**.

## 8. Live smoke variants (limit-3 unless noted)

| Variant | reasoning | max_tokens | result |
|---|---|---|---|
| A | enabled, cap 512, exclude | 2048 | **2/3** (test_0001 empty; cap ignored); ~47 s/sample |
| omit (Candidate 1) | omitted | 1024 | **0/3** empty (model reasons by default) |
| effort:low (Candidate 2) | enabled, effort low | 2048 | **2/3** (test_0001 empty); ~75 s/sample |
| **disabled (chosen)** | **`enabled:false`** | **1024** | **3/3 full JSON**, 1 call, ~3.8 s/sample |
| **disabled — limit-20** | `enabled:false` | 1024 | **20/20 parseable**, see below |

## 9. Per-variant parse / api_calls / latency

- **Chosen config, limit-20:** parse_ok **20/20**; sources **19 full JSON + 1
  answer-key recovery**; `api_calls` = **1 for all**; repairs **0**; mean
  **3.27 s/sample**; answers diverse (A=8, B=7, C=5); all labels valid (partial
  validation PASS). limit-3 of the same config: 3/3 full JSON, answers A/C/B.
- Reasoning-on variants were 2/3 (empty on the hardest long-context sample) and
  10–20× slower — i.e. **worse correctness** (fallback) and worse speed.

## 10. Chosen best config

```
--solver openrouter_graph --openrouter-model qwen/qwen3.5-9b
--openrouter-temperature 0 --openrouter-max-tokens 1024
# reasoning disabled (default => reasoning:{"enabled":false})
```
Correctness-first AND fast: every sample yields a non-empty, parseable, valid
label; full JSON in ~95% of cases, safe answer-key recovery otherwise; 1 API
call/sample; ~3.3 s/sample.

## 11. limit-20

**Run** (chosen config) — clean (see §9). `outputs/pred_phase2k2_best_limit20.csv`,
`outputs/run_phase2k2_best_limit20.jsonl`.

## 12. Confirmations

- **No full public inference** (max 20 samples). **No leaderboard upload.**
- **API key never logged/committed** (grep over all 2K.2 logs: 0 hits); `.env`
  ignored/untracked. **No `reasoning_details`/private chain-of-thought logged**
  (grep: 0 hits) — and reasoning is excluded/disabled anyway.

## 13. Remaining risks

- Only ~23 live samples seen; the full 463-set may surface rarer formats — the
  parser recovery + safe fallback bound the downside (always a valid label).
- `partial_answer_key` recovery is a *degraded* success (1/20 here); a high rate
  on the full set would warrant a small `max_tokens` bump.
- No ground truth — "correct" here means real parseable answers, not verified
  accuracy. Leaderboard score is the only accuracy signal.
- Provider may change `qwen/qwen3.5-9b` behavior/identity over time.

## 14. Recommended next phase

**Phase 2K.3 — full public OpenRouter generation** with the chosen config:
run all 463 samples (consider `--resume` for safety), validate the full CSV with
`scripts/validate_submission.py` (expect PASS / full coverage), review the
`partial_answer_key` rate and latency, then upload to the leaderboard. Keep the
local/offline solvers for the later Docker/private rounds.

## 15. Git status (uncommitted)

```
 M configs/default.yaml
 M docs/OPENROUTER_ROUND1_STRATEGY.md
 M run.py
 M src/openrouter_client.py
 M src/openrouter_graph_solver.py
 M src/openrouter_prompts.py
 M src/structured_answer.py
 M tests/test_openrouter_client.py
 M tests/test_structured_answer.py
?? docs/AUDIT_PHASE_2K1_LIVE_OPENROUTER_SMOKE.md
?? docs/AUDIT_PHASE_2K2_CORRECTNESS_FIRST_REASONING_OUTPUT_FIX.md
```

All changes **uncommitted**, for user review. `.env`, `.venv/`, `outputs/`, and
model dirs remain out of git.
