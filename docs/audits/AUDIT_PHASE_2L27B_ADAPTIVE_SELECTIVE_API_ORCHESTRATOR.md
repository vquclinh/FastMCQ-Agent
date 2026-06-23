# Audit — Phase 2L.27B: Adaptive Selective API Orchestrator + Pairwise Judge Fix

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Fixed the selective runner so the **pairwise judge actually runs** when requested, added
an **adaptive budget-aware selective API runner** driven by the overall accuracy plan,
hardened the **API prompt quality** to reduce placeholder evidence, and added **parser
rejection** of placeholder/numeric-mismatch candidates. Everything is **code-only**:
**no API call, no inference, nothing written under `outputs/`** — all artifacts live under
`scratch/adaptive_selective_2l27b/`.

## No-output rule confirmation

`outputs/` still contains only `pred.csv`, `pred_v10_full_production_user_run.csv`,
`pred_v8_clean_generalized_from_v7.csv`. This phase wrote zero files to `outputs/`; both
runners and the new audit script hard-refuse any non-`scratch/` output dir (tested). v10
(public 77.75) remains the locked submission.

## Part A — Pairwise judge fix (`scripts/run_selective_multicandidate_api.py`)

The 2L.27A behavior audit found the judge **never ran** (`judge_ran=False`). Root cause:
the runner never collected per-qid candidates nor invoked the judge. Fix:

- Per-qid loop now accumulates `qid_candidates` (only `parse_status=="ok"` records).
- The judge runs when `--judge pairwise` **AND** a valid candidate conflicts with v10.
- Skips are recorded with a reason (`no alternative candidate conflicts with v10`,
  `budget reached before judge`) in `judge_skip_reasons`.
- Summary now reports `judge_ran`, `judge_skipped`, `judge_skip_reasons`.

## Part B — Adaptive runner (`scripts/run_adaptive_selective_api.py`, NEW)

Dry-run by default; `--dry-run`/`--execute` mutually exclusive; model policy asserted at
startup; `scratch/`-only. Reads the overall accuracy plan and schedules per `--mode`:

- `_MODE_LAYERS` = `cheap:{cheap_api}`, `balanced:{cheap_api,rich_api}`,
  `rich:{cheap_api,rich_api,evidence_pack}`.
- `_agents_temps_for`: cheap = challenger+option_elimination @0; rich = all 4 agents
  @0,0.2; evidence_pack = route_specialist+challenger @0 (and only if the offline
  evidence pack is weak).
- `tool_only` questions are never sent to the API.
- Judge runs only on genuine disagreement; budget guard stops before exceeding
  `--budget-usd`; crash-safe JSONL append + `--resume`.

## Part C — Prompt quality + parser rejection (`src/api_candidate_agents.py`)

- `_QUALITY` contract forbids placeholder evidence and requires a concrete
  quote/calculation plus why other options are weaker; `_ROUTE_EVIDENCE_REQ` adds
  per-route evidence requirements.
- `parse_candidate` now rejects low/medium-risk replies with placeholder evidence
  (`parse_status="placeholder_evidence"`) and replies whose numeric result is absent from
  the chosen option (`parse_status="numeric_mismatch"`). Self-declared high-risk replies
  pass through (already weak; won't override).

## Part D — Candidate quality audit (`scripts/audit_candidate_quality.py`, NEW)

Read-only; no API. Over the existing 163 records:
`total=163`, agents `route_specialist 41 / challenger 41 / option_elimination 41 /
tool_hint 40`, `judge=0` (pre-fix data), `parse_fail=8`, `placeholder=47`,
`rejected=38`, `eligible=117`, `useful≈3`. Writes
`candidate_quality_audit.{md,csv}` under `scratch/adaptive_selective_2l27b/`.

## Part E — build_v11 compatibility

`scripts/build_v11_from_api_candidates.py` already loads any candidate JSONL path
(`_load_api_candidates` is filename-agnostic), so it ingests both `api_candidates.jsonl`
and `adaptive_api_candidates.jsonl`. Help text updated to say so. Re-ran over 463
questions: **1 proposed override**, `outputs/` untouched.

## Part F — Validations

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **487 passed** (was 476; +11 in `tests/test_judge_and_adaptive.py`).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- New tests: parser placeholder/numeric-mismatch/valid; judge runs on conflict; judge
  skipped (with reason) when no alternative; dry-run upper-bound == fake-execute call
  count; judge rejects disallowed model; adaptive dry-run no API; adaptive cheap < rich
  calls; adaptive refuses `outputs/` + mutual-exclusive flags; adaptive rejects
  disallowed model.

## Part G — Dry-runs (no API)

```
run_adaptive_selective_api.py ... --max-qids 40 --mode cheap     --budget-usd 0.50 --dry-run
  -> scheduled 18  layers=['cheap_api']           upper-bound 54  est. $0.11  budget=0.5
run_adaptive_selective_api.py ... --max-qids 40 --mode balanced  --budget-usd 1.00 --dry-run
  -> scheduled 18  layers=['cheap_api','rich_api'] upper-bound 54  est. $0.11  budget=1.0
```

(Within the first 40 plan rows all API-eligible questions are `cheap_api`, so cheap and
balanced schedule the same 18; `rich_api`/`evidence_pack` differences appear over the full
plan.)

## Confirmations

- **No OpenRouter/API call**; no inference run.
- **No files written under `outputs/`**; `pred.csv` and v10 untouched. All artifacts under
  `scratch/adaptive_selective_2l27b/`.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth.
- All LLM/rerank paths obey `src/model_policy.py` (policy audit PASS); no disallowed model.
- Nothing committed.

## Recommended next phase

The judge now runs and the parser rejects ~28% of weak candidates before ranking. A
human-initiated `--execute` run (cheap mode, small `--budget-usd`, `--resume`) over the
hardest plan rows can now produce cleaner candidates; feed them through the
consistency-guarded ranker and build a v11 A/B candidate (NEW file) only for review. v10
(77.75) remains the submission until a result is accepted. Do not commit until then.
