# AUDIT 72 — Phase 2: Confidence-Aware SHADOW Router (observational)

Audit number 72 (no prior `72-*` existed under `docs/audits/`).

## 1. Date, branch, starting HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `d9e5b0a8acdda204ab513b76137a90dbeea8f7f1` ("fix choice scoring with one-forward
  bare-label logits")
- Scope: implement the Phase 2 shadow router only. **Phase 3 was NOT implemented; V12B/V13/selector
  were not executed or changed.**

## 2. Initial working-tree state

Clean at start. AUDIT 66–70 and the corrected one-forward scorer are committed. Baseline before
Phase 2: Phase 1 tests 37, parser/backend 86, focused 38, full suite **16 failed / 684 passed** (the
16 = known missing frozen-artifact / public-replay failures).

## 3. Architecture stage and scope

Target staged architecture: Base generation + one-forward bare-label scoring → **Phase 2
confidence-aware shadow router** → (Phase 3 V12B) → (Phase 4 V13) → calibrated selector →
submission. This task adds **only** the shadow-router layer: it computes which qids WOULD be
selected and records diagnostics; it never runs follow-up reasoning, never merges/overrides an
answer, and never changes the official CSV, its order, schema, or filenames. It is opt-in and off by
default.

## 4. Summary of AUDIT 71 real-model evidence

User-run Windows Docker validation (RTX 4060, torch 2.7.1+cu128, transformers 5.12.1; not rerun in
Linux): corrected scorer valid 3/3 and 21/21; generation IDs == scoring IDs; greedy first token ==
scored top-1; exactly one forward per item for 3/4/10 choices; `scores_by_label` == captured logits
(max diff 0.0); mean scoring latency ≈ 0.30 s; peak GPU ≈ 6.07 GiB. On 21 synthetic items, correct
median margin 23.25 vs wrong median 7.75; the three lowest-margin items were all wrong; probability
margin saturated; entropy secondary; generated/scored agreement is a consistency check, not an
independent signal. Verdict there: **PHASE 1 REAL-MODEL VALIDATION PASSED — READY FOR PHASE 2 SHADOW
ROUTER**.

## 5. Why raw-logit margin is primary

It gave real diagnostic separation on the 21-item run (correct vs wrong medians 23.25 vs 7.75) and
is not saturated. It is the primary numerical uncertainty signal (lower margin = higher risk).

## 6. Why probability margin is not primary

The real run showed strong softmax saturation — probability margins cluster near 1.0 and lose
resolution. It is recorded but never used for ranking (a unit test proves ranking follows the raw
logit margin even when the probability margin is inverted).

## 7. Why generated/scored agreement is not an uncertainty signal

Corrected greedy generation and scored top-1 read the **same** next-token distribution, so they
agree by construction (21/21). Agreement is an implementation consistency check, not risk. The
router never uses it.

## 8. Files changed

New:
- `src/local_model/confidence_shadow_router.py` — the pure router (config/input/decision/summary +
  `run_shadow_router`).
- `tests/unit/test_confidence_shadow_router_2l48d.py` — 34 unit tests.
- `tests/integration/test_confidence_shadow_router_2l48e.py` — 8 integration tests.
- `docs/audits/71-…md`, `docs/audits/72-…md`.

Modified:
- `configs/confidence_selective.yaml` — added the `shadow_router` block; `choice_scoring` gains
  documented `scoring_method`/`batch_size`.
- `src/local_model/confidence_config.py` — added `ShadowRouterConfig` loading + validation; shared
  `_load_block` helper (choice-scoring loader behavior unchanged).
- `predict.py` — added `--confidence-shadow-router` / `--shadow-router-path` /
  `--shadow-router-summary-path`; refactored the loop to **score once per qid** and drive both
  telemetry and the shadow router; added shadow writers.

**Unchanged (verified absent from the diff):** `local_qwen_backend.py`, `choice_scoring.py`,
`qwen_mcq_predictor.py`, the formula bank, `dynamic_base_predictor`, V12B, V13, the selector, the
prompt builder, the parser, model settings, Dockerfile, and dependencies.

## 9. New router data structures and APIs

`ShadowRouterConfig` (frozen), `ShadowRoutingInput`, `ShadowRoutingDecision` (with `as_dict()`),
`ShadowRoutingSummary` (with `as_dict()`), and `run_shadow_router(inputs, config) -> (decisions,
summary)`. Pure, deterministic, imports only `math`/`dataclasses`; no torch, no ground truth.

## 10. Config schema/defaults

`shadow_router`: `enabled` (false), `provisional_margin_threshold` (10.0),
`entropy_threshold` (null), `budget_divisor` (8), `max_targets_override` (null),
`include_scoring_invalid`/`include_parser_failure`/`include_formula_disagreement` (true),
`analysis_margin_thresholds` ([5,7.5,10,12.5,15,20]). `choice_scoring` gains `scoring_method:
next_token_logits_one_forward` (fixed) and `batch_size: 1`. Validation: divisor ≥ 1,
override ≥ 0 or null, threshold numeric, entropy numeric or null, sweeps a list of numbers — else a
clear `ValueError`. Loading is safe on missing/malformed config (fail-closed → no shadow, warned).

## 11. Provisional-threshold disclaimer

`provisional_margin_threshold = 10.0` is **shadow-only and NOT a final production threshold**. It is
configurable and used only to record hypothetical selections. No final routing threshold is claimed
(only 21 synthetic items exist).

## 12. Budget-cap formula

`budget_cap = max_targets_override` if set, else `ceil(N / budget_divisor)` (0 for N=0). Verified:
N=1→1, 7→1, 8→1, 9→2, 21→3, 30→4. The cap is a **maximum**; selected count may be 0…cap; the router
never backfills with non-candidates.

## 13. Candidate conditions

An item is a candidate if any of: scoring invalid (and `include_scoring_invalid`); parser failure
(and `include_parser_failure`, and the flag is genuinely True); formula disagreement (and
`include_formula_disagreement`, and genuinely True — deferred here, see §15); entropy above
`entropy_threshold` when that threshold is set (null → ignored); or `logit_margin <=
provisional_margin_threshold` (inclusive). Reasons: `scoring_invalid`, `parser_failure`,
`formula_model_disagreement`, `high_normalized_entropy`, `low_logit_margin`.

## 14. Deterministic ranking logic

Sort key `(risk_tier, margin, -entropy, input_index)`, lower = higher risk: (1) explicit
failure/disagreement reasons form **tier 0** and rank above numerical-only **tier 1**; (2) within a
tier, lower raw-logit margin first; (3) higher entropy breaks near-ties; (4) stable input index is
the final tie-break. Candidates are truncated to the cap; only the top-cap are `selected`.

## 15. Optional parser/formula signals and their availability

Inspected directly:
- **Parser failure — AVAILABLE** on the single-pass path: `predictor.predict_one(item)` returns
  `None` (or an invalid label that gets coerced) → `parser_failed`; wired into `parser_failure`
  without changing the answer path.
- **Formula-bank source / disagreement — UNAVAILABLE (deferred)** on the single-pass path:
  `predict.py` uses `QwenMCQPredictor.predict_one` and **never calls the formula bank** (the formula
  bank + its `formula_bank:*` / `dynamic_local_qwen` / `dynamic_fallback` source metadata live only
  in `dynamic_base_predictor`, i.e. the selective path). So `formula_disagreement`/`formula_source`
  are left `None`, documented as deferred, and **never inferred from question text**. The formula
  bank was not refactored, re-prioritized, or altered; it does not bypass model scoring on the
  single-pass/shadow path (there is no formula bank there to bypass).

## 16. Primary shadow policy

Candidate → deterministic rank → truncate to cap. Selected qids are recorded only; nothing is sent
to V12B/V13 and no answer is merged/overridden.

## 17. Diagnostic threshold sweep

For each `analysis_margin_thresholds` value the summary records candidates-before-cap,
selected-after-cap, selected qids, and the selected-margin min/median/max — computed independently
so they **cannot** change the primary decisions (unit-tested). Observational only; no labels, no
follow-up, no accuracy claim.

## 18. CLI flags and output paths

`--confidence-shadow-router` (opt-in), `--shadow-router-path`
(default `scratch/fastmcq_run/confidence_shadow_router.jsonl`), `--shadow-router-summary-path`
(default `scratch/fastmcq_run/confidence_shadow_router_summary.json`). No flag → unchanged; only
`--confidence-telemetry` → unchanged Phase 1 behavior; `--confidence-shadow-router` → Base
generation + one scoring pass + shadow decisions.

## 19. Per-qid shadow JSONL schema

`qid`, `input_index`, `candidate`, `selected`, `selected_rank`, `candidate_reasons`,
`generated_answer`, `top1`, `top2`, `logit_margin`, `probability_margin`, `normalized_entropy`,
`scoring_valid`, `scoring_error`, `risk_tier`, `risk_margin`, `provisional_threshold`, `budget_cap`,
`scoring_method`. **No** question text, choices, prompt, or reasoning; JSON is finite-only
(`allow_nan=False`; `as_dict` scrubs non-finite → None).

## 20. Summary JSON schema

`n_input`, `budget_cap`, `provisional_threshold`, `candidate_count`, `selected_count`,
`selected_qids`, `reason_counts`, `scoring_method`, `threshold_sweeps` (per-threshold diagnostics),
and a shadow-only note. No question text.

## 21. Scoring-result reuse when telemetry + shadow are both enabled

The loop computes the score **once** per item via `_compute_score(...)` and passes that single
result to both `_telemetry_record(...)` and `_shadow_input(...)`. No duplicate model forward is
introduced.

## 22. Evidence of one scoring call per qid in combined mode

`test_scoring_runs_once_per_qid_in_combined_mode` instruments the fake predictor's `score_choices`
and asserts it is called exactly `len(samples)` times when **both** `--confidence-telemetry` and
`--confidence-shadow-router` are on.

## 23. Official-output byte invariance

`test_official_csv_identical_with_and_without_shadow` proves `submission.csv` is **byte-identical**
with vs without the shadow router; `submission_time.csv` schema/timing unchanged. Independent of
scoring/routing outcome.

## 24. Confirmation no answer override exists

The official answer is always the generated/`_coerce_label` result. In the fake test the scored
top-1 is `A` while q1's generated answer is `B`; the official CSV keeps `B`. The shadow router only
sets `candidate`/`selected` flags in its own artifacts — it holds no reference to `rows` and cannot
mutate answers.

## 25. Confirmation V12B/V13/selector/legacy runner are not invoked

Shadow mode runs entirely in the single-pass `else` branch. `test_shadow_never_invokes_legacy_selective`
monkeypatches `_run_legacy_dynamic_full` to raise and confirms it is never called. The router module
imports nothing from V12B/V13/selector/`dynamic_base`/`fastmcq_system`.

## 26. Synthetic 21-record router replay result

With provisional threshold 10.0, divisor 8, N=21 → cap `ceil(21/8)=3`: candidates are the four items
with margin ≤ 10 (0.0, 4.25, 7.75, 9.0); selected (top 3 by lowest margin) are
**`syn_020_sequence` (0.0), `syn_008_speed` (4.25), `syn_001_addition_3` (7.75)**. The margin-9.0
item (`syn_007_bat_ball`) is a candidate but **not** selected (cap). Lowering the threshold to 7.5
selects only the 0.0 and 4.25 items; a run where all margins exceed the threshold selects zero; the
router never fills the cap with non-candidates. (Ground-truth correctness of these qids appears only
in test comments / this audit — never as a runtime input.)

## 27. Tests added/updated

34 unit tests (`test_confidence_shadow_router_2l48d.py`): 21-item replay; lower-threshold; zero
selection; no backfill; inclusive threshold; margin ranking; scoring-invalid tier/enable/disable;
entropy null-ignored / configured; parser & formula used only when provided; missing metadata not a
reason; cap formula for N∈{1,7,8,9,21,30}; max_targets_override; deterministic tie-break; stable
order; sweep-does-not-override; probability-margin-not-primary; no-ground-truth; JSON-safe/no-text;
non-finite scrubbed; config defaults/yaml/validation errors. 8 integration tests
(`…2l48e.py`): official CSV byte-identical; artifact schema + no text; one scoring call per qid in
combined mode; legacy/V12B/V13 never invoked; shadow-output-failure safe; scoring-failure safe;
no files when off; skipped when choice_scoring disabled. Phase 1 telemetry tests updated implicitly
(refactor) and still pass unchanged.

## 28. Regression-test results

- `compileall src scripts tests predict.py` → PASS.
- Phase 1 + Phase 2 confidence tests → **79 passed** (37 Phase 1 + 42 Phase 2).
- Parser/backend group → **86 passed**.
- Focused suite → **38 passed**.
- Full suite → **16 failed, 726 passed** (was 16 / 684; **+42** = new tests).

## 29. Full-suite failure identity comparison

The 16 failing node IDs are **identical** to the pre-Phase-2 baseline (frozen-artifact / public-replay
class: `test_btc_short_2l31b` ×2, `test_fastmcq_dynamic_system_2l36b` ×3, `test_final_package_2l31a`
×6, `test_run_profiles_2l38c` ×1, `test_v12b_permutation_2l34b` ×2, `test_v13_dynamic_integration_2l37a`
×1, `test_v13_multilayer_2l35a` ×1). **No new failure introduced.**

## 30. Formula-bank / parser metadata findings

- Base generation exposes parser failure explicitly (via `predict_one → None`/coerced) → used.
- Formula-bank hits with exact/heuristic source metadata exist only in the selective path
  (`dynamic_base_predictor`), not in single-pass → not available to the shadow router → deferred.
- Formula/model disagreement cannot be computed on the single-pass path without invoking the formula
  bank (out of scope) → deferred; never fabricated from text.
- The formula bank does not bypass model scoring on the single-pass/shadow path (it is not called
  there). No formula-bank logic, priority, or answer was changed.

## 31. Remaining risks/caveats

- Real-model shadow behavior is unverified here (no torch/weights in Linux); the router is pure and
  fully fake-tested, but running it against the real model on Windows is a recommended confidence
  check (it cannot change answers regardless).
- `provisional_margin_threshold=10.0` is a placeholder; a final threshold requires a larger permitted
  labeled set, deferred to a future calibration task (not Phase 2).
- Formula-disagreement signal is deferred until the architecture routes through a base predictor that
  exposes formula source (a later phase), not wired now.
- Combined-mode single-scoring is proven with a fake predictor; on the real model it likewise issues
  one `score_choices` per qid by construction.

## 32. Confirmations

- Phase 3 was NOT implemented.
- V12B was not executed or changed; V13 was not executed or changed.
- Selector behavior was not changed (and is never invoked by shadow mode).
- No threshold was declared final.
- No organizer ground truth was used (only self-created synthetic evidence, in AUDIT 71/tests).
- No official answer was modified (byte-identical `submission.csv`).
- No prompt / parser / formula / model / Docker / dependency change occurred.
- No model was downloaded; no external API/OpenRouter call; no API key inspected/printed.
- No Git commit or push occurred.

## 33. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
?? docs/audits/71-windows-real-model-revalidation-phase1-scoring.md
?? docs/audits/72-phase2-confidence-shadow-router.md
?? src/local_model/confidence_shadow_router.py
?? tests/integration/test_confidence_shadow_router_2l48e.py
?? tests/unit/test_confidence_shadow_router_2l48d.py
```

## 34. Recommended next action

Independent review of Phase 2 (this audit + AUDIT 71). Then commit Phase 1 correction evidence (68–70
already committed) and Phase 2 separately. Only after independent review and explicit approval should
Phase 3 (confidence-routed V12B) begin — and only after a larger permitted labeled set exists to
inform (not yet finalize) thresholds.

## 35. Readiness verdict

**READY FOR INDEPENDENT REVIEW OF PHASE 2 SHADOW ROUTER.**

Phase 3 is **not** declared ready. The shadow router is observational, deterministic, fail-closed,
scope-contained, and regression-clean (same 16 pre-existing failures); it changes no official output
and invokes no follow-up reasoning.

STOP — Phase 2 shadow-router implementation and audits complete. Phase 3 not implemented; nothing
committed or pushed.
