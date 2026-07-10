# AUDIT 73 — Independent Review of the Phase 2 Confidence-Aware Shadow Router

Audit number 73 (no prior `73-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD

- Date: 2026-07-10
- Branch: `main`
- HEAD: `d9e5b0a8acdda204ab513b76137a90dbeea8f7f1` ("fix choice scoring with one-forward bare-label
  logits")
- Read-only independent review. The only file created is this audit. No production code, test, or
  config was modified; the Phase 2 working-tree changes were left exactly as found.

## 2. Initial working-tree state

3 modified (`configs/confidence_selective.yaml`, `predict.py`, `src/local_model/confidence_config.py`)
+ 5 untracked (`src/local_model/confidence_shadow_router.py`, the two `…shadow_router…` test files,
audits 71/72). `git diff --check` clean; `git diff --stat` = 204 insertions / 52 deletions across 3
files. This matches the AUDIT 72 change set; no unrelated changes; nothing staged.

## 3. Independence and read-only statement

Findings come from directly reading the router source, the predict.py/config diffs, and the tests;
independently probing the router with fake inputs (duplicate qids, None/negative margins, entropy
tie-break, N=0, override 0); reproducing the 21-item replay from metadata; and running the full test
battery. No model/torch is available in this Linux env (so real-model behavior is not exercised —
the router is pure and fully fake-testable). Temporary probes ran inline and created no files.

## 4. Files / call sites reviewed

`confidence_shadow_router.py` (full), the diffs of `predict.py` and `confidence_config.py`, the
yaml, both new test files; repo-wide `git grep` for `shadow_router`, `run_shadow_router`,
`ShadowRouting*`, `ShadowRouterConfig`, `provisional_margin_threshold`, `budget_divisor`,
`max_targets_override`, `include_*`, `parser_failed`, `formula_disagreement`, `score_choices`,
`_run_legacy_dynamic_full`, `V12B`, `V13`, `selector`.

## 5. Architecture / scope verification

Verified from source: the shadow router lives entirely in the single-pass `else` branch of
`predict.py:main`; `--confidence-shadow-router` is explicit opt-in (default False); no-flag and
telemetry-only behavior are unchanged; the router consumes only the Phase 1 `ChoiceScoreResult`
(+ parser-failure) and records `candidate`/`selected` flags in its own artifacts; it holds no
reference to `rows`/answers and cannot mutate them; it imports only `math`+`dataclasses`. No Phase 3
code, no formula-bank/parser/prompt/model/Docker/dependency/output-contract change (confirmed by
scope diff, §21). The scorer, backend, base predictor, V12B, V13, and selector are byte-unchanged
(absent from the diff).

## 6. Config review

`shadow_router` defaults: `enabled=false`, `provisional_margin_threshold=10.0` (documented
shadow-only, not final), `entropy_threshold=null`, `budget_divisor=8`, `max_targets_override=null`,
includes true, `analysis_margin_thresholds=[5,7.5,10,12.5,15,20]`. `_validate_shadow` enforces:
divisor int ≥ 1; override null or non-negative int (bool rejected); threshold numeric (bool
rejected); entropy numeric-or-null; sweeps a list of numbers — else clear `ValueError`
(unit-tested). `_load_block` is safe on dict / path / None (missing default file → `{}` → defaults;
choice-scoring loader behavior preserved). **predict.py is fail-CLOSED on shadow-config failure**:
`load_shadow_router_config()` is wrapped in try/except → warn → `shadow_cfg=None` → no shadow inputs
built → **no shadow, unintended threshold never used**, official output unaffected. When
`choice_scoring.enabled=false`, shadow is explicitly skipped with a message (no scoring, no
selection). No routing threshold is used outside explicit shadow mode. No fail-open selection after a
config-load failure was found.

## 7. Candidate-policy review

`_reasons_for` makes an item a candidate only via an enabled condition: `logit_margin <= threshold`
(**inclusive**), scoring-invalid (`include_scoring_invalid`), `parser_failure is True`
(`include_parser_failure`), `formula_disagreement is True` (`include_formula_disagreement`), or
entropy `>` a non-null `entropy_threshold`. `is True` gating means None/False optional metadata is
**not** a reason (verified). Probability margin is never used for candidacy/ranking; generated/scored
agreement is not a field the router sees. No ground truth is consumed (a smuggled `expected`/`correct`
attribute is ignored — unit-tested). No non-candidate can be selected; candidates are not synthesized
to fill the cap.

## 8. Parser-failure plumbing review (high-priority)

`predict.py` loop: `raw = predict_one(item)`; `ans = _coerce_label(raw, item)`;
`parser_failed = (raw is None) or (str(raw).strip().upper() != ans)` (or an exception). Verified
correct: a genuinely valid label (`raw="b"`→`ans="B"`, equal) is **not** flagged; a `None` parse is
flagged; an out-of-range parse (`raw="Z"`→coerced `ans="A"`, unequal) **is** flagged — so an invalid
output is not hidden by coercion before the router observes it. `parser_failed` is captured per item,
feeds only the shadow input, and never affects `ans`/official output. This high-priority area is
**sound**.

## 9. Formula-metadata deferral review

Confirmed: the single-pass path (`QwenMCQPredictor.predict_one`) never calls the formula bank (it
lives only in `dynamic_base_predictor`, the selective path). `_shadow_input` passes
`formula_disagreement=None`, `formula_source=None` (deferred, never fabricated); the router does not
inspect question text and does not import `dynamic_base_predictor`. `include_formula_disagreement=true`
is safe when the signal is always None (the `is True` gate never fires). No formula-bank priority,
answer, or solver logic changed.

## 10. Budget-cap review

`_budget_cap`: override → `max(0,int(override))`; N≤0 → 0; else `ceil(N/divisor)` with a positive
divisor guard. Independently verified: N=0→0, 1→1, 7→1, 8→1, 9→2, 21→3, 30→4; override replaces the
computed cap; override 0 → 0 selected; selected count may be < cap or 0; cap applies after candidate
filtering + ranking; no backfill. Integer/bool edge cases rejected by the config validator.

## 11. Deterministic ranking review

`_rank_key = (tier, margin, -entropy, input_index)`, lower = higher risk. `tier` = 0 when any
explicit reason present else 1; `margin` = `logit_margin` or `+inf` if None; `entropy` = value or
0.0 if None — so **no None-vs-numeric comparison ever occurs**. Probes confirmed: explicit invalid
ranks above numerical; lower/negative margin first; higher entropy breaks equal-margin ties; stable
`input_index` final tie-break; repeated runs identical. Decisions are emitted in **stable input
order**; risk order is encoded in `selected_rank` — consistent with the intended stable artifact.

## 12. Threshold-sweep isolation review

Sweeps call `_select` at each `analysis_margin_thresholds` value with the same cap, into separate
summary entries; they never mutate the primary `decisions`/`selected_qids` (unit-tested that the
sweep at 10.0 matches primary and a lower sweep selects fewer without changing primary). Sweep
thresholds never override the provisional threshold. Empty selections yield None min/median/max
safely. Malformed sweep values are rejected at config load. Duplicate/unordered thresholds are each
computed independently (deterministic).

## 13. Combined scoring-reuse review

The loop computes the score **once** per item via `_compute_score(...)` and passes the single result
dict to both `_telemetry_record` and `_shadow_input`. No later pass recomputes scoring; write retries
don't recompute. `test_scoring_runs_once_per_qid_in_combined_mode` asserts the **real predictor's**
`score_choices` call count equals `len(samples)` with both flags on (counts the actual predictor, not
a wrapper). Disabled scoring skips shadow entirely (no hidden duplicate attempts).

## 14. Official-output invariance review

`test_official_csv_identical_with_and_without_shadow` proves `submission.csv` is byte-identical; the
fake's scored top-1 is `A` while q1's generated answer is `B`, and the official CSV keeps `B` (no
override). Row order and count unchanged; no shadow column added; `submission_time.csv` schema/timing
unchanged. Scoring failure, router failure, and JSONL/summary write failure all leave official output
intact (shadow run+write wrapped in try/except in `main`, and `_write_shadow` catches OSError/
ValueError). Independently confirmed for shadow-only and telemetry+shadow modes.

## 15. Artifact-safety review

Decision/summary `as_dict` contain only qid, indices, flags, single-letter labels
(`generated_answer`/`top1`/`top2`), numeric diagnostics, reasons, threshold/cap, and scoring method —
**no** question text, choices, prompt, reasoning, expected answer, ground-truth, or secrets.
`allow_nan=False` on write + `_num` scrubbing keep NaN/Inf out; `selected_rank` is null for unselected
items; reasons are deterministic. `scoring_error` strings are structural (e.g. `no_choices`,
`label_not_single_token:B`) — see I2.

## 16. No-selective-component invocation review

Structural: the router imports only `math`+`dataclasses`; the shadow path in `predict.py` imports
only `confidence_shadow_router` and `confidence_config`. Nothing in the shadow path imports or calls
V12B, V13, the selector, `dynamic_base_predictor`, the formula bank, `_run_legacy_dynamic_full`, or
any OpenRouter/API path. `test_shadow_never_invokes_legacy_selective` corroborates at runtime. Verdict:
**shadow mode invokes no selective/follow-up component.**

## 17. Synthetic replay reproduction

Independently reproduced with metadata only (no ground truth in code): threshold 10.0, divisor 8,
N=21, cap 3 → candidates are margins {0.0, 4.25, 7.75, 9.0}; selected =
**`syn_020_sequence`, `syn_008_speed`, `syn_001_addition_3`**; the margin-9.0 item is candidate but
not selected; threshold 7.5 → {0.0, 4.25}; all-above → 0. Matches AUDIT 72 exactly.

## 18. Test-quality review

The 34 unit + 8 integration tests are behavior-oriented and would catch: `<` vs `<=` (inclusive
test), reversed/probability-margin ranking, non-candidate backfill, always-fill-budget, invalid
ranked-below-numerical, None-margin handling, unstable tie-break, risk-order reordering, duplicate
scoring in combined mode (real call count), scored-top1 override, V12B/V13/legacy invocation, NaN/Inf
JSON, ground-truth/text leakage, and JSONL-write failure. **Gaps:** (a) **no duplicate-qid test**
(and duplicate qids actually corrupt the artifact — see F1); (b) predict.py-level malformed-shadow-
config path is not integration-tested (config validation is unit-tested; behavior is correct);
(c) summary-write-failure not separately tested (JSONL-write failure is; both share one try). All
gaps are Low.

## 19. Regression-test results

- `compileall src scripts tests predict.py` → PASS.
- Confidence P1+P2 → **79 passed**.
- Parser/backend group → **86 passed**.
- Focused suite → **38 passed**.
- Full suite → **16 failed, 726 passed**.

## 20. Full-suite failure-identity comparison

The 16 failing node IDs are **identical** to the pre-Phase-2 baseline (frozen-artifact / public-replay
class: `test_btc_short_2l31b` ×2, `test_fastmcq_dynamic_system_2l36b` ×3, `test_final_package_2l31a`
×6, `test_run_profiles_2l38c` ×1, `test_v12b_permutation_2l34b` ×2, `test_v13_dynamic_integration_2l37a`
×1, `test_v13_multilayer_2l35a` ×1). No new failure.

## 21. Diff / scope review

Only `configs/confidence_selective.yaml`, `predict.py`, `confidence_config.py` modified + the new
router module/tests/audits. No change to prompts, parser, formula bank, Base answer logic, scoring
semantics, model config/path/dtype/device, Docker, dependencies, V12B, V13, selector, legacy dynamic
behavior, the official CSV schema/writer, or no-flag behavior. `git diff --check` clean.

## 22. Findings (ordered by severity)

No **Critical**, **High**, or **Medium** findings.

| ID | Sev | File/function | Evidence | Impact | Blocks commit? | Blocks Win. shadow val.? | Recommended correction |
|---|---|---|---|---|---|---|---|
| F1 | Low | `confidence_shadow_router.run_shadow_router` (lines ~200–201) | `reasons_by_qid`/`rank_by_qid` keyed by `qid`; probe with two inputs sharing a qid → both decisions get the same `selected_rank` (2) and the last-written reasons; `selected_qids` lists the qid twice | **Shadow artifact only** — corrupted `selected_rank`/reasons for duplicate-qid inputs; **no official-output impact**; abnormal input (BTC qids are unique; predict.py single-pass doesn't enforce uniqueness) | No | No | Key both dicts by the unique `input_index` instead of `qid` |
| F2 | Low | AUDIT 72 §13 + tests | §13 claims "duplicate qids do not corrupt selection or summaries"; no duplicate-qid test exists and the probe shows collision | Overstated audit claim + missing test | No | No | Soften §13 wording; add a duplicate-qid test after F1 fix |
| F3 | Low | `predict.py` shadow-config load / tests | malformed-shadow-config → warn + no-shadow (correct, fail-closed) but only unit-tested at the validator, not integration-tested end-to-end | Test gap; behavior correct | No | No | Add an integration test that malformed shadow config disables shadow and leaves official output intact |
| F4 | Low | `_write_shadow` / tests | JSONL-write failure tested; summary-write failure not separately tested (shared try) | Test gap; behavior safe | No | No | Add a summary-write-failure integration test |
| I1 | Info | whole router | not exercised on the real model here (no torch/weights) | none (pure, fully fake-tested; cannot change answers) | No | No | Run a real-model shadow smoke on Windows |
| I2 | Info | artifact `scoring_error` | structural error strings (e.g. `no_choices`); a raised-exception message could theoretically include a value, not question text | negligible leakage | No | No | Optionally whitelist error codes |
| I3 | Info | sweep `selected_margin_*` | raw floats, not `_num`-scrubbed; safe because real-scorer margins are finite (non-finite → `allow_nan=False` fails the shadow write closed) | none in practice | No | No | Optionally scrub for symmetry |

## 23. Required corrections before commit

**None.** All findings are Low/Informational and do not affect official output, determinism of normal
inputs, or the observational guarantee.

## 24. Required corrections before Windows shadow validation

**None required.** Recommended (non-blocking): F1 (duplicate-qid keying) and its test (F2) before the
shadow artifacts are relied upon for any analysis on inputs that might contain duplicate qids.

## 25. Remaining real-model checks

On the Windows GPU image, confirm the shadow router runs end-to-end without changing `submission.csv`,
emits well-formed JSONL/summary with `scoring_method=next_token_logits_one_forward`, that scoring runs
once per qid in combined mode, and that selected counts respect `ceil(N/8)` on a real N — all
diagnostic only; no threshold may be finalized from this.

## 26. Confirmation

No source/test/config implementation change, no Phase 3, no V12B/V13 execution or change, no selector
change, no prompt/parser/formula/model/Docker/dependency change, no external API/OpenRouter call, no
API key inspected/printed, no model download, no Git commit or push was performed. Temporary probes
created no files.

## 27. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
?? docs/audits/71-windows-real-model-revalidation-phase1-scoring.md
?? docs/audits/72-phase2-confidence-shadow-router.md
?? docs/audits/73-independent-review-phase2-shadow-router.md
?? src/local_model/confidence_shadow_router.py
?? tests/integration/test_confidence_shadow_router_2l48e.py
?? tests/unit/test_confidence_shadow_router_2l48d.py
```

## 28. Final verdict

**SAFE TO COMMIT WITH NON-BLOCKING CAVEATS; READY FOR WINDOWS SHADOW VALIDATION.**

The Phase 2 shadow router is strictly observational, deterministic, off by default, and
official-output byte-invariant; it never invokes V12B/V13/selector/legacy; it ranks by raw-logit
margin (probability margin and generated/scored agreement excluded); parser-failure plumbing is
correct; formula disagreement is safely deferred; the budget cap and no-backfill policy are correct;
fail-closed holds for config/scoring/router/write failures. The only findings are Low/Informational
(a duplicate-qid observational artifact collision + test/doc gaps), none blocking commit or Windows
shadow validation. **Phase 3 is NOT declared ready.**

STOP — independent review complete. No fixes applied; nothing committed or pushed; Phase 3 not
implemented.
