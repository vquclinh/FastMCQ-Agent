# AUDIT 74 — Phase 2 Shadow Router Corrective Pass (duplicate-qid identity + test gaps)

Audit number 74 (no prior `74-*` existed under `docs/audits/`).

## 1. Date, branch, starting HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `d9e5b0a8acdda204ab513b76137a90dbeea8f7f1` ("fix choice scoring with one-forward
  bare-label logits")
- Scope: a narrow correction of AUDIT 73's findings F1–F4 in the uncommitted Phase 2 shadow router.
  No Phase 3; no V12B/V13/selector; no policy/threshold change.

## 2. Initial working-tree state

3 modified (`configs/confidence_selective.yaml`, `predict.py`, `src/local_model/confidence_config.py`)
+ 5 untracked (`src/local_model/confidence_shadow_router.py`, the two `…shadow_router…` test files,
audits 71/72/73). `git diff --check` clean. This is the Phase 2 change set from AUDIT 72/73; no
unrelated changes.

## 3. Corrective-pass scope

Fix only: F1 (duplicate-qid dict collision), F2 (missing duplicate-qid tests + AUDIT 72 overclaim),
F3 (no end-to-end malformed-shadow-config test), F4 (no summary-write-failure test). Files touched
this pass: `src/local_model/confidence_shadow_router.py`, `tests/unit/test_confidence_shadow_router_2l48d.py`,
`tests/integration/test_confidence_shadow_router_2l48e.py`, and this audit. **AUDIT 71/72/73 were not
modified.** `configs/confidence_selective.yaml`, `predict.py`, and `confidence_config.py` were **not
changed in this pass** (their diff stats are identical to the pre-correction Phase 2 state).

## 4. AUDIT 73 findings addressed

- **F1 (Low):** `run_shadow_router` keyed `reasons_by_qid`/`rank_by_qid` by `qid`; duplicate qids
  overwrote per-record reasons and collapsed selected ranks. **Fixed.**
- **F2 (Low):** no duplicate-qid regression test; AUDIT 72 §13 overstated safety. **7 duplicate-qid
  unit tests added; the overclaim is corrected here (AUDIT 72 left unmodified as historical
  evidence).**
- **F3 (Low):** malformed-shadow-config fail-closed not integration-tested. **Integration test added.**
- **F4 (Low):** summary-write failure not independently tested. **Integration test added.**

## 5. Duplicate-qid defect reproduction (pre-fix)

AUDIT 73 reproduced: two inputs sharing a qid → both decisions received the same `selected_rank`
(the last one) and the last-written `candidate_reasons`; `selected_qids` listed the qid, and
per-record traceability was lost. Observational only (no official-output impact).

## 6. Root cause

Association dictionaries were keyed by the caller-supplied `qid`, which is not unique across input
records (predict.py's single-pass path does not enforce qid uniqueness). Distinct records with the
same qid collided.

## 7. Per-record identity strategy used

Every record is now associated by a **private enumeration ordinal** — its 0-based position in the
`inputs` list (`for ordinal, inp in enumerate(inputs)`). `_select` returns candidates/selected as
`(ordinal, input, reasons)` tuples; `reasons_by_ord` and `rank_by_ord` are keyed by `ordinal`; the
decision loop enumerates inputs and looks up each record's own reasons/rank by its ordinal. `qid`
and `input_index` are preserved purely as output metadata; decisions stay in original input order.

## 8. Why qid is no longer the internal association key

`qid` is caller-supplied and may repeat; using it collapses distinct records. The private ordinal is
generated internally and is unique **even when both `qid` and `input_index` are duplicated**, so
per-record correctness no longer depends on any caller-supplied uniqueness.

## 9. Duplicate input-index handling

The ordinal is independent of `input_index`. A test with two records sharing **both** qid and
`input_index` still yields two distinct decisions with distinct selected ranks (1 and 2) and a
traceable `selected_items` list — deterministic and non-overwriting.

## 10. Ranking determinism after correction

`_rank_key = (tier, margin, -entropy, input_index_or_ordinal, ordinal)`, lower = higher risk:
(1) explicit failures (tier 0) above numerical (tier 1); (2) lower raw-logit margin
(None→`+inf`); (3) higher entropy (None→`0.0`, negated); (4) stable caller `input_index` (falls back
to ordinal if not an int); (5) the private ordinal as the final deterministic tie-break. `None` is
never compared with a number. Verified deterministic for duplicate qids, duplicate input indexes,
equal margins, equal entropy, missing margin, and missing entropy; repeated runs are byte-equal.

## 11. Per-record reasons/rank correctness

Each decision now carries its own `candidate`, `candidate_reasons`, `selected`, `selected_rank`,
risk fields, margin/entropy, and `input_index`. A duplicate qid never copies another record's reasons
or rank. `selected_rank` is unique among selected records, starts at 1, reflects risk order, and is
null for unselected records (all asserted).

## 12. Summary-schema clarification

`ShadowRoutingSummary` gains `selected_items` — a per-record list of `{qid, input_index,
selected_rank}` in risk-rank order. `selected_count` counts **records**, not unique qids. Each
threshold-sweep entry gains `selected_input_indexes` alongside `selected_qids`. The summary `note`
documents that `selected_qids` is risk-rank order and may contain duplicates, and that
`selected_items`/`selected_input_indexes` provide unambiguous per-record tracing.

## 13. Semantics of duplicate qids in `selected_qids`

`selected_qids` is preserved for compatibility, is in risk-rank order, and **may contain duplicate
qid strings** when duplicate-qid records are selected (documented in the summary note and tests). It
is not deduplicated. Unique tracing is via `selected_items` / `selected_input_indexes`.

## 14. Threshold-sweep duplicate handling

Sweeps use the same ordinal-based `_select`; each sweep records `selected_qids` **and**
`selected_input_indexes` (traceable for duplicate qids) plus finite-only selected-margin min/median/
max. Sweeps remain diagnostic-only and never mutate the primary decisions.

## 15. Duplicate-qid tests added (unit)

`tests/unit/test_confidence_shadow_router_2l48d.py` (+8): same qid different reasons (each retains its
own); same qid both selected → distinct ranks + no overwrite + `selected_items`; same qid
one-selected-one-not (unselected not marked selected); summary traceable by `input_index`; duplicate
qid in threshold sweeps uses `selected_input_indexes`; duplicate **qid + input_index** still
deterministic; repeated-run determinism (decisions + summary byte-equal); and the 21-record replay
unchanged after the fix.

## 16. Malformed-config integration test

`test_malformed_shadow_config_fails_closed_end_to_end`: a temp config with valid `choice_scoring` and
a malformed `shadow_router` (`budget_divisor: 0`), run through `predict.py` with
`--confidence-shadow-router`. Verifies official `submission.csv` is byte-identical to the no-shadow
baseline, no qid dropped, order unchanged, and **no shadow JSONL/summary written** (fail-closed — no
unintended default threshold used to select qids).

## 17. Summary-write-failure integration test

`test_summary_write_failure_preserves_official_output`: the summary path is a directory (so its
write fails) while the JSONL path is valid. Verifies the JSONL **was** written (so the summary-write
step was genuinely reached), the official CSV is byte-identical to baseline and correct, no exception
escapes, and scoring is not recomputed.

## 18. Confirmation AUDIT 71–73 were not modified

`docs/audits/71`, `72`, `73` are unchanged (untouched by this pass). AUDIT 72's historical
duplicate-qid overclaim is preserved as-is; this audit records that AUDIT 73 disproved it and that
the corrective pass fixes it.

## 19. Confirmation router policy/threshold/budget unchanged

Unchanged: default `enabled=false`; provisional threshold `10.0`; margin comparison `<=`; entropy
condition; explicit-risk tiering; budget `ceil(N/budget_divisor)`; maximum-cap + no-backfill; raw-logit
margin primary; probability margin excluded from ranking; generated/scored agreement excluded;
parser-failure plumbing; formula-disagreement deferral; sweep diagnostic-only behavior. The default
`10.0` and all thresholds are byte-unchanged.

## 20. Synthetic 21-record replay result

Threshold 10.0, divisor 8, N=21, cap 3 → candidates {0.0, 4.25, 7.75, 9.0}; selected =
**`syn_020_sequence`, `syn_008_speed`, `syn_001_addition_3`**; margin-9.0 candidate-but-unselected.
Unchanged from AUDIT 72 (asserted by `test_synthetic_replay_unchanged_after_fix`), and `selected_items`
qids equal `selected_qids`.

## 21. Official-output byte-invariance result

`submission.csv` is byte-identical with vs without the corrected shadow router (existing test), and
also byte-identical under malformed-config and summary-write-failure (new tests). Scored top-1 never
replaces the generated answer; candidate/selected flags exist only in shadow artifacts; no schema/
filename change; no dropped row; order unchanged.

## 22. Combined telemetry/shadow scoring-call result

`test_scoring_runs_once_per_qid_in_combined_mode` (unchanged) still passes: with both
`--confidence-telemetry` and `--confidence-shadow-router`, the real predictor's `score_choices` is
called exactly once per input record.

## 23. V12B/V13/selector/legacy invocation result

The router still imports only `math`+`dataclasses`; the shadow path imports only the router + config.
`test_shadow_never_invokes_legacy_selective` passes. No V12B/V13/selector/`dynamic_base_predictor`/
formula bank/`_run_legacy_dynamic_full`/OpenRouter/API invocation.

## 24. Targeted-test results

- Confidence P1+P2 → **89 passed** (was 79; +10: 8 dup-qid unit + 2 integration).
- Parser/backend group → **86 passed**.
- Focused suite → **38 passed**.
- `compileall src scripts tests predict.py` → PASS.

## 25. Full-suite results

`pytest tests -q` → **16 failed, 736 passed** (was 16 / 726; **+10** = new tests).

## 26. Full-suite failure-identity comparison

The 16 failing node IDs are **identical** to the pre-correction baseline (frozen-artifact /
public-replay class: `test_btc_short_2l31b` ×2, `test_fastmcq_dynamic_system_2l36b` ×3,
`test_final_package_2l31a` ×6, `test_run_profiles_2l38c` ×1, `test_v12b_permutation_2l34b` ×2,
`test_v13_dynamic_integration_2l37a` ×1, `test_v13_multilayer_2l35a` ×1). No new failure.

## 27. Files changed

- `src/local_model/confidence_shadow_router.py` — ordinal-based association; added `selected_items`
  to the summary and `selected_input_indexes` to sweeps; documented duplicate-qid semantics. (Policy
  unchanged.)
- `tests/unit/test_confidence_shadow_router_2l48d.py` — +8 duplicate-qid/determinism/replay tests.
- `tests/integration/test_confidence_shadow_router_2l48e.py` — +2 (malformed-config fail-closed,
  summary-write failure).
- `docs/audits/74-phase2-shadow-router-corrective-pass.md` — this audit.

(Unchanged this pass: `configs/confidence_selective.yaml`, `predict.py`, `confidence_config.py`,
audits 71/72/73, and all Phase-1/backend/selector/V12B/V13 code.)

## 28. Remaining risks/caveats

- Real-model shadow behavior is still unverified in Linux (no torch/weights); the router is pure and
  fully fake-tested. A real-model shadow smoke on Windows remains recommended (cannot change answers).
- `selected_qids` may contain duplicate qids by design; downstream analysis should use
  `selected_items`/`selected_input_indexes` for per-record identity.
- The provisional `10.0` threshold is still a placeholder; no final threshold is claimed.

## 29. Explicit confirmations

- Phase 3 was not implemented.
- V12B was not executed or changed; V13 was not executed or changed.
- Selector was not executed or changed.
- No threshold was declared final (policy/threshold/budget unchanged).
- No official answer was modified (byte-identical `submission.csv`).
- No prompt / parser / formula / model / Docker / dependency change occurred.
- No model was downloaded; no external API/OpenRouter call; no API key inspected/printed.
- No Git commit or push occurred.

## 30. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
?? docs/audits/71-windows-real-model-revalidation-phase1-scoring.md
?? docs/audits/72-phase2-confidence-shadow-router.md
?? docs/audits/73-independent-review-phase2-shadow-router.md
?? docs/audits/74-phase2-shadow-router-corrective-pass.md
?? src/local_model/confidence_shadow_router.py
?? tests/integration/test_confidence_shadow_router_2l48e.py
?? tests/unit/test_confidence_shadow_router_2l48d.py
```

## 31. Recommended next action

Independent review of this corrective pass (AUDIT 74), then commit Phase 2 (router + config + audits
71–74). Only after review and explicit approval should Phase 3 (confidence-routed V12B) begin.

## 32. Readiness verdict

**READY FOR INDEPENDENT REVIEW OF PHASE 2 CORRECTIVE PASS.**

The duplicate-qid collision is fixed via a private per-record ordinal; per-record reasons/ranks are
isolated and traceable; the malformed-config and summary-write-failure paths are integration-tested
fail-closed; the router policy, threshold, budget, and official output are unchanged; the suite is
regression-clean (same 16 pre-existing failures). **Phase 3 is NOT declared ready.**

STOP — corrective implementation, tests, and AUDIT 74 complete. No independent review performed here;
nothing committed or pushed; Phase 3 not implemented.
