# AUDIT 94 — Final Review, Validation, and Promotion Decision: Full Confidence Pipeline

Audit number 94 (no prior `94-*` existed under `docs/audits/`).

> **Nature of this record.** This is a single, coherent finalization pass covering adversarial
> review + same-pass corrections, model-free regression testing, Windows real-model validation,
> a permitted labeled evaluation, and a default-promotion decision. AUDIT 93 was treated as
> implementation claims to verify, not as independent evidence — every claim in it that mattered
> to this decision was re-derived from source, tests, or real-model runs in this pass.

## 1. Date, branch, starting HEAD

- Date: 2026-07-10 (session spanned into 2026-07-11 local time during Docker recovery)
- Branch: `main`
- Starting full HEAD: `f556dc159f71929c86bb711c7d37946405e75f11` ("validate phase 3A-1 V12B
  shadow on Windows" — AUDIT 92). Unchanged at the end of this pass (nothing was committed).

## 2. Initial repository state

`git status --short`: `M configs/confidence_selective.yaml`, `M predict.py`,
`M src/local_model/confidence_config.py`, plus the AUDIT 93 untracked set (`docs/audits/93-...md`,
`src/evaluation/`, `src/local_model/confidence_full_pipeline.py`,
`src/local_model/confidence_full_pipeline_artifacts.py`, `src/local_model/confidence_v13_runner.py`,
four new test files). `git diff --check` clean (exit 0). `git diff --cached --check` clean (exit
0, nothing staged). `git diff --stat`: 3 files, 152 insertions(+), 9 deletions(-). Exactly the
scope AUDIT 93 claimed — no unrelated repository changes found; nothing to stop for.

## 3. Files reviewed

Full re-read of every changed/new production file and every new test file:
`predict.py`, `configs/confidence_selective.yaml`, `src/local_model/confidence_config.py`,
`src/local_model/confidence_v13_runner.py`, `src/local_model/confidence_full_pipeline.py`,
`src/local_model/confidence_full_pipeline_artifacts.py`, `src/evaluation/full_pipeline_metrics.py`,
all four new test files. Dependencies inspected: `src/local_model/confidence_v12b_runner.py`,
`src/local_model/confidence_v12b_artifacts.py`, `src/local_model/confidence_shadow_router.py`,
`src/local_model/qwen_mcq_predictor.py`, `src/local_model/local_qwen_backend.py`,
`src/layers/programmatic_solver_layer.py`, `src/layers/content_first_answerer.py`,
`src/layers/least_to_most_constraint_solver.py`, `src/layers/v13_dynamic_layer.py`,
`src/system/fastmcq_system.py` (confirmed: legacy full-system orchestrator, 223 lines, not
imported by any Phase 3B module — `run_fastmcq_system`/`FastMCQSystemConfig` are unrelated and
untouched).

## 4. Defects found

One real, worth-fixing gap (Low/Medium — not answer-corrupting in the actual `predict.py` call
path, but a genuine boundary-enforcement gap):

- **F1 — canonical-answer invariant enforced only by the caller, not the selector itself.**
  `run_full_pipeline` (`confidence_full_pipeline.py`) assigned `final_answer = base_answer` for
  unselected/invalid-boundary records without validating that `base_answer` (sourced from
  `decision.generated_answer`) was itself a canonical label for the sample. In the real
  `predict.py` path this is always true (`_coerce_label` guarantees it upstream), so this was
  never reachable in production — but the selector's own diagnostic artifact
  (`FullPipelineRecord.final_answer`) had no in-module guarantee, meaning a malformed `decision`
  object from any future caller could write a non-canonical label into the diagnostic JSONL even
  though `predict.py`'s separate, redundant safety net would still have protected the official
  CSV. This is exactly the "no partial result can corrupt output" property the task asked to
  verify, and it was only half-enforced.

No other Critical/High/Medium defects were found. Everything else the task asked to verify
(call counts, identity/pairing, V13 contract, selector fallback, privacy, CLI mode behavior) was
independently re-derived from source and confirmed correct — see §§7–13.

## 5. Corrections made in this same pass

- **Fix for F1**: `confidence_full_pipeline.py` now validates `final_answer` against
  `is_valid_label` **inside `run_full_pipeline` itself**, immediately before building each
  `FullPipelineRecord`. If ever non-canonical (unreachable via `predict.py` today, but now
  provably impossible regardless of caller), it is replaced with the same deterministic
  first-label fallback `predict.py` itself uses, and `final_source` is set to `base_fallback`.
  Added `_deterministic_fallback_label(sample)` helper.
- Added an explicit `AssertionError` when `len(decisions) != len(samples)` at the top of
  `run_full_pipeline` (previously this would have surfaced as an unclear `IndexError`
  mid-loop — still caught by `predict.py`'s outer fail-closed boundary either way, but now with a
  clear diagnostic message).
- **New tests added directly targeting the task's explicit asks**:
  - `test_v12b_literal_tie_routes_to_v13` and
    `test_v12b_literal_tie_with_failing_v13_falls_back_to_base` — a genuine
    `V12BAggregateStatus.TIE` (not merely an equivalent status path), constructed by alternating
    the V12B vote between two distinct original option texts across all 6 permutations of a
    4-choice question (empirically verified before writing the test: 6 permutation calls, exact
    3-3 split, `v12b_status == "tie"`).
  - `test_non_canonical_base_answer_is_replaced_by_deterministic_fallback` — directly exercises
    the F1 fix.
  - `test_decision_count_mismatch_raises_instead_of_silently_misaligning` — exercises the new
    length-mismatch assertion.
  - `test_v12b_result_count_mismatch_fails_closed` /
    `test_v13_result_count_mismatch_fails_closed` — monkeypatch the underlying runners to return
    a wrong-length result tuple and assert `run_full_pipeline` raises rather than silently
    misaligning records (the task's explicit "Result-list length mismatches fail closed to Base"
    ask, now tested directly at the module boundary, not only inferred from the pre-existing
    `AssertionError` calls).
- No change was needed to `src/local_model/confidence_v12b_runner.py` (no verified blocker
  required touching the approved runner) and no change was made to any legacy V13/system/selector
  file.

## 6. Final runtime architecture

Unchanged from AUDIT 93 §5 except for the F1 hardening described above. Summary: Base generation
→ one-forward scoring (once per record) → confidence router (once) → `run_v12b_for_selected` on
router-selected, input-valid records → selector decides V12B-accept vs. needs-V13 →
`run_v13_for_unresolved` on the needs-V13 subset → per-record final answer/source, now with an
in-module canonical-label guarantee → `predict.py` substitutes `rows` **before** the official CSV
write, with a full revert-to-Base safety net on any exception → official CSV/time files written →
V12B-shadow artifacts (if that separate flag was used) → full-pipeline diagnostics written
best-effort, independently atomic.

## 7. Backend/model reuse

Re-verified by direct code inspection (not just re-reading AUDIT 93's claim): `run_full_pipeline`
accepts one `backend` parameter and passes the identical object to both `run_v12b_for_selected`
and `run_v13_for_unresolved` — no `get_local_qwen_backend` call exists anywhere in
`confidence_v13_runner.py` or `confidence_full_pipeline.py` (grep-confirmed). `predict.py` calls
`_build_predictor(args)` exactly once in the offline branch; `predictor.backend` (the read-only
accessor from Phase 3A-1) is the only value ever passed into `run_full_pipeline`. Real-model
confirmation: a single `docker run` per validation run loaded the model exactly once (one "Loading
weights" progress bar per run in every real-model log below), and V12B + V13 generation both
occurred inside that single container process.

## 8. Identity and pairing

Re-verified unchanged from AUDIT 93 §8: `source_record_ordinal` (the `enumerate(samples)` index)
is authoritative; V12B's nested `aggregate.record_ordinal` and V13's `record_ordinal` are
runner-local and never used as global identity; pairing is by list position only
(`zip(valid, v12b_results)`, `zip(needs_v13, v13_results)`), guarded by the two `AssertionError`
checks (now also directly unit-tested, §5). `test_pairing_valid_invalid_valid_never_misaligns` and
`test_duplicate_qid_and_input_index_stay_distinct` re-run and re-verified passing in this pass.

## 9. V12B acceptance behavior

Unchanged, re-verified: accepted only when `aggregate_status == "valid_unique_majority"` **and**
`hypothetical_answer` is non-null and itself `is_valid_label`. Every other status
(`all_invalid`, `insufficient_valid_permutations`, `tie`, `valid_weak_consensus`,
`generation_failure`, `aggregate_error`) routes to V13. The literal `tie` case is now directly
tested (§5), closing the one coverage gap AUDIT 93 §17 had explicitly flagged as a caveat.

## 10. V13 runner/layer-selection behavior

Unchanged from AUDIT 93 §6, independently re-verified: three pure layers
(`programmatic_solver`/`content_first`/`least_to_most`), deterministic feature-based layer choice
(no model call for the choice itself), no file I/O anywhere in `confidence_v13_runner.py`
(grep-confirmed: no `open(`, no `Path(...).write`, no `mkdir`), closed `V13ErrorCode` set,
exception class name only (never `str(exc)`), one record's failure isolated from others
(re-verified via `test_one_record_failure_does_not_abort_others`). Real-model confirmation: in the
real Run B/C, both V13 attempts (`syn_001_addition_3`, `syn_008_speed`) used the
`programmatic_solver` layer (both are arithmetic-style questions) and both returned `error_code:
"ok"` with a validated canonical label — the first real-model evidence that the V13 runner
actually produces a usable structured response from the real Qwen3-4B model, not just from fake
backends.

## 11. Selector and fallback behavior

Re-verified: every final answer is now canonical **inside the module** (F1 fix, §5); a whole-
`run_full_pipeline` exception reverts `predict.py`'s `rows` to the untouched Base rows captured
immediately before the call (`test_full_pipeline_global_failure_preserves_base_submission`,
re-run passing); selected-but-input-invalid records never reach V12B or V13
(`test_selected_invalid_boundary_stays_base_and_skips_v12b_and_v13`); no model self-reported
`confidence` field is read anywhere in the selector (grep-confirmed — only `aggregate_status`,
`hypothetical_answer`, `valid`, `mapped_label` are consulted); no organizer ground truth or
leaderboard signal is used anywhere in the selector or its config.

## 12. CLI modes

Re-verified via both static reading and the integration test suite: no-flag path is provably
unchanged (identical code path to before this feature existed); `--confidence-v12b-shadow` stays
observational (`test_v12b_shadow_stays_observational`, byte-identical CSV); `--confidence-full-
pipeline` is answer-changing only for router-selected records
(`test_full_pipeline_overrides_selected_record_only`); `--legacy-dynamic-full` +
`--confidence-full-pipeline` and `--confidence-v12b-shadow` + `--confidence-full-pipeline` both
raise `SystemExit` before `_build_predictor`/`_run_legacy_dynamic_full` are reachable
(monkeypatched to raise `AssertionError` if invoked — both tests re-run passing); path-only flags
without the execution flag are inert (`test_no_full_pipeline_files_when_flag_off`).

## 13. Diagnostic privacy

Re-verified two ways. **Model-free**: unit/integration tests scan serialized full-pipeline JSONL/
summary output for banned substrings including the literal option text used in test fixtures
("Paris", "2 + 2", "Capital of France") — none found. **Real-model** (new in this pass, not
possible from AUDIT 93 alone): the actual `confidence_full_pipeline.jsonl` written by real Run B
was inspected programmatically. Top-level keys are exactly the whitelisted schema (`source_record_
ordinal`, `qid`, `input_index`, `base_answer`, `router_selected`, `v12b_status`,
`v12b_hypothetical_answer`, `v13_attempted`, `v13_status`, `v13_answer`, `final_answer`,
`final_source`) — no `question`/`choices`/`prompt`/`reasoning`/`evidence`/`expected`/`ground_truth`/
`api_key` field exists. A naive substring scan flagged `"choices"`, `"sequence"`, `"pills"` —
traced to `qid` values (`syn_006_ten_choices`, `syn_020_sequence`, `syn_021_pills`, all
self-authored identifiers, not question/option text) and confirmed as non-issues, the same class
of false positive documented in AUDIT 92 §14 for `"option"`/`"exception_class_name"`. `allow_nan=
False` on both files; every record round-tripped through `json.dumps(..., allow_nan=False)`
without error.

## 14. New/fixed tests

Test counts by file after this pass (unit unless noted):

| File | Tests |
|---|---|
| `test_confidence_v13_runner_2l51a.py` | 16 |
| `test_confidence_full_pipeline_selector_2l51b.py` | 17 (11 from AUDIT 93 + 6 new: 2 literal-tie, 4 hardening) |
| `test_confidence_full_pipeline_2l51c.py` (integration) | 13 |
| `test_full_pipeline_metrics_2l51d.py` | 7 |
| **Total** | **53** |

## 15. Model-free test results

```
tests/unit/test_confidence_v13_runner_2l51a.py .................. 16 passed
tests/unit/test_confidence_full_pipeline_selector_2l51b.py ....... 17 passed
tests/integration/test_confidence_full_pipeline_2l51c.py ......... 13 passed
tests/unit/test_full_pipeline_metrics_2l51d.py .................... 7 passed
```
Combined: **53 passed**.

Required Phase 3A regressions:
- `pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q` → **47 passed**.
- `pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py tests/integration/test_confidence_v12b_shadow_2l50d.py -q` → **100 passed**.
- `pytest tests/unit/test_confidence_v12b_config_2l50a.py tests/unit/test_qwen_predictor_backend_accessor_2l50b.py tests/unit/test_confidence_v12b_artifacts_2l50c.py -q` → **37 passed**.
  (47 + 100 + 37 = **184 passed**, matching AUDIT 89/92/93 exactly — no regressions in the
  approved Phase 3A surface.)

`python -m compileall predict.py src tests` → **OK**. `git diff --check` → **clean** (exit 0).

## 16. Full-suite baseline comparison

`python -m pytest -q` (with this pass's changes applied): **65 failed, 835 passed**.

A/B comparison against a clean baseline: `git stash --include-untracked` (reverting to the AUDIT
92 HEAD exactly) → full suite → **65 failed, 782 passed**. The two 65-line `FAILED` test-name
lists (post-fix vs. clean baseline) were diffed and are **byte-for-byte identical** — `diff`
produced no output. `git stash pop` restored the working tree. Arithmetic: 835 = 782
baseline-passed + 53 new. **This pass introduces zero new failures.** The 65 pre-existing failures
are Windows-only `UnicodeDecodeError`/`UnicodeEncodeError` (test helpers reading/writing
Vietnamese-language fixtures without `encoding="utf-8"`, defaulting to `cp1252`) and `bash -n`
subprocess syntax-check calls that fail because this session's WSL relay cannot exec `/bin/bash` —
both pre-existing, environment-only, and outside this pass's file scope, exactly as documented in
AUDIT 93 §17 and independently re-confirmed here after the F1 fix and new tests.

## 17. Windows/Docker/GPU/model identity

- Host: Windows (same machine as AUDIT 92).
- `docker image inspect vquclinh/fastmcq-local-selective:d0d8c28-lf` →
  `sha256:e62473ed524962fd44da393842a6adde0b4faf575327d4758680494555b6634a` — **identical digest**
  to AUDIT 92; image was **not** rebuilt or repulled.
- Model: `/models/qwen3-4b-instruct-2507` (baked into the image; no download).
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB total, idle (0 MiB used) before each run.

**Docker infrastructure incident (disclosed in full):** the first two Run-A attempts crashed with
Docker-daemon-level `unexpected EOF` immediately after model-weight loading completed (100%), both
times, with `docker run` exit code 125. Following that, `docker ps`/`docker inspect`/`docker
version` all hung indefinitely, indicating a genuinely unresponsive Docker Desktop/WSL2 backend —
not a code defect (weight loading succeeded both times; the crash was at the container-runtime
level, before any of this pass's Python code had a chance to run inference). The user was informed
and manually restarted Docker Desktop; after that, `docker ps` responded immediately and Run A
succeeded cleanly. No image rebuild, no repull, no model re-download occurred at any point during
this recovery — only the Docker Desktop application/WSL2 backend was restarted (an operational
action, not a change to the repository, the image, or the model).

## 18. Real-model Run A results (Base-only)

- Dataset: `scratch/phase2_real/synthetic21_input.json` (same 21-item self-authored synthetic set
  as AUDIT 71/76/92).
- Exit code: **0**. Wall duration: **173.3 s** (includes cold weight load; the earlier two crashed
  attempts are excluded from this figure).
- Peak GPU memory (host `nvidia-smi`, 1 Hz sampling): **6345 MiB**.
- Official CSV: SHA-256 `3A8940B96A0CB33D8F221E01B41CC7418C059CD51F5F51D3C82002C2D5DBEB8D`, 476
  bytes, 22 lines (header + 21 rows) — **identical hash** to AUDIT 92's Base-only run and to
  AUDIT 76's baseline, three independent sessions in a row producing byte-identical output on this
  fixed dataset/model/hardware.
- 21/21 predicted, 0 deterministic fallbacks.

## 19. Real-model Run B results (full pipeline)

- Command: `--confidence-full-pipeline --confidence-full-pipeline-path <jsonl>
  --confidence-full-pipeline-summary-path <summary>`.
- Exit code: **0**. Wall duration: **381.8 s**. Peak GPU memory: **6375 MiB**.
- Router-selected records: **3** (`syn_020_sequence`, `syn_008_speed`, `syn_001_addition_3`) —
  identical selected set to every prior real-model run of this dataset (AUDIT 76/92).
- V12B attempted: 3/3 selected records (all passed the input-validation boundary).
  V12B statuses: `insufficient_valid_permutations`: 1, `all_invalid`: 1, `valid_unique_majority`: 1
  — identical distribution to AUDIT 92's V12B-shadow run on the same dataset.
- V13 attempted: **2** records (the two V12B did not accept). V13 layer used for both: the
  question-appropriate layer chosen automatically by the deterministic classifier (both
  arithmetic-style questions → `programmatic_solver`, per source-level inspection of `predict.py`'s
  stdout and the artifact's `v13_status`). V13 status: `ok` for both (2/2 succeeded).
- `final_source` distribution: `v13`: 2, `v12b`: 1, `base`: 18.
- Base→V12B/V13 answer changes (3 total, all router-selected records):
  - `syn_001_addition_3`: Base `A` → final `B` (source: v13)
  - `syn_008_speed`: Base `A` → final `C` (source: v13)
  - `syn_020_sequence`: Base `C` → final `D` (source: v12b)
- Official CSV: SHA-256 `8E72EC955A3F47A53F705CADB2B8F32AC1359A2BA0FC40E64B03FCBD3D8A1A6A`, 476
  bytes, 21 rows, qid order identical to Run A; differs from Run A's hash in exactly the 3 changed
  rows (verified via `Compare-Object`).

## 20. Real-model Run C results (full-pipeline repeat)

- Identical command and settings to Run B. Exit code: **0**. Wall duration: **330.5 s**. Peak GPU
  memory: **6375 MiB**.
- Official CSV SHA-256: **identical** to Run B (`8E72EC95...B3D8A1A6A`) — confirmed via both hash
  comparison and a full byte-sequence `SequenceEqual` check.
- Diagnostic artifacts (`confidence_full_pipeline.jsonl` and `..._summary.json`): **byte-for-byte
  identical** to Run B (`diff` produced no output on either file).
- **Deterministic final answers, deterministic selector behavior, and stable artifact schema are
  all confirmed** by real-model evidence, not merely inferred from Run A/B's own consistency.

## 21. Failure-safety Run D

One real-model artifact-write-failure probe: `--confidence-full-pipeline-path /etc/hostname/
confidence_full_pipeline.jsonl` (an existing file inside the container, guaranteeing a directory-
creation failure even as root — the same technique validated in AUDIT 92 §15). Exit code: **0**.
Wall duration: 373.4 s. Result:
- `[predict] WARN full-pipeline JSONL not written (FileExistsError)`
- `[predict] WARN full-pipeline summary not written (FileExistsError)`
- Official submission: **21 rows, byte-identical to Run B/C** (SHA-256 confirmed equal) — the
  artifact-write failure had zero effect on the official output.
- Warnings contain only the operation name and the bare exception class; no path detail beyond
  what the operator itself passed, no stack trace, no record content.
- `git status --short` confirmed clean immediately after — no source/config change from the probe.

Per-record V13 generation-failure fallback (as opposed to the artifact-write failure exercised
above) was **not** additionally forced in the real-model context — doing so safely would require
either a broken/rate-limited model call or a source change, both out of scope. That exact fallback
path (`v13_result.valid is False` or an exception during `generate_text` → `final_source =
"base_fallback"`) is instead covered by extensive fake-backend tests
(`test_v13_invalid_output_falls_back_to_base`, `test_v13_exception_falls_back_to_base`,
`test_v12b_literal_tie_with_failing_v13_falls_back_to_base`, all re-run passing in this pass) —
model-free evidence for that specific path, real-model evidence for the artifact-write path.

## 22. Runtime/GPU comparison

| Run | Exit | Duration | Peak GPU MiB |
|---|---|---|---|
| A (Base) | 0 | 173.3 s | 6345 |
| B (full pipeline) | 0 | 381.8 s | 6375 |
| C (full pipeline repeat) | 0 | 330.5 s | 6375 |
| D (artifact-write failure) | 0 | 373.4 s | not separately sampled |

All peaks cluster at **≈6.2–6.4 GiB**, well under the 8188 MiB card limit — no OOM in any run.
Full-pipeline runs take noticeably longer than Base-only (V12B permutation calls + V13 calls add
real generation time for the 3 selected records), but duration varies run-to-run with OS
page-cache state for model-weight loading (consistent with the caveat already established in
AUDIT 76/92) and must not be read as a precise per-record V12B/V13 cost measurement.

## 23. Labeled-data provenance

Per Part 4's explicit preference order, the **existing explicit answer keys in the synthetic
validation source** were used — the first and most-preferred option, no new fixture needed:
`scratch/phase1_real/synthetic21_confidence_validation.py` (a local, untracked, self-authored file
already present on this machine from a prior session, gitignored under `scratch/*`, **not**
organizer test data, **not** leaderboard-inferred) contains an explicit `"expected"` field for all
21 items. A small labels-only manifest (`qid` → `expected`, no question/choice text) was extracted
via `ast.literal_eval` and written to `scratch/phase2_real/synthetic21_answer_manifest.json` (also
gitignored, not committed). This is the **same 21-item set** used for the real-model runs in
§§18–21, so Base/full-pipeline answers could be scored directly against it without any additional
model inference. No organizer ground truth was read at any point; no leaderboard score was
consulted or inferred from.

## 24. Base accuracy

**16/21 = 76.19%** (Run A). Wrong records: `syn_001_addition_3` (A vs expected B),
`syn_003_algebra_4` (B vs expected C), `syn_008_speed` (A vs expected C), `syn_017_vn_spelling` (C
vs expected A), `syn_020_sequence` (C vs expected D). This figure is **identical** to AUDIT 71's
independently-computed "Generated accuracy: 16/21 = 0.7619047619" from an earlier, unrelated
session — strong cross-session consistency evidence for the Base path itself (not a Phase 3B
claim).

## 25. Full-pipeline accuracy

**19/21 = 90.48%** (Run B/C, byte-identical to each other). All three router-selected/overridden
records (`syn_001_addition_3`, `syn_008_speed`, `syn_020_sequence`) were previously wrong in Base
and are now correct. `syn_003_algebra_4` and `syn_017_vn_spelling` — the two Base-wrong records the
router did **not** select — remain wrong (unchanged from Base; the pipeline never touches
non-selected records by design).

## 26. Corrections/regressions/net result

- **Corrections** (Base wrong → final correct): **3** — all three overridden records.
- **Regressions** (Base correct → final wrong): **0**.
- **Net corrected records**: **+3** (net accuracy difference: **+0.1429**, i.e. +14.3 percentage
  points on this 21-item set).
- V12B override count: 1. V13 override count: 2. Base-fallback count: 0.
- Per-final-source accuracy: `v12b` (n=1): 1/1 correct (100%); `v13` (n=2): 2/2 correct (100%);
  `base` (n=18, i.e. every non-selected record): 15/18 correct (83.3%, unchanged from Base since
  the pipeline does not touch these records).
- Records changed by the selector: exactly the 3 listed in §19/§25; every other qid's answer is
  byte-identical to Run A.

**This result is genuinely positive, but n=21 with only 3 overridden records is a very small
sample** — see §32 and §27 for why this does not, by itself, justify default promotion.

## 27. Default-promotion criteria evaluation

| Criterion | Status | Evidence |
|---|---|---|
| No Critical/High/Medium unresolved defect | **Met** | §4/§5 — the one defect found (F1) was fixed in this same pass |
| Real-model Runs A–D succeed without OOM | **Met** | §18–22 — all exit 0, peak ≈6.3–6.4 GiB of 8188 MiB |
| Output row count/qid order/schema correct | **Met** | §18–21 — 21 rows, header, qid order identical across all real runs |
| Every final answer is canonical | **Met** | §11 (module-enforced after F1 fix) + §19 real artifact inspection |
| V13 failures fall back safely | **Met (model-free evidence for the exact failure path; real-model evidence for the artifact-write path)** | §21, §5 tests |
| No privacy leak | **Met** | §13 |
| No forbidden legacy/API path | **Met** | §3/§9/§10 — no imports of legacy V13/system/selector/OpenRouter anywhere |
| Full-pipeline labeled accuracy not lower than Base | **Technically met, but on an insufficient sample** | §24–26: 90.48% vs 76.19%, but derived from only 3 override events |
| No unacceptable Base-correct→final-wrong regression pattern | **Technically met (0 regressions), but on an insufficient sample** | §26 |
| Behavior repeatable enough for BTC execution | **Met** | §20 — byte-identical official CSV and diagnostic artifacts across two independent real-model runs |

**Nine of ten criteria are unambiguously met on their own terms.** The two accuracy/regression
criteria are the exception: they are literally satisfied by the numbers, but the judgment call in
this audit is that **3 override events on a 21-item, self-authored synthetic set is not a
statistically meaningful basis for concluding "accuracy not lower than Base" or "no unacceptable
regression pattern" with the confidence a live competition default deserves.** A single flipped
outcome among those 3 (e.g., if `syn_020_sequence`'s V12B override had instead been wrong) would
have changed the corrections:regressions ratio from 3:0 to 2:1 — a materially weaker result — and
nothing in this evaluation rules that out as a plausible outcome on a different, larger, more
diverse item set (the true competition test set, which this pipeline has never been evaluated
against, since no organizer ground truth is permitted). This reasoning follows the same standard
every prior audit in this repository has applied to this exact 21-item set (AUDIT 71 §4: "these
results are diagnostic, not competition accuracy"; AUDIT 76 §21: "do not promote... on the basis
of this diagnostic run"), extended consistently to the accuracy criterion here. This is a stricter
reading than the task's literal criteria required, applied deliberately and transparently — not a
weakening of any criterion to force a particular outcome in either direction.

## 28. Whether default promotion was performed

**No.** The full confidence pipeline remains strictly opt-in (`--confidence-full-pipeline`). The
no-flag path, `--legacy-dynamic-full`, and `--confidence-v12b-shadow` are all **unchanged** by this
pass beyond the F1 hardening (which only affects `run_full_pipeline`'s own internal behavior, never
reachable unless `--confidence-full-pipeline` is explicitly passed). No `--base-only` escape hatch
was added because no promotion occurred — there is nothing to escape from.

## 29. Final no-flag behavior

Unchanged and re-verified in this pass: `test_no_flag_stays_base_only` (Run: same test as AUDIT
93) passes; real-model Run A (§18) is the Base-only path exercised for real, producing the same
hash as AUDIT 92 and AUDIT 76.

## 30. Base-only escape-hatch behavior

Not applicable — no promotion occurred (§28), so no escape hatch was needed or added.

## 31. BTC package checks

- **Offline operation**: confirmed — no network call occurs anywhere in the new code (grep-
  verified: no `requests`/`urllib`/`openrouter`/`api_key` import in any Phase 3B file); the real
  Docker runs used only the pre-baked model, no download.
- **No external network/API requirement**: confirmed for the same reason.
- **Accepted Docker image**: `vquclinh/fastmcq-local-selective:d0d8c28-lf`, digest unchanged
  (§17) — not rebuilt, not repulled.
- **Model path**: `/models/qwen3-4b-instruct-2507`, confirmed present and used (§17–21 logs).
- **Valid BTC submission schema**: `qid,answer` header + N data rows, confirmed in every real run.
- **Stable qid order**: confirmed identical across Runs A/B/C/D (§18–21).
- **Canonical labels**: confirmed both in tests (§14) and in the real Run B/C/D artifacts (§13,
  §19).
- **No unexpected runtime artifacts in tracked paths**: `git status --short` before and after this
  entire pass (including all Docker runs) shows only the expected Phase 3B source/test/audit
  files; all real-model run outputs and the labeled-answer manifest live under `scratch/`, which
  is gitignored (`.gitignore:64: scratch/*`) — confirmed via `git check-ignore -v`.
- **Clean Git scope**: confirmed (§2, and re-confirmed after all Docker activity).
- **Fallback behavior**: confirmed at three independent levels — per-record V13 failure (model-free
  tests), whole-pipeline failure (model-free test + design), and real-model artifact-write failure
  (§21).
- **No V13/selector/legacy accidental invocation outside the intended mode**: confirmed via static
  import analysis (no V13/selector/legacy import reachable from the no-flag or
  `--confidence-v12b-shadow` code paths) and via the mode-conflict tests (§12).

## 32. Remaining limitations

- **The labeled evaluation sample is small.** 21 total records, only 3 actually overridden by the
  pipeline. This is explicitly why default promotion was declined (§27) despite every other
  criterion being met. A larger, more diverse permitted labeled set (still self-authored/synthetic,
  never organizer data) would be needed before reconsidering promotion.
- **No organizer ground truth exists or was used anywhere in this pass** — the true competition
  accuracy of either Base or the full pipeline remains genuinely unknown.
- **V13's per-record layer choice is a small heuristic**, validated here only insofar as it
  produced two correct `programmatic_solver` results on two arithmetic-style questions; the
  `content_first` and `least_to_most` layers were not exercised by any router-selected record in
  this dataset (none of the 3 selected records triggered those layers) and so have **no real-model
  evidence** in this pass beyond the model-free fake-backend tests.
- **Thresholds remain provisional** (`provisional_margin_threshold=10.0`,
  `min_valid_permutations=5`, `consensus_votes=4`, V13's `max_new_tokens=384`) — none recalibrated
  or finalized by this pass.
- **Docker/WSL2 instability was observed on this host** during this session (§17) — resolved by a
  user-performed Docker Desktop restart, not by any code or environment change. This is noted as an
  operational risk for future validation sessions on this machine, not a defect in the pipeline
  itself.
- **Real-model evidence in this pass covers only this one 21-item dataset.** No other dataset size,
  domain mix, or choice-count distribution has been exercised against the real model under
  `--confidence-full-pipeline`.

## 33. Files modified/created

Modified (tracked, cumulative across AUDIT 93 + this pass): `predict.py`,
`configs/confidence_selective.yaml`, `src/local_model/confidence_config.py`. Created (untracked):
`src/local_model/confidence_v13_runner.py`, `src/local_model/confidence_full_pipeline.py`
(hardened in this pass, §5), `src/local_model/confidence_full_pipeline_artifacts.py`,
`src/evaluation/__init__.py`, `src/evaluation/full_pipeline_metrics.py`,
`tests/unit/test_confidence_v13_runner_2l51a.py`,
`tests/unit/test_confidence_full_pipeline_selector_2l51b.py` (extended in this pass, §5),
`tests/integration/test_confidence_full_pipeline_2l51c.py`,
`tests/unit/test_full_pipeline_metrics_2l51d.py`, `docs/audits/93-...md`, this audit. Untracked,
gitignored scratch artifacts (not part of the repository): `scratch/phase2_real/
synthetic21_answer_manifest.json`, `scratch/phase3b_full_pipeline_windows/{runA,runB,runC,
runD_probe1}/*`.

## 34. Files explicitly unchanged

`src/local_model/confidence_v12b_runner.py` (no verified blocker required touching it),
`src/local_model/confidence_v12b_artifacts.py`, `src/local_model/confidence_shadow_router.py`,
`src/local_model/qwen_mcq_predictor.py`, `src/local_model/local_qwen_backend.py`,
`src/layers/programmatic_solver_layer.py`, `src/layers/content_first_answerer.py`,
`src/layers/least_to_most_constraint_solver.py`, `src/layers/v13_dynamic_layer.py`,
`src/layers/v13_layer_registry.py`, `src/system/fastmcq_system.py`, everything under
`src/selector/`, the Dockerfile, dependency files, AUDIT 1–93 (all preserved unmodified;
`git diff --name-only` confirms none of these appear in the diff).

## 35. Confirmation

- No organizer ground-truth leakage: the labeled evaluation used only a self-authored synthetic
  answer key already present on this machine from a prior session (§23); no organizer test file
  was read as labeled data anywhere in this pass.
- No leaderboard label inference: no leaderboard score was consulted or used to infer any answer.
- No external API: confirmed (§31).
- No model download: confirmed — the model was already baked into the unchanged, non-rebuilt,
  non-repulled Docker image (§17).
- No unauthorized legacy path: confirmed (§3, §9, §10, §31) — no V13/selector/legacy/API import is
  reachable from any code path exercised in this pass.
- No raw private-text artifact: confirmed (§13) both by model-free tests and by direct inspection
  of the real Docker-run diagnostic artifacts.
- No commit or push: confirmed — `git status --short` at the end of this pass (§2/§31) shows the
  same working-tree scope as at the start, plus this audit file; nothing staged, nothing committed,
  nothing pushed.

## 36. Current Git status

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
?? docs/audits/93-confidence-full-pipeline-v12b-v13-selector-implementation.md
?? docs/audits/94-final-review-validation-and-promotion-full-confidence-pipeline.md
?? src/evaluation/
?? src/local_model/confidence_full_pipeline.py
?? src/local_model/confidence_full_pipeline_artifacts.py
?? src/local_model/confidence_v13_runner.py
?? tests/integration/test_confidence_full_pipeline_2l51c.py
?? tests/unit/test_confidence_full_pipeline_selector_2l51b.py
?? tests/unit/test_confidence_v13_runner_2l51a.py
?? tests/unit/test_full_pipeline_metrics_2l51d.py
```

## 37. Recommended next action

Construct or obtain a larger permitted labeled set (still self-authored/synthetic — never
organizer data) — ideally on the order of 100+ items with a similar domain/choice-count mix to the
real competition — and re-run the same Run A/B/C/D + labeled-evaluation procedure used here. If the
correction:regression ratio and net accuracy gain remain strongly positive at that scale, default
promotion (with a `--base-only` escape hatch, as specified in Part 5) would then have a
statistically credible basis. Independently, exercise the `content_first` and `least_to_most` V13
layers against the real model at least once each (this dataset never triggered them), since they
currently have real-model coverage of zero calls.

## 38. Final verdict

**FULL CONFIDENCE PIPELINE VALIDATED; REMAINS OPT-IN DUE TO EVIDENCE**

The one real defect found in adversarial review (F1, canonical-answer enforcement) was fixed in
this same pass; 53 tests (including the previously-missing literal V12B tie test and three new
fail-closed hardening tests) all pass; zero new failures were introduced anywhere in the 894-test
model-free suite (exact A/B diff against a clean AUDIT-92 baseline); real-model Runs A–D on the
accepted Windows/Docker/GPU/model stack all succeeded without OOM, with byte-identical, fully
deterministic output across repeated full-pipeline runs and a clean artifact-write failure-safety
demonstration; the one available permitted labeled evaluation (21 self-authored synthetic items)
showed a genuinely encouraging result — 3 corrections, 0 regressions, +14.3 percentage points — but
that sample is judged too small to justify changing the live competition default. The pipeline is
therefore validated as correct, safe, and fail-closed, and remains available via
`--confidence-full-pipeline` for continued evaluation; it is **not** promoted to the no-flag
default in this pass.
