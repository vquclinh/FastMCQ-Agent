# AUDIT 88 — Phase 3A-1 Observational V12B Integration (implementation record)

Audit number 88 (no prior `88-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD at start

- Date: 2026-07-10
- Branch: `main`
- HEAD at implementation start: `e61c948` ("document phase 3A-1 observational V12B integration plan")
- Working tree/index: clean before implementation; AUDITs 80–87 and the Phase 3A-0 runner committed.

## 2. Scope

One tightly scoped, observational Phase 3A-1 pass implementing the AUDIT 87 governing contract: an
opt-in `--confidence-v12b-shadow` mode that scores once, routes once (Phase 2 router), runs the approved
in-memory Phase 3A-0 runner **only on router-selected valid records**, and writes privacy-safe JSONL +
summary artifacts — with the official CSV kept **byte-identical to Base**. No answer replacement, merge,
V13, selector, legacy V12B, default promotion, final thresholds, ground truth, external API, or model
download. No real model inference was run.

**Where AUDIT 86 was ambiguous, AUDIT 87 governed** (choice range `2..26`; `source_record_ordinal`
identity distinct from the runner-local `record_ordinal`; `max_new_tokens` uses the runner default;
single CLI gate; official CSV before V12B artifacts; whitelist-only serialization).

## 3. Files changed

Production (tracked): `predict.py`; `src/local_model/confidence_config.py`;
`src/local_model/qwen_mcq_predictor.py`; `configs/confidence_selective.yaml`
(+142 / −13 across 4 files).

New production module: `src/local_model/confidence_v12b_artifacts.py` (validation, safe pairing, writer).

New tests: `tests/unit/test_confidence_v12b_config_2l50a.py`;
`tests/unit/test_qwen_predictor_backend_accessor_2l50b.py`;
`tests/unit/test_confidence_v12b_artifacts_2l50c.py`;
`tests/integration/test_confidence_v12b_shadow_2l50d.py`.

Documentation: this audit only.

**Forbidden files untouched (verified via `git diff --name-only`):** `confidence_v12b_runner.py`,
`test_confidence_v12b_runner_2l49a.py`, `mcq_permutation_debiaser.py`, `v12b_dynamic_layer.py`,
`fastmcq_system.py`, V13/selector/Docker/dependency files, the official submission schema, and Phase 1/2
scoring/routing semantics.

## 4. CLI contract (implemented)

Added `--confidence-v12b-shadow`, `--v12b-shadow-path`
(default `scratch/fastmcq_run/confidence_v12b_shadow.jsonl`), `--v12b-shadow-summary-path`
(default `scratch/fastmcq_run/confidence_v12b_shadow_summary.json`). The CLI flag is the **only**
execution opt-in; path flags without it are inert. `--legacy-dynamic-full` + `--confidence-v12b-shadow`
raises `SystemExit` **before** input resolution or model construction. No-flag and Phase-2-shadow-only
behavior are unchanged.

## 5. Config contract (implemented)

`load_v12b_config` / `V12BShadowConfig` in `confidence_config.py`: `enabled` (structural marker, default
false — not a second gate), `observational_only` (must be true), `require_router_selected` (must be
true), `permutation_count` (int `1..6`, default 6). Forbidden/unexposed fields (`answer_override`,
`merge`, `merge_threshold`, `balanced_policy`, `self_reported_confidence`, `v13`, `selector`,
`min_valid_permutations`, `consensus_votes`, `max_new_tokens`) **fail closed** (ValueError → V12B
disabled, Base output preserved). Unknown non-forbidden keys are tolerated (forward-compat). The
`confidence_v12b` block was added to `configs/confidence_selective.yaml` (disabled by default).

## 6. Backend accessor (implemented)

Added a read-only `@property backend -> LocalQwenBackendProtocol` on `QwenMCQPredictor` returning the
exact `self._backend` — no setter, no `get_local_qwen_backend` call, no load/cache/path side effect.
`predict.py` injects `predictor.backend` into the runner; it never touches `_backend`.

## 7. Score/router reuse and integration point (implemented)

`want_score = telemetry or want_router`; `want_router = shadow_router or v12b`. `_compute_score` runs at
most once per record; one `run_shadow_router` call serves both Phase 2 and V12B. Phase 2 artifacts are
written only when `--confidence-shadow-router` is set. V12B compute **and** write happen strictly **after**
the official CSV write, inside one broad fail-closed `try/except` (warns with class name only), so no V12B
failure can bypass the official output. When choice-scoring is disabled or any config is malformed, V12B
is skipped fail-closed.

## 8. Identity, validation, and pairing (implemented — `confidence_v12b_artifacts.py`)

- **Identity:** `source_record_ordinal` = `enumerate(samples)` index = decision-list position (router
  decisions are one-per-record in input order). `router_selected_rank` is risk-rank metadata only.
  `selected_sequence_ordinal` = position among valid inputs. The runner's own `record_ordinal` stays
  nested under `aggregate` (runner-local, filtered index) and is never used as global identity.
- **Validation (`2..26` choice range per AUDIT 87 §12):** closed codes `ok`, `invalid_record_shape`,
  `invalid_question`, `invalid_choices`, `unsupported_choice_count`, `invalid_canonical_labels`,
  `invalid_base_answer`, `invalid_score_diagnostic`, `invalid_router_rank`, `input_validation_error`.
  Invalid selected records never reach the runner, keep the Base answer, and never abort valid records.
- **Pairing:** only `[e.v12b_input for e in valid_entries]` is passed to `run_v12b_for_selected`; results
  are zipped by list position; `len(results) == len(valid)` is asserted. A valid record can never attach
  to an invalid one (verified by the A-valid / B-invalid / C-valid test).
- **Runner call:** `permutation_count` from config; `max_new_tokens` **not** overridden (runner default
  192); `min_valid_permutations`/`consensus_votes` at runner defaults (5 / 4).

## 9. Artifacts and privacy (implemented)

Whitelist-only serialization: wrapper metadata (labels/ordinals/reasons/status) + the runner's
text-free `V12BAggregateResult.as_dict()` (which nests `V12BPermutationResult.as_dict()` — labels-only
`permuted_to_original`, closed error codes, optional exception class name). `V12BRunInput`
(question/choices) is **never** serialized. Two independently atomic files (temp + rename), each failing
closed with a class-name-only warning; `json.dumps(..., allow_nan=False)`. `official_answer_source` is
fixed to `"base"` at both the record and aggregate level. Forbidden fields (question, choices, option
text, prompt, raw response, evidence, reasoning, model confidence, expected answer, correctness, ground
truth, API keys, raw exception text) are excluded — asserted by privacy tests.

## 10. Tests and results

New Phase 3A-1 tests: **48 passed** (config 12, backend accessor 3, artifacts 8, predict-path
integration 12 — plus parametrized cases). Coverage includes: no-flag unchanged; path-only inert;
disabled/malformed config fail-closed; legacy conflict before model load; one score call and one router
call in combined modes; injected-backend identity and no second lookup; A-valid/B-invalid/C-valid
pairing; duplicate qid / duplicate input_index staying distinct; `2..26` choice bounds and bad-record
codes; V12B generation failure, artifact-write failure, and scoring failure all preserving official CSV;
official CSV **byte-identical** across modes; privacy/`allow_nan=False`; no V13/selector/legacy call;
up-to-six permutation calls; source-vs-runner ordinal distinction.

Full suite: **831 passed, 16 failed**. The 16 failures are the **pre-existing frozen-artifact /
public-replay baseline** (`FileNotFoundError` on `output/*.csv` fixtures in
`test_btc_short_2l31b`, `test_fastmcq_dynamic_system_2l36b`, `test_final_package_2l31a`,
`test_run_profiles_2l38c`, `test_v12b_permutation_2l34b`, `test_v13_dynamic_integration_2l37a`,
`test_v13_multilayer_2l35a`). Verified pre-existing: with the four tracked edits stashed, the identical
16 fail (same names/count), and none of those files import any Phase 3A-1 module. **This pass introduced
zero new failures.**

## 11. Official-output invariance

The official `submission.csv`/`submission_time.csv` are written from the untouched Base `rows`/`times`
before any V12B work; `hypothetical_answer` is never copied into an official row. Integration tests
assert exact byte equality against the Base-only baseline for: V12B on, telemetry+Phase2+V12B combined,
V12B generation failure, artifact-write failure, scoring failure, and choice-scoring disabled.

## 12. Explicit confirmation

No Phase 3B, answer replacement, Base/V12B merge, V13, selector, legacy V12B runner/target selection,
default promotion, balanced policy, self-reported-confidence routing, or final thresholds. No organizer
ground truth, no OpenRouter/external API, no model download, no Docker/dependency change, and no real
model inference. Official answer remains Base. No forbidden file was modified. No commit or push.

## 13. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/confidence_config.py
 M src/local_model/qwen_mcq_predictor.py
?? docs/audits/88-phase3a1-observational-v12b-integration.md
?? src/local_model/confidence_v12b_artifacts.py
?? tests/integration/test_confidence_v12b_shadow_2l50d.py
?? tests/unit/test_confidence_v12b_artifacts_2l50c.py
?? tests/unit/test_confidence_v12b_config_2l50a.py
?? tests/unit/test_qwen_predictor_backend_accessor_2l50b.py
```

## 14. Recommended next action

Independent code review of this Phase 3A-1 implementation, then a Windows real-model **observational**
validation pass (official CSV byte invariance, artifact privacy, actual permutation counts, no
V13/selector/legacy). Do not promote to the no-flag default and do not finalize thresholds on the basis
of this pass.

## 15. Final status

**PHASE 3A-1 OBSERVATIONAL V12B INTEGRATION IMPLEMENTED — READY FOR INDEPENDENT REVIEW.** Observational
only; official output remains Base; Phase 3B / answer replacement / V13 / selector / default promotion
remain unauthorized.
