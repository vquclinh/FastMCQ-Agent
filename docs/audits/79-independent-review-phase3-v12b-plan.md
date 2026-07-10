# AUDIT 79 — Independent Review of the Phase 3 Confidence-Routed V12B Plan (AUDIT 78)

Audit number 79 (no prior `79-*` existed under `docs/audits/`).

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `08b97df4967dd305880a29faffe22fa48aa5df6b` ("document phase 2 Windows shadow validation")

## 2. Initial working-tree state

`git status --short` shows only `?? docs/audits/78-phase3-confidence-routed-v12b-planning.md`;
`git diff --check` clean; no tracked modifications. AUDIT 66–77 committed. Nothing was staged/reset/
committed/pushed.

## 3. Independence / read-only statement

Read-only planning review. I verified AUDIT 78's source claims directly against the committed code,
ran only pure/fake-backend tests (no model weights loaded, no V12B model-backed inference, no V13/
selector execution), and probed permutation/backend behavior with pure Python. The only file created
is this audit. AUDIT 78 (and 66–77) were not modified.

## 4. Files and tests reviewed

Source: `src/layers/mcq_permutation_debiaser.py`, `src/layers/v12b_dynamic_layer.py`,
`src/system/fastmcq_system.py`, `src/local_model/local_qwen_backend.py`,
`src/local_model/qwen_mcq_predictor.py`, `src/local_model/choice_scoring.py`,
`src/local_model/confidence_shadow_router.py`, `src/local_model/confidence_config.py`, `predict.py`,
`configs/confidence_selective.yaml`. Tests: `tests/unit/test_mcq_permutation_debiaser_2l34c.py`,
`tests/integration/test_v12b_permutation_2l34b.py`, the Phase 1/2 confidence tests. Repo-wide greps
for V12B/permutation/backend/V13/selector/API symbols.

## 5. Evidence available / unavailable

- **Available:** all committed source and non-model tests; deterministic permutation/backend probes.
- **Unavailable:** real V12B model-backed inference and its GPU cost/latency/VRAM (no torch/model in
  this Linux env) — not run, per constraints.

## 6. Current V12B inventory verification — ACCURATE

Two modules under `src/layers/`: `mcq_permutation_debiaser.py` (pure core) and `v12b_dynamic_layer.py`
(model-backed layer), consumed only by `src/system/fastmcq_system.py` (`--legacy-dynamic-full`).
Matches AUDIT 78 §6.

## 7. Actual V12B call graph — ACCURATE

Verified: `fastmcq_system.run_fastmcq_system` → `select_v12b_targets` → `run_v12b_layer` →
`build_option_permutations` → `backend.generate_text` → `parse_json_object` →
`map_permuted_answer_to_original` → JSONL emit → `summarize_permutation_votes` →
`select_permutation_override` → `V12BLayerResult`. **No V13, selector, `dynamic_base_predictor`,
OpenRouter, or API** in the V12B reachable path (grep confirms none in either V12B module). `run_v12b_layer`
can be called without the full legacy system, but it requires `base_predictions`
(`BasePrediction`-shaped) and `V12BTarget` and performs the record-writer side effect (see §11).

## 8. Permutation behavior verification — AUDIT 78 §11 IMPRECISE (Low, F3)

`build_option_permutations(sample, n=6, seed=42)` yields **UP TO** 6 deterministic permutations
(families in order: `original, reverse, rotate+1, rotate+2, random_seed1, random_seed2`), deduped by
ordering. Measured counts: **m=1→1, m=2→2, m=3→4, m=4→6, m=5→6, m=10→6.** So AUDIT 78 §11's flat
"Generations per selected record: **6**" is inaccurate for ≤3 choices (3-choice items are common).
§8 correctly says "up to 6". Positions (not labels) are permuted; canonical mapping direction is
permuted-label → original-label; tie-break is deterministic (`max(votes, -ord(label))`). The label
utility supports every claimed count. The cost formula `6·ceil(N/8)` is a valid **upper bound** (over-
estimates), so the impact is Low.

## 9. Mapping / validation behavior — ACCURATE

`map_permuted_answer_to_original` invalidates on: label out of range, missing label, `label_matches_
option=False`, option-text mismatch, and label/text conflict (distinguishing `label_text_conflict`
vs `option_text_no_match`). `summarize_permutation_votes` counts **only valid records** (parse ok +
label/option match); parse failures and mismatches are excluded from votes. `parse_json_object`
returns a dict or None; a malformed/mis-keyed response yields `selected_label=None` → invalid → not a
vote. **No parser fallback can turn a malformed V12B response into a valid vote.** Matches AUDIT 78 §9.

## 10. Aggregation / policy behavior — AUDIT 78 §10 SLIGHTLY BROAD (Low, F4)

`select_permutation_override` **conservative** policy uses only measurable vote/validity signals
(`valid_records≥5 AND top_non_current_votes≥4 AND current_votes≤1`). The **balanced** policy adds a
`mean_support_confidence ≥ 0.6` gate — and `mean_support_confidence` is derived from the model's own
`parsed.get("confidence")` (self-reported). AUDIT 78 §10 lists `select_permutation_override` as
"reusable as-is" without the caveat that Phase 3A must (a) use only conservative vote signals, (b)
avoid the balanced/self-confidence path, and (c) treat any `accept`/`proposed_answer` as a
**hypothetical** diagnostic (never applied). AUDIT 78 §14 (`hypothetical_answer`) and §18 (excludes
self-confidence) already reflect the right intent; §10 needs the explicit caveat.

## 11. Legacy artifact / privacy review — KEY FINDING (Medium, F1)

The legacy V12B record persists exactly: `original_qid`, `permutation_id`, `mapped_original_label`,
`parse_status`, `label_option_match`, `valid`, `failure_reason`, `confidence`. **It does NOT persist
question, choices, `selected_option_text`, raw response, prompt, or `evidence`.** `failure_reason` is
an enumerated mapping code or `type(exc).__name__` (exception **class name**, not `str(exc)`), and
`confidence` is numeric. So the legacy writer's CONTENT is text-safe.

**However**, `run_v12b_layer` **unconditionally** `work.mkdir(parents=True)` and `open(rec_path, "w")`
**before** the loop (`v12b_dynamic_layer.py:137,144`): calling it always creates a separate legacy
`v12b_dynamic_records.jsonl` and can raise `OSError` on open (which would propagate to the caller).
**Answer to AUDIT 78 §7's explicit question:** the legacy records file would NOT contain forbidden
text fields, but directly reusing `run_v12b_layer` (a) creates an extra legacy artifact and (b) can
fail-open into the caller. Therefore `run_v12b_layer` is **unsuitable for direct reuse** in an
observational Phase 3A; AUDIT 78 §10's option "(or calls a lightly-parameterized `run_v12b_layer` via
an adapter)" is too broad and contradicts §14 (which reuses the pure core). This materially affects
the implementation boundary → **Medium**.

## 12. Internal-input vs persisted-artifact boundary — IMPRECISE (Low, F2)

AUDIT 78 §14's `V12BRunInput` carries `question`/`choices` (necessary to build permutation prompts),
yet the same section says "Inputs/outputs are numeric/categorical only; no question text is carried
through." This conflates the **ephemeral inference input** (must carry question/choices) with the
**persisted artifact** (must not). §16 already lists a text-free persisted schema, so the risk of
actually persisting text is low, but the wording should explicitly separate the two boundaries.

## 13. Backend-reuse feasibility — AVAILABLE WITH A CAVEAT (Low, F5)

`QwenMCQPredictor.__init__` sets `self._backend = get_local_qwen_backend(model_path, device=..., ...)`
and exposes it only privately (methods `predict_one`/`score_choices`, no public accessor). Probe:
`get_local_qwen_backend('/models/x','auto')` twice → **same instance** (cache keyed by
`(resolved_path, device)`); trailing-slash path → **different instance** (cache key not normalized,
the AUDIT 61/67 L1 caveat). **Conclusion: backend reuse is directly available** if Phase 3A passes the
**exact** `args.model_path`/`args.device` `predict.py` used (same cached instance) or accesses
`predictor._backend`. Cleaner: add a **narrow public accessor** (e.g. a `backend` property) in 3A-0.
AUDIT 78 §11/§14 says "inject the already-loaded predictor backend" without noting the missing
accessor or the path-normalization caveat.

## 14. Component-by-component reuse verdict

| Component | Verdict | Evidence |
|---|---|---|
| `mcq_permutation_debiaser.py` (build/map/summarize) | **reusable as-is** | pure, deterministic; 15/15 unit tests pass |
| `select_permutation_override` | **reusable with caveat** | conservative-only; balanced uses self-confidence; output must be hypothetical in 3A (F4) |
| `run_v12b_layer` | **UNSUITABLE for direct reuse** | unconditional legacy-file side effect + can raise on open (F1) |
| `select_v12b_targets` (legacy router) | **do not use** | Phase 2 router replaces it (AUDIT 78 agrees) |
| legacy record writer | **do not reuse** | new runner writes its own text-free artifact |

**Safest Phase 3A-0 boundary:** a new `confidence_v12b_runner.py` reusing **only** the pure core
(`build_option_permutations`, `map_permuted_answer_to_original`, `summarize_permutation_votes`, and
optionally `select_permutation_override` as a hypothetical) + the injected shared backend; **never**
call `run_v12b_layer`, `select_v12b_targets`, or the legacy writer; never touch official rows; use a
per-record ordinal identity (Phase 2 pattern); fail closed per permutation and per record.

## 15. Resource / cost verification — MOSTLY ACCURATE (see F3)

One `backend.generate_text` per permutation; up to 6 unique permutations (fewer for ≤3 choices); no
batching; sequential; `max_new_tokens=384`; backend reused via injection. Theoretical **maximum**
`6·ceil(N/8)`: N=21→18, N=100→78, N=1,000→750, N=10,000→7,500 (recomputed, correct as an upper bound).
Actual cost is lower when permutations dedup (≤3 choices) or on early failure; resume can reuse prior
records. AUDIT 78 correctly labels these calculations (not benchmarks) and invents no latency/VRAM.

## 16. Phase 3A architecture review — SOUND

The proposed runner correctly: takes router-selected records only; keeps Base; never calls V13/
selector; fails closed. Confirmed additions needed: receive question/choices **only ephemerally** for
prompt construction (F2); receive router decisions by **per-record identity, not qid alone** (F1/
Phase-2 pattern); receive the already-loaded backend (F5); reuse the pure core, not `run_v12b_layer`
(F1). A **private ordinal** alongside qid/input_index is needed (mirroring the Phase 2 duplicate-qid
fix).

## 17. Proposed API review — ADEQUATE with additions

`V12BRunInput`/`V12BPermutationResult`/`V12BAggregateResult`/`V12BRunSummary`/`run_confidence_routed_v12b`
are reasonable. Missing/should-add fields: a private **ordinal** for unique per-record identity;
explicit **attempted vs valid permutation counts**; **parse-failure** and **generation-failure**
counts; an explicit **runner-up** label/votes (derivable but should be stored); a defined
**base_v12b_agreement**; a defined **stable** rule (see F7); enumerated **error codes** (F6); and a
correctly-measured **elapsed_sec**. No ground-truth fields (correctly absent).

## 18. Artifact-schema review — ADD MAPPING METADATA (Low, F5-schema)

**High-priority answer:** a permutation result with only `{permutation_id, mapped_label, valid, ...}`
CAN reconstruct the presented-position→canonical map only by **re-deriving** it from `permutation_id`
+ choice count + the fixed seed (deterministic). For direct, self-contained positional-bias analysis,
add a privacy-safe **`permuted_to_original`** (presented-label → canonical-label) map — labels only,
no option text. The schema correctly excludes question/choices/selected-text/prompt/raw-response/
evidence/expected/ground-truth/API-key. Recommend explicitly restricting `failure_reason`/`error_code`
to **enumerated codes / exception class names only** (never `str(exc)`) to prevent accidental leakage
(F6) — the legacy writer already does this, but the plan should mandate it for the new runner.

## 19. Stable/unstable semantics review — UNDER-DEFINED (Low, F7)

AUDIT 78 proposes a `stable` boolean without a definition. Recommend: record raw measurable signals
(valid count, winning/runner-up votes, consensus ratio, unique-answer count, tie); derive `stable`
via **explicitly provisional** config, never presented as calibrated correctness; and distinguish
valid-aggregate / unique-majority / strong-consensus / tie / insufficient-valid / generation-failure.
`min_valid_permutations=5` and `consensus_threshold=4` are **legacy-compatible provisional defaults**
(they mirror the conservative rule `n≥5, best≥4`), i.e. **calibration-dependent**, not structural —
AUDIT 78 §15 labels them "provisional" (correct).

## 20. CLI / config / mode-combination review — ADEQUATE; add explicit conflict rules

Proposed `--confidence-v12b-shadow` + paths are reasonable. Expected behavior confirmed compatible:
no flags → unchanged; Phase 2 shadow only → unchanged; V12B shadow only → Base + scoring + router +
V12B on selected, Base kept; telemetry + V12B shadow → score once, both artifacts; Phase 2 shadow +
V12B shadow → router shared, V12B on selected; invalid scoring/router/V12B config → **fail closed**
(no V12B, official output intact). **Recommendation:** `--legacy-dynamic-full` + `--confidence-v12b-
shadow` should **fail explicitly** (mutually exclusive execution paths) rather than silently combine —
AUDIT 78 does not state this; add it.

## 21. Phase 3A-0 vs 3A-1 scope review — CONTRADICTION (Medium, M2)

AUDIT 78 §27 and §33 correctly scope **3A-0 = new runner + runner unit tests only, no legacy/predict/
config change**. But §28 titles its file list "FIRST future implementation task (**3A-0/3A-1**)" and
includes `predict.py`, `configs/...`, `confidence_config.py`, and integration tests. This **combines
runner isolation with CLI/config wiring** — a task-boundary inconsistency that risks scope creep in the
"3A-0" task. Per the review's own blocking criteria, combining 3A-0 runner isolation with CLI/config
wiring is a blocking planning issue. Correction: split §28 into **3A-0 files** (new
`confidence_v12b_runner.py` + its unit tests **only**) and **3A-1 files** (`predict.py` +
`confidence_config.py` + YAML + integration tests + artifact writer/wiring).

## 22. Calibration-data / metrics review — SOUND

AUDIT 78 §20–§21 respect: no organizer ground truth; no per-question leaderboard inference; permitted
synthetic/manual/public/weak(marked)/Vietnamese-stratified data; label-position balance; Base-margin
bins; staged sizes clearly labeled as planning estimates. Metrics correctly separate diagnostic /
calibration / promotion. No leakage or circular threshold selection detected (thresholds are to be
learned on permitted labels, distinct from the evaluation).

## 23. Promotion-gate review — SOUND

The three gates (to-3A, 3A→3B, default promotion) are appropriately escalating; AUDIT 78 correctly
states current evidence does **not** satisfy the 3B or default-promotion gates and that Phase 2
evidence is insufficient. No gate authorizes answer replacement or default promotion.

## 24. Risk-register corrections / additions

AUDIT 78 §23 is largely accurate (V12B uses `parse_json_object` not the hardened parser — correct
Med risk; no V13/selector/API — correct; deterministic seed — correct). **Add:** (a) `run_v12b_layer`
unconditional legacy-file side effect + open-failure propagation (F1, Med); (b) new-runner
`error_code`/`failure_reason` must be enumerated / class-name-only to avoid `str(exc)` text leakage
(F6, Low); (c) model self-reported `confidence` must not contaminate the `stable` signal (F4/F7, Low);
(d) backend cache-key non-normalization could cause a second load if the runner passes a differently-
spelled path (F5, Low); (e) `--legacy-dynamic-full` + V12B-shadow mode conflict should fail explicitly
(F-mode, Low).

## 25. Existing-test results

- `tests/unit/test_mcq_permutation_debiaser_2l34c.py` → **15 passed** (pure core verified).
- `tests/integration/test_v12b_permutation_2l34b.py` → **5 passed, 2 failed** — the 2 failures
  (`test_selector_validates_and_no_change_on_empty`, `test_frozen_v11_md5_stable`) are the known
  missing-frozen-artifact baseline class (`FileNotFoundError`), not new and unrelated to the pure V12B
  logic.
- `tests/unit/test_confidence_shadow_router_2l48d.py` + `..._2l48e.py` + `test_choice_scoring_2l48b.py`
  → **82 passed** (Phase 1/2 reuse contracts hold).
- No model weights were loaded; no V12B model-backed inference ran.

## 26. Findings (ordered by severity)

No **Critical** or **High** findings (the plan cannot override official answers or invoke V13/selector;
the legacy writer does not persist private text).

| ID | Sev | AUDIT 78 § | Source | Evidence | Impact | Blocks committing 78? | Blocks 3A-0? | Correction |
|---|---|---|---|---|---|---|---|---|
| M1 | Med | §10, §14 | `v12b_dynamic_layer.py:137,144` | `run_v12b_layer` unconditionally mkdir+open a legacy JSONL (side effect; can raise) | ambiguous reuse boundary could add a legacy artifact / fail-open | No | **Yes** | Tighten §10: `run_v12b_layer` is unsuitable for direct reuse; the new runner reuses only the pure core |
| M2 | Med | §28 vs §27/§33 | AUDIT 78 | §28 combines "3A-0/3A-1" and lists predict.py/config; §27/§33 scope 3A-0 as runner+unit-tests only | scope creep into CLI/config during "3A-0" | No | **Yes** | Split §28 into distinct 3A-0 (runner+unit tests) and 3A-1 (predict/config/integration) file lists |
| F3/L1 | Low | §11 | `build_option_permutations` | m=1→1, m=2→2, m=3→4, m≥4→6 | "6 per record" over-states for ≤3 choices (cost formula is a valid upper bound) | No | No | §11: "up to 6 (m=3→4, m=2→2)" |
| F2/L2 | Low | §14 | AUDIT 78 | `V12BRunInput` carries question/choices, yet §14 says "numeric/categorical only" | privacy-boundary wording | No | No | Separate ephemeral input (carries text) from persisted artifact (text-free) |
| F4/L3 | Low | §10 | `select_permutation_override` | balanced uses model self-confidence | must use conservative-only, hypothetical output in 3A | No | No | §10 caveat: conservative-only; hypothetical; no balanced/self-confidence |
| F5/L4 | Low | §11, §14 | `qwen_mcq_predictor.py:25` | no public backend accessor; cache key not path-normalized | reuse needs accessor or exact-arg match | No | No | Add a narrow `backend` accessor (3A-0) or reuse via identical args; note normalization |
| F6/L5 | Low | §16 | new runner | `error_code`/`failure_reason` could carry `str(exc)` | accidental text leak | No | No | Mandate enumerated codes / exception class names only |
| F7/L6 | Low | §15 | AUDIT 78 | `stable` under-defined | ambiguous diagnostic | No | No | Define `stable` from raw signals via provisional config; label provisional |
| F-schema/L7 | Low | §16 | new artifact | no explicit position→canonical map | positional-bias analysis needs re-derivation | No | No | Add privacy-safe `permuted_to_original` label map |
| F-mode/L8 | Low | §15-CLI | plan | legacy-full + V12B-shadow not defined | silent mode combination | No | No | Make them mutually exclusive / fail explicitly |
| I1 | Info | — | tests | 2 V12B integration failures are the known frozen-artifact baseline | none | No | No | — |

## 27. Required corrections before committing AUDIT 78

**None strictly required to keep AUDIT 78 as a planning record.** All findings are documentation-level;
AUDIT 78 may be kept/committed as an evidence artifact. (The Medium corrections are required before the
implementation, not before storing the record.)

## 28. Required corrections before Phase 3A-0

Apply before starting 3A-0 implementation: **M1** (tighten §10 so the runner reuses only the pure core
and never calls `run_v12b_layer`) and **M2** (split §28 so 3A-0 is strictly the new runner + its unit
tests, with predict/config/integration deferred to 3A-1). Recommended alongside: F4 (conservative-only,
hypothetical), F5 (backend accessor), F6 (enumerated error codes), F-mode (explicit legacy-full/V12B
conflict).

## 29. Recommended exact Phase 3A-0 scope

Create `src/local_model/confidence_v12b_runner.py` that: reuses `build_option_permutations`,
`map_permuted_answer_to_original`, `summarize_permutation_votes` (and `select_permutation_override`
conservative-only, as a **hypothetical**) from `mcq_permutation_debiaser`; accepts an injected loaded
backend; runs up-to-6 permutations per record via `generate_text`; aggregates in memory; returns
`V12B*Result` diagnostics with a private per-record ordinal; persists **nothing** itself in 3A-0 (pure
+ in-memory); never calls `run_v12b_layer`/`select_v12b_targets`/the legacy writer/V13/selector; fails
closed per permutation and per record. Plus **unit tests only** (fake backend). **No** `predict.py`,
config, YAML, or integration-test changes in 3A-0.

## 30. Recommended exact Phase 3A-1 scope

`predict.py` opt-in flags (`--confidence-v12b-shadow` + paths), `confidence_config.py`
`load_v12b_config` + YAML `confidence_v12b` block, the privacy-safe artifact writer (fail-closed,
`allow_nan=False`, enumerated error codes, `permuted_to_original` map), the shared single-score/single-
select reuse, and integration tests (official CSV byte-invariance, only-selected-run, no V13/selector/
legacy, mode conflicts, malformed config, artifact-write failure).

## 31. Remaining open decisions

Final routing threshold; V12B acceptance thresholds (`min_valid_permutations`/`consensus_threshold`)
via calibration; whether to store model `confidence` at all (recommend: store raw but never use it for
`stable`); backend-accessor vs exact-arg reuse; permitted calibration-set composition/size; and the
`stable` definition.

## 32. Confirmation

No source/test/config/AUDIT-78 (or earlier audit) modification; no real V12B/V13/selector execution
(only pure and fake-backend tests ran, plus deterministic Python probes); no answer override; no final
threshold; no organizer ground truth; no external API/OpenRouter call; no model download; no Git
commit or push. Only this file (AUDIT 79) was created.

## 33. Current `git status --short`

```
?? docs/audits/78-phase3-confidence-routed-v12b-planning.md
?? docs/audits/79-independent-review-phase3-v12b-plan.md
```

## 34. Final verdict

**PHASE 3 PLAN REQUIRES CORRECTIONS BEFORE PHASE 3A-0.**

The plan's direction is sound and safe (Option B; observational Phase 3A; Base unchanged; V13 off;
V12B is cleanly isolated — verified no V13/selector/API in its path; the pure permutation core is
reusable and passes 15/15 tests; backend reuse is available; the legacy writer is text-safe). But two
**Medium** documentation corrections must be applied to AUDIT 78 before Phase 3A-0 implementation
begins: **M1** — tighten §10 so `run_v12b_layer` is treated as unsuitable for direct reuse (its
unconditional legacy-file side effect); the runner must reuse only the pure core; and **M2** — split
§28's combined "3A-0/3A-1" file list so Phase 3A-0 is strictly the new runner + its unit tests (no
predict/config/integration changes). Plus the Low refinements (up-to-6 permutations, ephemeral-input
vs artifact boundary, conservative-only/hypothetical override, backend accessor, enumerated error
codes, `stable` definition, position→canonical map, explicit mode conflict). AUDIT 78 itself may be
kept as the planning record; this verdict concerns only readiness to start Phase 3A-0. It does **not**
authorize Phase 3A-1, Phase 3B, answer replacement, V13, or default promotion.

STOP — independent planning review complete. AUDIT 78 not modified; nothing committed or pushed;
Phase 3 not implemented.
