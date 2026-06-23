# Audit — Phase 2L.16: Complete Adaptive Branch Calibration Suite

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Completed proposal/calibration tooling for **all five** adaptive branches
(short_knowledge, long_context, law_admin, ambiguous, self-consistency) plus a
unified analyzer. Everything is **proposal/calibration-first**: every runner is
**dry-run by default**, calls OpenRouter only under explicit `--execute`, and patches
an answer only under explicit `--allow-override` AND a single shared, unit-tested
override gate. **No API call was made; no prediction changed; no v8 created. v7
remains the current best candidate.**

## Files changed

**New (src)**
- `src/adaptive_proposal_common.py` — shared IO + protected-file guard + the single
  `override_gate` used by all branch runners.
- `src/evidence_sufficiency.py` — deterministic no-API long_context sufficiency.

**New (scripts)**
- `scripts/audit_long_context_evidence_sufficiency.py`
- `scripts/audit_law_admin_verifier_candidates.py`, `scripts/run_law_admin_verifier_sample.py`
- `scripts/audit_ambiguous_adjudicator_candidates.py`, `scripts/run_ambiguous_adjudicator_sample.py`
- `scripts/audit_self_consistency_candidates.py`, `scripts/run_selective_self_consistency_sample.py`
- `scripts/analyze_adaptive_branch_proposals.py`

**New (tests/docs)**
- `tests/test_adaptive_branch_calibration.py`; this audit.

**Modified**
- `configs/adaptive_reasoning.yaml` — added `law_admin_verifier`,
  `ambiguous_adjudicator`, `selective_self_consistency`, and `long_context_evidence_check`
  blocks (all OFF / proposal-only).
- `docs/ADAPTIVE_REASONING_ARCHITECTURE.md` — designs for the four new branches,
  proposal-first rationale, and v7-stays-best note.

Part A (short_knowledge proposal runner) reviewed: already logs the full required
field set (qid, route, priority, current_answer, verifier_selected, should_override,
verifier_confidence, evidence_type, reason, would_change_answer, override_applied,
trigger_reasons, original_confidence); dry-run default; `--allow-override` required;
`--risk-csv`/`--prioritize-risk` ordering-only. No changes needed.

## Branch completion status

| Branch | candidate audit | dry-run runner | override gate | status |
|---|---|---|---|---|
| short_knowledge | ✓ (2L.15C) | ✓ (2L.15C-B) | shared | complete |
| long_context | ✓ sufficiency audit | n/a (diagnostic, no answer change) | n/a | complete |
| law_admin | ✓ | ✓ | shared | complete |
| ambiguous | ✓ | ✓ | shared | complete |
| self_consistency | ✓ | ✓ (proposal-only, no override this phase) | n/a | complete |
| unified analyzer | — | — | reports gate pass/reject | complete |

## No-API audit commands & results

```
long_context evidence sufficiency : 100 long_context — 87 sufficient, 13 weak
   (recommendation: keep current 87 / reranker top_k sweep 13); weak ∩ first-100 P0/P1 = 0
law_admin candidates              : 7/7 eligible (source_grounding_recommended; 2 low_confidence)
ambiguous candidates              : 7/7 eligible (needs_adjudication); answers {E:2,A:2,B:2,D:1}
self_consistency candidates       : 149 (SK 121, long_context 14, ambiguous 7, law_admin 7);
                                    recommended max-calls 40
unified analyzer (candidates only): all candidate/audit files FOUND; 0 proposals present
                                    -> RECOMMENDATION: "no v8 yet — run proposal batches first"
```
All dry-run runners (law_admin, ambiguous, self-consistency) confirmed **no API call,
no answer changed**.

## Candidate counts by branch

- short_knowledge verifier-eligible: **121 / 190** (captures 11/11 first-100 SK P0/P1).
- long_context weak/insufficient evidence: **13 / 100**.
- law_admin eligible: **7 / 7**.
- ambiguous eligible: **7 / 7**.
- self-consistency aggregated candidates: **149**.

## Validation results

- `compileall -q src scripts tests`: OK
- `pytest -q`: **304 passed** (was 293; +11).
- Tests cover: evidence sufficiency statuses + never-returns-answer + missing-evidence;
  override gate requires `allow_override` and blocks uncertain/low-conf/same/empty-reason;
  candidate audits run with no API; dry-run runners run with no API; unified analyzer
  handles missing files; source safety (no qid hardcoding, no external sheet read, no
  network/eval, OpenRouter client imported lazily under the execute path only).

## Confirmations

- **No API call made** in this phase (all dry-run / no-API audits; clients imported
  lazily only under `--execute`, which was not passed).
- **No prediction changed; no v8 created.** `pred.csv` and v1/v2/v6/v6b/v7 untouched
  (v6b/v7 mtimes unchanged); all runners refuse to write protected files.
- `allow_override` OFF by default everywhere; self-consistency has no override path.
- No qid hardcoding; no public-test answer table.
- External Gemini/GPT/Claude sheet is **diagnostic only** — used for
  prioritization/overlap/reporting, never read by branch logic, never ground truth,
  never selects an answer.
- No leaderboard upload; `.env` not read; no API key exposed; only competition models.

## Recommended user-run proposal commands (calls API; NO patching — user-initiated)

```bash
# short_knowledge (25, prioritized)
.venv/bin/python scripts/run_short_knowledge_verifier_sample.py \
  --input public-test_1780368312.json --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --risk-csv outputs/first100_consensus_risk_audit.csv --prioritize-risk \
  --max-calls 25 --execute \
  --output-jsonl outputs/short_knowledge_verifier_proposals_25.jsonl \
  --output-csv outputs/short_knowledge_verifier_proposals_25.csv

# law_admin (7)
.venv/bin/python scripts/run_law_admin_verifier_sample.py \
  --input public-test_1780368312.json --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --max-calls 7 --execute \
  --output-jsonl outputs/law_admin_verifier_proposals_7.jsonl \
  --output-csv outputs/law_admin_verifier_proposals_7.csv

# ambiguous (7)
.venv/bin/python scripts/run_ambiguous_adjudicator_sample.py \
  --input public-test_1780368312.json --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --max-calls 7 --execute \
  --output-jsonl outputs/ambiguous_adjudicator_proposals_7.jsonl \
  --output-csv outputs/ambiguous_adjudicator_proposals_7.csv

# selective self-consistency (e.g. 25)
.venv/bin/python scripts/run_selective_self_consistency_sample.py \
  --input public-test_1780368312.json --candidates outputs/self_consistency_candidates.csv \
  --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --n-samples 3 --temperature 0.2 --max-calls 25 --execute \
  --output-jsonl outputs/selective_self_consistency_proposals_25.jsonl \
  --output-csv outputs/selective_self_consistency_proposals_25.csv

# then the unified analyzer over whatever proposals exist
.venv/bin/python scripts/analyze_adaptive_branch_proposals.py \
  --risk-csv outputs/first100_consensus_risk_audit.csv \
  --long-context-audit outputs/long_context_evidence_sufficiency_audit.csv \
  --sk-proposals outputs/short_knowledge_verifier_proposals_25.csv \
  --law-admin-proposals outputs/law_admin_verifier_proposals_7.csv \
  --ambiguous-proposals outputs/ambiguous_adjudicator_proposals_7.csv \
  --self-consistency-proposals outputs/selective_self_consistency_proposals_25.csv
```
(None include `--allow-override`, so they produce proposals only — predictions stay
untouched.)

## git status (this phase's additions)

```
?? src/adaptive_proposal_common.py
?? src/evidence_sufficiency.py
?? scripts/audit_long_context_evidence_sufficiency.py
?? scripts/audit_law_admin_verifier_candidates.py
?? scripts/run_law_admin_verifier_sample.py
?? scripts/audit_ambiguous_adjudicator_candidates.py
?? scripts/run_ambiguous_adjudicator_sample.py
?? scripts/audit_self_consistency_candidates.py
?? scripts/run_selective_self_consistency_sample.py
?? scripts/analyze_adaptive_branch_proposals.py
?? tests/test_adaptive_branch_calibration.py
?? docs/AUDIT_PHASE_2L16_ADAPTIVE_BRANCH_COMPLETION.md
 M configs/adaptive_reasoning.yaml
 M docs/ADAPTIVE_REASONING_ARCHITECTURE.md
```
(Plus still-uncommitted files from 2L.13–2L.15C-B. `outputs/*` and `scratch/*` are
gitignored.)

## Next decision point

1. **Submit v7 now** (`outputs/pred_v7_programmatic_assist_from_v6b.csv`) — validated,
   deterministically correct on its 2 changes; or
2. **Run proposal batches** (commands above, no `--allow-override`) and review with the
   unified analyzer; or
3. **Build v8 only after** proposal quality review — into a NEW file, gated overrides,
   A/B vs v7, no leaderboard claim without validation.

Do not commit. All changes left uncommitted for user review.
