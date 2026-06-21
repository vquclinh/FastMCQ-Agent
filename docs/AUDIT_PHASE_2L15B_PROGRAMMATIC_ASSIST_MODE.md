# Audit — Phase 2L.15B: Programmatic Assist Mode (Calculation Branch)

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Built an offline, deterministic **calculation assist** that patches the frozen v6b
predictions with only safe calculation overrides — **no OpenRouter, no inference**.
The result is a new prediction file `pred_v7_programmatic_assist_from_v6b.csv` that
differs from v6b on exactly **2** samples, both deterministic-correct and both in
agreement with the external 3/3 diagnostic majority.

## Files changed

**New**
- `scripts/apply_programmatic_assist_to_predictions.py` — patch v6b → v7 (calc-only,
  safe-override-only); writes pred CSV + run JSONL + diff CSV; refuses to write
  protected files.
- `scripts/compare_v7_programmatic_assist_pseudo.py` — read-only v6b/v7 vs external
  majority diagnostic.
- `docs/AUDIT_PHASE_2L15B_PROGRAMMATIC_ASSIST_MODE.md` (this file).

**Modified**
- `tests/test_adaptive_orchestrator.py` — +6 assist-mode tests.
- `docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md` — removed stale "pending"
  wording (sheet received; diagnostics only; predictions untouched).
- `docs/AUDIT_PHASE_2L14B_CALCULATION_FORMULA_EXPANSION.md` and
  `docs/CALCULATION_TAXONOMY.md` — **corrected a sheet-read bug** (see below).

No solver/orchestrator code changes were needed: `AdaptiveOrchestrator` already
supports `assist` mode (calc-branch override gated by `calculation_allow_override`),
verified by tests. The default config stays OFF / `trace_only`.

## Exact commands run

```bash
.venv/bin/python scripts/apply_programmatic_assist_to_predictions.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
  --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
  --output outputs/pred_v7_programmatic_assist_from_v6b.csv \
  --log-path outputs/run_v7_programmatic_assist_from_v6b.jsonl \
  --diff outputs/programmatic_assist_diff.csv

.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json \
  --submission outputs/pred_v7_programmatic_assist_from_v6b.csv

.venv/bin/python scripts/compare_v7_programmatic_assist_pseudo.py \
  --public-test public-test_1780368312.json \
  --external-sheet scratch/first100_external_3llm.csv \
  --v6b outputs/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
  --v7 outputs/pred_v7_programmatic_assist_from_v6b.csv
```

## Validation result

- `validate_submission.py` on `pred_v7_...csv`: **PASS** (463 rows).
- `compileall -q src scripts tests`: OK.
- `pytest -q`: **277 passed** (was 271; +6).

## Answers changed vs v6b: 2

From `outputs/programmatic_assist_diff.csv`:

| qid | route | method | old (v6b) | new (v7) | reason |
|---|---|---|---|---|---|
| test_0085 | calculation | `relativistic_momentum` | B | **C** | `p=γβ·m₀c=0.75·m₀c` (safe deterministic override) |
| test_0099 | calculation | `operating_margin_asset_turnover` | A | **B** | margin `(400k−150k)/800k=31.25%`, turnover `0.40` (safe override) |

All other 461 answers kept from v6b. No `short_knowledge` / `long_context` /
`law_admin` / `ambiguous` answer was touched.

## First-100 diagnostic pseudo-comparison (external majority = risk signal, NOT truth)

`compare_v7_programmatic_assist_pseudo.py`:

```
first-100 v6b vs external majority : 76/100 (76.0%)
first-100 v7  vs external majority : 78/100 (78.0%)
P0 remaining (3/3 differ from v7) : 14   (was 16)
P1 remaining                      : 8
changed rows:
  test_0085: ext_majority=C(3/3)  v6b=B -> v7=C  [toward_majority]
  test_0099: ext_majority=B(3/3)  v6b=A -> v7=B  [toward_majority]
```

Both deterministic overrides move **toward** the external 3/3 majority and improve
the diagnostic pseudo-score (76→78), dropping P0 from 16 to 14. This is consistent
with the answers also being mathematically/physically correct.

### Correction to the 2L.14B audit (sheet-read bug)

An earlier ad-hoc, **line-by-line** read of `scratch/first100_external_3llm.csv` in
the 2L.14B audit mis-reported the external majority for these two qids as `A`
(claiming the LLMs erred). Root cause: the sheet has 100 CSV **records** but 101
physical lines — record 80's GPT cell is `'C\n'` (embedded newline), so line-index
drifts from record-index after row 80. The authoritative `csv.reader` alignment
(used by `audit_first100_consensus_risks.py` and the pseudo script) gives **C**
(test_0085) and **B** (test_0099) — agreeing with the deterministic answers. The
2L.14B audit and `CALCULATION_TAXONOMY.md` have been corrected.

## Safety checks

- Overrides applied **only** when `selected_branch == "calculation"` AND
  `would_override` (assist + `calculation_allow_override`) AND the candidate is a
  `safe_to_override` family whose answer is a valid label AND differs from v6b.
- `trace_only` mode still never overrides (test asserts `would_override == 0`).
- Patch script refuses to write protected files (`pred.csv`, v2, v6, v6b).
- Tests: assist changes only the calculation branch; no override when calc agrees or
  no family matches; gamma/momentum eligibility disjoint; patch script has no
  network/API/`.env`/qid-hardcoding and does not read the external sheet.

## Confirmations

- No OpenRouter API call made; no full inference run.
- No qid hardcoding; no public-test answer table; the patch script does not read the
  external sheet.
- External Gemini/GPT/Claude sheet used for **diagnostics only**, never as ground
  truth, never inside solver/patch code.
- `outputs/pred.csv` and v1/v2/v6/v6b prediction/log files **untouched** (v6b mtime
  unchanged; patch writes only new v7 + diff files; protected-file guard in code).
- No leaderboard upload; `.env` not read; no API key exposed; model files untouched.

## Remaining risks

- Only 2 of 463 answers change; net leaderboard effect is small and unverified
  (the leaderboard is the only ground truth).
- The deterministic families remain pattern-specific; questions with unusual phrasing
  decline (safe) rather than override.
- v7 was produced by **patching v6b offline**, not by a fresh graph run; a future
  in-graph assist mode (gated) should reproduce the same overrides.

## Recommended next step

- v7 preserves/improves diagnostic quality and is deterministically correct on the 2
  changed rows → it is a reasonable **leaderboard submission candidate**
  (`outputs/pred_v7_programmatic_assist_from_v6b.csv`), at the user's discretion.
- Then **Phase 2L.15C — Short-Knowledge Selective Verifier** (the 11 short_knowledge
  P0/P1 cluster), acting on the `verifier_recommended` trace flag.

## git status

```
 M .gitignore
 M docs/AUDIT_PHASE_2L13_FIRST100_CONSENSUS_RISK_AUDIT.md
 M docs/AUDIT_PHASE_2L14B_CALCULATION_FORMULA_EXPANSION.md
 M docs/CALCULATION_TAXONOMY.md
 M run.py
 M src/calculation_solver.py
 M src/openrouter_graph_solver.py
 M tests/test_adaptive_orchestrator.py
 M tests/test_calculation_solver.py
?? configs/adaptive_reasoning.yaml
?? docs/ADAPTIVE_REASONING_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2L14A_P0P1_REVIEW_PACK.md
?? docs/AUDIT_PHASE_2L15A_ADAPTIVE_REASONING_ORCHESTRATOR.md
?? docs/AUDIT_PHASE_2L15B_PROGRAMMATIC_ASSIST_MODE.md
?? scripts/apply_programmatic_assist_to_predictions.py
?? scripts/audit_adaptive_orchestrator_trace.py
?? scripts/audit_calculation_solver_on_public.py
?? scripts/audit_first100_consensus_risks.py
?? scripts/compare_v7_programmatic_assist_pseudo.py
?? scripts/export_risk_review_pack.py
?? src/adaptive_orchestrator.py … (2L.15A modules)
```
(`outputs/*` v7 + diagnostics and `scratch/*` are gitignored; tracked changes are
code/docs only.)

Do not commit. All changes left uncommitted for user review.
