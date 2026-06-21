# Audit — Phase 2L.15C-B: Short-Knowledge Verifier Proposal Calibration

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added **proposal-only** calibration for the short_knowledge verifier: it can call
OpenRouter (only when the user explicitly passes `--execute`) to gather verifier
*proposals*, but it **never patches a prediction** unless `--allow-override` is also
set. A new analyzer summarizes proposal quality. **No API call was made in this
phase; no prediction was changed; no v8 was created.**

## Files changed

**Modified**
- `scripts/run_short_knowledge_verifier_sample.py` — proposal-only logging
  (`verifier_selected`, `should_override`, `verifier_confidence`, `evidence_type`,
  `reason`, `would_change_answer`, `override_applied`, `trigger_reasons`, `route`,
  `original_confidence`, `priority`); `--risk-csv` + `--prioritize-risk` (ordering
  only); `override_applied` is always False unless `--allow-override` AND the gate
  passes.

**New**
- `scripts/analyze_short_knowledge_verifier_proposals.py` — read-only proposal
  summary (change/keep counts, confidence + evidence_type distributions, toward/away
  vs the first-100 external majority for diagnostics).
- `tests/test_sk_verifier_proposal.py` — gate + analyzer + source-safety tests.
- `docs/AUDIT_PHASE_2L15C_B_VERIFIER_PROPOSAL_CALIBRATION.md` (this file).

## What proposal-only mode does

- `--execute` (user-only): the verifier may call OpenRouter and the proposal fields
  are logged per candidate.
- Without `--allow-override`: **no answer is patched** — `override_applied` is forced
  False for every row; the run is purely a proposal/diagnostic artifact.
- `--prioritize-risk --risk-csv <first100 risk CSV>`: orders candidates **P0/P1
  first, then lowest confidence, then most trigger flags** — used for *ordering and
  reporting only*, never to select an answer (no qid drives a decision).

## Why override is not enabled yet

The verifier's reliability on short_knowledge is unmeasured. We must first inspect a
real proposal batch (change-rate, confidence, evidence_type, and how proposals relate
to the diagnostic external majority) before trusting it to patch answers. Enabling
overrides prematurely risks regressing v7. The override gate is intentionally strict
(`should_override` ∧ valid ∧ ≠current ∧ `confidence≥0.90` ∧ non-empty reason ∧
`evidence_type≠uncertain` ∧ `allow_override`) and is unit-tested.

## Validation results

- `compileall -q src scripts tests`: OK
- `pytest -q`: **293 passed** (was 284; +9).
- Dry-run (default, no API) with `--prioritize-risk --max-calls 25`: 121 eligible,
  25 planned, **P0 rows ordered first** by ascending confidence, `override_applied`
  False, no API call.
- Analyzer verified on the dry-run CSV and with a **missing** risk CSV (graceful).

Key gate tests: a *perfect* override proposal is **not** applied when
`allow_override=False`; and is rejected for `uncertain` evidence, confidence < 0.90,
same-as-current answer, empty reason, or `should_override=false`.

## Recommended user-initiated command (calls API; does NOT patch predictions)

```bash
.venv/bin/python scripts/run_short_knowledge_verifier_sample.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --risk-csv outputs/first100_consensus_risk_audit.csv \
  --prioritize-risk \
  --max-calls 25 \
  --execute \
  --output-jsonl outputs/short_knowledge_verifier_proposals_25.jsonl \
  --output-csv outputs/short_knowledge_verifier_proposals_25.csv
# (NO --allow-override -> proposals only, predictions untouched)

.venv/bin/python scripts/analyze_short_knowledge_verifier_proposals.py \
  --proposals outputs/short_knowledge_verifier_proposals_25.csv \
  --risk-csv outputs/first100_consensus_risk_audit.csv
```

Review the analyzer output (change-rate, confidence/evidence mix, toward/away vs the
diagnostic majority). Only if proposals look reliable should a future phase consider
a **gated** override run into a NEW v8 file, A/B'd vs v7 — no leaderboard claim
without validation.

## Confirmations

- **No prediction file changed** (no v8 created); `pred.csv`, v1/v2/v6/v6b/v7
  untouched; protected-file guard in the runner.
- **No API call made in this phase** (default dry-run; client imported lazily only
  under `--execute`, which was not passed).
- No qid hardcoding; no public-test answer table.
- External Gemini/GPT/Claude sheet is **diagnostic only** — used for candidate
  prioritization/reporting, never as ground truth and never to select an answer.
- `allow_override` is OFF by default; the override gate is strict and unit-tested.
- No leaderboard upload; `.env` not read; no API key exposed.

## git status (new/changed this phase)

```
 M scripts/run_short_knowledge_verifier_sample.py
?? scripts/analyze_short_knowledge_verifier_proposals.py
?? tests/test_sk_verifier_proposal.py
?? docs/AUDIT_PHASE_2L15C_B_VERIFIER_PROPOSAL_CALIBRATION.md
```
(Plus the still-uncommitted 2L.13–2L.15C files; `outputs/*` and `scratch/*` are
gitignored.)

Do not commit. All changes left uncommitted for user review.
