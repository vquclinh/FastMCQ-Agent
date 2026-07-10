# AUDIT 75 — Independent Review of the Phase 2 Shadow-Router Corrective Pass

Audit number 75 (no prior `75-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD

- Date: 2026-07-10
- Branch: `main`
- HEAD: `d9e5b0a8acdda204ab513b76137a90dbeea8f7f1` ("fix choice scoring with one-forward bare-label
  logits")
- Read-only independent review. Only this audit file was created. No production code, test, config,
  or AUDIT 71–74 modified; the working-tree changes were left as found.

## 2. Initial working-tree state

3 modified (`configs/confidence_selective.yaml`, `predict.py`, `src/local_model/confidence_config.py`)
+ 6 untracked (`src/local_model/confidence_shadow_router.py`, two `…shadow_router…` test files,
audits 71/72/73/74). `git diff --check` clean; `git diff --stat` = 204/52 across the same 3 files as
Phase 2 (unchanged by the corrective pass). Matches AUDIT 74; no unrelated changes; nothing staged.

## 3. Independence / read-only statement

Findings come from reading the corrected router source, the tests, and the diffs; probing the router
with fake inputs (duplicate qid, duplicate input_index, both duplicated, double-duplicate sweep
tracing); reconstructing the OLD qid-keyed logic to confirm the new tests are genuine regressions;
verifying predict.py's input_index assignment; and running the full test battery. No model/torch is
available in this Linux env (router is pure and fully fake-testable). Temporary probes created no
files.

## 4. Files / call sites reviewed

`confidence_shadow_router.py` (full), the tests, the yaml/predict/config diffs; repo-wide `git grep`
for `run_shadow_router`, `ShadowRouting*`, `ShadowRouterConfig`, `selected_qids`, `selected_items`,
`selected_input_indexes`, `selected_rank`, `candidate_reasons`, `reasons_by_ord`, `rank_by_ord`,
`reasons_by_qid`, `rank_by_qid`, `input_index`, `ordinal`, `threshold_sweeps`, `_write_shadow`,
`load_shadow_router_config`.

## 5. Original defect recap

AUDIT 73 F1: `run_shadow_router` keyed `reasons_by_qid`/`rank_by_qid` by `qid`, so duplicate-qid
records overwrote each other's reasons and collapsed selected ranks (observational only).

## 6. Internal ordinal verification

`_select` enumerates the input sequence (`for ordinal, inp in enumerate(inputs)`) and returns
`(ordinal, input, reasons)` tuples; the decision loop enumerates the **same** `inputs` list in the
**same** order, so ordinals align between selection and reconstruction. `reasons_by_ord`/`rank_by_ord`
are keyed by ordinal; threshold sweeps reuse the same ordinal-based `_select`. The ordinal is
generated internally, stable for the run, never exposed in output, and not replaced by qid/input_index
in any sort/filter step. Records are plain tuples (no mutable aliasing that could exchange reasons/
ranks). Empty input → cap 0, no candidates; single input handled. **`grep` confirms no `reasons_by_qid`/
`rank_by_qid`/`_by_qid` map remains** — all association is ordinal-based.

## 7. Duplicate-qid correction verification

Probed three records sharing qid `dup` with distinct reasons (low-margin / scoring-invalid /
non-candidate): each decision retains **its own** reasons and its own selected status/rank; no
overwrite. Reconstructing the OLD qid-keyed logic on the same input shows all three would have
collapsed to `['low_logit_margin']` and rank 2 — so the correction is real and the new tests would
have failed pre-fix. **Fixed.**

## 8. Duplicate-input-index verification

The ordinal is independent of `input_index`; `_rank_key` uses `input_index if isinstance(int) else
ordinal`, so a non-int or duplicated `input_index` never causes a type error or collision. Two records
sharing **both** qid and input_index still yield two distinct decisions with distinct ranks (1, 2) and
a traceable `selected_items` list. Note: predict.py assigns `input_index` via `enumerate(samples)`
(`for idx, item …: _shadow_input(qid, idx, …)`), so **input_index is always unique in the real
pipeline** — duplicate-input_index only arises synthetically.

## 9. Ranking-policy preservation

`_rank_key = (tier, margin→+inf if None, -entropy→0 if None, input_index_or_ordinal, ordinal)`, lower
= higher risk. Verified: explicit failures (tier 0) rank above numerical (tier 1); lower/negative
margin first; higher entropy secondary; caller input_index late tie-break; private ordinal final
tie-break. `None` is never compared with a number; non-int input_index handled. Deterministic across
repeated runs (decisions + summary byte-equal). The 21-record replay is unchanged.

## 10. Selected-rank uniqueness / correctness

`rank_by_ord = {ordinal: i+1 …}` over the selected list gives ranks 1..k, each ordinal distinct →
**ranks are unique, contiguous, start at 1, and follow risk order**. Unselected candidates and
non-candidates have `selected_rank=None`. Duplicate qids / duplicate input indexes / both do not
duplicate ranks (probed and unit-tested). Decisions are emitted in input order; `selected_rank`
encodes risk order.

## 11. Candidate-reason isolation

Each decision's `candidate_reasons` come from `reasons_by_ord.get(ordinal, [])` — its own reasons.
Verified for low_logit_margin, parser_failure, scoring_invalid, high_normalized_entropy (configured),
formula_model_disagreement (when supplied), and non-candidate. A reason for one ordinal never appears
on another. Missing optional metadata (`is True` gate) creates no invented reason.

## 12. Primary-summary traceability

`selected_items = [{qid, input_index, selected_rank}]` (one per selected record), `selected_count`
counts records, `selected_qids` preserved (risk order, may duplicate). **High-priority answer:** yes —
every primary selected item is uniquely matchable to exactly one per-item decision **even when qid AND
input_index are both duplicated**, because `selected_rank` is unique among selected records (1..k) and
each decision carries its own `selected_rank`. Verified: for two identical `{qid:q, input_index:0}`
records, `selected_items` ranks are `[1, 2]` and the decisions carry ranks 1 and 2. No selected record
is lost or deduplicated; order is deterministic.

## 13. Threshold-sweep traceability

Each sweep entry has `selected_qids` **and** `selected_input_indexes` (parallel arrays in risk-rank
order) plus finite-only selected-margin min/median/max. For duplicate **qids** with distinct
input_index (the realistic degenerate case), records are uniquely traceable via
`selected_input_indexes`. For the synthetic case of duplicate **qid AND input_index**, the two sweep
entries (`['q','q']` / `[0,0]`) are distinguishable **only by array position** (documented as risk
order) — the sweep has **no explicit per-record `selected_rank`/ordinal** like the primary summary
does. This is **Low** (F1 below): array position = risk rank is documented; the double-duplicate case
is unreachable in the real pipeline (unique input_index by enumerate); AUDIT 74 does not claim sweep
traceability beyond duplicate qids. Sweep selected counts records, does not dedupe, is in risk order,
computes margins from the correct selected records, never mutates primary decisions, and
`_num`/`allow_nan=False` keep non-finite out of JSON.

## 14. Duplicate-qid test-quality review

The 8 new unit tests + 2 new integration tests are behavior-oriented and **genuinely would have
failed** on the old qid-keyed logic (reconstructed and confirmed: reasons/ranks collapse). They verify
record identity (not just counts): per-record reasons; distinct ranks with `selected_items`;
selected-vs-unselected non-overwrite; primary summary tracing by `input_index`/`selected_rank`;
sweep `selected_input_indexes`; duplicate qid+input_index determinism with distinct ranks;
repeated-run byte-equality; unchanged replay. **Gap:** the duplicate-qid+duplicate-input_index test
(`test_duplicate_input_index_and_qid_still_deterministic`) asserts distinct ranks and determinism but
does **not** assert unambiguous **sweep** tracing for that degenerate case (consistent with F1). Low.

## 15. Malformed-config integration review

`test_malformed_shadow_config_fails_closed_end_to_end` writes a temp config with valid
`choice_scoring` + malformed `shadow_router` (`budget_divisor: 0`), monkeypatches
`cc._DEFAULT_CONFIG_PATH`, and runs `predict.py --confidence-shadow-router`. Verified it genuinely
reaches the loader (valid choice_scoring means scoring is enabled and shadow load is attempted),
fails closed (no JSONL/summary written — so no unintended default-10 selection), keeps official CSV
byte-identical to the no-shadow baseline with unchanged qid count/order, and invokes no legacy path.
The test is not a false pass (shadow mode is activated; the malformed block is genuinely loaded).

## 16. Summary-write-failure integration review

`test_summary_write_failure_preserves_official_output` points the summary path at a **directory**
(write fails) with a valid JSONL path. Verified: the JSONL **is** written (so the summary-write step
is genuinely reached, failing after — not at — the JSONL write), the failure is caught with a warning,
the official CSV is byte-identical to baseline and correct, no exception escapes, and scoring is not
recomputed. Partial artifact (JSONL present, no summary) is acceptable and understood.

## 17. Official-output invariance

`submission.csv` is byte-identical with vs without the corrected shadow router, and also under
malformed config, summary-write failure, and scoring failure (all tested). The generated/coerced
answer is always official; scored top-1 never replaces it; no shadow column reaches the CSV; row
order/count unchanged; candidate/selected flags are shadow-only.

## 18. Scoring-reuse verification

The loop computes the score once per record (`_compute_score`) and feeds both telemetry and shadow
inputs; write failures don't recompute; malformed config disables shadow without repeated scoring.
`test_scoring_runs_once_per_qid_in_combined_mode` asserts the real predictor's `score_choices` count
equals the record count with both flags on. **Confirmed: one scoring call per input record.**

## 19. No-selective-component verification

Structural: the router imports only `math`+`dataclasses`; the shadow path in predict.py imports only
`confidence_shadow_router` and `confidence_config`. No import/call of V12B, V13, selector,
`dynamic_base_predictor`, formula bank, `_run_legacy_dynamic_full`, OpenRouter, or any API. Runtime
test corroborates. **None invoked.**

## 20. Policy-drift review

Unchanged (verified against the router source and the unchanged config/predict diffs):
`enabled=false`; provisional threshold `10.0`; `margin <= threshold`; entropy condition; explicit-risk
tiering; raw-logit margin ranking; probability margin excluded; generated/scored agreement excluded;
`budget_divisor=8`; `ceil(N/divisor)`; max-override behavior; no backfill; parser-failure plumbing;
formula-disagreement deferral; diagnostic-only sweeps. **No policy drift.**

## 21. Synthetic 21-record replay

Threshold 10.0, divisor 8, N=21, cap 3 → selected = `syn_020_sequence`, `syn_008_speed`,
`syn_001_addition_3`; margin-9.0 candidate-but-unselected. Unchanged (asserted by
`test_synthetic_replay_unchanged_after_fix`; `selected_items` qids equal `selected_qids`).

## 22. Regression-test results

- `compileall src scripts tests predict.py` → PASS.
- Confidence P1+P2 → **89 passed**.
- Parser/backend group → **86 passed**.
- Focused suite → **38 passed**.
- Full suite → **16 failed, 736 passed**.

## 23. Full-suite failure-identity comparison

The 16 failing node IDs are **identical** to the pre-correction baseline (frozen-artifact /
public-replay class: `test_btc_short_2l31b` ×2, `test_fastmcq_dynamic_system_2l36b` ×3,
`test_final_package_2l31a` ×6, `test_run_profiles_2l38c` ×1, `test_v12b_permutation_2l34b` ×2,
`test_v13_dynamic_integration_2l37a` ×1, `test_v13_multilayer_2l35a` ×1). No new failure.

## 24. Diff / scope and historical-audit integrity

`git diff --check` clean. `configs/confidence_selective.yaml`/`predict.py`/`confidence_config.py`
carry the same Phase 2 diff stats (38/156/62) — **not changed by the corrective pass**. AUDIT 71/72/73
are untracked and unmodified (only AUDIT 74/75 added). The corrective pass touched only
`confidence_shadow_router.py` and the two shadow test files. No prompt/parser/formula/model/Docker/
dependency/V12B/V13/selector/output-contract change; no Phase 3.

## 25. Findings (ordered by severity)

No **Critical**, **High**, or **Medium** findings.

| ID | Sev | File/function | Evidence | Impact | Blocks commit? | Blocks Win. val.? | Recommended correction |
|---|---|---|---|---|---|---|---|
| F1 | Low | `confidence_shadow_router.run_shadow_router` (sweep dict, ~lines 243–252) | Sweep entries expose only `selected_qids`/`selected_input_indexes` (no explicit per-record `selected_rank`/ordinal); two selected records with identical qid AND input_index are distinguishable only by array position | Shadow-diagnostic only; **unreachable in the real pipeline** (predict.py assigns unique input_index); primary summary is fully unambiguous via `selected_rank` | No | No | Add a `selected_rank` (or the ordinal) to each sweep's selected entries — e.g. mirror `selected_items` inside each sweep — and add a sweep double-duplicate traceability assertion |
| I1 | Info | summary `selected_qids` | may contain duplicate qids by design (documented in the note) | none | No | No | Consumers should trace via `selected_items`/`selected_input_indexes` |
| I2 | Info | whole router | not exercised on the real model here (no torch/weights) | none (pure, fake-tested; cannot change answers) | No | No | Windows shadow smoke |
| I3 | Info | duplicate-input_index scenarios | only synthetic (real pipeline enumerates input_index) | none | No | No | n/a |

## 26. Required corrections before commit

**None.** F1 is Low, observational-only, and unreachable in the real pipeline; the primary summary
already satisfies the traceability contract via explicit `selected_rank`.

## 27. Required corrections before Windows shadow validation

**None required.** Recommended (non-blocking): F1 (explicit per-record rank in sweep entries) for
schema symmetry.

## 28. Remaining Windows-only checks

Run the corrected shadow router on the real GPU image and confirm: no change to `submission.csv`;
well-formed JSONL/summary with `selected_items` present and `scoring_method=next_token_logits_one_forward`;
one scoring call per qid in combined mode; `ceil(N/8)` cap on a real N — diagnostic only; no threshold
finalized.

## 29. Confirmation

No implementation fix, no Phase 3, no V12B/V13 execution or change, no selector change, no
prompt/parser/formula/model/Docker/dependency change, no external API/OpenRouter call, no API key
inspected/printed, no model download, no Git commit or push was performed. AUDIT 71–74 were not
modified.

## 30. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
?? docs/audits/71-windows-real-model-revalidation-phase1-scoring.md
?? docs/audits/72-phase2-confidence-shadow-router.md
?? docs/audits/73-independent-review-phase2-shadow-router.md
?? docs/audits/74-phase2-shadow-router-corrective-pass.md
?? docs/audits/75-independent-review-phase2-corrective-pass.md
?? src/local_model/confidence_shadow_router.py
?? tests/integration/test_confidence_shadow_router_2l48e.py
?? tests/unit/test_confidence_shadow_router_2l48d.py
```

## 31. Final verdict

**SAFE TO COMMIT WITH NON-BLOCKING CAVEATS; READY FOR WINDOWS SHADOW VALIDATION.**

The corrective pass genuinely fixes the duplicate-qid collision via a private per-record ordinal (no
qid-keyed maps remain); per-record reasons and selected ranks are isolated, unique, and traceable; the
primary summary is unambiguous even for double-duplicate records via explicit `selected_rank`; the
malformed-config and summary-write-failure paths are integration-tested fail-closed; the router
policy, threshold, budget, and official output are unchanged; the suite is regression-clean (same 16
pre-existing failures). The only finding is Low (sweep schema clarity for a non-production
double-duplicate case), non-blocking. **Phase 3 is NOT declared ready.**

STOP — independent review complete. No fixes applied; nothing committed or pushed; Phase 3 not
implemented.
