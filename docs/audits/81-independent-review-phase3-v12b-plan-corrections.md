# AUDIT 81 - Independent Review of AUDIT 80 Phase 3 V12B Plan Corrections

Audit number 81 (no prior `81-*` existed under `docs/audits/`).

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `08b97df4967dd305880a29faffe22fa48aa5df6b` ("document phase 2 Windows shadow validation")

## 2. Initial working-tree state

Preflight matched the takeover contract:

```text
git branch --show-current
main

git rev-parse HEAD
08b97df4967dd305880a29faffe22fa48aa5df6b

git status --short
?? docs/audits/78-phase3-confidence-routed-v12b-planning.md
?? docs/audits/79-independent-review-phase3-v12b-plan.md
?? docs/audits/80-phase3-v12b-plan-corrections.md
```

`git diff --check`, `git diff --stat`, `git diff --cached --check`, and `git diff --cached --stat`
were all empty. Nothing was staged. No source, test, or config file was modified.

## 3. Independence/read-only statement

This is an independent, adversarial, read-only planning review of
`docs/audits/80-phase3-v12b-plan-corrections.md`. No Phase 3A-0 implementation was attempted. No
source, test, config, Docker, model, artifact writer, official-output code, AUDIT 78, AUDIT 79, or
AUDIT 80 file was modified. The only repository file created by this pass is this audit.

## 4. Project takeover/context reconstruction statement

The repository state matches the supplied context: `main` is at the expected committed HEAD, Phase 1
and Phase 2 are already committed, Phase 2's router remains opt-in/observational/off by default, and
Phase 3 is not implemented. The current uncommitted planning records are exactly AUDIT 78, AUDIT 79,
and AUDIT 80 before this audit is created.

## 5. Files and tests reviewed

Planning history read completely:

- `docs/audits/78-phase3-confidence-routed-v12b-planning.md`
- `docs/audits/79-independent-review-phase3-v12b-plan.md`
- `docs/audits/80-phase3-v12b-plan-corrections.md`

Completed-stage context read completely:

- `docs/audits/72-phase2-confidence-shadow-router.md`
- `docs/audits/74-phase2-shadow-router-corrective-pass.md`
- `docs/audits/75-independent-review-phase2-corrective-pass.md`
- `docs/audits/76-windows-real-model-validation-phase2-shadow-router.md`
- `docs/audits/77-independent-review-windows-phase2-evidence.md`

Source read completely:

- `src/layers/mcq_permutation_debiaser.py`
- `src/layers/v12b_dynamic_layer.py`
- `src/local_model/local_qwen_backend.py`
- `src/local_model/qwen_mcq_predictor.py`
- `src/local_model/confidence_shadow_router.py`
- `src/local_model/choice_scoring.py`
- `predict.py`

Additional targeted context read: `src/system/fastmcq_system.py`, `src/utils/labels.py`, and the
allowed test files needed to confirm fake-only execution.

Repo-wide searches were run for: `run_v12b_layer`, `select_v12b_targets`,
`build_option_permutations`, `map_permuted_answer_to_original`, `summarize_permutation_votes`,
`select_permutation_override`, `mean_support_confidence`, `balanced`, `conservative`,
`v12b_dynamic_records.jsonl`, `work.mkdir`, `open(`, `get_local_qwen_backend`, `self._backend`,
`backend`, `generate_text`, `V13`, `selector`, `legacy_dynamic_full`, `qid`, `input_index`, and
`ordinal`.

## 6. Evidence available/unavailable

Available: committed source, uncommitted planning audits 78-80, completed Phase 2 audit records,
repo-wide grep output, pure permutation probes, backend-cache probes, and pure/fake-only test results.

Unavailable by design: real V12B generation behavior, GPU latency/VRAM, Windows runtime behavior for
Phase 3A, calibration evidence, organizer ground truth, and any external API behavior. Those were not
needed for this planning review and were not used.

## 7. AUDIT 80 governing-rule review

AUDIT 80 explicitly states that it supersedes AUDIT 78 where conflicts exist and names the exact
superseded portions: AUDIT 78 sections on direct `run_v12b_layer` reuse, exact six-generation wording,
the ephemeral/persisted boundary, and the combined 3A-0/3A-1 file list. That is sufficient for AUDIT
80 to serve as the governing contract over AUDIT 78.

No wording in AUDIT 80 re-authorizes Phase 3B, answer replacement, V13, selector use, default
promotion, real-model execution, or CLI/config implementation during Phase 3A-0.

## 8. M1 resolution verification

M1 is fully resolved.

Source verification:

- `src/layers/v12b_dynamic_layer.py:137` creates the work directory with `work.mkdir(...)`.
- `src/layers/v12b_dynamic_layer.py:138` fixes the legacy record path to
  `v12b_dynamic_records.jsonl`.
- `src/layers/v12b_dynamic_layer.py:144` opens that JSONL before processing targets.
- The file-open is outside the per-permutation `try`, so an `OSError` can propagate.
- `run_v12b_layer` consumes legacy-shaped `samples`, `BasePrediction`-like objects, and
  `V12BTarget` objects, with qid-keyed maps.

AUDIT 80 section 6 correctly records these facts and makes the binding conclusion that
`run_v12b_layer` must not be called, even through an adapter. AUDIT 80 also bans `select_v12b_targets`
and the legacy writer and requires Phase 3A-0 to persist nothing.

Search result: every `run_v12b_layer` mention in AUDIT 80 is prohibitive or historical; none permits
direct reuse.

## 9. Component reuse verification

`src/layers/mcq_permutation_debiaser.py` is pure for the relevant Phase 3A-0 boundary: it imports only
standard modules plus label helpers, performs no model load, no file I/O, no global backend lookup, no
V13/selector import, and no official-output mutation.

Reuse verdict:

| Component | Review result |
|---|---|
| `build_option_permutations` | Reusable as-is; deterministic, pure, includes mapping metadata. |
| `map_permuted_answer_to_original` | Reusable as-is; validates labels/text/self-checks and returns raw measurable outcomes. |
| `summarize_permutation_votes` | Reusable as-is; counts valid records only and exposes vote/parse/mismatch signals. |
| `select_permutation_override` | Reusable only as conservative hypothetical diagnostic. Balanced is forbidden because it uses `mean_support_confidence`. |
| `run_v12b_layer` | Not reusable for direct Phase 3A; legacy file side effect and legacy-shaped inputs. |
| `select_v12b_targets` | Not reusable; Phase 3A uses Phase 2 router-selected records only. |
| legacy writer | Not reusable; Phase 3A-0 writes nothing, Phase 3A-1 must use a separate privacy-safe writer. |

No V13, selector, or API dependency is reachable from the proposed Phase 3A-0 boundary when the new
runner imports only the permutation core, JSON parsing as needed, and consumes an injected backend.

## 10. M2 resolution verification

M2 is fully resolved.

AUDIT 80 splits the work into separate tasks:

- Phase 3A-0: isolated in-memory runner, fake-backend unit tests, optional narrow backend accessor,
  and implementation/review audits.
- Phase 3A-1: later CLI/config/artifact/predict.py integration after 3A-0 and independent review.

The file scopes are no longer blurred. AUDIT 80 explicitly says the scopes are non-overlapping and
places `predict.py`, YAML/config loading, artifact writers, and predict.py integration tests only in
Phase 3A-1.

## 11. Exact Phase 3A-0 scope verification

AUDIT 80 precisely limits Phase 3A-0 to:

- New `src/local_model/confidence_v12b_runner.py`.
- Runner-specific fake-backend unit tests.
- Future implementation/review audits.
- Optionally one narrow read-only backend accessor in `src/local_model/qwen_mcq_predictor.py` only if
  genuinely needed for clean backend injection.

AUDIT 80 forbids in Phase 3A-0: `predict.py`, `configs/confidence_selective.yaml`,
`src/local_model/confidence_config.py`, CLI flags, config loading, artifact writers, integration
tests invoking `predict.py`, official CSV code, legacy V12B modules, the legacy system, V13, selector,
Docker/dependencies, and answer-changing logic.

This is sufficiently tight for Phase 3A-0.

## 12. Exact Phase 3A-1 scope verification

AUDIT 80 reserves Phase 3A-1 for later observational integration only: `predict.py`,
`configs/confidence_selective.yaml`, `src/local_model/confidence_config.py`, Phase 3A integration
tests, privacy-safe JSONL/summary helpers, explicit CLI/config validation, single scoring/router
reuse, V12B only for selected records, official Base answer unchanged, artifact write fail-closed, and
mode-conflict validation.

AUDIT 80 does not authorize implementing Phase 3A-1 during Phase 3A-0.

## 13. Backend injection/accessor review

Verified source facts:

- `QwenMCQPredictor.__init__` stores the backend in private `self._backend`.
- Public methods are `load`, `predict_one`, and `score_choices`; no public accessor exists.
- `get_local_qwen_backend` caches by `(resolved, device)`, where `resolved` is the raw model-path
  string after default/env fallback, not normalized via `Path.resolve`.
- Probe result: exact same path/device returns the same instance; trailing slash or different device
  returns a different instance; no weights were loaded during the probe.

AUDIT 80's contract is safe: the runner receives an already-created backend instance and never
resolves model paths or calls `get_local_qwen_backend`. The optional read-only accessor is not required
by the plan itself, but it is a clean allowed 3A-0 escape hatch if private-member access would
otherwise be needed. Duplicate-load uncertainty is Low under AUDIT 80 because the binding runner
contract is instance injection, not path-based lookup.

## 14. Ordinal identity review

The private ordinal requirement is sufficient for duplicate qids, duplicate input indexes, both
duplicated, stable decision reconstruction, input-order output, and record-count summaries.

Phase 2's corrected router uses private enumeration ordinals internally and preserves qid/input_index
only as metadata. AUDIT 80 mirrors that pattern and explicitly says qid must not be an internal
association key, input_index must not be assumed unique, summaries count records rather than unique
qids, and future tests must cover duplicate qid/input_index combinations.

The proposed 3A data structures include private per-record identity plus qid/input_index and selected
rank metadata, enough for future 3A-1 artifact writing without falling back to qid-only association.

## 15. Permutation-count/cost review

Source and pure probe agree:

```text
1 choice -> 1 permutation
2 choices -> 2 permutations
3 choices -> 4 permutations
4 choices -> 6 permutations
5 choices -> 6 permutations
10 choices -> 6 permutations
```

The deterministic family order is `original`, `reverse`, `rotate+1`, `rotate+2`, `random_seed1`,
`random_seed2`, deduped by ordering. `run_v12b_layer` currently calls `backend.generate_text` once per
unique generated permutation, so the proposed runner can preserve one generation per unique
permutation.

AUDIT 80 consistently states `6 * ceil(N / 8)` as a theoretical maximum, not an exact generation
count.

## 16. Ephemeral-input/persisted-output review

AUDIT 80 correctly distinguishes ephemeral inference inputs from persisted diagnostics.

Allowed in memory: question, choices, canonical labels, Base answer, Base scoring diagnostics, router
diagnostics, qid, input_index, and private ordinal. These are necessary to build permutation prompts.

Forbidden in persisted artifacts: question text, choices, option text, selected option text, prompts,
raw model responses, evidence, reasoning, expected answers, correctness, ground truth, API keys, and
arbitrary exception strings.

Phase 3A-0 persists nothing. AUDIT 80 also requires the runner not to log question/choice/raw output.
No wording incorrectly requires ephemeral text to be absent from memory, and no wording permits
ephemeral text in future artifacts.

## 17. Conservative/self-confidence review

AUDIT 80 unambiguously prohibits model self-reported confidence from determining selection, validity,
stability, hypothetical acceptance, merge, or answer replacement. It forbids the balanced policy,
requires conservative-only measurable vote/validity logic if `select_permutation_override` is reused,
and omits raw model confidence from future Phase 3A artifacts.

Source confirms this matters: `select_permutation_override(..., policy="balanced")` uses
`mean_support_confidence`, which is computed from per-record `confidence` fields.

## 18. API/data-structure review

The corrected proposed structures support the required implementation surface:

- private ordinal identity;
- qid/input_index metadata;
- attempted and valid permutation counts;
- parse and generation failure counts;
- vote counts;
- winning and runner-up labels/votes;
- vote margin;
- consensus ratio;
- unique-answer count;
- tie status;
- aggregate status;
- Base/V12B agreement;
- hypothetical answer and conservative acceptance;
- fixed `official_answer_source = "base"`;
- elapsed time if measured;
- record-level error code;
- selected qids/items/ranks;
- no ground truth.

No proposed field is impossible to compute from the pure permutation core plus an injected backend.

## 19. Mapping metadata review

`OptionPermutation` already exposes `permuted_to_original` and `original_to_permuted`. AUDIT 80
requires each `V12BPermutationResult` to include the labels-only `permuted_to_original` map
(presented label -> canonical/original label), with `original_to_permuted` optional. That is sufficient
for positional-bias analysis without re-deriving maps from seed/family.

The mapping is deterministic, JSON-finite, and free of option text. Label support is consistent with
`src/utils/labels.py`, which provides A-Z labels and rejects counts outside 0..26. The competition's
current 2..11 choice range is covered.

## 20. Error-code review

AUDIT 80's closed error-code set is directionally correct and privacy-safe:

`ok`, `generation_error`, `parse_error`, `missing_selected_label`, `label_out_of_range`,
`label_option_mismatch`, `label_text_conflict`, `option_text_no_match`,
`insufficient_valid_permutations`, `tie`, `aggregate_error`.

It correctly forbids `str(exc)`, raw generated content, prompts, question fragments, and choice
fragments. Exception class name is optional and separate.

Low caveat L1: the implementation should define a normalization table from existing raw mapping/
legacy values into this closed set. Existing source can emit `self_label_option_conflict`,
`label_out_of_range`, `label_text_conflict`, `option_text_no_match`, `local_error`, `parse_error`, and
validation strings such as `parse_status=<value>` or `no_mapped_label`. AUDIT 80 gives enough contract
to implement this safely, but the exact mapping should be explicit in Phase 3A-0.

## 21. Aggregate/stability semantics review

AUDIT 80 fixes the under-defined `stable` boolean by requiring raw measurable fields plus aggregate
status. It lists understandable statuses: `valid_unique_majority`, `valid_weak_consensus`, `tie`,
`insufficient_valid_permutations`, `all_invalid`, `generation_failure`, and `aggregate_error`.

It also correctly states that raw fields are authoritative, any `stable` formula must be explicit and
provisional, self-confidence cannot be used, and legacy-compatible values
`min_valid_permutations = 5` and `consensus_votes = 4` are calibration-dependent.

Low caveat L2: Phase 3A-0 should define a deterministic precedence order for overlapping cases, e.g.
aggregate error before generation failure, generation failure/all invalid before insufficient valid,
tie before weak consensus, then valid consensus statuses. Without this, two implementers could label a
mixed failure case differently. This is non-blocking because AUDIT 80 already requires raw fields to be
authoritative and the formula to be explicit.

## 22. Future CLI/mode-contract review

AUDIT 80's Phase 3A-1 mode contract is correctly future-only and not implemented now:

- no flags unchanged;
- current Phase 2 shadow unchanged;
- V12B shadow implies Base scoring and router selection;
- telemetry and V12B share one score per record;
- Phase 2 shadow and V12B share one router decision set;
- `--legacy-dynamic-full` and `--confidence-v12b-shadow` are mutually exclusive;
- malformed configs fail closed to Base-only official output;
- artifact write failure warns and preserves official output;
- V13 and selector are never invoked.

No CLI/config implementation is authorized during Phase 3A-0.

## 23. Risk-register/test-plan review

AUDIT 80's revised risk register covers the important hazards: direct legacy runner calls, accidental
legacy JSONL creation, file-open failure propagation, self-confidence contamination, backend duplicate
load, arbitrary exception-text leakage, missing mapping metadata, duplicate identity, ambiguous
stability, mode conflicts, and up-to-six permutation counts.

Low caveat L3: the Phase 3A-0 test plan should explicitly add several edge cases implied by the
contract but not all named in AUDIT 80 section 22:

- backend exception on one permutation;
- backend exception on all permutations;
- malformed JSON;
- valid JSON with missing required fields;
- duplicate normalized option texts;
- no selected inputs;
- stable input order;
- no mutation of input objects;
- no global backend lookup;
- no filesystem access.

These are implementation-time test-plan clarifications, not blockers to committing the corrective
plan.

## 24. Allowed-test results

Pure permutation core:

```text
pytest tests/unit/test_mcq_permutation_debiaser_2l34c.py -q
15 passed in 0.15s
```

V12B integration file (safe: legacy script/static-artifact tests, no model weights):

```text
pytest tests/integration/test_v12b_permutation_2l34b.py -q
5 passed, 2 failed in 0.37s
```

The two failures are the known missing-frozen-artifact baseline:

- `test_selector_validates_and_no_change_on_empty`
- `test_frozen_v11_md5_stable`

Both fail with `FileNotFoundError` for `output/pred_v11_independent_rerun1.csv`. They are not new
regressions and do not affect this planning review.

Phase 1/2 confidence group:

```text
pytest \
  tests/unit/test_choice_scoring_2l48b.py \
  tests/integration/test_confidence_telemetry_2l48c.py \
  tests/unit/test_confidence_shadow_router_2l48d.py \
  tests/integration/test_confidence_shadow_router_2l48e.py \
  -q
89 passed in 0.62s
```

No model weights were loaded. No real V12B/V13/selector execution occurred.

## 25. Findings table ordered by severity

No Critical, High, or Medium findings.

| ID | Severity | AUDIT 80 section | Source evidence | Impact | Blocks committing 78-80? | Blocks Phase 3A-0? | Recommended correction |
|---|---|---|---|---|---|---|---|
| L1 | Low | 18 | `mcq_permutation_debiaser.py` emits raw reasons including `self_label_option_conflict`; legacy layer uses `local_error`/`parse_error` statuses | Implementer must normalize raw outcomes to closed codes consistently | No | No | In 3A-0, define a closed normalization table from raw parse/mapping/generation outcomes to AUDIT 80 codes |
| L2 | Low | 19 | Statuses are listed but no precedence is specified for mixed cases | Two implementations could label the same mixed failure case differently | No | No | In 3A-0, define deterministic aggregate-status precedence while keeping raw fields authoritative |
| L3 | Low | 22 | Test plan covers the main risks but omits several explicit fake-backend edge cases | Test coverage could miss contract regressions | No | No | Add explicit 3A-0 unit tests for exception, malformed/missing JSON, duplicate normalized text, empty input, order, immutability, no global backend lookup, and no filesystem access |
| I1 | Informational | 14 | Backend cache key is raw path/device; exact instance injection avoids duplicate loads | Accessor remains an implementation choice | No | No | Prefer injected backend instance; add accessor only if it avoids private-member access |
| I2 | Informational | 24 | Real V12B was not run by design | No runtime/quality calibration evidence yet | No | No | Collect real-model observational evidence only after 3A-0 and 3A-1 are separately implemented/reviewed |

Finding counts: Critical 0, High 0, Medium 0, Low 3, Informational 2.

## 26. Required corrections before committing AUDIT 78-80

None. AUDIT 80 fully resolves AUDIT 79's Medium findings and is safe to commit with the non-blocking
caveats above.

## 27. Required corrections before Phase 3A-0

No blocking correction is required before Phase 3A-0. Recommended implementation-time clarifications:
define the error-code normalization table, aggregate-status precedence, and the missing fake-backend
edge tests before accepting the Phase 3A-0 implementation.

## 28. Recommended exact Phase 3A-0 implementation contract

Phase 3A-0 should implement only an isolated in-memory runner:

- create `src/local_model/confidence_v12b_runner.py`;
- create runner-specific fake-backend unit tests;
- optionally add a narrow read-only `QwenMCQPredictor.backend` accessor only if clean injection
  otherwise requires private-member access;
- accept only explicitly router-selected inputs;
- assign and use private per-record ordinals internally;
- never key associations by qid alone or assume input_index is unique;
- receive an already-created backend instance;
- never call `get_local_qwen_backend`, resolve model paths, instantiate/reload the model, or use a
  global backend lookup;
- reuse `build_option_permutations`, `map_permuted_answer_to_original`,
  `summarize_permutation_votes`, and optionally conservative-only `select_permutation_override` as a
  hypothetical diagnostic;
- run one `generate_text` call per unique permutation;
- fail closed per permutation and per selected record;
- normalize errors to closed category codes;
- include labels-only `permuted_to_original` metadata;
- keep all text ephemeral and in memory;
- write no files and log no question/choice/prompt/raw-response text;
- never import/call `run_v12b_layer`, `select_v12b_targets`, the legacy writer, V13, selector, legacy
  system, artifact writers, CLI/config loading, or official CSV logic;
- never receive or mutate official output rows;
- never change an answer.

## 29. Files allowed in Phase 3A-0

- `src/local_model/confidence_v12b_runner.py`
- `tests/unit/test_confidence_v12b_runner_*.py`
- Phase 3A-0 implementation/review audit files
- Optional, only if genuinely necessary: a narrow read-only backend accessor in
  `src/local_model/qwen_mcq_predictor.py`

## 30. Files forbidden in Phase 3A-0

- `predict.py`
- `configs/confidence_selective.yaml`
- `src/local_model/confidence_config.py`
- `src/layers/mcq_permutation_debiaser.py`
- `src/layers/v12b_dynamic_layer.py`
- `src/system/fastmcq_system.py`
- any V13 module
- any selector module
- legacy system modules
- Docker/dependency files
- artifact writers
- integration tests invoking `predict.py`
- official CSV writer/schema logic
- AUDIT 78, AUDIT 79, AUDIT 80
- any answer-changing or merge logic

## 31. Confirmation of unauthorized future work

Phase 3A-1, Phase 3B, V13, selector behavior, answer replacement, default promotion, CLI/config
changes, artifact writing, threshold finalization, and any Base/V12B merge remain unauthorized by this
review.

## 32. Confirmation of actions not performed

No source/test/config/AUDIT-78/79/80 modification occurred. No real V12B inference, V13 execution,
selector execution, answer override, final threshold declaration, organizer ground-truth use, external
API/OpenRouter call, model download, Docker modification, image rebuild, commit, or push occurred.

## 33. Current git status

After creating this audit, the expected status is:

```text
?? docs/audits/78-phase3-confidence-routed-v12b-planning.md
?? docs/audits/79-independent-review-phase3-v12b-plan.md
?? docs/audits/80-phase3-v12b-plan-corrections.md
?? docs/audits/81-independent-review-phase3-v12b-plan-corrections.md
```

No tracked source/test/config diff is expected.

## 34. Final verdict

**PHASE 3 CORRECTIVE PLAN SAFE TO COMMIT WITH NON-BLOCKING CAVEATS; READY FOR PHASE 3A-0**

AUDIT 80 fully resolves AUDIT 79's M1 and M2. The direct legacy V12B runner is banned, pure-core reuse
is correctly scoped, Phase 3A-0 and Phase 3A-1 are separated, backend injection is safe, ordinal
identity is sufficient, permutation cost is corrected, privacy boundaries are explicit, self-reported
confidence is prohibited, mapping metadata and error-code contracts are privacy-safe, and future mode
conflicts are specified for 3A-1 only.

This verdict authorizes only the future Phase 3A-0 runner-isolation task under the scope above. It does
not authorize Phase 3A-1, CLI/config changes, artifact writing, Phase 3B, answer replacement, V13,
selector use, or default promotion.

STOP - independent review complete. No implementation; nothing committed or pushed.
