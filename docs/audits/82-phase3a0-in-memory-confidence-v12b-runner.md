# AUDIT 82 - Phase 3A-0 In-Memory Confidence-Routed V12B Runner

## 1. Date, branch, starting full HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `80554f6c4c863c02666d83031040d2006a79e5f7`
- Starting commit title: `document phase 3 V12B implementation plan`

## 2. Initial working-tree state

Preflight was clean before implementation.

- `git branch --show-current`: `main`
- `git rev-parse HEAD`: `80554f6c4c863c02666d83031040d2006a79e5f7`
- `git status --short`: no output
- `git diff --check`: no output
- `git diff --stat`: no output
- `git diff --cached --check`: no output
- `git diff --cached --stat`: no output

Recent committed history confirmed AUDIT 78-81 were already committed.

## 3. Codex takeover/context reconstruction

I reconstructed the project state from committed audits and source before editing. Phase 1 and Phase 2
remain complete. Phase 3 was not implemented at takeover. AUDIT 80 is the governing Phase 3 contract
where it conflicts with AUDIT 78, and AUDIT 81 approves Phase 3A-0 with non-blocking implementation
requirements.

## 4. Governing audits read

Read/verified for architecture and scope:

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

## 5. Exact Phase 3A-0 scope

Implemented only the isolated in-memory V12B permutation runner for caller-supplied selected records,
with fake-backend unit tests and this implementation audit.

Out of scope and not implemented: CLI/config/YAML wiring, `predict.py` integration, JSONL/summary
artifact writing, router selection, official CSV changes, answer replacement, Phase 3A-1, Phase 3B,
V13, selector behavior, Docker/dependency changes, default promotion, real-model inference, model
download, and external API calls.

## 6. Files created

- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`
- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`

## 7. Files modified

No existing source, test, config, or prior audit file was modified. The implementation consists only
of new files.

No `QwenMCQPredictor.backend` accessor was added because Phase 3A-0 can be implemented and tested
cleanly through explicit backend injection. Future Phase 3A-1 may add a narrow read-only accessor only
if integration requires it.

## 8. Files explicitly unchanged

Verified unchanged by scope and status:

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
- official CSV writer/schema files
- AUDIT 78, AUDIT 79, AUDIT 80, AUDIT 81

## 9. Runner architecture

The new runner is a pure in-memory execution boundary:

- caller supplies selected `V12BRunInput` records;
- runner assigns private `record_ordinal` by enumeration;
- runner builds unique option permutations with `build_option_permutations`;
- runner calls exactly one injected backend `generate_text` per unique permutation;
- runner parses the minimal JSON object with `parse_json_object`;
- runner maps labels back with `map_permuted_answer_to_original`;
- runner aggregates votes with `summarize_permutation_votes`;
- runner may call `select_permutation_override` only with `policy="conservative"` and only for
  hypothetical diagnostics;
- official source remains fixed to `"base"`.

## 10. Backend injection contract

`V12BBackendProtocol` exposes only:

`generate_text(prompt_or_messages, *, max_new_tokens=None, temperature=0.0) -> str`

The runner receives the backend explicitly via `run_v12b_for_selected(..., backend=...)`. Tests inject
fake backends. The runner never resolves model paths and never instantiates a backend.

## 11. Confirmation no global backend/model lookup

The runner does not import or call `get_local_qwen_backend`, `LocalQwenBackend`, model paths, torch, or
transformers. A unit test monkeypatches `get_local_qwen_backend` to raise and proves the runner still
uses only the injected fake backend.

## 12. Ephemeral text boundary

`V12BRunInput` may hold `question` and `choices` in memory because prompts require them. The runner
does not return, log, or persist those strings. `V12BPermutationResult`, `V12BAggregateResult`, and
`V12BRunSummary` are text-free except for safe labels, qids, input indexes, statuses, and counts.

## 13. Data structures/API

Implemented:

- `V12BRunInput`
- `V12BPermutationResult`
- `V12BAggregateResult`
- `V12BSelectedItem`
- `V12BRunSummary`
- `V12BErrorCode`
- `V12BAggregateStatus`
- `V12BBackendProtocol`
- `run_v12b_for_selected`

All result/summary structures provide JSON-compatible `as_dict()` methods.

## 14. Private ordinal identity

The runner assigns `record_ordinal` internally using input-order enumeration. It does not key
associations by `qid` or assume `input_index` uniqueness. Unit tests cover duplicate `qid`, duplicate
`input_index`, both duplicated together, stable output order, record-count summaries, and selected item
identity.

## 15. Permutation behavior and counts

The runner reuses `build_option_permutations` unchanged and makes one backend generation call per
returned unique permutation.

Unit-tested counts:

- 1 choice -> 1 call
- 2 choices -> 2 calls
- 3 choices -> 4 calls
- 4 choices -> 6 calls
- 5 choices -> 6 calls
- 10 choices -> 6 calls

No code assumes exactly six calls.

## 16. Minimal prompt/response contract

The runner has a private prompt builder. It includes only the ephemeral question, permuted options, and
the required response keys:

- `selected_label`
- `selected_option_text`
- `label_matches_option`

It does not request model confidence, evidence, reasoning, chain-of-thought, or explanation. Raw
responses are held only long enough to parse/map and are never returned.

## 17. Closed error normalization table

Implemented `V12BErrorCode` as a closed enum:

- `ok`
- `generation_error`
- `parse_error`
- `missing_selected_label`
- `label_out_of_range`
- `label_option_mismatch`
- `label_text_conflict`
- `option_text_no_match`
- `insufficient_valid_permutations`
- `tie`
- `all_invalid`
- `aggregate_error`

Explicit raw normalization:

- successful mapping -> `ok`
- backend exception -> `generation_error`
- malformed/non-object JSON -> `parse_error`
- absent/empty `selected_label` -> `missing_selected_label`
- `label_out_of_range` -> `label_out_of_range`
- `self_label_option_conflict` -> `label_option_mismatch`
- `label_text_conflict` -> `label_text_conflict`
- `option_text_no_match` -> `option_text_no_match`
- `no_mapped_label` -> `missing_selected_label`
- unexpected aggregation failure -> `aggregate_error`

Only exception class names may be returned, never exception text.

## 18. Aggregate-status precedence

Implemented deterministic precedence:

1. `aggregate_error` for unexpected aggregation failures.
2. `generation_failure` when at least one permutation was attempted and all attempts failed during
   generation.
3. `all_invalid` when no valid votes exist and the record is not all-generation-failure.
4. `insufficient_valid_permutations` when valid count is greater than zero but below the provisional
   minimum.
5. `tie` when enough valid permutations exist and top vote count is shared.
6. `valid_unique_majority` when enough valid permutations exist, the winner is unique, and winning
   votes meet the provisional consensus vote count.
7. `valid_weak_consensus` when enough valid permutations exist and the winner is unique but below
   strong consensus.

Defaults are local constructor/function defaults only: minimum valid permutations = 5, consensus
votes = 4. No YAML/config loading was added.

## 19. Vote/runner-up/consensus behavior

Vote counts come from `summarize_permutation_votes`. The runner derives:

- deterministic winner and runner-up using canonical label order;
- vote margin;
- consensus ratio;
- unique-answer count;
- tie status before policy acceptance;
- Base/V12B agreement only when a unique diagnostic winner exists.

Tie cases retain a deterministic label representation but never allow hypothetical acceptance.

## 20. Conservative hypothetical policy

The runner calls `select_permutation_override` only with `policy="conservative"` and only after
aggregate status is a unique valid status. It never calls `"balanced"`, never uses
`mean_support_confidence` as a gate, never exposes raw model confidence, and never changes official
answers.

Output fields are strictly diagnostic:

- `hypothetical_answer`
- `hypothetical_conservative_acceptance`
- `official_answer_source = "base"`

## 21. Fail-closed behavior

Per permutation:

- backend exception -> invalid `generation_error`;
- malformed JSON -> invalid `parse_error`;
- missing selected label -> invalid `missing_selected_label`;
- mapping conflicts -> invalid normalized code;
- remaining permutations continue.

Per record:

- unexpected aggregation failure -> `aggregate_error` aggregate diagnostic;
- no raw exception text;
- input order preserved.

Whole run:

- empty input returns empty result tuple and zero-count summary;
- one failed record does not remove or reorder other records.

## 22. No-mutation guarantees

Inputs are frozen dataclasses. `choices`, canonical labels, and router reasons are copied to tuples on
construction. The runner builds fresh sample dictionaries/lists for the permutation core and does not
mutate caller-owned lists or mappings.

Unit tests cover frozen input mutation rejection and caller-owned list preservation.

## 23. No-filesystem/no-artifact guarantees

The runner does not call `open`, `Path.write_*`, `mkdir`, artifact writers, config readers, JSONL
writers, or official-output writers. A unit test monkeypatches filesystem write/open helpers to raise
and proves the runner still completes.

Phase 3A-0 persists nothing.

## 24. Privacy guarantees

Results and summaries do not include:

- question text;
- choices;
- option text;
- selected option text;
- prompts;
- raw responses;
- evidence;
- reasoning;
- model confidence;
- expected answers;
- correctness;
- ground truth;
- arbitrary exception strings.

Unit tests assert sensitive question/choice/raw/exception markers do not appear in returned JSON-safe
diagnostics.

## 25. Unit tests added, grouped by category

New file: `tests/unit/test_confidence_v12b_runner_2l49a.py`

Coverage includes:

- backend injection and no global backend lookup;
- no filesystem write/open/mkdir;
- static forbidden runtime imports/symbols;
- minimal prompt keys and no extra requested fields;
- 1/2/3/4/5/10-choice permutation counts;
- labels-only `permuted_to_original`;
- unanimous, strong-majority, weak-consensus, tie, insufficient, all-invalid, and all-generation-failure
  aggregate states;
- runner-up, margin, consensus ratio, Base/V12B agreement/disagreement;
- conservative hypothetical acceptance only;
- malformed JSON, missing selected label, label out of range, self label/option conflict, label/text
  conflict, option-text no-match, duplicate normalized option text;
- backend exception on one permutation and every permutation;
- unexpected aggregation exception;
- no ephemeral text or raw response in diagnostics;
- JSON-safe dictionaries with `allow_nan=False`;
- duplicate qids/indexes and stable private ordinals;
- empty input;
- repeated-run determinism except elapsed time;
- input/caller collection immutability.

## 26. Exact test commands and results

- `pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q`
  - `32 passed in 0.35s`
- `pytest tests/unit/test_mcq_permutation_debiaser_2l34c.py -q`
  - `15 passed in 0.10s`
- `pytest tests/integration/test_v12b_permutation_2l34b.py -q`
  - `5 passed, 2 failed in 0.30s`
  - failures are the known unrelated missing frozen artifact baseline listed below.
- `pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py -q`
  - `89 passed in 0.65s`
- `pytest tests/unit/test_local_qwen_backend.py -q`
  - `4 passed in 0.06s`
- `python -m py_compile src/local_model/confidence_v12b_runner.py`
  - passed with no output
- `python -m compileall src/local_model/confidence_v12b_runner.py tests/unit/test_confidence_v12b_runner_2l49a.py`
  - passed
- `git diff --check`
  - passed with no output

## 27. Known unrelated baseline failures

`pytest tests/integration/test_v12b_permutation_2l34b.py -q` retains the known baseline failures:

- `test_selector_validates_and_no_change_on_empty`
- `test_frozen_v11_md5_stable`

Both fail with `FileNotFoundError` for:

`output/pred_v11_independent_rerun1.csv`

These were not introduced by Phase 3A-0 and were not fixed in this task.

## 28. Static forbidden-symbol/import checks

Production runner scan:

`rg -n "run_v12b_layer|select_v12b_targets|get_local_qwen_backend|v12b_dynamic_records|V13|selector|legacy_dynamic_full|submission|pred\\.csv|open\\(|write_text|write_bytes|mkdir|confidence" src/local_model/confidence_v12b_runner.py`

Result: no matches.

The same scan over the test file finds only explicit negative assertions and monkeypatch guards.

Production imports are limited to:

- stdlib dataclass/enum/time/type/typing helpers;
- pure V12B permutation helpers from `src.layers.mcq_permutation_debiaser`;
- `parse_json_object`;
- `labels_for`.

## 29. Git diff/scope evidence

Before this audit file was created, `git status --short` showed only:

```text
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

After this audit file, the expected status is:

```text
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

No tracked file modifications and no staged changes were made.

## 30. Risks/caveats

- The runner is not wired into `predict.py`; that is intentionally deferred to Phase 3A-1.
- The provisional diagnostic defaults 5 valid / 4 votes are not calibrated correctness thresholds.
- Prompt quality and real local-model JSON adherence are unvalidated here because Phase 3A-0 forbids
  real-model inference.
- Future Phase 3A-1 must keep artifact writers privacy-safe and must not persist raw text or raw
  exception strings.

## 31. Confirmation

Confirmed:

- no `predict.py` change;
- no YAML/config change;
- no CLI;
- no artifact writer;
- no integration wiring;
- no official-output change;
- no real model/V12B execution;
- no V13/selector;
- no answer replacement;
- no threshold finalization;
- no organizer ground truth;
- no API/OpenRouter;
- no model download;
- no commit/push.

## 32. Current git status

Expected current status after this audit creation:

```text
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

## 33. Recommended next action

Perform an independent read-only review of Phase 3A-0 before any Phase 3A-1 integration work. Phase
3A-1 remains a separate authorization boundary for CLI/config wiring and privacy-safe artifact output.

## 34. Final verdict

PHASE 3A-0 IMPLEMENTED — READY FOR INDEPENDENT REVIEW
