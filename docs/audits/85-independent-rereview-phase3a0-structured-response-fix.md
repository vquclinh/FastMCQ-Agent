# AUDIT 85 - Independent Re-Review of Phase 3A-0 Structured Response Fix

## 1. Date, branch, starting HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `80554f6c4c863c02666d83031040d2006a79e5f7`
- Starting commit: `document phase 3 V12B implementation plan`

## 2. Initial working-tree state

Preflight matched the requested re-review state.

```text
git branch --show-current
main

git rev-parse HEAD
80554f6c4c863c02666d83031040d2006a79e5f7

git status --short
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md
?? docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

`git diff --check`, `git diff --stat`, `git diff --name-only`,
`git diff --cached --check`, `git diff --cached --stat`, and
`git diff --cached --name-only` produced no output. The index was empty.

## 3. Independent/read-only statement

This is an independent, adversarial, read-only re-review of the corrected Phase 3A-0 implementation.
I inspected the source and tests directly and used fake-backend probes. I did not modify production
code, tests, configs, or AUDIT 78-84. The only file created by this pass is this audit.

## 4. Context reconstruction

Phase 1 and Phase 2 are complete and committed. Phase 3A-0 is implemented and corrected but remains
uncommitted and not independently approved before this audit. Phase 3A-1 and Phase 3B remain
unauthorized. AUDIT 80 governs over AUDIT 78; AUDIT 81 authorized only isolated Phase 3A-0; AUDIT 83
found the blocking malformed-structured-response defect; AUDIT 84 claims to fix it.

## 5. Governing audits reviewed

Read completely:

- `docs/audits/78-phase3-confidence-routed-v12b-planning.md`
- `docs/audits/79-independent-review-phase3-v12b-plan.md`
- `docs/audits/80-phase3-v12b-plan-corrections.md`
- `docs/audits/81-independent-review-phase3-v12b-plan-corrections.md`
- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`
- `docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md`
- `docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md`

## 6. Files/source/tests reviewed

Read completely:

- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`
- `src/layers/mcq_permutation_debiaser.py`
- `src/local_model/local_qwen_backend.py`
- `src/utils/labels.py`

Also inspected imports, forbidden-symbol searches, backend signatures, and focused fake-backend probe
outputs.

## 7. Exact corrected call graph

`run_v12b_for_selected` materializes selected inputs, enumerates them to assign private
`record_ordinal`, and calls `_run_one_record` for each input.

`_run_one_record` builds a fresh sample dictionary, calls `build_option_permutations`, then calls
`_run_one_permutation` once per unique permutation.

`_run_one_permutation` builds a minimal prompt, calls only the injected `backend.generate_text`,
parses with `parse_json_object`, validates the structured response, then calls
`map_permuted_answer_to_original` only after schema validation passes.

`_aggregate_record` converts permutation results to vote records, calls
`summarize_permutation_votes`, derives vote leaders/status/counters, and calls
`select_permutation_override(summary, policy="conservative")` only for diagnostic hypothetical output.

`_build_summary` aggregates text-free counts and selected item identities. No call path reaches
legacy V12B, V13, selector, `predict.py`, artifact writers, config loaders, or official-output code.

## 8. Strict Phase 3A-0 scope re-verification

The corrected production runner still does not import or call:

- `run_v12b_layer`
- `select_v12b_targets`
- legacy system code
- V13
- selector code
- `predict.py`
- YAML/config loading
- `get_local_qwen_backend`
- model/backend constructors
- model environment lookup
- file write helpers
- JSONL writers
- official-output mutation or answer replacement

Production forbidden-symbol scan returned no matches for:

```text
run_v12b_layer|select_v12b_targets|get_local_qwen_backend|v12b_dynamic_records|V13|selector|legacy_dynamic_full|submission|pred\.csv|open\(|write_text|write_bytes|mkdir|confidence
```

Test-file matches were limited to negative assertions, monkeypatch guards, and privacy fixtures.

## 9. Structured-response schema-gate review

Source evidence: `src/local_model/confidence_v12b_runner.py:382-424`.

The gate now requires before mapping:

- `selected_label` is present, is `str`, and is non-empty after stripping.
- `selected_option_text` is present, is `str`, and is non-empty after stripping.
- `label_matches_option` has exact type `bool`.

Missing/null/empty selected labels return `missing_selected_label`. Wrong label type, malformed
option text, and missing/non-Boolean self-check values return `invalid_response_schema`.

This fixes AUDIT 83's unsafe path for incomplete structured responses.

## 10. Strict Boolean review

The implementation uses `type(label_matches_option) is not bool`, which rejects truthy/falsy
non-Boolean values including `"false"`, `"true"`, `0`, `1`, floats, lists, and dictionaries. Probe
results confirm all such cases produce `invalid_response_schema`, zero valid votes, and no
hypothetical acceptance.

Real `True` proceeds to the mapper and can produce valid votes. Real `False` proceeds to the mapper,
which returns `label_option_mismatch`; this is fail-closed and produces zero valid votes. This is a
minor boundary nuance because the re-review checklist preferred direct pre-mapper handling for
Boolean `False`, but there is no vote, acceptance, or privacy impact.

## 11. Mapper-call boundary review

In-process monkeypatch probe results:

| Case | Mapper calls | Result |
|---|---:|---|
| missing `selected_option_text` | 0 | `invalid_response_schema`, 0 valid |
| empty `selected_option_text` | 0 | `invalid_response_schema`, 0 valid |
| non-string `selected_option_text` | 0 | `invalid_response_schema`, 0 valid |
| missing `label_matches_option` | 0 | `invalid_response_schema`, 0 valid |
| string `label_matches_option` | 0 | `invalid_response_schema`, 0 valid |
| real Boolean `False` | 6 | `label_option_mismatch`, 0 valid |
| real Boolean `True` with exact option text | 6 | `ok`, 6 valid |

The AUDIT 83 malformed-schema path no longer reaches the mapper. Boolean `False` is the only
non-`True` value that reaches the mapper, and it fails closed.

## 12. AUDIT 83 probe reproduction

Fake-backend probes reproduced the previous failure inputs:

| Probe | Result |
|---|---|
| `{"selected_label": "B"}` | all 6 invalid; `invalid_response_schema`; 0 valid; empty votes; `all_invalid`; no hypothetical answer; acceptance false; source `base` |
| `label_matches_option: "false"` | all 6 invalid; `invalid_response_schema`; 0 valid; no acceptance |
| `label_matches_option: "true"` | all 6 invalid; `invalid_response_schema`; 0 valid; no acceptance |
| real `label_matches_option: false` | all 6 invalid; `label_option_mismatch`; 0 valid; no acceptance |
| real `label_matches_option: true` with exact matching option text | 6 valid; `ok`; winning vote counted; diagnostic hypothetical acceptance possible; source still `base` |

M1's unsafe vote/acceptance behavior is fixed.

## 13. Exhaustive field-type matrix results

Selected-label cases:

- missing, null, empty string, whitespace -> `missing_selected_label`, mapper not called, 0 votes.
- integer, Boolean, list, dict -> `invalid_response_schema`, mapper not called, 0 votes.
- valid string with other valid fields -> mapper called, valid votes possible.

Selected-option-text cases:

- missing, null, empty string, whitespace, integer, Boolean, list, dict -> `invalid_response_schema`,
  mapper not called, 0 votes.
- valid exact string with other valid fields -> mapper called, valid votes possible.

`label_matches_option` cases:

- missing, null, empty string, `"false"`, `"true"`, `0`, `1`, float, list, dict ->
  `invalid_response_schema`, mapper not called, 0 votes.
- real `False` -> mapper called, `label_option_mismatch`, 0 votes.
- real `True` -> mapper called, valid votes possible.

All public error codes belonged to `V12BErrorCode`. No raw field value or raw response appeared in
`as_dict()` JSON.

## 14. Closed error-code review

`V12BErrorCode` includes `invalid_response_schema`. Public result fields use only enum values or
exception class names. `str(exc)` is not retained. Unknown mapper reasons map to `aggregate_error`.

Schema-invalid results use `parse_status = "ok"` because JSON parsing succeeded, but `_vote_record`
sets `mapped_original_label = None`, `label_option_match = False`, `valid = False`, and a closed
failure reason. `summarize_permutation_votes` excludes them; parse status alone does not make a vote
valid.

## 15. Vote-exclusion/aggregation review

Aggregation probes:

- 5 schema-invalid + 1 valid -> 1 valid vote, `insufficient_valid_permutations`, no acceptance.
- 1 schema-invalid + 5 valid -> 5 valid votes, `valid_unique_majority`, diagnostic acceptance true.
  The schema-invalid result is excluded; acceptance is based only on the five valid votes.
- schema-invalid + generation errors -> 0 valid, `all_invalid`, no acceptance.
- schema-invalid + parse errors -> 0 valid, `all_invalid`, no acceptance.

This is coherent with the raw-count contract. Schema-invalid responses never enter vote counts.

## 16. Unit-test-quality review

The corrected unit tests now explicitly cover:

- only `selected_label`;
- missing/null/empty/whitespace/non-string `selected_option_text`;
- missing/null/string/integer `label_matches_option`;
- missing/null/empty `selected_label`;
- wrong-type `selected_label`;
- real Boolean `False`;
- complete valid response path;
- zero votes and no hypothetical acceptance for schema-invalid responses;
- closed code and JSON safety for schema-invalid responses;
- raw response marker exclusion.

Remaining minor test gaps: list/dict `label_matches_option`, Boolean `selected_label`, and explicit
mapper-call-count assertions are covered by this audit's probes but not by committed tests. They are
not blocking because the implementation source and probe behavior are clear.

## 17. L1 input-validation reassessment

AUDIT 83's L1 remains Low.

Probe results:

- Plain string `choices` are iterated as character options and can produce valid votes.
- `bytes` choices become integer-derived strings and can produce valid votes.
- Zero choices make one backend call and fail closed to `all_invalid`.
- More than 26 choices with explicit labels fail closed as a record-level `aggregate_error` before any
  backend call.
- More than 26 choices without explicit labels raise `ValueError` during `V12BRunInput` construction.
- Duplicate/mismatched canonical labels are accepted and can still produce valid diagnostics because
  the permutation core uses actual choice count.
- An invalid >26-choice record followed by a valid record preserves order and produces
  `aggregate_error` then `valid_unique_majority`.
- A non-`V12BRunInput` object aborts with `AttributeError`.

These are caller-contract hardening gaps. They can produce misleading diagnostics under malformed
caller inputs, but normal Phase 3A-1 construction should pass validated MCQ records. They do not
change official answers or leak text.

## 18. L2 threshold-alignment reassessment

AUDIT 83's L2 remains Low.

With `consensus_votes=5`:

- 4-vote unique winner -> aggregate status `valid_weak_consensus`, but hypothetical conservative
  acceptance is `true`.
- 5-vote unique winner -> `valid_unique_majority`, acceptance `true`.

Source reason: aggregate status uses caller-supplied `consensus_votes`
(`confidence_v12b_runner.py:655-657`), while `select_permutation_override` uses the legacy fixed
conservative rule `best >= 4` (`mcq_permutation_debiaser.py:243-244`), and the runner calls it for
both unique-majority and weak-consensus statuses (`confidence_v12b_runner.py:490-494`).

Defaults remain coherent. This should be aligned before Phase 3A-1 exposes thresholds through config,
but it does not block committing this observational Phase 3A-0 runner.

## 19. Backend/import-side-effect review

Signature probe:

```text
LocalQwenBackend.generate_text
(self, prompt_or_messages: 'str | list[dict[str, str]]', *, max_new_tokens: 'int | None' = None, temperature: 'float' = 0.0) -> 'str'

V12BBackendProtocol.generate_text
(self, prompt_or_messages: 'str | list[dict[str, str]]', *, max_new_tokens: 'int | None' = None, temperature: 'float' = 0.0) -> 'str'
```

The runner passes a chat-message list as the sole positional argument and uses the matching keyword
names. Import probe after importing the runner showed no `torch`, `transformers`,
`src.layers.v12b_dynamic_layer`, or `predict` module loaded. Importing `parse_json_object` from
`local_qwen_backend.py` has no model/network/file side effect.

## 20. JSON/privacy review

`json.dumps(..., allow_nan=False)` succeeded for valid, parse-error, invalid-schema, Boolean-false
mismatch, generation-error, all-invalid, mixed valid/invalid, and summary dictionaries.

Marker probes found no returned question text, choices, option text, selected option text, prompt, raw
response, evidence, reasoning, confidence, expected answer, ground truth, or arbitrary exception
message. Exception class names only are retained.

## 21. Identity/permutation/immutability/no-filesystem regression review

Original invariants remain intact:

- private `record_ordinal` assigned by enumeration;
- duplicate qids and duplicate input indexes remain distinct;
- output order equals input order;
- up-to-six unique permutations are produced by the pure core;
- one backend call per returned unique permutation;
- `permuted_to_original` contains labels only;
- no caller-owned choices/reasons mutation in tested paths;
- no filesystem write/open/mkdir in production runner;
- no config loading or global backend lookup;
- `official_answer_source` is always forced to `base`;
- balanced policy is unreachable;
- self-reported confidence is not parsed, stored, or used.

## 22. Exact test commands and results

Runner tests:

```text
pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q
47 passed in 0.23s
```

Permutation core:

```text
pytest tests/unit/test_mcq_permutation_debiaser_2l34c.py -q
15 passed in 0.12s
```

Phase 1/2 confidence regression group:

```text
pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py -q
89 passed in 0.60s
```

Local backend tests:

```text
pytest tests/unit/test_local_qwen_backend.py -q
4 passed in 0.10s
```

Legacy V12B integration baseline:

```text
pytest tests/integration/test_v12b_permutation_2l34b.py -q
5 passed, 2 failed in 0.36s
```

Compile/static:

```text
python -m compileall src/local_model/confidence_v12b_runner.py tests/unit/test_confidence_v12b_runner_2l49a.py
passed

git diff --check
passed with no output
```

## 23. Known unrelated baseline failures

The two legacy V12B integration failures are exactly the known baseline:

- `test_selector_validates_and_no_change_on_empty`
- `test_frozen_v11_md5_stable`

Both fail with `FileNotFoundError` for:

```text
output/pred_v11_independent_rerun1.csv
```

No other failure was observed.

## 24. Findings table

No Critical, High, or Medium findings.

| ID | Severity | Source location | Direct evidence | Impact | Blocks committing Phase 3A-0? | Blocks Phase 3A-1? | Smallest recommended correction |
|---|---|---|---|---|---|---|---|
| L1 | Low | `confidence_v12b_runner.py:80-84` | Plain string/bytes choices are accepted as iterables; zero choices make one backend call; >26 without labels raises at construction; non-`V12BRunInput` aborts. | Caller misuse can produce misleading diagnostics or abort outside the selected-input contract. | No | No, but validate 3A-1 input construction. | Validate choices as a non-string sequence, enforce choice/label count consistency, and reject invalid selected inputs before generation. |
| L2 | Low | `confidence_v12b_runner.py:490-494`, `:655-657`; `mcq_permutation_debiaser.py:243-244` | With `consensus_votes=5`, a 4-vote winner is `valid_weak_consensus` but conservative hypothetical acceptance is true. | Custom thresholds can make status naming and hypothetical acceptance semantics diverge. | No | No for planning; align before exposing config. | Tie hypothetical acceptance to the same threshold used for aggregate status or keep the legacy threshold fixed and documented. |
| L3 | Low | `confidence_v12b_runner.py:415-429` | Real Boolean `False` reaches `map_permuted_answer_to_original`; mapper returns `label_option_mismatch`, 0 valid votes. | Fail-closed behavior is correct, but the boundary is not as strict as the re-review checklist's direct pre-mapper preference. | No | No | Return `label_option_mismatch` directly before the mapper when `label_matches_option is False`, and add a mapper-call-count unit test. |
| T1 | Low | `tests/unit/test_confidence_v12b_runner_2l49a.py:318-344` | Tests cover key malformed schema cases but not list/dict self-check values or mapper-call counts; probes covered them. | Minor test coverage gap for future regression resistance. | No | No | Add parameter cases for list/dict self-check and direct mapper-boundary tests. |
| I1 | Informational | Whole Phase 3A-0 | No real local-model/V12B run by design. | Real JSON adherence/runtime remains unknown until later authorized validation. | No | No | Validate only after separate Phase 3A-1 planning/review. |
| I2 | Informational | `local_qwen_backend.py` parser import | Parser import has no side effect but couples runner to backend module. | Acceptable for 3A-0; possible future cleanup. | No | No | Optionally move parser to a smaller utility if reuse grows. |

Finding counts: Critical 0, High 0, Medium 0, Low 4, Informational 2.

## 25. Required corrections before committing Phase 3A-0

None. The AUDIT 83 Medium blocker is fixed: incomplete structured responses no longer become valid
votes or hypothetical acceptances. Remaining findings are non-blocking caveats.

## 26. Required corrections before Phase 3A-1

Before implementing Phase 3A-1:

- define and validate the selected-input construction boundary so malformed choice/label shapes cannot
  silently reach the runner;
- if Phase 3A-1 exposes `consensus_votes` or related thresholds, align aggregate status and
  hypothetical conservative acceptance semantics;
- keep artifact writers text-free, closed-code-only, and separate from Phase 3A-0.

These are not required before committing Phase 3A-0.

## 27. Files verified changed/created

Expected uncommitted files before this re-review audit:

- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`
- `docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md`
- `docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md`
- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`

This re-review adds only:

- `docs/audits/85-independent-rereview-phase3a0-structured-response-fix.md`

## 28. Files verified unchanged

No tracked files are modified. Specifically unchanged:

- `predict.py`
- `configs/confidence_selective.yaml`
- `src/local_model/confidence_config.py`
- `src/local_model/qwen_mcq_predictor.py`
- `src/layers/mcq_permutation_debiaser.py`
- `src/layers/v12b_dynamic_layer.py`
- `src/system/fastmcq_system.py`
- V13 files
- selector files
- Docker/dependency files
- official-output code
- AUDIT 78, 79, 80, 81, 82, 83, and 84

## 29. Confirmation unauthorized work remains unauthorized

No Phase 3A-1, Phase 3B, answer replacement, V13, selector behavior, CLI/config/YAML work, artifact
writer, official-output change, real model/V12B inference, final threshold, organizer ground truth,
external API/OpenRouter call, model download, commit, or push occurred.

## 30. Current git status

Expected status after this audit creation:

```text
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md
?? docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md
?? docs/audits/85-independent-rereview-phase3a0-structured-response-fix.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

No staged files are expected.

## 31. Final verdict

PHASE 3A-0 SAFE TO COMMIT WITH NON-BLOCKING CAVEATS; READY FOR PHASE 3A-1 PLANNING

This verdict authorizes only committing the Phase 3A-0 files and AUDIT 82-85 after user approval and
planning Phase 3A-1 separately. It does not authorize implementing Phase 3A-1, Phase 3B, answer
replacement, V13, selector behavior, CLI/config work, artifact writing, official-output changes, or
default promotion.
