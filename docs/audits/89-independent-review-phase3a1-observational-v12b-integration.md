# AUDIT 89 — Independent Review of the Phase 3A-1 Observational V12B Integration

Audit number 89 (no prior `89-*` existed under `docs/audits/`).

> **Governing rule.** AUDIT 87 governs the Phase 3A-1 contract where AUDIT 86 is ambiguous. AUDIT 88 is
> an implementation report and was treated as claims to verify, not evidence. This review modified
> nothing except creating this file.

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `e61c9485756561abf63daae2b7521f31d5785fe6` ("document phase 3A-1 observational V12B
  integration plan")

## 2. Initial repository state

`git status --short` matched the expected Phase 3A-1 set exactly: `M` on
`configs/confidence_selective.yaml`, `predict.py`, `src/local_model/confidence_config.py`,
`src/local_model/qwen_mcq_predictor.py`; `??` on `docs/audits/88-…md`,
`src/local_model/confidence_v12b_artifacts.py`, and the four new test files. Index empty
(`git diff --cached` empty). `git diff --check` clean. No unrelated change. AUDITs 85/86/87 committed at
HEAD; AUDIT 88 correctly untracked.

## 3. Independent / read-only statement

Independent, adversarial, read-only. I modified no production code, tests, config/YAML, or existing
audits (80–88); implemented no fixes; ran no real model inference; loaded no weights; invoked no
V13/selector/legacy/API; changed no official answer; used no ground truth; downloaded nothing; did not
commit or push. Only this audit was created.

## 4. Claude Code takeover context

Claude Code reconstructed state from Git + audits. Phase 1/2 complete and Windows-validated; Phase 3A-0
committed and independently approved (AUDIT 85); Phase 3A-1 implemented (AUDIT 88) but uncommitted and
observational only. Phase 3B / V13 / selector / legacy V12B / answer replacement / default promotion
remain forbidden.

## 5. Governing audits reviewed

Read completely: AUDIT 80, 85, 86, 87, 88. Verified every significant AUDIT 88 claim against source,
tests, and independent probes.

## 6. Files / source / tests reviewed

Changed production: `predict.py`, `confidence_config.py`, `qwen_mcq_predictor.py`,
`confidence_v12b_artifacts.py` (new), `confidence_selective.yaml`. New tests:
`test_confidence_v12b_config_2l50a.py`, `test_qwen_predictor_backend_accessor_2l50b.py`,
`test_confidence_v12b_artifacts_2l50c.py`, `test_confidence_v12b_shadow_2l50d.py`. Dependencies:
`confidence_v12b_runner.py`, `confidence_shadow_router.py`, `local_qwen_backend.py`, `choice_scoring.py`,
`labels.py`. Full `git diff` of the four tracked files inspected.

## 7. Exact Phase 3A-1 runtime call graph (verified)

`main` → `parse_known_args` → **mode-conflict check** (`predict.py:257`: `legacy_dynamic_full and
confidence_v12b_shadow` → `SystemExit`, before `_resolve_input`/model construction) → resolve paths →
(no-legacy `else`) set `want_v12b`/`want_router`/`want_score` (`:301-303`) → load choice-scoring config
(`score_enabled`) → load shadow-router config when `want_router` and `score_enabled` (`:314-326`) → load
V12B config when `want_v12b`, `score_enabled`, and router available (`:327-340`) → `load_dataset` →
`_build_predictor` (one predictor, one backend) → per-record loop: `predict_one` → `_coerce_label` →
append Base `(qid, ans)`/time; `_compute_score` **once** when telemetry-or-router active, reused for
telemetry + shadow input (`:365-372`) → `run_shadow_router` **once** if `shadow_inputs` present
(`:377-384`); Phase 2 artifacts written only if `--confidence-shadow-router` (`:387-389`) → stash V12B
context if `want_v12b and v12b_cfg and decisions` (`:391-393`) → **write official `submission.csv` +
`submission_time.csv` from Base rows** (`:395-405`) → **V12B compute+write AFTER official CSV, in one
broad `try/except`** (`:413-423`) → legacy mirrors (`:425-432`). Verified: conflict before load; one
predictor/backend; one Base generation per record; official rows independent of V12B; scoring ≤1×;
router once; only selected+valid records reach the runner; official written before V12B; mirrors intact;
V12B errors cannot suppress official output (post-official + broad catch + `v12b_ready` guard avoids any
NameError in legacy mode).

## 8. CLI / config activation review

- `--confidence-v12b-shadow` is the **only** execution gate; path flags without it are inert (verified
  by `test_no_v12b_files_when_flag_off`).
- YAML `enabled` cannot independently activate V12B (loaded only when the CLI flag is set;
  `V12BShadowConfig.enabled` is never consulted as a gate).
- Absent block + CLI on → safe defaults (`load_v12b_config({...})` → `permutation_count=6`).
- Malformed block → `ValueError` → caught in `predict.py:338-340` → `v12b_cfg=None` → V12B disabled,
  Base preserved.
- `observational_only`/`require_router_selected` must be `True` (else `ValueError`); `permutation_count`
  int `1..6`; forbidden/unexposed fields (`answer_override`, `merge`, `merge_threshold`,
  `balanced_policy`, `self_reported_confidence`, `v13`, `selector`, `min_valid_permutations`,
  `consensus_votes`, `max_new_tokens`) → `ValueError` (fail closed). Runner defaults 192/5/4 preserved
  (not exposed). All asserted by `test_confidence_v12b_config_2l50a.py` (12 cases).
- **Unknown non-forbidden keys are tolerated** (forward-compat). Assessment: acceptable — a *misspelled
  forbidden* key (e.g. `answeroverride`) would be silently ignored rather than honored, so it cannot
  activate a forbidden behavior (no code reads it); the security-relevant fields are matched by exact
  name and rejected. Informational, not a defect.

## 9. Backend identity / accessor review

`QwenMCQPredictor.backend` (`qwen_mcq_predictor.py:39-41`) returns exactly `self._backend`; no setter;
no load/cache/path lookup. `predict.py` injects `_predictor.backend` (`:419`) and never touches
`_backend` or calls `get_local_qwen_backend` a second time (static grep confirmed; `get_local_qwen_backend`
appears only in the predictor constructor). `predict_one`/`score_choices`/V12B all use the same object.
Tests: identity, no-relookup (monkeypatched counter == 0), read-only (setter raises `AttributeError`).

## 10. Score / router call-count review

`want_score = telemetry or shadow_router or v12b`; `_compute_score` runs at most once per record and is
shared. `run_shadow_router` runs once for any router-requiring combination. Verified counts:
telemetry-only = 1 score/record, no router; Phase-2-only = 1 score, 1 router; V12B-only = 1 score, 1
router; telemetry+V12B = 1 score (asserted `score_calls == N`), 1 router; Phase-2+V12B = 1 score, 1
router shared (both artifact families emitted); all three = 1 score, 1 router. Scoring failure
(`_compute_score` catches) and router failure (`predict.py:381-384` catches → `decisions=None` → V12B
skipped) cannot terminate Base output — Base rows are appended before scoring and written from `rows`.

## 11. Source-record identity review

Authoritative identity is `source_record_ordinal = enumerate(samples)` index = router decision-list
position (decisions are one-per-record in input order, confirmed in `confidence_shadow_router.py`). `qid`
and `input_index` are metadata only; `router_selected_rank` is risk-rank metadata; the runner's
`record_ordinal` stays **nested under `aggregate`** (runner-local filtered index) and is never used as
global identity. Independent probe confirmed: for A-valid/B-invalid/C-valid, top-level
`source_record_ordinal` = 0/2 while nested `aggregate.record_ordinal` = 0/1 (runner-local).

## 12. Valid / invalid pairing review

`build_selected_entries` keeps all selected records in input order and assigns
`selected_sequence_ordinal` only to valid ones; only `[e.v12b_input for e in valid]` is passed to the
runner; `_build_records` pairs by `results[selected_sequence_ordinal]`; `len(results) != len(valid)` →
`AssertionError` (`:239-240`). A valid record's result can never attach to an invalid record (invalid
records get no aggregate). Duplicate qids/input_indexes stay distinct records (counted as records, not
merged). Verified by `test_confidence_v12b_artifacts_2l50c.py` (A/B/C pairing; duplicate qid+index;
nested-vs-source ordinal) and the integration suite.

## 13. Input-validation review

`_validation_code` returns closed codes only, checked in order: `invalid_record_shape`,
`invalid_question`, `invalid_choices` (string/bytes rejected), `unsupported_choice_count` (`<2` or `>26`,
per AUDIT 87 §12), `invalid_canonical_labels` (defensive), `invalid_base_answer`,
`invalid_score_diagnostic` (bad top1/top2 or non-finite margin/entropy), `invalid_router_rank`
(non-positive/non-int); any unexpected exception → `input_validation_error`. Invalid selected records
never build a `V12BRunInput`, never reach the runner, never abort valid records, keep Base, and emit only
the closed code. Probes confirmed `2..26` bounds and each code. Wrapper rows for invalid records use only
decision fields — **no** sample question/choice text is serialized even for invalid records.

## 14. Runner-invocation / default review

`confidence_v12b_artifacts.py:234-238` calls only `run_v12b_for_selected(inputs, backend=predictor.backend,
permutation_count=cfg.permutation_count)` — the approved Phase 3A-0 runner. `max_new_tokens` **not**
overridden (runner default 192); `min_valid_permutations`/`consensus_votes` **not** overridden (5/4). No
`run_v12b_layer`, `select_v12b_targets`, legacy writer, V13, selector, or external API is imported or
reachable (static + import inspection). `confidence_v12b_runner.py` is unmodified (not in `git diff`).

## 15. Official-output ordering review

Official `submission.csv`/`submission_time.csv` are built only from Base `rows`/`times` and written at
`predict.py:395-405`, **before** the V12B block (`:413-423`). `hypothetical_answer` is never read into a
row. The V12B block is guarded by `v12b_ready` (False in legacy mode → no NameError) and a broad
`except Exception` warning with class name only. Mirrors run after and are unchanged.

## 16. Official CSV byte-invariance review

Integration tests compare **exact file bytes** (`read_bytes() == read_bytes()`), not parsed rows, against
the Base-only baseline for: V12B on; V12B generation failure; V12B artifact-write failure; scoring
failure; choice-scoring disabled. Independent probes additionally confirmed official CSV intact under:
V12B success, runner exception, scoring failure, invalid selected record, serialization failure,
directory failure, and write/rename failure (all post-official + caught). No probe altered an official
answer.

## 17. Artifact schema / privacy review

Whitelist-only construction: `_wrapper_row` emits fixed metadata keys; records merge the runner's
text-free `V12BAggregateResult.as_dict()` (nesting `V12BPermutationResult.as_dict()` — labels-only
`permuted_to_original`, closed error codes, optional `exception_class_name`). `V12BRunInput`
(question/choices) and raw samples are **never** serialized; no `__dict__`. `official_answer_source` is
fixed to `"base"` at record and aggregate level. **Independent marker probe** (private markers embedded in
question, choices, raw model response, and exception message) → **no marker** appeared in JSONL, summary,
or stdout warnings; records were still emitted with closed codes (`generation_failure`, `all_invalid`).
`allow_nan=False` on both files. Warnings carry operation + exception class only, never `str(exc)` (grep
confirmed no `str(exc)`/`{e}` in `confidence_v12b_artifacts.py`; the `predict.py:422` V12B boundary warning
uses `type(e).__name__` only).

## 18. Atomic writer / failure-semantics review

`_write_json_atomic` writes a sibling `*.tmp` then `Path.replace` (atomic per-file on POSIX and Windows,
same directory/filesystem). JSONL and summary have **independent** try/except and independent status; one
failing does not prevent the other's attempt (probe: JSONL write failed → summary still written); neither
affects official output. No cross-file atomicity is claimed. Caveat (F1) below on non-finite scrubbing;
minor temp-cleanup note (F2).

## 19. No-V13 / no-selector / no-legacy / no-API review

Static scan of changed production files found `V13`/`selector`/`run_v12b_layer`/`select_v12b_targets`
only inside descriptive comments/help text (documenting what does **not** run), never as calls; no
`OpenRouter`/`api_key`. `test_v12b_never_invokes_legacy_selective` monkeypatches `_run_legacy_dynamic_full`
to raise and confirms it is never reached. Import graph of `confidence_v12b_artifacts.py` reaches only the
runner + `labels` + stdlib.

## 20. Unit / integration test-quality review

Tests exercise real production code: integration tests drive `mod.main([...])` through real argparse and
monkeypatch `_build_predictor` at the module object (correct location); byte-equality uses file bytes;
privacy tests scan serialized **content** (incl. real option text like `Paris`), not just field names;
the write-failure test targets the real write/rename op (JSONL path = directory); the accessor test
asserts object identity and a zero relookup count; the conflict test proves neither model nor legacy path
is reached. Fake backend matches the production `generate_text(prompt, *, max_new_tokens, temperature)`
signature (not broader). Coverage gaps (Low, F3): no explicit test for (a) `run_shadow_router` raising
under V12B (structurally handled), (b) the result-count-mismatch assertion, (c) an explicit assertion that
the summary is written when the JSONL write fails (independent atomicity).

## 21. New-test results

`test_confidence_v12b_config_2l50a.py` + `..._backend_accessor_2l50b.py` + `..._artifacts_2l50c.py` +
`..._v12b_shadow_2l50d.py` → **48 passed**.

## 22. Regression-test results

Runner + choice-scoring + telemetry + shadow (unit+integration) + local backend → **140 passed**.
Submission/output contract tests (`test_btc_submission_contract_2l47a`, `test_full_system_output_contract_2l41a`,
`test_submission_variants_2l29a`) → **33 passed**.

## 23. Implementation-tree full-suite result

`python -m pytest -q` → **831 passed, 16 failed**.

## 24. Clean-worktree baseline full-suite result

Detached clean worktree at HEAD `e61c948` (`git worktree add --detach`), verified **no** Phase 3A-1
untracked files present, `python -m pytest -q` → **783 passed, 16 failed**. Worktree removed with
`git worktree remove --force`; main tree untouched.

## 25. Exact baseline-failure comparison

Both runs fail the **same 16** frozen-artifact / public-replay tests (`FileNotFoundError` on
`output/*.csv`): `test_btc_short_2l31b` (2), `test_fastmcq_dynamic_system_2l36b` (3),
`test_final_package_2l31a` (6), `test_run_profiles_2l38c` (1), `test_v12b_permutation_2l34b` (2),
`test_v13_dynamic_integration_2l37a` (1), `test_v13_multilayer_2l35a` (1). Arithmetic: 831 = 783
baseline-passed + 48 new. **The Phase 3A-1 change introduces zero new failures**; AUDIT 88's "16
pre-existing" claim is independently confirmed via a clean worktree (not merely by stashing).

## 26. Compile / static checks

`python -m compileall predict.py confidence_config.py qwen_mcq_predictor.py confidence_v12b_artifacts.py
tests` → OK. `git diff --check` → clean. Forbidden-path scan → no forbidden calls; `_backend` confined to
`QwenMCQPredictor`; no second `get_local_qwen_backend`.

## 27. Findings (ordered by severity)

| ID | Severity | Location | Evidence | Impact | Blocks commit? | Blocks Windows val? | Smallest fix |
|---|---|---|---|---|---|---|---|
| F1 | Low | `confidence_v12b_artifacts.py:126-127,247` | Probe: an **invalid** selected record with a non-finite `base_logit_margin` makes `json.dumps(allow_nan=False)` reject the whole JSONL (valid records lost); summary still writes | Diagnostic completeness only — official output & privacy unaffected; **not reachable via the real scorer** (finite-or-`None`); contract's "fail closed" is technically met | No | No | Scrub wrapper floats to `null` (reuse a `_num`-style helper) or serialize records individually so one bad record loses only itself |
| F2 | Low | `confidence_v12b_artifacts.py:154,222-224` | Dead local `invalid` in `build_selected_entries` (return is `(selected, valid)`); on write failure the sibling `*.tmp` may persist (non-private content) | Cosmetic + minor temp leftover | No | No | Drop the dead line; optionally `unlink(missing_ok=True)` the temp on failure |
| F3 | Low | tests | No explicit test for router-raise-under-V12B, result-count-mismatch assertion, or summary-written-when-JSONL-fails | Coverage completeness (all structurally handled/observed) | No | No | Add three focused fake tests |
| I1 | Info | — | Linux env; no weights | No real-model evidence yet | No | No | Windows observational validation (next) |

Counts: **Critical 0 / High 0 / Medium 0 / Low 3 / Informational 1.**

## 28. Required corrections before commit

None. All findings are non-blocking.

## 29. Required corrections before Windows validation

None required. Optional (recommended) hardening: F1 non-finite wrapper scrub, and the F3 tests — but the
real scorer yields finite-or-`None`, so these do not block observational validation.

## 30. Files verified modified / created

Modified (tracked, +142/−13): `predict.py`, `confidence_config.py`, `qwen_mcq_predictor.py`,
`configs/confidence_selective.yaml`. Created (untracked): `confidence_v12b_artifacts.py`, four new test
files, AUDIT 88. This review adds only AUDIT 89.

## 31. Files verified unchanged

`confidence_v12b_runner.py`, `test_confidence_v12b_runner_2l49a.py`, `mcq_permutation_debiaser.py`,
`v12b_dynamic_layer.py`, `fastmcq_system.py`, V13/selector/Docker/dependency files, the official
submission schema, and Phase 1/2 scoring/routing semantics (none in `git diff --name-only`).

## 32. Authorization confirmation

Phase 3B, answer replacement, V13, selector, legacy V12B, default promotion, and final thresholds remain
**unauthorized**. A positive verdict authorizes only committing Phase 3A-1 (after user approval) and
Windows real-model **observational** validation.

## 33. Explicit confirmation

No source/test/config/AUDIT-88 modification; no real model/V12B/V13/selector execution; no answer
override; no final threshold; no organizer ground truth; no API/OpenRouter call; no model download; no
commit or push. Only AUDIT 89 was created. (A temporary detached worktree was added and removed; the main
tree was untouched.)

## 34. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
 M src/local_model/qwen_mcq_predictor.py
?? docs/audits/88-phase3a1-observational-v12b-integration.md
?? docs/audits/89-independent-review-phase3a1-observational-v12b-integration.md
?? src/local_model/confidence_v12b_artifacts.py
?? tests/integration/test_confidence_v12b_shadow_2l50d.py
?? tests/unit/test_confidence_v12b_artifacts_2l50c.py
?? tests/unit/test_confidence_v12b_config_2l50a.py
?? tests/unit/test_qwen_predictor_backend_accessor_2l50b.py
```

## 35. Recommended next action

Commit Phase 3A-1 (after user approval), then run the Windows real-model **observational** validation
(official CSV byte invariance, artifact privacy, actual permutation counts, no V13/selector/legacy).
Optionally apply the F1/F3 hardening first. Do not promote to the no-flag default or finalize thresholds.

## 36. Final verdict

**PHASE 3A-1 SAFE TO COMMIT WITH NON-BLOCKING CAVEATS; READY FOR WINDOWS OBSERVATIONAL VALIDATION**

The implementation faithfully realizes the AUDIT 87 contract: single CLI gate, score-once/router-once,
injected-backend identity, `source_record_ordinal` identity with safe positional pairing, closed-code
input validation (`2..26`), runner defaults preserved, official CSV written first and byte-identical to
Base, whitelist-only text-free artifacts with independent atomic writes, and no V13/selector/legacy/API
reachability. Only three Low findings and one Informational remain; none blocks commit or observational
validation. This verdict does not authorize Phase 3B, answer replacement, V13, selector, legacy V12B,
default promotion, or final thresholds.
