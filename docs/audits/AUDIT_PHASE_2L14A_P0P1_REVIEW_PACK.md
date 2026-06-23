# Audit — Phase 2L.14A: P0/P1 Risk Review Pack Export

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## ⚠️ External 3-model sheet is NOT ground truth

The Gemini / ChatGPT / Claude majority is a **risk signal only**. This pack is for
**human review**; it proposes **no answer overrides**, contains **no qid→answer
table**, and the sheet is never used in pipeline code.

## Input files

- `public-test_1780368312.json` (questions + choices)
- `outputs/first100_consensus_risk_audit.csv` (Phase 2L.13B, real run)
- `outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl` (v6b trace)
- `scratch/first100_external_3llm.csv` (external sheet, gitignored; consumed only by
  the 2L.13B audit script, not by the pack exporter directly)

## Output files

- `outputs/first100_p0p1_review_pack.md` — per-qid review cards (priority, external
  vs ours, calc/verifier/parse/reranker trace, full question, all labeled choices,
  compressed evidence for long_context, suspected root cause + general fix).
- `outputs/first100_p0p1_review_pack.csv` — same data, one row per P0/P1 qid.

## P0/P1 counts

- **P0 = 16** (3/3 external agree, v6b differs)
- **P1 = 8** (≥2/3 external differ from v6b)
- **total = 24**

## Route distribution (P0/P1)

| route | count |
|---|---|
| short_knowledge | 11 |
| calculation | 11 |
| long_context | 2 |

## Root-cause distribution (P0/P1)

| suspected root cause | count |
|---|---|
| short_knowledge_needs_verifier | 11 |
| calculation_solver_missing_formula | 10 |
| long_context_evidence_issue | 2 |
| calculation_possibly_wrong | 1 |

### Notable concrete finding

`test_0085` (P0, calculation): the `relativistic_gamma` family fired with
`safe_override=True`, but the question asks for relativistic **momentum**
(`p = γ·m₀·v`), not the γ factor. The family **over-matches** on "0.6c"/relativity
wording — a generalizable bug (tighten the trigger to only fire when γ itself is the
requested quantity). This is the single `calculation_possibly_wrong` case and a prime
2L.14B target.

## Confirmations

- External 3-model sheet is **not ground truth** and is **not** used in pipeline code.
- **No answer overrides** implemented or recommended (review pack only).
- No OpenRouter API call made; no full inference run.
- Predictions untouched (`pred.csv`, v1/v2/v6/v6b unchanged); only new diagnostic
  files written under `outputs/`.
- No leaderboard upload; `.env` not read; no API key exposed.
- No qid→answer hardcoding anywhere.
- `compileall` OK; `pytest -q` **247 passed**.

## Next recommended implementation phases

- **2L.14B — Calculation Formula Expansion** (11 calculation P0/P1). Fix the
  `relativistic_gamma` over-match (test_0085) and add generic families for the
  `calculation_solver_missing_formula` cases (10), each with pattern-based synthetic
  regression tests — never qid hardcoding. Keep the conservative
  override-only-when-safe policy.
- **2L.14C — Short-Knowledge Selective Verification** (11 short_knowledge P0/P1).
  Extend the selective MCQ verifier to trigger on low-confidence short_knowledge
  answers (config-first, A/B before adoption). Where it's a pure model-knowledge gap,
  accept there is no safe deterministic fix.
- **2L.14D (optional, later) — Long-Context Evidence Tuning** (2 long_context P0/P1).
  Sweep `candidate_top_k`/`top_k`/method with the chunk-comparison script; confirm the
  answer-bearing chunk is selected before any full run.

After fixes: a controlled **v7** run into NEW files, re-run this consensus audit, and
A/B vs v6b — no leaderboard claim without validation.

## git status

```
 M .gitignore                                              # user added `scratch/*` (ignores the external sheet)
?? docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md  # updated with real results (still untracked from 2L.13)
?? docs/AUDIT_PHASE_2L14A_P0P1_REVIEW_PACK.md
?? scripts/audit_first100_consensus_risks.py              # P2 root-cause update (still untracked from 2L.13)
?? scripts/export_risk_review_pack.py
```

`outputs/*` (the risk CSV and review pack) and `scratch/*` (the external sheet) are
gitignored, so they do not appear in `git status`. The `.gitignore` modification was
made by the user (to ignore `scratch/`); left as-is.

Do not commit. All changes left uncommitted for user review.
