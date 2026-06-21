# Audit — Phase 2L.13: First-100 Consensus Risk Audit & Generalizable Accuracy Fix Plan

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## ⚠️ The external 3-model sheet is NOT ground truth

The Gemini / ChatGPT / Claude (+ old v6) sheet is a **risk signal only**. It is
never written into the pipeline, never hardcoded as a qid→answer table, and is
**never** used to override an answer. It only helps *categorize* where we might be
wrong so we can propose *generalizable* fixes. No public-test answers were invented.

## Inputs used

- `public-test_1780368312.json` (first-100 qids, by file order)
- `outputs/pred_v6_qwen_rerank_calc_verifier.csv` + `run_v6_*.jsonl`
- `outputs/pred_v6b_qwen_rerank_calc_verifier_fast.csv` + `run_v6b_*.jsonl`
- External first-100 sheet: **NOT present in the repo / cwd** (see below).

## Deliverable: `scripts/audit_first100_consensus_risks.py`

Created and validated. It:
- aligns the external sheet (col1 Gemini, col2 ChatGPT, col3 Claude, optional col4
  old v6) to the first-100 public-test qids by row order;
- computes the external majority + agreement count;
- flags **P0** (3/3 external agree, v6b differs), **P1** (≥2/3 agree and differ from
  v6b), **P2** (otherwise);
- joins v6b trace fields (route, confidence, calc match/method/override, verifier
  triggered/applied, parsed_answer_source/error, completion_tokens, reranker
  method/cache_hit);
- assigns a `suspected_root_cause` + `recommended_general_fix` per row;
- writes the 26-column risk CSV and prints a summary (pseudo-accuracy, P0/P1 counts,
  route + root-cause distribution, v6→v6b changes).
- **Proposes no overrides.** If `--external-sheet` is absent it exits cleanly,
  writing nothing and inventing nothing.

### Validation

- `compileall`: OK. Graceful no-sheet path verified (writes nothing).
- Full logic exercised against a **synthetic scratchpad fixture** (random perturbations
  of v6b labels — a code-test fixture, NOT real model answers, never written to the
  repo): all 26 columns populate, P0/P1/P2 classification, route/root-cause grouping,
  and v6b trace joins all work. Those synthetic numbers are **not** reported here.
- `pytest -q`: **247 passed** (no regressions).

## External sheet status: RECEIVED (results below)

The external first-100 sheet is now at `scratch/first100_external_3llm.csv` (100 rows,
no header, 4 columns: Gemini, ChatGPT, Claude, old v6; `scratch/` is gitignored). The
audit was run for real:

```bash
.venv/bin/python scripts/audit_first100_consensus_risks.py \
  --public-test public-test_1780368312.json \
  --external-sheet scratch/first100_external_3llm.csv \
  --v6 outputs/pred_v6_qwen_rerank_calc_verifier.csv \
  --v6-log outputs/run_v6_qwen_rerank_calc_verifier.jsonl \
  --v6b outputs/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
  --v6b-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --output outputs/first100_consensus_risk_audit.csv
```

### Real results (first 100; external majority is a RISK SIGNAL, not truth)

- **v6 vs external majority: 76/100.  v6b vs external majority: 76/100.** (v6b changed
  exactly 1 first-100 answer, `test_0063` A→D, and held pseudo-accuracy.)
- **P0 = 16** (3/3 external agree, v6b differs).  **P1 = 8** (≥2/3 differ from v6b).
  P0/P1 total **24**.
- **Route distribution (P0/P1):** short_knowledge 11, calculation 11, long_context 2.
- **Root-cause distribution (P0/P1):** short_knowledge_needs_verifier 11,
  calculation_solver_missing_formula 10, long_context_evidence_issue 2,
  calculation_possibly_wrong 1.
- **Concrete finding (calculation_possibly_wrong):** `test_0085` — the
  `relativistic_gamma` family fired with safe_override, but the question asks for
  relativistic **momentum** `p=γm₀v`, not the γ factor. The family is **over-matching**
  on "0.6c"/relativity wording. This is a real generalizable bug to fix in 2L.14B
  (tighten the gamma trigger so it only fires when γ itself is asked).

### Output files

- `outputs/first100_consensus_risk_audit.csv` — full 100-row risk table (26 cols).
- `outputs/first100_p0p1_review_pack.md` / `.csv` — P0/P1 human-review pack (Phase 2L.14A).

## What we CAN report now (no external sheet needed)

**v6 → v6b answer changes (real):** 12 of 463 changed; **only 1 is in the first 100**
(`test_0063`) — consistent with "v6b preserved first-100 pseudo-accuracy." The 12
changed answers break down by route as **8 calculation, 3 short_knowledge, 1
long_context**, and **all 12 now parse as clean JSON** in v6b. This indicates the
Phase-2L.12 schema/prompt tightening recovered answers that were previously
malformed (`no_json`/`partial_answer_key`) — a correctness-neutral-to-positive change
in output discipline, not a behavior regression.

(Recall from 2L.12: v6 had 58/463 malformed-JSON rows; tightening the schema should
shrink that. A v6b malformed-rate check is the first thing to read off `run_v6b`.)

## Root-cause categories the audit assigns (for P0/P1 rows)

| category | generalizable fix (no hardcoding) |
|---|---|
| `calculation_possibly_wrong` | re-check the named calc family's extraction/formula; add a synthetic regression test |
| `calculation_solver_missing_formula` | add a new generic formula family (see CALCULATION_TAXONOMY.md) |
| `short_knowledge_needs_verifier` | extend selective verifier triggers to low-confidence short_knowledge; else model-knowledge gap (no safe deterministic fix) |
| `ambiguous_needs_verifier` / `law_admin_needs_verifier` | enable/loosen the selective MCQ verifier for that route |
| `long_context_evidence_issue` | tune reranker (`candidate_top_k`/`top_k`/method); confirm the answer-bearing chunk is selected |
| `prompt_schema_issue` | tighten prompt/max-tokens; confirm the v6b enum schema took effect |
| `route_or_model_knowledge` | review routing; may be an inherent model-knowledge limit (no safe override) |

## P0 / P1 lists (real; from the external sheet — RISK SIGNAL only)

**P0 (3/3 external agree, v6b differs) — 16:**
test_0019 (D, SK), test_0038 (B, calc), test_0042 (A, calc), test_0047 (A, long_ctx),
test_0054 (G, calc), test_0063 (B, calc), test_0065 (D, SK), test_0066 (B, SK),
test_0074 (B, SK), test_0077 (A, calc), test_0079 (B, SK), test_0082 (D, calc),
test_0085 (C, calc/relativistic_gamma), test_0086 (C, SK), test_0096 (A, calc),
test_0099 (B, calc).

**P1 (≥2/3 external differ from v6b) — 8:**
test_0010 (D, SK), test_0022 (D, SK), test_0043 (E, calc), test_0045 (B, long_ctx),
test_0068 (B, SK), test_0070 (C, SK), test_0080 (A, SK), test_0093 (A, calc).

(Format: qid (external majority, route). These are review targets, **not** answers to
hardcode. Full per-qid detail is in `outputs/first100_p0p1_review_pack.md`.)

## Recommended next implementation phases (priority order)

1. **Read v6b malformed-JSON rate** (`scripts/analyze_v6_runtime.py --log run_v6b_*`)
   to confirm the 2L.12 schema fix cut the 58 no_json cases; if any remain, tighten
   the prompt further (this is the cheapest, fully-generalizable accuracy lever).
2. **Run this audit against the real sheet** → triage P0/P1 by `suspected_root_cause`.
3. **Calculation** (largest changed bucket): for `calculation_possibly_wrong` P0/P1,
   add synthetic regression tests reproducing the *pattern* (not the qid) and fix the
   family; for `calculation_solver_missing_formula`, add a generic family.
4. **Verifier coverage**: if P0/P1 cluster in short_knowledge/ambiguous/law_admin,
   widen the selective verifier triggers (config-only, A/B first).
5. **Long-context**: if P0/P1 cluster there, sweep `candidate_top_k`/`top_k` with the
   chunk-comparison script before any full run.
6. Re-run a controlled **v7** into NEW files and A/B vs v6b — no leaderboard claim
   without validation.

## Confirmations

- No OpenRouter API call made; no full inference run.
- The external sheet `scratch/first100_external_3llm.csv` was **received and used for
  DIAGNOSTICS ONLY** (risk categorization) — never as ground truth, never written into
  the pipeline, never used as a qid→answer table.
- **No prediction CSV was modified.** Only diagnostic files were created under
  `outputs/` (`first100_consensus_risk_audit.csv`, `first100_p0p1_review_pack.{md,csv}`),
  all of which are gitignored.
- `outputs/pred.csv` and v1/v2/v6/v6b untouched.
- No leaderboard upload.
- `.env` not read; no API key printed/exposed.
- **No qid hardcoding; no public-test answer table added to pipeline code.**
- **The external 3-model sheet is not used as ground truth anywhere in the pipeline**
  — it is consumed only by the diagnostic script, for risk categorization.
- `compileall` OK; `pytest -q` **247 passed**.

## git status

```
?? docs/AUDIT_PHASE_2L11A_OUTPUTS_CLEANUP.md
?? docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md
?? scripts/audit_first100_consensus_risks.py
```

(2L.11A audit doc remains from a prior uncommitted phase.)

Do not commit. All changes left uncommitted for user review.
