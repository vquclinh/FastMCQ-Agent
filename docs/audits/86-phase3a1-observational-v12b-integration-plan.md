# AUDIT 86 - Phase 3A-1 Observational V12B Integration Plan

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `77e940d3075405361e264019f7c5afa3e80038d6`
- HEAD title: `add in-memory confidence-routed V12B runner`

## 2. Initial clean working-tree state

Preflight passed.

```text
git branch --show-current
main

git rev-parse HEAD
77e940d3075405361e264019f7c5afa3e80038d6

git status --short
<no output>
```

`git diff --check`, `git diff --stat`, `git diff --cached --check`, and
`git diff --cached --stat` produced no output. The working tree and index were clean.

The committed HEAD contains the Phase 3A-0 runner, its fake-backend unit tests, and AUDIT 82 through
AUDIT 85.

## 3. Codex takeover/context reconstruction

I reconstructed the current state from committed source and audits. Phase 1 and Phase 2 are complete,
Phase 3A-0 is complete and independently approved by AUDIT 85, and Phase 3A-1 is not implemented.
Phase 3B, V13, selector behavior, answer replacement, and default promotion remain unauthorized.

## 4. Planning-only/read-only statement

This pass is documentation-only planning for Phase 3A-1. I did not modify production source, tests,
configs, YAML, existing audits, Docker/dependency files, or official-output code. I did not run real
V12B inference, load model weights, call an external API, download a model, commit, or push.

## 5. Completed Phase 1/2/3A-0 state

Phase 1 provides one-forward bare-label next-token-logit choice scoring through
`LocalQwenBackend.score_mcq_choices` and pure scoring math in `choice_scoring.py`.

Phase 2 provides an opt-in observational shadow router in `confidence_shadow_router.py`. It filters
candidates before the `ceil(N / 8)` budget cap, never backfills non-candidates, preserves duplicate
records with private enumeration ordinals, and never changes official answers.

Phase 3A-0 provides `confidence_v12b_runner.py`: an injected-backend, in-memory runner that accepts
only explicitly selected inputs, executes one generation per unique permutation, validates the minimal
structured response, emits text-free diagnostics with closed error codes, computes deterministic
aggregate statuses, and records only conservative hypothetical diagnostics with
`official_answer_source = "base"`.

## 6. Governing audits

Read completely:

- `docs/audits/78-phase3-confidence-routed-v12b-planning.md`
- `docs/audits/79-independent-review-phase3-v12b-plan.md`
- `docs/audits/80-phase3-v12b-plan-corrections.md`
- `docs/audits/81-independent-review-phase3-v12b-plan-corrections.md`
- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`
- `docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md`
- `docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md`
- `docs/audits/85-independent-rereview-phase3a0-structured-response-fix.md`

Binding interpretation:

- AUDIT 80 governs wherever it conflicts with AUDIT 78.
- AUDIT 81 approved only the isolated Phase 3A-0 task.
- AUDIT 85 approved committing Phase 3A-0 with non-blocking caveats and authorizes Phase 3A-1
  planning only.

## 7. Current predict.py call graph

Current no-legacy path:

```text
main
  -> argparse + input/output resolution
  -> load_dataset
  -> _build_predictor
       -> QwenMCQPredictor(...)
       -> get_local_qwen_backend(...)
       -> backend.load()
  -> for each input record, enumerate(samples)
       -> predictor.predict_one(item)
       -> _coerce_label(raw, item)
       -> append official Base row and generation time
       -> if telemetry or shadow is requested:
            -> _compute_score(predictor, item)
            -> _telemetry_record(...)
            -> _shadow_input(...)
  -> optional _write_telemetry
  -> optional run_shadow_router + _write_shadow
  -> write submission.csv and submission_time.csv
  -> optional legacy output mirrors
```

Current `--legacy-dynamic-full` bypasses the local single-pass path and delegates to
`scripts/tools/final_infer.py`. Phase 3A-1 must reject `--legacy-dynamic-full` combined with V12B
shadow before any model load or inference.

## 8. Exact Phase 3A-1 objective

Phase 3A-1 should add only opt-in observational integration:

```text
input records
  -> Base generation
  -> one-forward choice scoring
  -> Phase 2 confidence router
  -> router-selected records only
  -> Phase 3A-0 V12B runner
  -> privacy-safe observational artifacts
  -> official Base answers unchanged
```

The official CSV must be byte-identical to the corresponding Base-only run. V13, selector code, the
legacy V12B runner, legacy target selection, answer replacement, Phase 3B, threshold finalization, and
default promotion remain out of scope.

## 9. Integration point

The correct integration point is after Base predictions and score/router metadata are available, and
before any V12B artifact is written.

Recommended future flow:

1. Parse arguments and reject illegal mode combinations.
2. Load input records and the single `QwenMCQPredictor`.
3. Generate Base answers exactly once per record and append official rows.
4. Compute choice scores exactly once per record when any scoring-dependent mode is active.
5. Build one set of `ShadowRoutingInput` records and run the router once when either Phase 2 shadow or
   V12B shadow is active.
6. Construct `V12BRunInput` only from router-selected decisions that pass the 3A-1 validation boundary.
7. Call `run_v12b_for_selected` once with the already-loaded backend instance.
8. Write official Base CSV independently of V12B outcomes.
9. Write privacy-safe V12B artifacts in a final best-effort section.

No official row should ever receive a value from `hypothetical_answer`.

## 10. Score/router reuse plan

Extend the existing `want_score` logic to include V12B shadow:

```text
want_score = confidence_telemetry or confidence_shadow_router or confidence_v12b_shadow
```

When `want_score` is true, each record gets at most one `score_choices` call. The same score dictionary
feeds telemetry, router input construction, and V12B input construction.

When V12B shadow is enabled, router selection is required even if `--confidence-shadow-router` is not
requested. If both Phase 2 shadow and V12B shadow are requested, run the router once and share the same
decision list for both artifact families.

If choice scoring is disabled or the router config is malformed, V12B shadow must fail closed: no V12B
execution, no official-output change, and only a privacy-safe warning/status.

## 11. Backend-instance injection plan

`QwenMCQPredictor` currently stores the backend as private `self._backend`; public methods are
`load`, `predict_one`, and `score_choices`. There is no public backend accessor.

Do not call `get_local_qwen_backend` again during Phase 3A-1. The backend cache is keyed by raw
`(model_path, device)`, so spelling differences can create a second backend instance. Do not access
`predictor._backend` directly in production integration.

Recommended future source change:

```python
@property
def backend(self) -> LocalQwenBackendProtocol:
    return self._backend
```

Requirements for that accessor:

- read-only property, no setter;
- returns the exact existing backend instance;
- performs no model loading, path resolution, cache lookup, or backend replacement;
- typed against the existing backend protocol or concrete backend type;
- unit test proves `predictor.backend` is the same object already used by `predict_one` and
  `score_choices`.

Phase 3A-1 then calls:

```python
run_v12b_for_selected(v12b_inputs, backend=predictor.backend, ...)
```

## 12. Input-validation boundary

AUDIT 85 L1 should be resolved at the Phase 3A-1 construction boundary before creating
`V12BRunInput`.

For each router-selected record validate:

- the source record is a mapping/object with expected keys;
- `qid` is serializable metadata, not a uniqueness key;
- `question` is a string;
- `choices` is a non-string, non-bytes sequence;
- choice count is in `1..26`, matching `labels_for`;
- canonical labels are exactly `tuple(labels_for(len(choices)))`;
- no duplicate canonical labels;
- Base answer is a valid label for that record;
- Base top1/top2 are valid labels or `None` under a documented scoring-invalid contract;
- non-`None` margin and entropy values are finite;
- router-selected rank is a positive integer;
- `input_index` is preserved as metadata but not treated as unique.

Invalid selected records must not call V12B. They should produce a closed observational
input-validation diagnostic if artifact writing succeeds, retain the Base official answer, and not
abort other selected records.

## 13. AUDIT 85 L1 resolution plan

Add a Phase 3A-1-only helper, for example `_build_v12b_inputs_from_router(...)`, that returns:

- valid `V12BRunInput` objects;
- per-selected-record wrapper metadata containing original record ordinal, qid, input_index, selected
  rank, and validation status;
- closed input-validation error records for invalid selected inputs.

Do not change the approved Phase 3A-0 runner for L1 in the first Phase 3A-1 implementation unless a
separate review requires it. The integration boundary is sufficient because `predict.py` owns the
conversion from raw dataset records and router decisions into runner inputs.

Recommended closed input-validation codes for the Phase 3A-1 artifact wrapper:

- `ok`
- `invalid_record_shape`
- `invalid_question`
- `invalid_choices`
- `unsupported_choice_count`
- `invalid_canonical_labels`
- `invalid_base_answer`
- `invalid_score_diagnostic`
- `invalid_router_rank`
- `input_validation_error`

No code may include question text, choice text, raw exceptions, or arbitrary field values.

## 14. AUDIT 85 L2 resolution plan

Use Option A for the first Phase 3A-1 implementation:

- do not expose `consensus_votes` in YAML or CLI;
- do not expose `min_valid_permutations` in YAML or CLI;
- call Phase 3A-0 with default `min_valid_permutations = 5` and `consensus_votes = 4`;
- label both as provisional diagnostics;
- do not modify the already approved Phase 3A-0 runner just to align custom thresholds.

Option B, aligning hypothetical acceptance to a configurable status threshold, should be deferred to a
separately reviewed runner correction before any threshold configurability is exposed.

## 15. CLI flags and mode combinations

Recommended explicit flags:

- `--confidence-v12b-shadow`
- `--v12b-shadow-path` with default `scratch/fastmcq_run/confidence_v12b_shadow.jsonl`
- `--v12b-shadow-summary-path` with default
  `scratch/fastmcq_run/confidence_v12b_shadow_summary.json`

Do not add a broad `--confidence-config` flag in the first 3A-1 pass unless a separate scope decision
requires changing Phase 1/2 config behavior.

Required combinations:

| Combination | Required behavior |
|---|---|
| no flags | Current behavior unchanged. |
| `--confidence-telemetry` only | Current telemetry behavior unchanged. |
| `--confidence-shadow-router` only | Current Phase 2 shadow behavior unchanged. |
| `--confidence-v12b-shadow` only | Compute/reuse scoring and router; run V12B only for selected records; write V12B artifacts if possible. |
| telemetry + V12B shadow | One score per record, shared by telemetry and V12B routing. |
| Phase 2 shadow + V12B shadow | One score set and one router decision set; optionally write both artifact families. |
| `--legacy-dynamic-full` + V12B shadow | Explicit error before model load. |
| invalid V12B paths | Warn/status only; preserve official Base output. |

Argument conflicts should be rejected immediately after parsing and before loading the model.

## 16. Config block and field classification

Minimal YAML block:

```yaml
confidence_v12b:
  enabled: false
  observational_only: true
  require_router_selected: true
  permutation_count: 6
  max_new_tokens: 192
```

Classification:

| Field | Classification | Phase 3A-1 rule |
|---|---|---|
| `enabled` | structural/default-disabled marker | CLI flag remains the explicit execution opt-in, matching current Phase 2 convention where YAML `enabled: false` does not run by itself. |
| `observational_only` | structural invariant | Must validate true; false is invalid. |
| `require_router_selected` | structural invariant | Must validate true; false is invalid. |
| `permutation_count` | safe implementation default | Allow only `1..6`; default 6; actual calls still depend on unique permutations. |
| `max_new_tokens` | safe implementation default | Positive integer; default 192. |
| `min_valid_permutations` | provisional diagnostic | Do not expose in first 3A-1. |
| `consensus_votes` | provisional diagnostic with AUDIT 85 L2 caveat | Do not expose in first 3A-1. |
| merge threshold/answer override | forbidden | No config field. |
| balanced policy | forbidden | No config field. |
| self-reported confidence | forbidden | No config field. |
| V13/selector switch | forbidden | No config field. |

Malformed V12B config must disable V12B shadow and preserve Base official output.

## 17. V12B input-construction schema

For each selected record, construct:

```text
V12BRunInput(
  qid=str(qid),
  input_index=int(input_index),
  question=question,
  choices=tuple(choices),
  canonical_labels=tuple(labels_for(len(choices))),
  base_answer=base_answer,
  router_selected_rank=decision.selected_rank,
  router_candidate_reasons=tuple(decision.candidate_reasons),
  base_top1=decision.top1,
  base_top2=decision.top2,
  base_logit_margin=decision.logit_margin,
  base_normalized_entropy=decision.normalized_entropy,
)
```

Keep wrapper metadata outside the runner:

- original source record ordinal;
- selected-sequence ordinal;
- qid;
- input_index;
- selected_rank;
- validation code.

Pair wrapper metadata and runner results by list position only, never by qid or input_index.

## 18. Privacy-safe per-record artifact schema

Per-record JSONL rows may include:

- `observational_only: true`
- `qid`
- `input_index`
- original `record_ordinal` or equivalent stable occurrence identity
- selected-sequence ordinal
- `router_selected_rank`
- `router_candidate_reasons`
- Base answer
- Base top1/top2
- Base margin
- Base entropy
- input-validation status/code
- `v12b_attempted`
- `official_answer_source: "base"`
- aggregate result fields from `V12BAggregateResult.as_dict()`
- permutation result fields from `V12BPermutationResult.as_dict()`

Allowed permutation metadata includes labels-only `permuted_to_original`, mapped labels, parse status,
validity, closed error codes, and optional exception class name.

Forbidden fields:

- question text;
- choices;
- option text;
- selected option text;
- prompts;
- raw model output;
- evidence;
- reasoning;
- model confidence;
- expected answers;
- correctness;
- ground truth;
- API keys;
- arbitrary exception text.

## 19. Summary schema

Summary JSON may include:

- `observational_only: true`
- total input records
- total router candidates
- total router-selected records
- total V12B attempted records
- total V12B skipped-invalid records
- total V12B failed records
- total permutation attempts
- total valid permutations
- parse-failure total
- generation-failure total
- input-validation error counts
- aggregate-status counts
- Base/V12B disagreement count
- selected qids in risk-rank order, duplicates allowed
- selected items with qid, input_index, selected rank, and stable occurrence identity
- artifact writer status, if written without private text

No expected answers, correctness, ground truth, question text, choices, prompts, raw responses, or raw
exception messages.

## 20. Artifact writer/failure semantics

Phase 3A-1 owns all artifact writing. Phase 3A-0 remains write-free.

Recommended writer behavior:

- build per-record dictionaries in memory;
- validate JSON compatibility with `json.dumps(..., allow_nan=False)`;
- write JSONL and summary via temporary files followed by rename when practical;
- use deterministic key ordering where practical;
- catch `OSError`, `ValueError`, and serialization errors;
- warn with exception class name only, never `str(exc)` if it may include private text;
- preserve official Base output regardless of writer failure.

Safest ordering:

1. Build official Base rows and times.
2. Build optional diagnostics in memory.
3. Write `submission.csv` and `submission_time.csv` from Base rows.
4. Write V12B artifacts best-effort after official output exists.

If the implementation keeps the current Phase 2 artifact-before-official shape, it must still prove
that every V12B runner, serialization, mkdir, write, and rename failure cannot bypass the final
official CSV write.

## 21. Official-output invariance contract

Future tests must prove byte identity against the corresponding Base-only run for:

- no flag;
- Phase 2 shadow only;
- V12B shadow;
- telemetry + V12B shadow;
- Phase 2 shadow + V12B shadow;
- V12B backend exceptions;
- malformed selected input;
- artifact writer failure;
- no selected records;
- selected records below cap;
- selected records at cap.

The official CSV schema and row order remain unchanged. `hypothetical_answer` must never be copied
into an official row.

## 22. Identity and duplicate-record handling

Never associate records by qid alone. Never assume `input_index` is unique.

Use these identities:

- original source record ordinal from `enumerate(samples)`;
- router decision list position, which matches input order;
- router `selected_rank` for risk-rank metadata;
- selected-sequence ordinal used by `run_v12b_for_selected`;
- qid and input_index as non-unique metadata.

For duplicate qids, duplicate input indexes, both duplicated, or identical question/choice text, pair
selected inputs, wrapper metadata, and V12B results by stable list position. Summaries must count
records, not unique qids.

## 23. No-V13/no-selector/no-legacy guarantees

Phase 3A-1 must not import or call:

- V13 modules;
- selector code;
- `run_v12b_layer`;
- `select_v12b_targets`;
- legacy V12B record writers;
- `src/system/fastmcq_system.py`;
- external APIs.

Add static and monkeypatch tests proving those paths are not reached under V12B shadow.

## 24. Future unit-test plan

CLI/config tests:

- default disabled;
- flag parsing;
- malformed `confidence_v12b` config;
- conflict with `--legacy-dynamic-full`;
- no answer-changing, balanced-policy, self-confidence, V13, or selector setting.

Input-construction tests:

- valid 3/4/5/10-choice records;
- string choices;
- bytes choices;
- zero choices;
- over-supported choice count;
- canonical-label mismatch;
- duplicate labels;
- invalid Base answer;
- non-finite score diagnostics;
- duplicate qid/input_index combinations;
- invalid selected record followed by valid records.

Backend/accessor tests:

- read-only accessor returns the exact existing backend instance;
- no second `get_local_qwen_backend` lookup;
- fake backend supports `generate_text` signature.

Artifact helper tests:

- `allow_nan=False`;
- closed error codes only;
- labels-only mappings;
- no private text fields;
- no arbitrary exception text;
- temporary-write failure handling.

## 25. Future integration-test plan

Predict-path tests with fake predictors/backends:

- Base generation not duplicated;
- scoring runs once per record when telemetry/router/V12B modes combine;
- router runs once per decision set;
- V12B runs only for router-selected records;
- one backend/model instance is used;
- up-to-six V12B calls per selected record;
- no selected records creates empty V12B artifacts and unchanged official CSV;
- V12B record failure and all-record failure preserve official CSV;
- artifact directory/JSON/summary failures preserve official CSV;
- malformed config and invalid selected input fail closed;
- official CSV byte equality against Base-only output;
- qid order, answer values, and row count unchanged;
- no V13, selector, legacy V12B, or external API call.

## 26. Future Windows real-model validation plan

Do not run now. Later validation should use the already accepted local Windows Docker/model setup and
remain observational.

Coverage:

- 21-item synthetic diagnostic set;
- at least one selected record;
- no-selected case;
- selected count below and equal to cap;
- valid and invalid structured V12B outputs when observable;
- actual permutation call counts;
- elapsed runtime;
- peak GPU memory;
- artifact privacy;
- official CSV byte invariance;
- no V13/selector/legacy path.

Do not claim accuracy improvement from this validation.

## 27. Exact implementation file scope

Likely future modified files:

- `predict.py`
- `src/local_model/confidence_config.py`
- `configs/confidence_selective.yaml`
- `src/local_model/qwen_mcq_predictor.py` only for the read-only backend accessor

Possible new file:

- `src/local_model/confidence_v12b_artifacts.py` or similar, if keeping privacy-safe writer logic out
  of `predict.py` is cleaner.

Likely future tests:

- focused config/CLI unit tests;
- Phase 3A-1 predict-path integration tests with fake predictor/backend;
- accessor tests in the local backend/predictor test area.

## 28. Files that must remain unchanged

Must remain unchanged unless a separate reviewed correction is authorized:

- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`
- `src/layers/mcq_permutation_debiaser.py`
- `src/layers/v12b_dynamic_layer.py`
- `src/system/fastmcq_system.py`
- V13 files
- selector files
- Docker/dependency files
- official CSV schema/writer semantics
- Phase 1/2 scoring and router semantics
- existing audits

## 29. Recommended implementation sequence

Safest practical split:

1. 3A-1a: add config schema/validation, CLI flags, conflict checks, and predictor backend accessor;
   no V12B execution yet.
2. 3A-1b: add selected-input validation, backend injection, runner call, and in-memory result pairing;
   official answers unchanged.
3. 3A-1c: add privacy-safe V12B artifact writer and artifact-failure isolation.
4. 3A-1d: independent implementation review.
5. 3A-1e: Windows real-model observational validation.

3A-1a through 3A-1c may be one implementation task only if the diff remains tightly scoped and the
test suite covers every contract above. The safer reviewable split is separate 3A-1a, 3A-1b, and
3A-1c passes.

## 30. Risk register

| Risk | Location | Severity | Mitigation | Required future test |
|---|---|---:|---|---|
| Malformed selected input | V12B input construction | Medium | Validate before `V12BRunInput`; emit closed input error; skip V12B for that record. | string/bytes/zero/>26 choices, invalid labels, invalid Base answer. |
| qid/index collision | Router-to-runner pairing | Medium | Pair by original ordinal and list position, not qid/input_index. | duplicate qid, duplicate input_index, both duplicated. |
| Duplicated scoring | `predict.py` opt-in modes | Medium | One shared `want_score` branch for telemetry/router/V12B. | combined modes score-call count equals N. |
| Duplicated router execution | `predict.py` shadow modes | Medium | One router decision set shared by Phase 2 and V12B. | monkeypatch router call count. |
| Duplicate backend/model load | Backend injection | Medium | Read-only accessor returns existing backend; no second cache lookup. | backend identity/load-count test. |
| Invalid V12B config | Config loader | Low | Validate and disable V12B fail-closed. | malformed config preserves official CSV. |
| Legacy mode conflict | CLI | High | Reject `--legacy-dynamic-full` + V12B shadow before model load. | parser/conflict integration test. |
| Artifact privacy leak | Writer schema | High | Whitelist fields; forbid text/raw output; marker tests. | artifact marker privacy tests. |
| Arbitrary exception leak | Runner/writer warnings | Medium | Store exception class only; do not serialize `str(exc)`. | exception message marker absent. |
| Non-finite JSON | Artifact serialization | Medium | Scrub/validate finite values; `allow_nan=False`. | NaN/Inf diagnostics fail closed. |
| Partial artifact | Writer | Low | temp/write-then-rename; document temp leftovers. | summary/JSONL write failure tests. |
| Official answer override | `predict.py` row handling | High | Official rows built only from Base answer; no merge helper. | byte-identical CSV tests. |
| V13/selector invocation | Imports/calls | High | Static and monkeypatch guards. | forbidden-call tests. |
| Legacy V12B invocation | Imports/calls | High | Use only Phase 3A-0 runner. | forbidden `run_v12b_layer`/`select_v12b_targets` tests. |
| Threshold/status inconsistency | V12B config | Low | Do not expose consensus thresholds in 3A-1. | config has no consensus field. |
| Windows/Linux path differences | Artifact paths | Low | Use explicit paths and `Path`; no hard-coded separators. | tmp path tests; later Windows validation. |
| Runtime cost from permutations | V12B runner | Informational | V12B only selected records; cap inherited from router; record counts. | selected count/call count tests. |
| Prompt/JSON adherence on real model | Real V12B behavior | Informational | Later Windows real-model observational validation. | real-model validation only after approval. |

## 31. Open decisions

- Whether 3A-1a through 3A-1c are separate commits/tasks or one tightly scoped implementation pass.
- Exact artifact helper module name if writer logic is factored out of `predict.py`.
- Whether to reorder existing Phase 2 telemetry/router artifact writes after official CSV, or keep
  Phase 2 ordering unchanged and apply the after-official rule only to V12B artifacts.
- Whether `confidence_v12b.enabled` remains a validated marker like current `shadow_router.enabled`,
  or becomes a required config gate in addition to the CLI flag. The first pass should preserve the
  current CLI-as-opt-in convention.

None of these block planning. They must be decided before or during the reviewed 3A-1 implementation.

## 32. Promotion limitations

This plan does not authorize:

- Phase 3A-1 implementation;
- Phase 3B;
- answer replacement;
- V13;
- selector behavior;
- default promotion;
- final threshold selection;
- ground-truth calibration;
- claims of accuracy improvement.

## 33. Explicit confirmation

This planning pass made no source, test, or config change; did not implement Phase 3A-1; did not run
real model/V12B inference; did not change answers; did not invoke V13/selector; did not finalize any
threshold; did not use organizer ground truth; did not call an API/OpenRouter; did not download a
model; and did not commit or push.

## 34. Current git status

Current verified status after creating this audit:

```text
?? docs/audits/86-phase3a1-observational-v12b-integration-plan.md
```

No other file should be changed or untracked.

## 35. Recommended next action

Send AUDIT 86 for independent review before implementing Phase 3A-1. If approved, implement 3A-1 in
the staged order above with fake-only tests first, then a separate Windows real-model observational
validation pass.

## 36. Final verdict

PHASE 3A-1 PLAN READY FOR INDEPENDENT REVIEW
