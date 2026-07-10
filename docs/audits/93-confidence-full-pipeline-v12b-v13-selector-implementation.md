# AUDIT 93 — Full Confidence-Routed Pipeline Implementation (Base -> V12B -> V13 -> Selector)

Audit number 93 (no prior `93-*` existed under `docs/audits/`).

> **Nature of this record.** This is an **implementation report** for one tightly-scoped pass
> that adds an opt-in, answer-changing pipeline (`--confidence-full-pipeline`) on top of the
> already-approved, observational Phase 3A-1 V12B shadow (AUDIT 88/89, Windows-validated in
> AUDIT 92). It is written by the implementer and should be treated as claims to verify, not as
> independent evidence — an independent review is the recommended next action (§20).

## 1. Starting branch and HEAD

- Branch: `main`
- Starting full HEAD: `f556dc159f71929c86bb711c7d37946405e75f11` ("validate phase 3A-1 V12B
  shadow on Windows" — this is AUDIT 92).
- This HEAD was reached via `git pull`; `git log --oneline -5` at session start showed AUDIT 92 as
  the tip, preceded by AUDIT 90/91 (blocked Fedora attempts), AUDIT 73cf35b (Phase 3A-1
  implementation), and the Phase 3A-0 runner commit.

## 2. Initial clean state

`git status --short` at session start: empty (clean). `git branch --show-current`: `main`.
`git rev-parse HEAD`: `f556dc1...`. No stash, no uncommitted work, no unrelated in-progress
changes present before this implementation pass began.

## 3. Existing V13 architecture discovered

Read completely before writing any code: `docs/audits/80-phase3-v12b-plan-corrections.md`,
`docs/audits/87-independent-review-phase3a1-observational-integration-plan.md`,
`docs/audits/89-independent-review-phase3a1-observational-v12b-integration.md`,
`docs/audits/92-windows-real-model-validation-phase3a1-v12b-shadow.md`,
`src/layers/v13_dynamic_layer.py`, `src/layers/v13_layer_registry.py`,
`src/layers/programmatic_solver_layer.py`, `src/layers/content_first_answerer.py`,
`src/layers/least_to_most_constraint_solver.py`, `src/local_model/confidence_v12b_runner.py`,
`src/local_model/confidence_v12b_artifacts.py`, `src/local_model/confidence_config.py`,
`src/local_model/qwen_mcq_predictor.py`, `src/local_model/local_qwen_backend.py`,
`src/local_model/confidence_shadow_router.py`, `predict.py`.

Findings:

- **V13 consists of three pure, deterministic, model-backed layers** (`programmatic_solver`,
  `content_first`, `least_to_most`), each exposing a `build_*_prompt(sample, ...)` function, a
  `parse_*` function for the model's structured JSON response, and a pure interpreter
  (`match_result_to_options` / `match_content_to_options` / `select_answer_from_constraint_table`)
  that maps the parsed response to a canonical option label or rejects it. **These three modules
  make no API calls, hold no legacy-orchestration coupling, and were judged safe to reuse.**
- `src/layers/v13_dynamic_layer.py`'s `run_v13_layer` is **legacy orchestration and was NOT
  reused**: it unconditionally creates a work directory and opens/writes
  `v13_dynamic_records.jsonl` before any processing (`work.mkdir(...)`, `open(rec_path, "w"/"a")`),
  and its `select_v13_targets` selects targets from legacy `BasePrediction`-shaped objects
  (`bp.route`, `bp.risk_reason`, `bp.confidence`) that do not exist in the Phase 3A-1/3B data
  model. Both violate the task's constraint ("no filesystem-dependent merging", "no legacy target
  selection") and AUDIT 80's binding precedent for V12B (§6/§7), which this pass extends to V13 by
  the same reasoning.
- `src/layers/v13_layer_registry.py`'s `run_v13_layers_if_enabled` only returns static registry
  metadata (no real execution) — not usable for this pass either.
- **Decision:** a new clean module, `src/local_model/confidence_v13_runner.py`, was written,
  reusing only the three pure layer modules' prompt/parse/interpret functions and the layer's own
  small deterministic feature-classification logic (`classify_programmatic_domain` plus two short
  hint-string tuples, duplicated locally rather than importing the legacy module, per the "clean
  adapter" instruction). It never imports `v13_dynamic_layer.py`, `v13_layer_registry.py`,
  `fastmcq_system.py`, or anything under `src/selector/`.

## 4. Files modified and created

Modified (tracked): `predict.py` (+106/−9 lines: CLI flags, mode conflicts, config wiring,
pre-CSV pipeline substitution, post-CSV artifact write), `src/local_model/confidence_config.py`
(+44 lines: `FullPipelineConfig` + `load_full_pipeline_config`), `configs/confidence_selective.yaml`
(+11 lines: `confidence_full_pipeline` block).

Created (untracked): `src/local_model/confidence_v13_runner.py`,
`src/local_model/confidence_full_pipeline.py`, `src/local_model/confidence_full_pipeline_artifacts.py`,
`src/evaluation/__init__.py`, `src/evaluation/full_pipeline_metrics.py`,
`tests/unit/test_confidence_v13_runner_2l51a.py`,
`tests/unit/test_confidence_full_pipeline_selector_2l51b.py`,
`tests/integration/test_confidence_full_pipeline_2l51c.py`,
`tests/unit/test_full_pipeline_metrics_2l51d.py`, this audit.

**Files verified unchanged:** `src/local_model/confidence_v12b_runner.py` (no integration blocker
was found that required modifying the approved Phase 3A-0 runner — confirmed by `git diff
--name-only` not listing it), `src/layers/v13_dynamic_layer.py`, `src/layers/v13_layer_registry.py`,
`src/layers/mcq_permutation_debiaser.py`, `src/system/fastmcq_system.py`, everything under
`src/selector/`, the Dockerfile, dependency files, and AUDIT 1–92.

## 5. Full runtime call graph

Inside `predict.py`'s offline (`else`) branch, when `--confidence-full-pipeline` is set:

1. `parse_known_args` → three mode-conflict checks, all before any model construction:
   `--legacy-dynamic-full` + `--confidence-v12b-shadow` (pre-existing),
   `--legacy-dynamic-full` + `--confidence-full-pipeline` (new),
   `--confidence-v12b-shadow` + `--confidence-full-pipeline` (new — see §9 for why).
2. `want_full_pipeline = True` folds into the existing `want_router`/`want_score` computation
   (unchanged pattern from Phase 3A-1) so scoring and the router run exactly once regardless of
   which confidence mode(s) are combined.
3. Base generation loop (unchanged): `predict_one` → `_coerce_label` → `rows`/`times` appended;
   `_compute_score` once per record; `shadow_inputs` collected.
4. `run_shadow_router(shadow_inputs, shadow_cfg)` once → `decisions` (one per record, input order).
5. `load_v12b_config()` (shared with V12B-shadow's own loader — same YAML block, same
   `permutation_count`) then `load_full_pipeline_config()` (new; structural `enabled` marker only,
   CLI flag is the sole gate, mirrors the Phase 2/3A-1 convention).
6. **Before the official CSV write** (this is the key structural difference from V12B shadow,
   which always runs strictly after): `run_full_pipeline(samples, decisions,
   backend=predictor.backend, v12b_config=v12b_cfg)` is called inside a broad `try/except`. On
   success, `rows` is rebuilt from the returned `FullPipelineRecord.final_answer` values (with an
   extra per-record `is_valid_label` safety net reverting to the original Base answer for any
   non-canonical value); on **any** exception, `rows` is reverted to the untouched Base rows
   captured just before the call, and no partial pipeline record is used.
7. Official `submission.csv`/`submission_time.csv` written from `rows` (now possibly overridden).
8. **After** the official CSV write: V12B-shadow's own artifact write (unchanged, only fires when
   `--confidence-v12b-shadow` was requested — impossible simultaneously with full-pipeline per the
   mode conflict), then full-pipeline's own diagnostics write
   (`write_full_pipeline_artifacts`), guarded by its own `try/except`.
9. Legacy `--output`/`/output/pred.csv` mirrors (unchanged).

`run_full_pipeline` itself (`src/local_model/confidence_full_pipeline.py`):

1. `build_selected_entries(samples, decisions)` — **reused directly from
   `confidence_v12b_artifacts.py`**, the same input-validation boundary V12B shadow already uses
   (closed codes, `2..26` choice range, etc.), so router-selected records that are structurally
   unsafe for V12B are equally never sent to V13.
2. `run_v12b_for_selected([...valid entries...], backend=backend,
   permutation_count=v12b_config.permutation_count)` — the unmodified, approved Phase 3A-0 runner.
3. For each valid+selected record, apply the selector's V12B-acceptance rule (§7) to decide
   `v12b` vs. "needs V13".
4. `run_v13_for_unresolved([...needs-V13 entries...], backend=backend)` — the new V13 runner,
   **same `backend` object** as step 2 (never a second `get_local_qwen_backend` call — this is
   structurally guaranteed because both calls receive the identical Python object reference
   `predictor.backend`, not a re-derived one).
5. Build one `FullPipelineRecord` per input sample, in input order, applying the selector (§7).

## 6. V13 runner contract (`src/local_model/confidence_v13_runner.py`)

- `V13RunInput` (frozen dataclass): `qid`, `input_index`, `question`, `choices`,
  `canonical_labels` — ephemeral, in-memory only, never persisted.
- `run_v13_for_unresolved(inputs, *, backend, max_new_tokens=384) -> (results, summary)` — accepts
  **only** the records the caller (the selector) explicitly hands it; has no target-selection
  policy of its own beyond a small deterministic per-record **layer choice**
  (`classify_programmatic_domain` → numeric hints → `programmatic_solver`; Vietnamese/English
  content-definition hints → `content_first`; multi-condition/statement hints →
  `least_to_most`; default → `content_first`, mirroring the legacy layer's own default).
- Per record: build the chosen layer's prompt → `backend.generate_text(messages,
  max_new_tokens=384, temperature=0.0)` → `parse_json_object` → the layer's own pure interpreter →
  accept only if the layer reports success **and** the resulting label is `is_valid_label` for the
  sample.
- `V13ErrorCode` (closed `str` enum): `ok`, `empty_prompt`, `generation_error`, `parse_error`,
  `no_match`, `invalid_label`, `unknown_layer`, `runner_error`. Exceptions store
  `type(exc).__name__` only, never `str(exc)` or any raw text.
- `V13RunResult` (frozen, `as_dict()`): `record_ordinal` (position in the list passed to this
  call — runner-local, never the record's global identity), `qid`, `input_index`, `layer`,
  `attempted`, `valid`, `mapped_label` (a bare label or `None`), `error_code`,
  `exception_class_name`. No question/choice/prompt/response/reasoning field exists anywhere on
  this dataclass.
- Every record is wrapped in its own `try/except`; one record's exception (verified with a
  monkeypatched injected failure — `test_one_record_failure_does_not_abort_others`) never aborts
  the batch.
- No file I/O anywhere in this module (grep-verified: no `open(`, no `Path(...).write`, no
  `mkdir`).
- No import of `v13_dynamic_layer`, `v13_layer_registry`, `fastmcq_system`, or anything under
  `src/selector/`.

## 7. Selector policy (`src/local_model/confidence_full_pipeline.py`)

Implemented exactly as the task specified, with one explicit, documented extension for the case
the task's five rules did not enumerate:

1. Not router-selected → `final_source = "base"`.
2. Selected **but** rejected by the V12B input-validation boundary (the same closed codes V12B
   shadow already uses, e.g. `unsupported_choice_count`) → `final_source = "base"`. **This case is
   not literally one of the task's five numbered rules** (which only discuss "router did not
   select" vs. "V12B produced X"); the implementation treats "V12B could not even be attempted due
   to a structurally unsafe record" as equivalent to rule 1, and — because the same record shape
   that fails the V12B boundary would equally risk crashing a V13 prompt builder — V13 is **not**
   attempted for these records either. This is a deliberate, conservative scope-limiting choice
   documented here for review, not an oversight.
3. Selected + input-valid + V12B `aggregate_status == "valid_unique_majority"` **and** a non-null
   `hypothetical_answer` that is itself `is_valid_label` → `final_source = "v12b"`,
   `final_answer = hypothetical_answer`. V13 is **never** invoked for this record (verified:
   `test_v12b_valid_unique_majority_accepted_and_v13_never_called` uses a V13 backend mode that
   would raise if called, and the test still passes).
4. Selected + input-valid + V12B anything else (`all_invalid`, `insufficient_valid_permutations`,
   `tie`, `valid_weak_consensus`, `generation_failure`, `aggregate_error`) → sent to V13.
5. V13 returns `valid=True` with a `mapped_label` → `final_source = "v13"`,
   `final_answer = mapped_label`.
6. V13 fails, returns malformed output, an invalid label, or raises → `final_source =
   "base_fallback"`, `final_answer` reverts to the record's Base answer.

No model self-reported confidence, chain-of-thought, organizer ground truth, or external API is
read or used anywhere in this policy (grep-verified: no `confidence` field is read from any V12B/
V13 result by the selector; only `aggregate_status`, `hypothetical_answer`, `valid`, and
`mapped_label` are consulted).

## 8. Identity and pairing

- The authoritative per-record identity is `source_record_ordinal` = the position in
  `enumerate(samples)`, identical to the Phase 3A-1 contract (AUDIT 87 §10). `qid` and
  `input_index` are metadata only.
- V12B results are paired to their source record by `zip(valid_entries, v12b_results)` (positional,
  inherited unchanged from `confidence_v12b_artifacts.build_selected_entries`/
  `run_v12b_for_selected`'s own invariant, including its `len(results) != len(valid)` assertion).
- V13 results are paired to their "needs V13" entries the same way: `zip(needs_v13,
  v13_results)`, with an equivalent `len(v13_results) != len(needs_v13)` `AssertionError` guard.
- `test_pairing_valid_invalid_valid_never_misaligns` (selector unit test) and
  `test_duplicate_qid_and_input_index_stay_distinct` (both selector and integration levels) prove
  a duplicate-qid / invalid-in-the-middle record can never have another record's V12B/V13 result
  attached to it — matching the exact A-valid/B-invalid/C-valid pattern AUDIT 87/89 required for
  V12B and extending it through V13.

## 9. Backend reuse

- `run_full_pipeline` accepts one `backend` parameter and passes the **identical object** to both
  `run_v12b_for_selected` and `run_v13_for_unresolved` — no second `get_local_qwen_backend()` call
  exists anywhere in the new code (grep-verified across all four new/modified production files).
- `predict.py` passes `predictor.backend` (the existing read-only accessor from AUDIT 88) into
  `run_full_pipeline`; no new accessor or backend-loading path was added.
- **`--confidence-v12b-shadow` and `--confidence-full-pipeline` are mutually exclusive** (explicit
  `SystemExit` before model load). Rationale: full-pipeline already performs its own internal
  V12B pass; permitting both flags together would either silently run V12B twice (double the model
  calls, double the latency) or require new de-duplication logic. Scope-limiting this to an
  explicit CLI error was judged the smallest safe choice for a "tightly scoped pass"; combining
  Phase 2 shadow-router output **with** full-pipeline remains fully supported (they share the same
  single router-decision list and never duplicate V12B).
- `test_full_pipeline_uses_single_injected_backend_no_second_model_load` (integration) asserts
  exactly one `_build_predictor` call and a nonzero shared `backend.calls` count spanning both
  V12B and V13 activity within one full-pipeline run.

## 10. Failure fallback

- **Per-record**: any V13 exception, malformed output, or invalid label reverts only that record
  to `base_fallback` (§7 rule 6); other records in the same run are unaffected
  (`test_one_record_failure_does_not_abort_others` at the V13-runner level; the selector-level
  tests confirm the same at the pipeline level).
- **Whole-pipeline**: if `run_full_pipeline` itself raises (config malformed, router decisions
  malformed, an internal assertion trips, etc.), `predict.py`'s wrapping `try/except` reverts
  `rows` to the untouched Base rows captured immediately before the call — a global optional-layer
  failure still produces a valid, complete, unmodified Base submission
  (`test_full_pipeline_global_failure_preserves_base_submission`).
- **Artifact-write failure**: `write_full_pipeline_artifacts` writes the JSONL and summary as two
  independently atomic files (temp-then-`replace`, same pattern as `confidence_v12b_artifacts.py`)
  under their own `try/except`; a write failure only warns (`type(e).__name__` only) and never
  touches the already-written official submission
  (`test_full_pipeline_artifact_write_failure_preserves_submission`).
- **Extra safety net**: even after `run_full_pipeline` succeeds, `predict.py` re-validates every
  `final_answer` with `is_valid_label` against the actual sample before writing it into `rows`,
  falling back to the original Base answer for that single record if it is ever not a canonical
  label (defense in depth beyond the selector's own guarantees).

## 11. Output behavior

- No flag: unchanged (`test_no_flag_stays_base_only`).
- `--confidence-v12b-shadow`: unchanged, still fully observational
  (`test_v12b_shadow_stays_observational` — official CSV byte-identical to a Base-only run).
- `--confidence-full-pipeline`: **can** change the official answer for router-selected records
  only; non-selected records are provably unaffected
  (`test_full_pipeline_overrides_selected_record_only`,
  `test_full_pipeline_differs_from_base_only_csv`).
- Row count and qid order are preserved in every mode (asserted directly in
  `test_full_pipeline_differs_from_base_only_csv` and implicitly everywhere `rows` length is
  checked against `len(_SAMPLES)`).
- Every final answer is a valid canonical label for its own sample
  (`test_every_final_answer_is_a_valid_canonical_label`, selector level; the `is_valid_label`
  safety net in predict.py, integration level).

## 12. Diagnostic privacy

`FullPipelineRecord`/`FullPipelineSummary` (`as_dict()`) whitelist only: ordinals, `qid`,
`input_index`, booleans, and closed-vocabulary status/label strings (`base_answer`,
`v12b_hypothetical_answer`, `v13_answer`, `final_answer` are all bare option labels like `"A"`,
never option text). No `question`, `choices`, `prompt`, raw model output, `reasoning`, `evidence`,
expected answer, correctness, or ground-truth field exists anywhere on either dataclass or in the
writer module. `write_full_pipeline_artifacts` never serializes a raw sample or a `V13RunInput`
(which does carry ephemeral question/choice text in memory) — only the pre-built, already-scrubbed
`FullPipelineRecord`/`FullPipelineSummary` objects. `allow_nan=False` on both files (mirrors AUDIT
87/89's contract). Privacy was verified two ways: (a) unit-level, scanning serialized V13 results
for banned substrings; (b) integration-level, scanning the actual files predict.py wrote —
including the literal option text used in the test fixtures ("Paris", "2 + 2", "Capital of
France") — and confirming none appear (`test_full_pipeline_artifacts_privacy_and_schema`).

## 13. Evaluator metrics (`src/evaluation/full_pipeline_metrics.py`)

Pure, deterministic, offline arithmetic over caller-supplied `FullPipelineEvalRecord`s
(`record_ordinal`, `qid`, `expected_answer`, `base_answer`, `final_answer`, `final_source`). Not
imported anywhere in the inference path (`predict.py` does not import
`src.evaluation.*`; grep-verified). Computes `base_accuracy`, `final_accuracy`,
`v12b_override_count`, `v13_override_count`, `base_fallback_count`, `corrections` (Base wrong →
final right), `regressions` (Base right → final wrong), and `net_accuracy_difference`. Records are
compared by list position, never merged/deduplicated by `qid` — a fixture with a repeated `qid` is
scored as that many distinct records (`test_duplicate_qids_handled_as_distinct_records`). No new
fixture file was added to the repository: the task's "use existing synthetic labeled fixtures when
available" note was interpreted as applying to *real* calibration runs (out of scope for this
implementation-only pass, which explicitly must not run a real model); the evaluator's own unit
tests construct small in-test records directly, which satisfies "add focused synthetic fixtures
only when necessary for testing selector arithmetic" without introducing a new committed dataset
file.

## 14. Tests added

- `tests/unit/test_confidence_v13_runner_2l51a.py` — 16 tests: layer selection (all three layers +
  default), success paths for all three layers, empty-prompt/generation-error/parse-error/
  no-match/invalid-label closed codes, one-record-failure isolation, record-ordinal-by-position
  (not qid), `max_new_tokens` default and override, summary layer/error counts, text-free results.
- `tests/unit/test_confidence_full_pipeline_selector_2l51b.py` — 11 tests: not-selected→base,
  selected-invalid-boundary→base (V12B/V13 never called), `valid_unique_majority`→v12b (V13 never
  called), `all_invalid`→V13→success, `insufficient_valid_permutations`→V13→success, V13
  invalid-output→base_fallback, V13 exception→base_fallback, ambiguous-V12B-plus-failing-V13→
  base_fallback (the "tie/ambiguity" requirement — see §17 for the literal-tie caveat),
  A-valid/B-invalid/C-valid positional-pairing, duplicate qid/input_index as distinct records,
  every final answer is a valid canonical label across a mixed batch.
- `tests/integration/test_confidence_full_pipeline_2l51c.py` — 13 tests: no-flag unchanged, V12B
  shadow stays observational, full-pipeline overrides only the selected record, full-pipeline CSV
  differs byte-for-byte from a Base-only run while qid order is preserved, artifact privacy/schema
  (including a literal scan for the test fixtures' real option text), global full-pipeline failure
  preserves the Base submission, artifact-write failure preserves the submission, both new mode
  conflicts refuse before model load, full pipeline never invokes
  `_run_legacy_dynamic_full`, single injected backend / one predictor build / one score pass per
  record, full pipeline coexists with Phase 2 shadow-router artifacts, path-only flags are inert
  when the execution flag is off.
- `tests/unit/test_full_pipeline_metrics_2l51d.py` — 7 tests: zero overrides, perfect Base, perfect
  full pipeline, exact corrections/regressions arithmetic, duplicate qids as distinct records,
  empty input, `as_dict()` field whitelist.

Total new tests: **47**, all passing.

## 15. Exact test results

```
tests/unit/test_confidence_v13_runner_2l51a.py .............. 16 passed
tests/unit/test_confidence_full_pipeline_selector_2l51b.py ... 11 passed
tests/integration/test_confidence_full_pipeline_2l51c.py ..... 13 passed
tests/unit/test_full_pipeline_metrics_2l51d.py ................ 7 passed
```
Combined run: `47 passed in 0.33s`.

## 16. Existing regression results

Exact suites requested by the task:

- `pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q` → **47 passed**.
- `pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py tests/integration/test_confidence_v12b_shadow_2l50d.py -q` → **100 passed**.
- `pytest tests/unit/test_confidence_v12b_config_2l50a.py tests/unit/test_qwen_predictor_backend_accessor_2l50b.py tests/unit/test_confidence_v12b_artifacts_2l50c.py -q` → **37 passed**.
  (47 + 100 + 37 = 184, matching the exact figure independently confirmed in AUDIT 89/92.)
- Relevant existing V13 tests (`tests/integration/test_v13_dynamic_integration_2l37a.py`,
  `tests/integration/test_v13_multilayer_2l35a.py`): **28 passed / 6 failed** — all 6 failures are
  the pre-existing Windows `UnicodeDecodeError`/`bash`-unavailable issues described in §17, not
  caused by this pass (proven in §17).
- Relevant output/submission tests (`test_submission_variants_2l29a.py`,
  `test_btc_submission_contract_2l47a.py`, `test_full_system_output_contract_2l41a.py`): **19
  passed / 14 failed** — same pre-existing-failure class, proven unrelated in §17.
- `python -m compileall predict.py src tests` → **OK** (no syntax errors).
- `git diff --check` → **clean** (exit 0, no whitespace/conflict-marker errors).

## 17. Known failures

**Full fake/model-free suite** (`python -m pytest -q`): **65 failed, 829 passed** with this pass's
changes applied. All 65 failures are **pre-existing and unrelated to this implementation** — proven
by an exact A/B comparison:

1. `git stash --include-untracked` (reverting to the clean AUDIT 92 HEAD) → full suite → **65
   failed, 782 passed**.
2. `git stash pop` (restoring this pass's changes) → full suite → **65 failed, 829 passed**.
3. The two 65-line `FAILED` test-name lists were diffed and are **byte-for-byte identical**
   (`diff` produced no output).
4. Arithmetic: 829 = 782 baseline-passed + 47 new. **This pass introduces zero new failures and
   zero new errors anywhere in the fake/model-free suite.**

Root causes of the 65 pre-existing failures (inspected directly, none touched by this pass):
almost all are `UnicodeDecodeError`/`UnicodeEncodeError` from test helpers reading/writing
Vietnamese-language source or fixture text via `Path.read_text()`/`Path.write_text()` without an
explicit `encoding="utf-8"` argument, which falls back to the Windows default `cp1252` codec and
cannot represent Vietnamese diacritics or the em-dash (`—`) used in several docstrings; the
remainder are `bash -n <script>` syntax-check subprocess calls that fail because this Windows
session's WSL relay cannot exec `/bin/bash`. Both classes are pre-existing environment/locale
issues in the test suite itself (unrelated to Phase 3A-1, Phase 3B, or any code path this pass
touches) and are outside this pass's file scope to fix.

**Caveat on "tie/ambiguity always falls back to Base" (§7/§14):** the task's literal
`V12BAggregateStatus.TIE` case was not separately constructed as a test fixture, because
engineering a genuine vote-count tie requires precise control over the underlying permutation
family/seed mechanics in `mcq_permutation_debiaser.py` (out of this pass's file scope to touch).
Instead, `test_ambiguous_v12b_and_failing_v13_falls_back_to_base` demonstrates the equivalent and
more general property — any V12B outcome that is not a clean `valid_unique_majority` acceptance,
combined with a V13 that also cannot resolve it, ends at `base_fallback` — which covers `TIE` by
the same code path (§7 rule 4 routes every non-accepted status, including `tie`, to V13 uniformly;
there is no separate branch for `tie` that could behave differently). This is a coverage
simplification, not a functional gap: `tie` and `all_invalid` are handled by literally the same
`elif ordinal in v12b_by_ordinal` branch in `confidence_full_pipeline.py`.

## 18. Confirmation

- No external API / OpenRouter call anywhere in the new code (grep-verified; the new modules
  import only `src.layers.*`, `src.local_model.confidence_v12b_runner`,
  `src.local_model.confidence_v12b_artifacts`, `src.local_model.local_qwen_backend`,
  `src.utils.labels`, and stdlib).
- No organizer ground truth used or read; the evaluator takes only caller-supplied records and was
  never pointed at any real dataset file in this pass.
- No model download; no model was even loaded (all new/changed code was exercised exclusively with
  fake in-memory backends/predictors — no torch/transformers import occurs anywhere in the new
  test files).
- No Docker/dependency file changed (`git diff --name-only` lists only `predict.py`,
  `configs/confidence_selective.yaml`, `src/local_model/confidence_config.py`, plus new files under
  `src/local_model/`, `src/evaluation/`, and `tests/`).
- No default promotion: `--confidence-full-pipeline` is opt-in, `store_true`, default `False`; the
  no-flag path is provably unchanged (§11).
- No real-model execution occurred in this pass.
- No commit and no push were performed.

## 19. Repository status

Current `git status --short`:

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
?? docs/audits/93-confidence-full-pipeline-v12b-v13-selector-implementation.md
?? src/evaluation/
?? src/local_model/confidence_full_pipeline.py
?? src/local_model/confidence_full_pipeline_artifacts.py
?? src/local_model/confidence_v13_runner.py
?? tests/integration/test_confidence_full_pipeline_2l51c.py
?? tests/unit/test_confidence_full_pipeline_selector_2l51b.py
?? tests/unit/test_confidence_v13_runner_2l51a.py
?? tests/unit/test_full_pipeline_metrics_2l51d.py
```

`git diff --stat` (tracked files only): `configs/confidence_selective.yaml | 11 ++`,
`predict.py | 106 ++++++++++++++-`, `src/local_model/confidence_config.py | 44 ++` — 3 files
changed, 152 insertions(+), 9 deletions(-). Nothing staged, nothing committed, nothing pushed.

## 20. Limitations

- No ground truth was used and no accuracy claim is made anywhere in this audit. The evaluator
  (§13) is offline calibration/analysis tooling only, never exercised against a real labeled
  dataset in this pass.
- Observational-only claims apply solely to the pre-existing `--confidence-v12b-shadow` mode; the
  new `--confidence-full-pipeline` mode is explicitly answer-changing by design and is documented
  as such everywhere (CLI help text, config docstring, this audit).
- All evidence in this audit comes from **fake predictor/backend unit and integration tests** — no
  real model, no real GPU, no real Docker container was exercised in this pass (explicitly
  forbidden by the task). Real-model behavior (actual V13 layer-selection accuracy, actual
  permutation/vote outcomes, actual latency) is **unverified** and requires a future Windows
  real-model observational-or-answer-changing validation pass, analogous to AUDIT 92 but for
  `--confidence-full-pipeline`.
- Thresholds remain provisional: `provisional_margin_threshold=10.0`,
  `min_valid_permutations=5`, `consensus_votes=4` are all inherited unchanged from Phase 2/3A-1 and
  are not recalibrated or finalized by this pass.
- The V13 runner's per-record layer choice is a small heuristic (numeric-hint / content-hint /
  multi-condition-hint / default-to-content-first) mirroring the legacy layer's own classification
  logic; it has not been validated against a real labeled dataset for layer-selection accuracy.
- The literal `V12BAggregateStatus.TIE` code path is exercised only implicitly (§17 caveat), not
  via a dedicated fixture.
- `DEFAULT_MAX_NEW_TOKENS = 384` for V13 is an unvalidated implementation default (by analogy with
  V12B's approved 192 and the legacy layer's own default of 768), not a calibrated value, and is
  not exposed as a CLI/config tunable in this first pass.

## 21. Explicit confirmation

No source/test/config/YAML/Docker file was changed beyond the files listed in §4/§19. Phase 3B is
now **partially implemented** by this pass (Base→V12B→V13→selector exists and is opt-in), but this
does **not** constitute default promotion, and no organizer ground truth, external API, model
download, or real-model execution occurred. No git commit or push was performed.

## 22. Final verdict

**FULL CONFIDENCE PIPELINE IMPLEMENTED — READY FOR FINAL REVIEW**

The opt-in `--confidence-full-pipeline` flag composes the approved, unmodified Phase 3A-0 V12B
runner with a new clean in-memory V13 runner and a conservative deterministic selector, entirely
inside one new orchestration module plus minimal `predict.py`/config wiring. The existing no-flag
and `--confidence-v12b-shadow` behaviors are unchanged and independently re-verified. 47 new tests
cover routing/call-counts, the full selector policy (including positional-pairing and duplicate-
identity safety), output-contract and failure-fallback behavior, artifact privacy, and evaluator
arithmetic — all passing. The full fake/model-free suite shows zero new failures versus a clean
A/B baseline comparison against the AUDIT 92 HEAD. Recommended next action: an independent
adversarial code review of this pass (mirroring the AUDIT 87/89 pattern used for Phase 3A-1),
followed by a Windows real-model validation of `--confidence-full-pipeline` specifically (actual
V13 layer-selection behavior, actual override rates, actual latency, and official-CSV correctness
under real generation) before any consideration of default promotion.
