# AUDIT 80 — Phase 3 Confidence-Routed V12B Plan: Corrective Addendum (governing contract)

Audit number 80 (no prior `80-*` existed under `docs/audits/`).

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `08b97df4967dd305880a29faffe22fa48aa5df6b` ("document phase 2 Windows shadow validation")

## 2. Initial working-tree state

`git status --short`: `?? docs/audits/78-…md`, `?? docs/audits/79-…md`. `git diff --check` clean; no
tracked modifications. Nothing staged/reset/committed/pushed. Source facts cited by AUDIT 79 were
re-verified before writing this addendum (see §6/§14).

## 3. Documentation-only corrective scope

This addendum is **documentation only**. It creates no code/test/config and implements no Phase 3.
It resolves AUDIT 79's two Medium findings (M1, M2) and folds in the Low clarifications, producing a
binding contract for the future Phase 3A-0 and Phase 3A-1 tasks. It does **not** authorize Phase 3B,
answer replacement, V13, selector use, or default promotion.

## 4. Relationship among AUDIT 78, 79, and 80

- **AUDIT 78** — original Phase 3 planning record (preserved unchanged).
- **AUDIT 79** — independent review of AUDIT 78 (preserved unchanged; verdict: "REQUIRES CORRECTIONS
  BEFORE PHASE 3A-0").
- **AUDIT 80** (this) — corrective addendum that supersedes the inaccurate/ambiguous portions of
  AUDIT 78 identified by AUDIT 79 and becomes the **governing implementation contract** for Phase
  3A-0/3A-1.

## 5. Governing / superseding rule

**Where AUDIT 78 conflicts with this addendum, this addendum governs.** AUDIT 78 and AUDIT 79 remain
unmodified as historical records. Specifically superseded: AUDIT 78 §10 (V12B reuse), §11 ("6
generations"), §14 ("numeric/categorical only" + `run_v12b_layer` adapter option), §28 (combined
3A-0/3A-1 file list).

## 6. M1 correction — direct `run_v12b_layer` prohibition

Verified source facts (`src/layers/v12b_dynamic_layer.py`):
- `run_v12b_layer` unconditionally creates its work directory (`work.mkdir(parents=True, exist_ok=True)`,
  line 137).
- It unconditionally opens/writes `v12b_dynamic_records.jsonl` (`open(rec_path, "w"/"a")`, line 144)
  **before** observational processing.
- That `open` can raise `OSError` (e.g. unwritable `work_dir`) and propagate to the caller.
- It requires legacy `BasePrediction`-shaped `base_predictions` and `V12BTarget`-shaped `targets`.
- Its record-writer side effect is undesirable for an isolated, in-memory Phase 3A-0 runner.

**Binding conclusion (supersedes AUDIT 78 §10 and any suggestion that a thin adapter may call
`run_v12b_layer`):**
- `run_v12b_layer` is **unsuitable for direct Phase 3A reuse**; the new runner **must not** call it,
  even through a thin adapter.
- `select_v12b_targets` (legacy feature router) **must not** be reused (Phase 2 confidence router
  selects records).
- The legacy record writer **must not** be reused.
- The new runner **must** directly reuse the pure core + the injected shared backend and **must
  persist nothing** in Phase 3A-0.

## 7. Component-by-component reuse contract

| Component | Contract |
|---|---|
| `src/layers/mcq_permutation_debiaser.py` (module) | reusable **as-is** (pure, deterministic; 15/15 unit tests pass) |
| `build_option_permutations` | **reuse** |
| `map_permuted_answer_to_original` | **reuse** |
| `summarize_permutation_votes` | **reuse** |
| `select_permutation_override` | reuse **only** under the **conservative** policy, **as a hypothetical diagnostic**, **never** to change the official answer in Phase 3A |
| `run_v12b_layer` | **do not reuse** (unconditional legacy-file side effect + can raise on open) |
| `select_v12b_targets` | **do not reuse** |
| legacy record writer | **do not reuse** |

## 8. M2 correction — strict Phase 3A-0 / 3A-1 split

Phase 3A-0 and Phase 3A-1 are **separate tasks with separate review gates** (supersedes AUDIT 78 §28's
combined "3A-0/3A-1" file list). Their file scopes are **non-overlapping**.

## 9. Correct Phase 3A-0 files and forbidden files

**Phase 3A-0 — isolated in-memory runner only.** Allowed:
- New: `src/local_model/confidence_v12b_runner.py`.
- New runner-specific unit-test file(s), e.g. `tests/unit/test_confidence_v12b_runner_*.py`.
- Audit files from that future implementation/review.
- *Potentially* one small source change: a **narrow read-only** `backend` accessor in
  `src/local_model/qwen_mcq_predictor.py`, **only if** clean backend injection cannot otherwise be
  achieved without private-member access (§14).

**Forbidden in Phase 3A-0:** `predict.py`; `configs/confidence_selective.yaml`;
`src/local_model/confidence_config.py`; CLI flags; artifact writers; any integration test that executes
`predict.py`; official CSV code; the legacy V12B modules; the legacy system; V13; selector; Docker/
dependencies; any answer-changing logic.

**Phase 3A-0 runner requirements:** in-memory only; fake-backend unit tests only; **no file writes**;
no config loading; no CLI; no official-row reference; no answer mutation; no V13/selector/legacy
imports; private ordinal identity per record; accepts only explicitly router-selected inputs; accepts
an injected already-loaded backend; fails closed per permutation and per selected record.

## 10. Correct Phase 3A-1 files and responsibilities

**Phase 3A-1 — observational integration and artifacts** (only after 3A-0 implementation **and**
independent review pass). Expected files: `predict.py`; `configs/confidence_selective.yaml`;
`src/local_model/confidence_config.py`; Phase 3A observational integration tests; privacy-safe
artifact-writing helpers if needed; Phase 3A-1 audit files. Responsibilities: explicit opt-in CLI;
config loading/validation; Phase 2 router reuse; V12B only for selected records; observational JSONL/
summary; official Base answer unchanged; fail-closed artifact writing; mode-conflict validation;
official CSV byte invariance.

## 11. Up-to-six permutation correction (supersedes AUDIT 78 §11)

- **Up to 6** unique permutations per selected record (not exactly 6).
- Verified unique counts: 1 choice → **1**; 2 choices → **2**; 3 choices → **4**; ≥4 choices → up to
  **6** (families: `original, reverse, rotate+1, rotate+2, random_seed1, random_seed2`, deduped).
- **One** model generation per generated unique permutation.
- `6·ceil(N/8)` is a **theoretical maximum**, not an exact count. Maxima (not benchmarks): N=21 → ≤18;
  N=100 → ≤78; N=1,000 → ≤750; N=10,000 → ≤7,500.

## 12. Ephemeral-input / persisted-artifact boundary (supersedes AUDIT 78 §14 wording)

The private ephemeral `V12BRunInput` **may** contain: question, choices, canonical labels, Base answer,
Base scoring diagnostics, router diagnostics, private ordinal, qid/input_index — necessary to construct
permutation prompts. It **must**: stay in memory; never be emitted into observational artifacts; never
appear in error messages/exception strings persisted to disk; never be logged by the runner.

**Persisted artifacts must exclude:** question text, choices, option text, selected option text,
prompts, raw model responses, evidence, reasoning, expected answers, correctness, ground truth, API
keys. AUDIT 78 §14's phrase "inputs/outputs are numeric/categorical only" is **superseded**:
**ephemeral inputs contain text; persisted outputs remain text-free.**

## 13. Conservative-policy / self-reported-confidence rule

Binding Phase 3A rules: the **balanced** policy must not be used. Model self-reported `confidence`
must not determine candidate selection, vote validity, stable/unstable classification, or hypothetical
acceptance; `mean_support_confidence` must not be a primary or gating signal. If `select_permutation_
override` is reused, it uses only the **conservative** measurable vote/validity logic; `accept` and
`proposed_answer` are **hypothetical diagnostics only**; the official answer remains Base regardless.
**Decision:** raw model `confidence` is **omitted from the persisted Phase 3A artifact** (no specific
diagnostic justification exists) and is **never** used for routing, stability, or merge.

## 14. Backend-reuse / accessor contract

Verified: `QwenMCQPredictor` stores the backend in **private** `self._backend` (only `predict_one`/
`score_choices` are public; no `backend` accessor); `get_local_qwen_backend` reuses the cache only when
the `(resolved_model_path, device)` key matches, so **differently spelled paths can yield distinct
cached instances** (a second load). Binding design: the runner **accepts a backend instance
explicitly**; Phase 3A-0 **may** add a **narrow read-only** `backend` property to `QwenMCQPredictor`
if needed (no mutating controls); the runner **never** instantiates/reloads the model; unit tests
inject a fake backend; future integration tests verify a **single** model/backend load. The accessor
is **part of Phase 3A-0 only if** a cleaner existing injection path is not found (otherwise optional).

## 15. Per-record ordinal identity contract

Mirror the corrected Phase 2 pattern (AUDIT 74): a **private enumeration ordinal** is the authoritative
internal identity; **qid must not** be an internal association key; caller `input_index` must **not**
be assumed unique; duplicate qids and duplicate input indexes must not overwrite records; output
decisions remain in input order; risk/selection/permutation ranks are explicit metadata; summaries
count **records**, not unique qids. Future unit tests must cover duplicate qid, duplicate input_index,
both duplicated, and repeated-run determinism.

## 16. Corrected API / data structures

**`V12BRunInput`** (ephemeral, in-memory only): internal ordinal (assigned by the runner), qid,
input_index, ephemeral question, ephemeral choices, canonical labels, Base answer, router selected
rank, router candidate reasons, Base top1/top2, Base raw-logit margin, Base normalized entropy.

**`V12BPermutationResult`** (persistable, text-free): permutation ordinal, permutation identifier/
family, privacy-safe `permuted_to_original` label map, mapped canonical label, parse status, validity,
label-option-match status, enumerated failure/error code. **No** option text, prompt, raw response,
evidence/reasoning, or arbitrary exception string.

**`V12BAggregateResult`** (persistable): private per-record identity (internal), qid/input_index,
attempted permutation count, valid permutation count, parse-failure count, generation-failure count,
vote counts, winning label/votes, runner-up label/votes, vote margin, consensus ratio, unique-answer
count, tie status, aggregate status, Base/V12B agreement, hypothetical answer, hypothetical
conservative acceptance, `official_answer_source = "base"` (fixed), elapsed time only if correctly
measured, enumerated record-level error code.

**`V12BRunSummary`** (persistable): total selected records; attempted/succeeded/failed records; total
permutation attempts; total valid permutations; parse/generation failure totals; aggregate-status
counts; Base/V12B disagreement count; vote/consensus distributions; selected qids/items with ranks;
explicit observational-only note. **No** ground truth or expected answers.

## 17. Position-to-canonical mapping metadata contract

Each `V12BPermutationResult` **must** include `permuted_to_original` (presented label → canonical/
original label); `original_to_permuted` optional. Requirements: **labels only** (no option text);
finite JSON; deterministic ordering; sufficient to analyze positional sensitivity **without**
re-deriving mappings from the permutation seed.

## 18. Enumerated error-code requirements

Persisted artifacts store **category codes only**, from a closed/documented set: `ok`,
`generation_error`, `parse_error`, `missing_selected_label`, `label_out_of_range`,
`label_option_mismatch`, `label_text_conflict`, `option_text_no_match`,
`insufficient_valid_permutations`, `tie`, `aggregate_error`. An exception **class name** may be stored
in a separate field only if needed. **Never** persist `str(exc)`, raw generated content, or prompt/
question/choice fragments.

## 19. Aggregate / stability semantics

Replace the under-defined `stable` boolean with an explicit **aggregate status** plus provisional
derivation. Recommended statuses: `valid_unique_majority`, `valid_weak_consensus`, `tie`,
`insufficient_valid_permutations`, `all_invalid`, `generation_failure`, `aggregate_error`. Raw
measurable fields remain authoritative. A convenience `stable` boolean may exist **only if** its exact
formula is defined, it is explicitly **provisional**, it uses only measurable vote/validity fields,
it **never** uses model self-reported confidence, and it is **never** described as calibrated
correctness. Legacy-compatible provisional values `min_valid_permutations = 5` and `consensus_votes =
4` remain **calibration-dependent** and **must not** be finalized in Phase 3A.

## 20. Phase 3A-1 CLI mode-combination contract (future behavior; not implemented now)

- no flags → existing behavior unchanged;
- `--confidence-shadow-router` → current Phase 2 behavior unchanged;
- `--confidence-v12b-shadow` alone → implies/performs Base scoring + router selection + observational
  V12B (Base kept);
- telemetry + V12B shadow → reuse **one score per record**;
- Phase 2 shadow + V12B shadow → reuse the same router decisions; optionally emit both artifact
  families;
- `--legacy-dynamic-full` + `--confidence-v12b-shadow` → **explicit CLI error; mutually exclusive**;
- malformed scoring/router/V12B config → **fail closed to Base-only** official output;
- V12B artifact-write failure → **warn, preserve** official output;
- V13 and selector → **never** invoked.

## 21. Revised risk register

| Risk | Severity | Future mitigation | Test required |
|---|---|---|---|
| Direct legacy `run_v12b_layer` side effects | Med | new runner never calls it; reuse pure core only (§6/§7) | unit: runner does not import/call `run_v12b_layer` |
| Accidental legacy JSONL creation | Med | runner writes nothing in 3A-0; 3A-1 writer is separate/opt-in | unit: no file writes in 3A-0; integration: only the 3A-1 artifact is created |
| File-open failure propagation | Low | 3A-1 writer try/except → warn, official output intact | integration: artifact-write-failure keeps official CSV |
| Self-reported-confidence contamination | Low | omit model confidence from artifact; never used for stable/select/merge (§13) | unit: stability ignores confidence |
| Backend duplicate load via cache-key mismatch | Low | inject one backend; accessor or exact-arg reuse (§14) | integration: single model/backend load |
| Arbitrary exception-text leakage | Low | enumerated codes / class name only; never `str(exc)` (§18) | unit: error fields are codes; no text |
| Missing positional mapping metadata | Low | add `permuted_to_original` (labels only) (§17) | unit: mapping present, labels-only |
| Duplicate record identity | Low | private ordinal; count records not qids (§15) | unit: dup qid / dup index / both |
| Ambiguous stability definition | Low | explicit aggregate status + provisional `stable` (§19) | unit: status per case |
| Mode conflicts | Low | explicit CLI error for legacy-full + V12B-shadow (§20) | integration (3A-1): conflict errors |
| Up-to-six (not exactly six) permutations | Low | document up-to-6; cost as upper bound (§11) | unit: counts for m=1..10 |

## 22. Corrected unit-test requirements (future Phase 3A-0; do not add now)

Only router-selected records run V12B; non-selected never run; **up to 6** permutations per record
(counts for m=1,2,3,4,5,10); canonical mapping for every permutation family; `permuted_to_original`
present (labels only); invalid labels → invalid → not a vote; ties → hypothetical keep-Base;
partial-valid outputs; deterministic aggregation; aggregate-status per case; **no** V13/selector/legacy
import or call; **no** `run_v12b_layer` call; **no** file writes; finite in-memory results; enumerated
error codes (no `str(exc)`); confidence not used for stability; duplicate qid / duplicate input_index /
both duplicated; repeated-run determinism; fail-closed per permutation and per record; fake backend
only.

## 23. Corrected future integration-test requirements (Phase 3A-1; do not add now)

No flag unchanged; Phase-2 shadow-only unchanged; V12B observational mode keeps official CSV
byte-identical; only the selected subset incurs V12B calls; Base generation/scoring not duplicated
(one score per record); single model/backend load; V12B failure keeps Base; artifact-write failure
keeps Base (warn); malformed config fails closed to Base-only; `--legacy-dynamic-full` +
`--confidence-v12b-shadow` errors explicitly; no V13/selector/API/legacy call; artifact privacy (no
text); finite JSON; Windows path compatibility.

## 24. Phase 3A-0 readiness gate

Phase 3A-0 may begin **only after**: this corrective addendum is independently reviewed; the
direct-legacy-runner prohibition is accepted; the 3A-0/3A-1 scope separation is accepted; the backend
injection strategy is defined; the ephemeral/persisted privacy boundary is accepted; the error-code and
mapping-metadata contracts are accepted; and no answer-changing behavior is included.

## 25. Files that must remain unchanged

`src/layers/mcq_permutation_debiaser.py` (reused as-is), `src/layers/v12b_dynamic_layer.py`,
`src/system/fastmcq_system.py`, the V13 modules, the selector, `dynamic_base_predictor`,
`build_mcq_prompt`, `parse_mcq_label`, `score_mcq_choices`, the Phase-2 shadow router, the official CSV
writer/schema, the Dockerfile, dependencies, model settings — and, in **Phase 3A-0 specifically**,
also `predict.py`, `configs/confidence_selective.yaml`, and `src/local_model/confidence_config.py`
(these change only in Phase 3A-1). AUDIT 78 and AUDIT 79 remain unchanged.

## 26. Remaining calibration-dependent decisions

Final routing threshold (provisional 10.0); V12B acceptance thresholds (`min_valid_permutations=5`,
`consensus_votes=4`) via permitted labeled calibration; the exact `stable` formula; whether to add the
narrow backend accessor vs exact-arg reuse; permitted calibration-set composition/size. None finalized
in Phase 3A.

## 27. Explicit confirmation

- No source/test/config change (only this audit created).
- No real V12B/V13/selector execution.
- No answer override; no final threshold declared.
- No organizer ground truth used.
- No external API/OpenRouter call; no model download.
- No Git commit or push.

## 28. Current `git status --short`

```
?? docs/audits/78-phase3-confidence-routed-v12b-planning.md
?? docs/audits/79-independent-review-phase3-v12b-plan.md
?? docs/audits/80-phase3-v12b-plan-corrections.md
```

## 29. Recommended next action

Independent review of this corrective addendum (AUDIT 80). If accepted, begin **Phase 3A-0 only** — the
isolated in-memory `confidence_v12b_runner.py` + fake-backend unit tests, reusing the pure core and an
injected backend, persisting nothing — as a standalone task with its own review gate, before any
Phase 3A-1 CLI/config wiring.

## 30. Final verdict

**PHASE 3 PLAN CORRECTIONS COMPLETE — READY FOR INDEPENDENT REVIEW**

M1 (direct `run_v12b_layer` prohibition) and M2 (strict 3A-0/3A-1 split) are resolved; the up-to-six
permutation count, ephemeral-vs-persisted privacy boundary, conservative-only/self-confidence rule,
backend-reuse/accessor contract, per-record ordinal identity, corrected API/data structures,
position→canonical mapping metadata, enumerated error codes, aggregate/stability semantics, and CLI
mode-conflict contract are all specified as binding. Phase 3A-0 is **not** declared ready until this
correction itself receives independent review. This addendum does not authorize Phase 3A-1, Phase 3B,
answer replacement, V13, selector use, or default promotion.

STOP — corrective planning addendum complete. AUDIT 78/79 unmodified; nothing committed or pushed;
Phase 3 not implemented.
