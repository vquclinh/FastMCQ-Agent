# Phase 2K.4 — System Overview & Next Accuracy Roadmap

**Date:** 2026-06-21
**Branch:** `main` @ `02c59b9`
**Type:** Read-only overview. No API call, no inference, no CSV created/changed,
no leaderboard upload, no code changes, no commit.
**Optimization order:** (1) correctness/accuracy → (2) reliability/safety → (3) speed.

## A. Current milestone summary

| Phase | What | Status |
|---|---|---|
| 1 / 1.1 | Repo skeleton, baseline `always_a`, validator, Docker, input auto-detect | ✅ |
| 2A | Dataset profiling + experiment log | ✅ |
| 2B/C | Local HF solvers (`hf_generate`, `hf_option_score`) + prompting/parsing/logging | ✅ |
| 2C.1 | Model-compliance guardrail + LLM env check + score-mode hardening | ✅ |
| 2D.1 | Local `.venv` LLM-ready (torch+transformers, CUDA RTX 4060 7.6 GB) | ✅ |
| 2E / 2E.1 | Multi-agent architecture design + hardening | ✅ |
| 2F/G | `adaptive_agent` core (profiler, router, compressor, confidence) | ✅ |
| 2I.0 | Optional 4-bit/8-bit quantization readiness (bitsandbytes optional) | ✅ |
| 2J.0 | Downloaded Qwen3.5-9B locally (offline path, not used in Round 1) | ✅ |
| 2K.0/0B/0C | OpenRouter graph solver + speed/payload hardening | ✅ |
| 2K.1 | Live smoke → found reasoning-output blocker | ✅ |
| 2K.2 | Correctness-first reasoning fix (disable reasoning + minimal prompt + parser recovery) | ✅ |
| 2K.3-preflight | Manual full-run readiness check | ✅ |
| **Full public generation** | **Done by the user** — 463-row CSV produced | ✅ |

## B. Current architecture (two modes)

### Mode A — Round-1 OpenRouter leaderboard mode (ACTIVE)

```text
Input sample
→ Input Normalizer (data_io)
→ Dynamic Label Manager (labels: A..K, sized to choices)
→ Question Profiler (deterministic features)
→ Evidence Compressor (passage_compressor; long-context only)
→ Route Selector (question_router: short_knowledge/long_context/calculation/law_admin/safety_ethics/ambiguous)
→ Prompt Builder (openrouter_prompts; minimal JSON, answer-first, no CoT)
→ OpenRouter qwen/qwen3.5-9b Answer Node (1 call)
→ Structured JSON Parser (structured_answer: strict/fenced/embedded → answer-key recovery)
→ Deterministic Verifier (structural; no extra API call)
→ Conditional Repair (only if no valid label; capped at 1 extra call)
→ Final Answer Guard (always a valid label; fallback A)
→ pred.csv (qid,answer)
```

- model **`qwen/qwen3.5-9b`**; reasoning **explicitly disabled** (`reasoning:{"enabled":false}`);
  temperature **0**; **max_tokens 1024** for the full run; `stream:false`.
- structured JSON output (`response_format` json_schema, evidence capped).
- minimal-output prompt; explicit `"answer":"X"` parser recovery for truncated JSON.
- correctness-first; default **1 API call/sample**; self-consistency OFF.

### Mode B — later local / HF / Docker mode (READY, not used in Round 1)

- local `hf_option_score` and `adaptive_agent` (profiler→route→score→verify→fallback).
- 4-bit/8-bit quantization readiness (bitsandbytes optional).
- Qwen3.5-9B weights downloaded under `/mnt/vquclinh/models` (outside git).
- **Blocker for the offline path:** no compliance-confirmed local *generation*
  model wired for the private round yet; 7.6 GB VRAM needs 4-bit for a 9B.
- Docker/private-round reproducibility remains a separate later track.

## C. Current output artifacts

| File | Role |
|---|---|
| `outputs/pred_phase2k3_openrouter_full.csv` | Canonical full OpenRouter run output (463 rows). |
| `outputs/pred.csv` | **Upload copy** — identical answers to the full file (see §D). |
| `outputs/run_phase2k3_openrouter_full.jsonl` | Per-sample debug trace (1.2 MB) for analysis. |

**Upload file: `outputs/pred.csv`** (content-identical to the full run). All are
git-ignored.

## D. Validation status

- `compileall -q src tests scripts` → **OK**.
- `pytest -q` → **141 passed**.
- `validate_submission.py` on `pred_phase2k3_openrouter_full.csv` → **PASS** (463 rows, full coverage, valid labels).
- `validate_submission.py` on `pred.csv` → **PASS**.
- `cmp` flagged a byte difference, but a qid-by-qid comparison shows **0 differing
  answers** across all 463 qids — the only difference is a trailing newline
  (464 vs 463 lines). The two files are functionally identical.

### Full-run log summary (`run_phase2k3_openrouter_full.jsonl`, 463 samples)

- **parse sources:** `json` **420** (90.7%), `partial_answer_key` **43** (9.3%).
- **api_calls:** 1 for **all 463**; **repairs: 0**; **empty content: 0**.
- **routes:** short_knowledge 190, calculation 159, long_context 100, ambiguous 7, law_admin 7.
- **answer distribution:** A 145, B 150, C 88, D 58, E 12, F 3, G 3, H 4 — diverse,
  **not all-A**, and correctly uses high labels (E–H) for ≥10-choice questions.
- **latency:** min 1.05s, mean 5.25s, median 2.29s, max 76.5s; **total ≈ 40.5 min**.
- **confidence:** mean 0.888; **43 low-confidence (<0.5)** — exactly the 43
  `partial_answer_key` recoveries (assigned confidence 0.0).

## E. What has been achieved

- No more all-A baseline — real, diverse predictions across A–H.
- Dynamic labels handled for **2–11 choices**; final label always valid.
- Reasoning-output blocker fixed → **0 empty responses** on the full run.
- **1 API call/sample**, **0 repairs** needed on the full set.
- Robust structured parsing: 90.7% full JSON, 9.3% safe answer-key recovery.
- Security: **no API key logged/committed**; **no `reasoning_details`/CoT logged**;
  `.env` ignored/untracked.
- Full public CSV generated manually by the user and validated.

## F. Known weaknesses / risks (honest)

- **No ground truth** — accuracy is unknown until the leaderboard score; all
  "correctness" so far means *valid, parseable, non-fallback* answers, not verified accuracy.
- **Calculation route is the largest bucket (159)** and the most error-prone for an
  LLM without tools; math correctness is unverified.
- **Long-context (100):** current evidence selection is lexical (BM25-lite); a
  reranker could improve which passage spans are kept.
- **`partial_answer_key` (43, 9.3%):** degraded successes (truncated/odd JSON) with
  confidence 0.0 — monitor; a small `max_tokens` bump or tighter evidence cap may reduce them.
- **OpenRouter provider behavior may change** (served revision, latency, cost).
- **External-API mode is Round-1 only** — not the final Docker/offline solution.
- **Embedding/rerank (BGE-m3 / Qwen-Rerank) not used yet**; self-consistency / debate not enabled.
- One sample took **76.5s** (outlier) — worth identifying if latency matters.

## G. Next accuracy roadmap (proposed; not implemented)

Ranked, correctness-first:

1. **Phase 2K.5 — Error / Leaderboard Feedback Analysis.** After upload+score:
   record it in `experiments/leaderboard_log.csv`; treat as the v1 baseline; use the
   JSONL trace + route breakdown to localize weakness (math vs long-context vs law/safety).
2. **Phase 2L.0 — In-Question Evidence Reranking.** BGE-m3 / Qwen-Rerank-style
   reranking of in-question chunks (no web retrieval) for **long-context only**;
   A/B vs the current lexical compressor.
3. **Phase 2L.1 — Calculation / PAL-lite Solver.** Deterministic math helper
   (elasticity, rates, Hess's law, expectation, derivatives) for the **calculation
   route**; emits a final label, not verbose reasoning; reduces LLM math errors.
4. **Phase 2L.2 — Selective Second-Pass Verifier.** Only for low-confidence /
   long-context / calculation; correctness-first; not always-on.
5. **Phase 2L.3 — Selective Self-Consistency.** Ambiguous/hard samples only, k≤3,
   only if the leaderboard justifies the cost.
6. **Phase 2M — Local / Docker model path.** Compliant local Qwen3.5/Gemma +
   quantization for the private/final round reproducibility.

## H. Recommendation

- **Do not change the full-run CSV until v1 is uploaded and scored.** Freeze
  `outputs/pred.csv` as the v1 submission.
- **Next action:** the user uploads the current `pred.csv`, obtains the leaderboard
  score, and records it in `experiments/leaderboard_log.csv` as the v1 baseline.
- **If improving before upload is insisted on:** the safest, correctness-first first
  step is **in-question reranking for long-context only (Phase 2L.0)** — but the v1
  leaderboard baseline should still be recorded first so every later change is
  measured against a real number.

## Git status (uncommitted)

```
?? docs/AUDIT_PHASE_2K4_SYSTEM_OVERVIEW_AND_ACCURACY_ROADMAP.md
```

Only this overview is new. No code, config, or output files were modified.
`.env`, `.venv/`, `outputs/`, and model dirs were not touched.
