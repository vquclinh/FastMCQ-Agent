# AUDIT 84 - Phase 3A-0 Corrective Pass: Structured Response Validation

## 1. Date, branch, starting HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `80554f6c4c863c02666d83031040d2006a79e5f7`
- Starting commit: `document phase 3 V12B implementation plan`

## 2. Initial working-tree state

Preflight matched the expected corrective-pass state.

```text
git branch --show-current
main

git rev-parse HEAD
80554f6c4c863c02666d83031040d2006a79e5f7

git status --short
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

`git diff --check`, `git diff --stat`, `git diff --name-only`,
`git diff --cached --check`, `git diff --cached --stat`, and
`git diff --cached --name-only` produced no output. Nothing was staged.

## 3. Context reconstruction

I reconstructed the current state from the committed Phase 3 planning audits and the uncommitted
Phase 3A-0 implementation/review files before editing. Phase 1 and Phase 2 remain complete. Phase
3A-0 is implemented but uncommitted. Phase 3A-1 and Phase 3B remain unauthorized.

Binding context:

- AUDIT 80 governs over AUDIT 78 where they conflict.
- AUDIT 81 approved the corrected Phase 3A-0 plan.
- AUDIT 83 found one blocking Medium implementation defect.
- AUDIT 82 and AUDIT 83 are historical records and were not modified.

## 4. Files read

Read for this corrective pass:

- `docs/audits/78-phase3-confidence-routed-v12b-planning.md`
- `docs/audits/79-independent-review-phase3-v12b-plan.md`
- `docs/audits/80-phase3-v12b-plan-corrections.md`
- `docs/audits/81-independent-review-phase3-v12b-plan-corrections.md`
- `docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md`
- `docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md`
- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_2l49a.py`
- `src/layers/mcq_permutation_debiaser.py`
- `src/local_model/local_qwen_backend.py`
- `src/utils/labels.py`

## 5. Exact corrective scope

This pass addressed only AUDIT 83 finding M1: incomplete structured V12B responses could become valid
permutation votes because the runner validated `selected_label` only, then passed missing
`selected_option_text` or missing/non-boolean `label_matches_option` through to the pure mapper.

No Phase 3A-1 work was performed. No CLI/config/YAML wiring, artifact writing, `predict.py`
integration, router integration, official-output change, answer replacement, V13, selector behavior,
Phase 3B, model loading, external API call, download, commit, or push occurred.

## 6. Files modified

Allowed implementation file:

- `src/local_model/confidence_v12b_runner.py`

Allowed test file:

- `tests/unit/test_confidence_v12b_runner_2l49a.py`

Allowed audit file created:

- `docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md`

No other file was modified.

## 7. Structured-response correction

Before calling `map_permuted_answer_to_original`, `_run_one_permutation` now requires:

- `selected_label` is present, is a string, and is non-empty after stripping.
- `selected_option_text` is present, is a string, and is non-empty after stripping.
- `label_matches_option` is present and has exact type `bool`.

Missing/null/empty `selected_label` remains normalized to `missing_selected_label`.

Wrong field types, missing/empty `selected_option_text`, and missing/non-boolean
`label_matches_option` normalize to a new closed code:

```text
invalid_response_schema
```

This keeps malformed structured responses invalid before the mapper can skip option-text checking or
ignore a non-boolean self-check.

## 8. Error-code design

`V12BErrorCode` now includes `invalid_response_schema`. The public error-code set remains closed.
No raw parser reason, generated text, option text, prompt text, or `str(exc)` is returned.

The new code is used only for response-schema defects. Mapping conflicts still use the existing
closed mapping codes:

- `label_out_of_range`
- `label_option_mismatch`
- `label_text_conflict`
- `option_text_no_match`

## 9. Fail-closed behavior after correction

Malformed structured responses now produce invalid permutation results with:

- `valid = False`
- `mapped_original_label = None`
- `label_option_match = False`
- `parse_status = "ok"` when JSON parsing succeeded but schema validation failed
- `error_code = invalid_response_schema` or `missing_selected_label`

Record aggregation then produces `all_invalid` when every permutation has only schema-invalid results.
No votes are counted, `hypothetical_answer` remains `None`, and
`hypothetical_conservative_acceptance` remains `False`.

## 10. Tests added

Added fake-backend regression coverage for:

- missing `selected_label`;
- null `selected_label`;
- empty/whitespace `selected_label`;
- wrong-type `selected_label`;
- missing `selected_option_text`;
- null `selected_option_text`;
- empty/whitespace `selected_option_text`;
- non-string `selected_option_text`;
- missing `label_matches_option`;
- null `label_matches_option`;
- string `label_matches_option`;
- integer `label_matches_option`;
- raw response markers not appearing in returned diagnostics;
- JSON-safe result and summary dictionaries for schema-invalid responses.

Existing tests still cover the complete valid response path and `label_matches_option = false`
normalizing to `label_option_mismatch`.

## 11. Test results

Runner unit tests:

```text
pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q
47 passed in 0.39s
```

Permutation core:

```text
pytest tests/unit/test_mcq_permutation_debiaser_2l34c.py -q
15 passed in 0.12s
```

Phase 1/2 confidence regression group:

```text
pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py -q
89 passed in 0.61s
```

Local backend parser/backend tests:

```text
pytest tests/unit/test_local_qwen_backend.py -q
4 passed in 0.10s
```

Legacy V12B integration baseline:

```text
pytest tests/integration/test_v12b_permutation_2l34b.py -q
5 passed, 2 failed in 0.35s
```

The two failures are the known unrelated frozen-artifact baseline:

- `test_selector_validates_and_no_change_on_empty`
- `test_frozen_v11_md5_stable`

Both fail with `FileNotFoundError` for:

```text
output/pred_v11_independent_rerun1.csv
```

Compile/static checks:

```text
python -m compileall src/local_model/confidence_v12b_runner.py tests/unit/test_confidence_v12b_runner_2l49a.py
passed

git diff --check
passed with no output
```

## 12. Static forbidden-symbol checks

Production runner scan:

```text
rg -n "run_v12b_layer|select_v12b_targets|get_local_qwen_backend|v12b_dynamic_records|V13|selector|legacy_dynamic_full|submission|pred\.csv|open\(|write_text|write_bytes|mkdir|confidence" src/local_model/confidence_v12b_runner.py
no matches
```

The same scan over the unit-test file returns only expected negative assertions, monkeypatch guards,
and privacy fixtures. No forbidden runtime path was added.

## 13. Scope confirmations

Confirmed unchanged/not performed:

- no `predict.py` change;
- no YAML/config change;
- no `confidence_config.py` change;
- no `qwen_mcq_predictor.py` change;
- no legacy V12B module change;
- no V13 or selector file change;
- no Docker/dependency change;
- no official-output code change;
- no AUDIT 78, 79, 80, 81, 82, or 83 modification;
- no filesystem artifact writer;
- no real model loading;
- no real V12B inference;
- no V13/selector execution;
- no answer override;
- no final threshold;
- no organizer ground truth;
- no OpenRouter or external API call;
- no model download;
- no commit or push.

## 14. Current git status

Expected current status after this audit creation:

```text
?? docs/audits/82-phase3a0-in-memory-confidence-v12b-runner.md
?? docs/audits/83-independent-review-phase3a0-in-memory-v12b-runner.md
?? docs/audits/84-phase3a0-corrective-pass-structured-response-validation.md
?? src/local_model/confidence_v12b_runner.py
?? tests/unit/test_confidence_v12b_runner_2l49a.py
```

No tracked diff and no staged changes are expected.

## 15. Remaining caveats

AUDIT 83 Low findings were not addressed because this task authorized only the blocking M1
correction:

- broader invalid-input validation for caller misuse remains a future hardening item;
- threshold/status alignment should be kept explicit before any future Phase 3A-1 config exposure.

These caveats do not change the M1 corrective result.

## 16. Final verdict

PHASE 3A-0 CORRECTIVE PASS COMPLETE - READY FOR INDEPENDENT REVIEW

The blocking AUDIT 83 M1 defect has been corrected in the isolated runner and covered by
fake-backend unit tests. This verdict does not authorize Phase 3A-1, Phase 3B, answer replacement,
V13, selector use, CLI/config work, artifact writing, official-output changes, or default promotion.
