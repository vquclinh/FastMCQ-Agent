# AUDIT 95 - Large Benchmark, Time-Constrained Subset30 Evaluation, and Default-Promotion Decision

Audit number 95 (no prior `95-*` existed under `docs/audits/`).

## 1. Date, branch, starting HEAD

- Date: 2026-07-10.
- Branch: `main`.
- Starting full HEAD: `da399a79797bc4cff5f672b70da869bc91e208a4`
  (`add and validate confidence-routed V12B V13 pipeline`).
- Governing prior state: AUDIT 94. AUDIT 94 is committed in the starting history and remains the
  current governing pre-Audit-95 confidence-pipeline state.

## 2. Initial clean state

Preflight results:

- `git branch --show-current` -> `main`.
- `git rev-parse HEAD` -> `da399a79797bc4cff5f672b70da869bc91e208a4`.
- `git status --short` -> empty.
- `git log -8 --oneline --decorate` included `da399a7` with AUDIT 93 and AUDIT 94 committed at the
  tip history.
- `git diff --check` -> clean.
- `git diff --cached --check` -> clean.

No unrelated work existed at session start.

## 3. Benchmark construction method

Created a deterministic self-authored 120-record benchmark with stable seed `20260710`:

- `scripts/validation/build_confidence_promotion_benchmark.py`
- `validation/confidence_promotion_benchmark.json`
- `validation/confidence_promotion_manifest.json`

The model-facing benchmark JSON contains only `qid`, `question`, and `choices`. The manifest contains
the expected answer, category, intended V13 layer, choice count, language, seed, template id, and
deterministic gold provenance.

Gold answers come from:

- local arithmetic/programmatic calculations;
- explicit invented local fact tables embedded in the generated questions;
- exhaustive local ordering/scheduling/assignment/table solvers.

No organizer data, leaderboard inference, evaluated-model output, or LLM-generated unverified label is
used as gold.

## 4. 120-record distribution

- Categories: `programmatic_arithmetic`: 40, `content_first`: 40, `least_to_most`: 40.
- Intended V13 layers: `programmatic_solver`: 40, `content_first`: 40, `least_to_most`: 40.
- Choice counts: 2/3/4/5/6 choices, 24 records each.
- Languages: English 60, Vietnamese ASCII-form 60.
- Correct-label positions:
  - 2 choices: A 12, B 12.
  - 3 choices: A 8, B 8, C 8.
  - 4 choices: A 6, B 6, C 6, D 6.
  - 5 choices: A 5, B 5, C 5, D 5, E 4.
  - 6 choices: A 4, B 4, C 4, D 4, E 4, F 4.

Validation checks prove unique qids, canonical labels, 2-26 choices, category/layer/choice/language
coverage, answer-position balance, byte-deterministic regeneration, and deterministic non-model gold.

## 5. Subset30 pivot

The initial 120-record full-pipeline Run B was taking longer than the available time. The user
explicitly redirected the validation to a deterministic 30-record subset and instructed that no partial
120-record Run B output be used for accuracy or promotion metrics.

The in-flight 120-record Run B was stopped safely:

- Background PowerShell runner PID: `25376`, stopped.
- Docker container: `b48a34da724d`, stopped.
- `scratch/confidence_promotion_large/runB_full/status.json` marked:
  `ABORTED FOR TIME-CONSTRAINED VALIDATION`.
- Docker remained responsive: final `docker ps` output was empty.
- GPU returned to idle: `NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB, 0 MiB`.

Partial Run B output is explicitly excluded from all metrics in this audit.

## 6. Subset30 construction

Created:

- `validation/confidence_promotion_subset30.json`
- `validation/confidence_promotion_subset30_manifest.json`

The subset is selected deterministically from the committed 120-record manifest, independent of model
outputs, Base correctness, router decisions, or expected pipeline behavior.

Subset30 distribution:

- Total records: 30.
- Categories: 10 programmatic, 10 content-first, 10 least-to-most.
- Intended V13 layers: 10 programmatic_solver, 10 content_first, 10 least_to_most.
- Choice counts: 2/3/4/5/6 choices, 6 records each.
- Languages: English 15, Vietnamese ASCII-form 15.
- Correct-label positions:
  - 2 choices: A 3, B 3.
  - 3 choices: A 2, B 2, C 2.
  - 4 choices: A 2, B 2, C 1, D 1.
  - 5 choices: A 1, B 2, C 1, D 1, E 1.
  - 6 choices: A 1, B 1, C 1, D 1, E 1, F 1.

## 7. Files created/modified

Created:

- `scripts/validation/build_confidence_promotion_benchmark.py`
- `scripts/validation/evaluate_confidence_promotion_outputs.py`
- `validation/confidence_promotion_benchmark.json`
- `validation/confidence_promotion_manifest.json`
- `validation/confidence_promotion_subset30.json`
- `validation/confidence_promotion_subset30_manifest.json`
- `tests/unit/test_confidence_promotion_benchmark_2l52a.py`
- this audit.

Modified:

- `src/local_model/confidence_full_pipeline.py` - adds privacy-safe `v13_layer` per-record diagnostics
  and `v13_layer_counts` summary.
- `tests/unit/test_confidence_full_pipeline_selector_2l51b.py` - asserts V13 layer diagnostics.
- `tests/integration/test_confidence_full_pipeline_2l51c.py` - asserts V13 layer diagnostics in
  artifacts.

Scratch-only helpers/outputs were written under `scratch/confidence_promotion_large/` and are not
tracked.

## 8. Tests added

`tests/unit/test_confidence_promotion_benchmark_2l52a.py`: 15 tests covering:

- deterministic 120-record regeneration;
- committed artifact byte identity;
- answer-key correctness;
- arithmetic generator correctness;
- content-fact mapping correctness;
- least-to-most solver correctness;
- choice-label validity;
- duplicate-qid rejection;
- malformed-record rejection;
- category/layer coverage;
- answer-position distribution;
- deterministic subset30 regeneration;
- committed subset30 byte identity;
- subset30 counts/labels;
- subset30 membership in the 120-record benchmark.

## 9. Model-free test results

- `pytest tests/unit/test_confidence_promotion_benchmark_2l52a.py -q --basetemp=scratch\pytest_benchmark_tmp`
  -> 15 passed.
- `pytest tests/unit/test_confidence_v12b_runner_2l49a.py -q` -> 47 passed.
- Required confidence suite with workspace temp base:
  `pytest tests/unit/test_choice_scoring_2l48b.py tests/integration/test_confidence_telemetry_2l48c.py tests/unit/test_confidence_shadow_router_2l48d.py tests/integration/test_confidence_shadow_router_2l48e.py tests/integration/test_confidence_v12b_shadow_2l50d.py tests/unit/test_confidence_v13_runner_2l51a.py tests/unit/test_confidence_full_pipeline_selector_2l51b.py tests/integration/test_confidence_full_pipeline_2l51c.py tests/unit/test_full_pipeline_metrics_2l51d.py -q --basetemp=scratch\pytest_confidence_tmp`
  -> 153 passed.
- `python -m compileall predict.py src scripts tests` -> OK.
- `git diff --check` -> clean.

Note: the same broad confidence command without `--basetemp` first hit a Windows temp-directory
permission setup error (`PermissionError` under `C:\Users\Vo Quoc Linh\AppData\Local\Temp`), before
integration tests could run. Rerunning with a workspace temp base produced the real regression signal:
153 passed. This is an environment/temp permission issue, not a code assertion failure.

## 10. Windows/Docker/GPU/model identity

- Docker image: `vquclinh/fastmcq-local-selective:d0d8c28-lf`.
- Image digest: `sha256:e62473ed524962fd44da393842a6adde0b4faf575327d4758680494555b6634a`.
- Model path: `/models/qwen3-4b-instruct-2507`; confirmed present inside the container.
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, 8188 MiB.
- Container CUDA check: CUDA available; GPU visible as NVIDIA GeForce RTX 4060 Laptop GPU.
- No image rebuild, no repull, no model download, no external API.

## 11. Run A - completed 120-record Base

Run A was the current no-flag Base-only path on the full 120-record benchmark.

- Input: `validation/confidence_promotion_benchmark.json`.
- Exit code: 0.
- Duration: 179.265 s.
- Peak GPU memory: 6359 MiB.
- CSV SHA-256: `332E4119CD8B3CA4517D688F87ABA5FC38D0104E79D8F33248E571D0CEBC1DB3`.
- Rows: 120.
- qid-order SHA-256: `7E4335C7A1864617443A64B62A81A9A235118D0183300931E58EE3DE1AF8AEFE`.

Run A was retained and reused only as the source of Base predictions for subset30. It was filtered to
`scratch/confidence_promotion_large/runA_base/submission_subset30.csv` in deterministic subset order.
The subset was selected before scoring the filtered Base output, so no cherry-picking occurred.

## 12. Run B - aborted 120-record full pipeline

The initial full 120-record Run B was aborted solely for time-constrained validation.

- Input: `validation/confidence_promotion_benchmark.json`.
- Mode: `--confidence-full-pipeline`.
- Status: `ABORTED FOR TIME-CONSTRAINED VALIDATION`.
- No partial Run B output was used for accuracy, repeatability, or promotion metrics.

## 13. Subset30 Base score

Base predictions came from completed 120-record Run A, filtered to the fixed 30 subset qids in subset
order.

- Base correct: 28/30.
- Base accuracy: 93.33%.
- By category:
  - content_first: 10/10.
  - least_to_most: 10/10.
  - programmatic_arithmetic: 8/10.

## 14. Run B30 - full pipeline on fixed subset30

Run B30 executed the full confidence pipeline on the same fixed 30 records.

- Input: `validation/confidence_promotion_subset30.json`.
- Command mode: `--confidence-shadow-router --confidence-full-pipeline`.
- Exit code: 0.
- Duration: 476.516 s.
- Peak GPU memory: 6425 MiB.
- CSV SHA-256: `A9DB8C92436100894F1689D91E889CC8A9C9115EFEE6E463945B47B98DEE4946`.
- Rows: 30.
- qid-order SHA-256: `F83A515340C5CC2FC2013CC7F6554F229EF37A0520D9D50B9AE7DACC4AC546CE`.

Router:

- Candidates: 10.
- Selected: 4 (`cp_prog_001`, `cp_logic_table_016`, `cp_prog_016`, `cp_prog_028`).
- Reason counts: `low_logit_margin`: 10.

V12B:

- Attempted: 4.
- Status counts: `insufficient_valid_permutations`: 4.
- Accepted V12B overrides: 0.

V13:

- Attempted: 4.
- Accepted: 3.
- Layer counts: `programmatic_solver`: 3, `content_first`: 1.
- Status counts: `ok`: 3, `parse_error`: 1.
- `least_to_most` was present in the subset design but was not exercised as a V13 layer by the normal
  router-selected set in B30.

Final source counts:

- `base`: 26.
- `v13`: 3.
- `base_fallback`: 1.

## 15. Run B30 accuracy and changes

Against the fixed subset30:

- Base accuracy: 28/30 = 93.33%.
- Full-pipeline accuracy: 28/30 = 93.33%.
- Changed-answer count: 0.
- Corrections: 0.
- Regressions: 0.
- Neutral changes: 0.
- Net corrected records: 0.
- Correction precision: 0.0.
- Regression rate: 0.0.

By category:

- content_first: Base 10/10, full pipeline 10/10.
- least_to_most: Base 10/10, full pipeline 10/10.
- programmatic_arithmetic: Base 8/10, full pipeline 8/10.

By final source:

- `base` (n=26): Base 24/26, final 24/26.
- `v13` (n=3): Base 3/3, final 3/3.
- `base_fallback` (n=1): Base 1/1, final 1/1.

The full pipeline was not below Base, but it also produced no corrections. The explicit promotion gate
"corrections exceed regressions" is therefore not met (`0 > 0` is false).

## 16. Selected-record repeat diagnostic

A diagnostic repeat was run on only the four B30 router-selected records, using B30's captured router
decisions and the real model. This was diagnostic only and was not counted as a second accuracy
evaluation.

Repeat summary:

- Records: 4.
- V12B status counts: `insufficient_valid_permutations`: 4.
- V13 layer counts: `programmatic_solver`: 3, `content_first`: 1.
- V13 status counts: `ok`: 3, `parse_error`: 1.
- Final source counts: `v13`: 3, `base_fallback`: 1.

Per-qid comparison with B30 selected records was stable for:

- `final_answer`
- `final_source`
- `v12b_status`
- `v13_attempted`
- `v13_layer`
- `v13_status`
- `v13_answer`

Diagnostic result: `all_stable: true`.

## 17. Failure safety probe

A scratch-only 6-record input was created deterministically from subset30: two records per category.
The artifact-write failure probe used bad full-pipeline artifact paths under `/etc/hostname/...`.

- Input: `scratch/confidence_promotion_large/subset6.json`.
- Exit code: 0.
- Duration: 144.208 s.
- Peak GPU memory: 6375 MiB.
- Rows: 6.
- Warnings:
  - `[predict] WARN full-pipeline JSONL not written (FileExistsError)`
  - `[predict] WARN full-pipeline summary not written (FileExistsError)`
- Official submission remained complete and valid.

This supplements, rather than replaces, the more extensive failure-safety evidence from AUDIT 94.

## 18. Promotion criteria evaluation

- At least 120 labeled records constructed: met.
- Time-constrained promotion comparison used deterministic subset30: documented and fixed before
  scoring.
- Full-pipeline accuracy not below Base on same fixed 30 records: met (28/30 vs 28/30).
- Corrections exceed regressions: not met (0 corrections, 0 regressions).
- No severe Base-correct to final-wrong pattern: met (0 regressions).
- Outputs canonical and ordered: met by evaluator and row/qid checks.
- Router/V12B/V13/selector execution valid: met for B30 selected records.
- No OOM: met in completed Run A, B30, selected-repeat diagnostic, and 6-record failure probe.
- Privacy/failure safety: met for the exercised artifacts and failure probe.
- Statistical certainty: not claimed. Thirty records and four selected records remain limited.

Because corrections did not exceed regressions, promotion is not allowed under the user's gate.

## 19. Promotion decision and code behavior

No promotion was performed.

- The no-flag path remains Base-only.
- `--confidence-full-pipeline` remains opt-in.
- `--confidence-v12b-shadow` remains observational.
- `--base-only` was not added because there is no promoted default to escape.
- Final no-flag promoted smoke, `--base-only`, and promoted-default failure fallback checks were not
  applicable.

The only production-code change is diagnostic schema hardening: `v13_layer` and `v13_layer_counts` are
now recorded in the privacy-safe full-pipeline artifact/summary.

## 20. BTC package checks

- Offline operation: confirmed; no external API path was used.
- One accepted local model/image: confirmed.
- No model download: confirmed.
- Valid `qid,answer` CSV outputs: confirmed for Run A, B30, and 6-record failure probe.
- Stable qid order: confirmed by subset evaluator and qid-order hashes.
- Canonical labels: confirmed by evaluator.
- Safe artifact-write fallback: confirmed by 6-record probe and AUDIT 94.
- No tracked scratch outputs: scratch files are untracked/ignored.
- No unauthorized legacy/API path: no legacy dynamic path used.
- Runtime/GPU fit: completed runs stayed below 8 GiB; peak observed here was 6425 MiB.

## 21. Remaining limitations

- Subset30 is deliberately small and was used only because time became limited.
- B30 selected only four records; this is not enough evidence for statistical certainty.
- The full pipeline made no answer changes relative to Base on subset30, so there is no positive
  correction signal.
- B30 did not exercise the `least_to_most` V13 layer under the normal router-selected path.
- The 120-record full-pipeline run was not completed; it was aborted solely for time and excluded from
  metrics.

## 22. Confirmations

- No organizer data.
- No leaderboard label inference.
- No model-generated gold labels.
- No external API.
- No model download.
- No image rebuild or repull.
- No unauthorized legacy path.
- No partial 120-record Run B metric use.
- No commit.
- No push.

## 23. Current Git status

Before adding this audit file, `git status --short` showed:

```text
 M src/local_model/confidence_full_pipeline.py
 M tests/integration/test_confidence_full_pipeline_2l51c.py
 M tests/unit/test_confidence_full_pipeline_selector_2l51b.py
?? scripts/validation/
?? tests/unit/test_confidence_promotion_benchmark_2l52a.py
?? validation/
```

This audit file is additionally untracked after creation. Nothing is staged.

## 24. Recommended next action

Do not promote on this evidence. If more time is available, complete the original 120-record full
pipeline run or build an additional fixed permitted benchmark and look for a positive correction signal
with enough override events. Also obtain normal-route real-model coverage for the `least_to_most` V13
layer before reconsidering default promotion.

## 25. Final verdict

**LARGE-BENCHMARK EVIDENCE INCONCLUSIVE — FULL PIPELINE REMAINS OPT-IN**
