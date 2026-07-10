# AUDIT 83 - Independent Review of Phase 3A-0 In-Memory V12B Runner

## 1. Date, branch, starting full HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `80554f6c4c863c02666d83031040d2006a79e5f7`
- Starting commit: `document phase 3 V12B implementation plan`

## 2. Initial working-tree state

Preflight matched the expected Phase 3A-0 review state.

```text
git branch --show-current
main

git rev-parse HEAD
80554f6c4c863c02666d83031040d2006a79e5f7

git status --short
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

`git diff --check`, `git diff --stat`, `git diff --name-only`,
`git diff --cached --check`, `git diff --cached --stat`, and
`git diff --cached --name-only` all produced no output. Nothing was staged. There were no tracked
source/test/config modifications.

## 3. Independence/read-only statement

This is an independent, adversarial, read-only review of the uncommitted Phase 3A-0 implementation.
I inspected the implementation, tests, and reachable dependencies directly. I did not modify source,
tests, configs, AUDIT 78-82, or the implementation. The only file created by this review is this audit.

## 4. Codex takeover/context reconstruction

Phase 1 and Phase 2 are complete and committed. Phase 3A-0 is implemented but uncommitted and not yet
approved. Phase 3A-1 and Phase 3B remain unauthorized. AUDIT 80 governs over AUDIT 78, AUDIT 81
approved the corrected plan with implementation-time requirements, and AUDIT 82 is an implementation
report whose claims were checked against code.

## 5. Governing audits reviewed

Read completely:

- `docs/audits/69-pre-phase2-next-token-logit-scoring.md`
- `docs/audits/70-independent-review-pre-phase2-logit-scoring.md`
- `docs/audits/71-windows-real-model-revalidation-phase1-scoring.md`
- `docs/audits/72-phase2-confidence-shadow-router.md`
- `docs/audits/73-independent-review-phase2-shadow-router.md`
- `docs/audits/74-phase2-shadow-router-corrective-pass.md`
- `docs/audits/75-independent-review-phase2-corrective-pass.md`
- `docs/audits/76-windows-real-model-validation-phase2-shadow-router.md`
- `docs/audits/77-independent-review-windows-phase2-evidence.md`
- `docs/audits/78-phase3-confidence-routed-v12b-planning.md`
- `docs/audits/79-independent-review-phase3-v12b-plan.md`
- `docs/audits/80-phase3-v12b-plan-corrections.md`
- `docs/audits/81-independent-review-phase3-v12b-plan-corrections.md`
- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`

## 6. Files/source/tests reviewed

Read completely:

- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`
- `src/layers/mcq_permutation_debiaser.py`
- `src/layers/v12b_dynamic_layer.py`
- `src/local_model/local_qwen_backend.py`
- `src/local_model/qwen_mcq_predictor.py`
- `src/local_model/choice_scoring.py`
- `src/local_model/confidence_shadow_router.py`
- `src/utils/labels.py`
- `tests/unit/test_local_qwen_backend.py`

Also ran repository-wide and targeted searches for the requested V12B runner, backend, parser,
identity, legacy, confidence, and official-output symbols.

## 7. Evidence available/unavailable

Available: current uncommitted Phase 3A-0 files, committed source, committed tests, planning audits,
runtime fake-backend tests, source-level call graph, `inspect.signature` probes, JSON/protocol probes,
and import-side-effect probes.

Unavailable by design: real local-model generation, GPU latency/VRAM, Windows Phase 3A runtime
behavior, calibration evidence, organizer ground truth, OpenRouter/API behavior. None was used.

## 8. Exact implementation call graph

`run_v12b_for_selected`:

1. Materializes selected inputs as a tuple.
2. Enumerates inputs and assigns `record_ordinal`.
3. `_run_one_record` builds a fresh sample dictionary.
4. Calls `build_option_permutations(sample, n=permutation_count)`.
5. For each unique permutation, `_run_one_permutation`:
   - builds a minimal chat-message prompt;
   - calls only the injected `backend.generate_text(..., max_new_tokens=..., temperature=0.0)`;
   - parses with `parse_json_object`;
   - maps with `map_permuted_answer_to_original`;
   - returns a text-free `V12BPermutationResult`.
6. `_aggregate_record` builds vote records, calls `summarize_permutation_votes`, derives leaders,
   status, counts, and conservative-only hypothetical diagnostics.
7. `_build_summary` summarizes record counts, permutation counts, statuses, selected qids/items, and
   `observational_only=True`.

No call path reaches `run_v12b_layer`, `select_v12b_targets`, artifact writers, `predict.py`, V13,
selector code, or official-output mutation.

## 9. Strict Phase 3A-0 scope review

Scope is mostly satisfied:

- no `predict.py`, YAML/config, CLI, artifact writer, or integration wiring change;
- no official CSV logic;
- no legacy V12B module change;
- no V13/selector imports;
- no model/backend instantiation;
- no `get_local_qwen_backend`;
- no answer replacement or merge behavior;
- no filesystem writes from the new production runner.

The only production file added is `src/local_model/confidence_v12b_runner.py`, with one new
runner-specific unit-test file and this audit.

## 10. Import-time side-effect review

Importing the new runner imports the pure permutation core, `parse_json_object` from
`local_qwen_backend.py`, and `labels_for`. Importing `local_qwen_backend.py` imports stdlib `os`,
`re`, `json`, `Path`, a logging helper, and choice-scoring definitions, but it does not instantiate a
backend, read the model environment variable, load torch/transformers, open files, create directories,
or touch the backend cache.

Fresh Python probe after importing the runner showed no `torch`, `transformers`,
`src.layers.v12b_dynamic_layer`, V13 module, selector module, or `predict` module loaded.

## 11. Real-backend protocol/signature compatibility

`inspect.signature` results:

```text
LocalQwenBackend.generate_text
(self, prompt_or_messages: 'str | list[dict[str, str]]', *, max_new_tokens: 'int | None' = None, temperature: float = 0.0) -> 'str'

V12BBackendProtocol.generate_text
(self, prompt_or_messages: 'str | list[dict[str, str]]', *, max_new_tokens: 'int | None' = None, temperature: float = 0.0) -> 'str'
```

The runner passes a chat-message list as the sole positional argument and the exact keyword names
`max_new_tokens` and `temperature`. `LocalQwenBackend._render_prompt` accepts a list of message
dictionaries and applies the chat template after loading the already-injected backend. No real-backend
signature mismatch found.

## 12. Minimal prompt/response review

Prompt builder output is a list of `{role, content}` messages. It includes the ephemeral question and
the permuted option labels/texts and requests only:

- `selected_label`
- `selected_option_text`
- `label_matches_option`

It does not request confidence, evidence, reasoning, explanation, or chain-of-thought. The prompt is
not returned in any result. Because messages are plain strings, quotes, Unicode, braces, and multiline
choices are not interpolated into JSON; they remain ephemeral prompt text. Long choices would fail via
the injected backend and become `generation_error`.

Finding M1 below: the runner requests three fields but validates only `selected_label` before treating
a permutation as mappable.

## 13. Parser behavior/coupling review

`parse_json_object` returns a dict or `None`; it does not extract arbitrary A/B/C labels and does not
invent an answer. Fenced or embedded JSON objects are accepted; malformed/non-object output becomes
`parse_error`. Raw output is not retained.

Coupling to `local_qwen_backend.py` is acceptable for Phase 3A-0 because import-time model/network/file
side effects are absent, though future refactoring could move the JSON parser to a smaller utility
module.

## 14. Input-validation review

Expected `V12BRunInput` values work. Duplicate qids and duplicate input indexes remain separate.
Mutable choices/reasons are copied into tuples.

Validation gaps:

- `choices` is accepted as any iterable and converted by iteration; a plain string would be split into
  characters rather than rejected.
- canonical label count, duplicates, and mismatch with choice count are not validated.
- zero choices still produce one empty permutation and one backend call before failing closed to
  `all_invalid`.
- more than 26 choices can fail closed at record level only if canonical labels were supplied; with no
  canonical labels, construction itself raises via `labels_for`.
- non-finite Base margin/entropy are not scrubbed, but they are not currently exposed in results.

These are Low validation gaps for caller misuse. They do not affect the normal Phase 3A-1 path if it
constructs inputs from validated MCQ samples.

## 15. Private ordinal identity review

Confirmed:

- `record_ordinal` is assigned by input enumeration.
- No qid-keyed association map is used in the new runner.
- `input_index` is metadata only and not assumed unique.
- duplicate qid/input_index records remain distinct and output order matches input order.
- summary counts selected records, not unique qids.
- `selected_items` includes `record_ordinal`, `qid`, `input_index`, and `router_selected_rank`, enough
  for future artifact association.

## 16. Permutation count/order/mapping review

Confirmed:

- `build_option_permutations` is reused unchanged.
- one backend call occurs per returned unique permutation.
- no exactly-six assumption in the runner.
- counts are tested for 1/2/3/4/5/10 choices.
- deterministic family order and fixed seed are preserved.
- each permutation result copies `permuted_to_original` directly from the permutation object.
- result objects do not retain `OptionPermutation` or `permuted_choices`, so option text is not
  returned.

Permutation identifiers are unique among returned deduped permutations.

## 17. Complete raw-error normalization review

Covered mappings:

- backend exception -> `generation_error`;
- malformed/non-object JSON -> `parse_error`;
- missing/empty `selected_label` -> `missing_selected_label`;
- `label_out_of_range` -> `label_out_of_range`;
- `self_label_option_conflict` -> `label_option_mismatch`;
- `label_text_conflict` -> `label_text_conflict`;
- `option_text_no_match` -> `option_text_no_match`;
- `no_mapped_label` -> `missing_selected_label`;
- `local_error` -> `generation_error`;
- unknown future mapping reason -> `aggregate_error`.

No arbitrary raw reason is exposed in public fields.

Finding M1: missing `selected_option_text`, missing `label_matches_option`, and non-boolean
`label_matches_option` are not normalized as errors; they can become valid votes.

## 18. Exception isolation/privacy review

Per-permutation backend exceptions are isolated and return invalid `generation_error` results with
exception class name only. `str(exc)` is not returned. Record-level unexpected failures during
permutation construction or aggregation return an `aggregate_error` diagnostic for that record when
the input is a valid `V12BRunInput`.

No prompt, raw response, question, or choice text is returned. A probe with exception messages
containing private question/choice markers did not leak those messages in `as_dict()`.

For wrong object types instead of `V12BRunInput`, the error handler itself can fail while trying to
build an aggregate-error record. This is a Low type-contract limitation.

## 19. Aggregate-status precedence review

Precedence is deterministic:

1. `aggregate_error` is produced by the outer record-level exception handler.
2. `_aggregate_status` returns `generation_failure` if all attempted permutations failed generation.
3. `all_invalid` if no valid votes exist.
4. `insufficient_valid_permutations` if valid votes are below the local minimum.
5. `tie` if enough valid votes have a tied top count.
6. `valid_unique_majority` if the unique winner meets `consensus_votes`.
7. `valid_weak_consensus` otherwise.

Mixed cases are coherent: some generation errors plus zero valid votes become `all_invalid`; some
generation errors plus below-minimum valid votes become `insufficient_valid_permutations`; ties are
detected before weak/strong status.

## 20. Winner/runner-up/tie/consensus review

Winner and runner-up are sorted by vote count descending and canonical label order. Zero valid votes
return no winner/runner-up. One unique label yields no runner-up and a vote margin equal to the winner
votes. Two-way and multi-way top ties are detected via runner-up votes matching winner votes.

`base_v12b_agreement` is `None` for ties or no winner, otherwise a boolean comparing the deterministic
winner to Base. This means insufficient-valid unique winners can still contribute agreement/
disagreement diagnostics; that is measurable but should not be read as calibrated reliability.

## 21. Conservative hypothetical-policy review

The runner calls `select_permutation_override` only with `policy="conservative"`. It never calls
`balanced`, never includes a `confidence` field in vote records, and never uses
`mean_support_confidence`. Official answer source is forced to `"base"` in `V12BAggregateResult`.

Tie, insufficient-valid, all-invalid, generation-failure, and aggregate-error cases have hypothetical
acceptance false under the default thresholds.

Low caveat: if a caller raises `consensus_votes` above the legacy conservative threshold of 4, a
record can be labeled `valid_weak_consensus` while the legacy conservative helper still accepts a
4-vote override hypothetically. Defaults avoid this, but the acceptance/status semantics should be
kept aligned if these parameters are exposed in Phase 3A-1.

## 22. JSON/finite serialization review

`as_dict()` converts enums to `.value`, mapping proxies to dicts, tuples to lists where needed, and
nested permutation/selected-item dataclasses to dictionaries. No backend object or raw permutation
object leaks.

Runner-produced results serialized with `json.dumps(..., allow_nan=False)` for tested valid/failure
paths. `elapsed_seconds` comes from `perf_counter()` and is finite in normal runs. Non-finite
Base-margin/entropy inputs do not currently appear in output. Direct manual construction of result
dataclasses with non-finite floats is not scrubbed, but the public runner does not produce such values
under normal clocks.

## 23. Immutability/caller-isolation review

Input dataclasses are frozen. `choices`, canonical labels, and router reasons are copied into tuples.
Fresh sample dictionaries/lists are built for the permutation core. Result mappings are stored as
`MappingProxyType`, and `as_dict()` returns copies. Repeated runs do not share mutable state.

No mutation of caller-owned choices/reasons was observed in tests or source review.

## 24. No-filesystem/global-lookup review

Production runner source contains no `open`, `Path`, `os`, `mkdir`, `write_text`, `write_bytes`, temp
file, JSONL writer, artifact writer, environment lookup, global backend cache call, model-path
resolution, or logging. It imports no `get_local_qwen_backend`. Targeted grep of the production
runner for forbidden runtime symbols returned no matches except the fixed `official_answer_source`
field when searching for official-source terminology.

## 25. Unit-test quality review

Strengths:

- fake backend enforces call counts;
- 1/2/3/4/5/10 permutation counts;
- success, strong/weak/tie/insufficient/all-invalid/generation-failure statuses;
- mapping conflicts and malformed JSON;
- duplicate identity/order;
- privacy markers and exception-message privacy;
- no filesystem/global-lookup behavior;
- JSON compatibility for representative paths.

Gaps:

- no test for JSON missing `selected_option_text`;
- no test for JSON missing `label_matches_option`;
- no test for non-boolean `label_matches_option`;
- no invalid `choices` shape/canonical-label mismatch tests;
- no test ensuring zero-choice records avoid backend calls;
- static grep tests are useful but not a substitute for import-graph reasoning.

The first three gaps correspond to the blocking implementation finding.

## 26. Exact test/probe commands and results

Preflight and status:

- `git branch --show-current` -> `main`
- `git rev-parse HEAD` -> `80554f6c4c863c02666d83031040d2006a79e5f7`
- `git status --short` -> exactly the three expected untracked Phase 3A-0 files
- `git diff --check`, `git diff --stat`, `git diff --name-only`, `git diff --cached --check`,
  `git diff --cached --stat`, `git diff --cached --name-only` -> no output

Signatures/import probes:

- `inspect.signature(LocalQwenBackend.generate_text)` matched `V12BBackendProtocol.generate_text`.
- Import probe after importing the runner showed no `torch`, `transformers`, V12B legacy layer, V13,
  selector, or `predict` module loaded.

Behavior probe results:

- `{"selected_label": "B"}` repeated across permutations produced valid permutation votes and an
  aggregate `tie` with `valid_permutation_count=6`.
- JSON with `selected_label` and `selected_option_text` but no `label_matches_option` produced
  `valid_unique_majority`, `valid_permutation_count=6`, and hypothetical acceptance true.
- JSON with `label_matches_option: "false"` as a string also produced `valid_unique_majority`,
  `valid_permutation_count=6`, and hypothetical acceptance true.
- zero choices produced one backend attempt and `all_invalid`.
- 27 choices with supplied canonical labels failed closed to `aggregate_error` before any backend
  attempt.

Allowed tests:

```text
pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q
32 passed in 0.19s

pytest tests/unit/test_mcq_permutation_debiaser_2l34c.py -q
15 passed in 0.11s

pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py -q
89 passed in 0.57s

pytest tests/unit/test_local_qwen_backend.py -q
4 passed in 0.10s

pytest tests/integration/test_v12b_permutation_2l34b.py -q
5 passed, 2 failed in 0.35s

python -m compileall src/local_model/confidence_v12b_runner.py tests/unit/test_confidence_v12b_runner_2l49a.py
passed

git diff --check
passed with no output
```

No model weights were loaded.

## 27. Known unrelated baseline failures

The two failures in `tests/integration/test_v12b_permutation_2l34b.py` are exactly the known baseline:

- `test_selector_validates_and_no_change_on_empty`
- `test_frozen_v11_md5_stable`

Both fail with `FileNotFoundError` for:

`output/pred_v11_independent_rerun1.csv`

No different legacy V12B integration failure was observed.

## 28. Findings table ordered by severity

No Critical or High findings.

| ID | Severity | Source location | Direct evidence | Runtime/architectural impact | Blocks committing Phase 3A-0? | Blocks Phase 3A-1? | Recommended smallest correction |
|---|---|---|---|---|---|---|---|
| M1 | Medium | `confidence_v12b_runner.py:381-400`; `mcq_permutation_debiaser.py:160-165` | Runner validates only `selected_label`, then passes missing `selected_option_text`/`label_matches_option` as `None`; mapper treats `label_matches_option is False` only and skips text check when option text is missing. Probe: `{"selected_label":"B"}` produced 6 valid votes; missing/non-boolean `label_matches_option` produced strong majority + hypothetical acceptance. | Incomplete/malformed structured responses can become valid votes and hypothetical acceptances instead of failing closed. This violates the Phase 3A-0 response contract and closed error-normalization requirement. | **Yes** | **Yes** | Require all minimal response keys with correct types before mapping. Normalize missing option text / missing or non-boolean `label_matches_option` to closed invalid codes, and add fake-backend tests for those cases. |
| L1 | Low | `confidence_v12b_runner.py:79-83`; `labels.py:32-35` | `choices` is any iterable and string choices become character options; canonical label count/duplicates are not validated; zero choices still perform one backend call; some >26-choice construction fails before the runner can make a diagnostic. | Caller misuse can produce misleading diagnostics or unnecessary generation, though the normal Phase 3A-1 path should supply valid MCQ choices. | No, after M1 is fixed | No | Validate `choices` as a non-string sequence, canonical label count/uniqueness, supported label range, and fail invalid/zero-choice records before backend calls. |
| L2 | Low | `confidence_v12b_runner.py:432-445`; `mcq_permutation_debiaser.py:241-248` | Aggregate status uses caller-supplied `consensus_votes`, but conservative acceptance always uses the legacy fixed 4-vote threshold. With non-default `consensus_votes > 4`, a `valid_weak_consensus` record could still hypothetically accept. | Default settings are coherent, but exposing thresholds later could make status naming and hypothetical acceptance inconsistent. | No | No, if clarified before config exposure | Either keep `consensus_votes=4` fixed while using the legacy helper, or implement local conservative acceptance tied to the same threshold used for status. |
| I1 | Informational | Whole Phase 3A-0 | No real local-model/V12B run by design. | Prompt adherence, runtime, and real parse rates remain unknown until later authorized validation. | No | No | Validate only after Phase 3A-1 is separately authorized/reviewed. |
| I2 | Informational | `local_qwen_backend.py` import boundary | Parser is imported from a backend module that also defines model/backend classes but has no import-time model side effect. | Acceptable coupling for 3A-0; parser could later move to a smaller utility. | No | No | Optional future refactor if parser reuse expands. |

Finding counts: Critical 0, High 0, Medium 1, Low 2, Informational 2.

## 29. Required corrections before committing Phase 3A-0

M1 must be fixed before committing Phase 3A-0:

- reject or invalidate missing `selected_option_text`;
- reject or invalidate missing/non-boolean `label_matches_option`;
- keep errors in the closed-code set and never persist raw output;
- add unit tests proving these incomplete structured responses do not become votes or hypothetical
  acceptances.

L1 and L2 are recommended non-blocking hardening items, but M1 is sufficient to block the current
implementation.

## 30. Required corrections before Phase 3A-1

Before Phase 3A-1 planning/integration:

- Phase 3A-0 must be corrected and independently re-reviewed.
- If 3A-1 exposes `min_valid_permutations` or `consensus_votes`, align status and conservative
  hypothetical acceptance semantics.
- Validate and document the selected-input construction path so invalid choice shapes cannot reach
  the runner silently.
- Keep artifact writers text-free and closed-code-only.

## 31. Files verified changed/created

Untracked Phase 3A-0 files present before this review audit:

- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`
- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`

This review adds only:

- `docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md`

## 32. Files verified unchanged

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
- AUDIT 78, AUDIT 79, AUDIT 80, AUDIT 81, AUDIT 82

## 33. Confirmation unauthorized work remains unauthorized

Phase 3A-1, Phase 3B, answer replacement, V13, selector behavior, CLI/config changes, YAML changes,
artifact writing, official-output changes, real V12B/model execution, and default promotion remain
unauthorized by this review.

## 34. Confirmation actions not performed

No source/test/config/AUDIT-82 modification occurred. No real V12B/model/V13/selector execution,
answer override, final threshold declaration, organizer-ground-truth use, API/OpenRouter call, model
download, commit, or push occurred. No fixes were implemented.

## 35. Current git status

Expected current status after creating this audit:

```text
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

No tracked diff and no staged changes are expected.

## 36. Final verdict

PHASE 3A-0 REQUIRES CORRECTIONS BEFORE COMMIT

The implementation is well scoped, backend-compatible, in-memory, private-ordinal based, and largely
privacy-safe. However, the runner does not fail closed on incomplete minimal JSON responses: missing
`selected_option_text`, missing `label_matches_option`, or non-boolean `label_matches_option` can be
counted as valid votes and can lead to hypothetical conservative acceptance. That Medium defect must
be corrected and tested before Phase 3A-0 is committed or used as the basis for Phase 3A-1 planning.

This verdict does not authorize Phase 3A-1, Phase 3B, answer replacement, V13, selector use, CLI/config
work, artifact writing, or default promotion.
