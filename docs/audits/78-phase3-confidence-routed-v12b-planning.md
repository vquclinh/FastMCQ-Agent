# AUDIT 78 — Phase 3 Planning: Confidence-Routed V12B (V13 disabled)

Audit number 78 (no prior `78-*` existed under `docs/audits/`).

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `08b97df4967dd305880a29faffe22fa48aa5df6b` ("document phase 2 Windows shadow validation")

## 2. Initial working-tree state

`git status --short` empty (clean); `git diff --check` clean; no tracked modifications. Phase 1
(one-forward scoring, `d9e5b0a`), Phase 2 (shadow router, `7b8134c`), and AUDIT 66–77 are committed.

## 3. Planning-only / read-only statement

This is a **documentation-and-source-inspection planning pass**. No code/test/config was created or
modified; V12B/V13/selector were **not** executed; no model/API/network was used. The only file
created is this audit. All statements below marked "verified" come from reading the committed source;
statements marked "recommendation/proposed" are design proposals, not implementations.

## 4. Phase 1 / Phase 2 completion status

- Phase 1: one-forward bare-label next-token-logit choice scoring — committed, independently reviewed
  (AUDIT 67/70), real-model validated on Windows (AUDIT 68/71).
- Phase 2: observational confidence-aware shadow router — committed, independently reviewed (AUDIT
  73/75), corrective pass for the duplicate-qid case (AUDIT 74), real-model validated (AUDIT 76/77).
- Neither changes official answers; both are opt-in and off by default.

## 5. Governing architecture

Raw MCQ → local Qwen Base generation → one-forward bare-label choice scoring → confidence-aware
router (confident → keep Base; uncertain → V12B permutations) → (V13 in a later phase for unresolved
items) → calibrated merge/selector → official submission. **Phase 3 scope:** use the Phase 2 router's
bounded uncertain subset to run **V12B only** for selected records, keep V13 disabled, and (in Phase
3A) keep the Base answer unchanged. The provisional threshold 10.0 is not final; no non-candidate
backfill; explicit opt-in only; no default promotion.

## 6. Current V12B code inventory (verified)

Two modules, both under `src/layers/`, consumed **only** by `src/system/fastmcq_system.py` (the
`--legacy-dynamic-full` selective path):

- **`mcq_permutation_debiaser.py`** — pure, deterministic, no model, no I/O, no ground truth. Owns
  permutation construction, permuted→original label mapping, record validation, vote tallying, and
  the override decision.
- **`v12b_dynamic_layer.py`** — the model-backed layer: feature-based target selection, per-permutation
  prompting/generation via the shared local backend, JSONL record I/O (resume-capable), and
  aggregation into `V12BLayerResult`.

Imports of `v12b_dynamic_layer.py` (verified): `json`, `dataclasses`, `pathlib`, `src.utils.labels`,
`src.layers.mcq_permutation_debiaser`, and `src.local_model.local_qwen_backend`
(`get_local_qwen_backend`, `parse_json_object`). **No import of V13, selector, `dynamic_base_predictor`,
OpenRouter, or any API.** `mcq_permutation_debiaser.py` imports only `random`, `re`, `unicodedata`,
`src.utils.labels`.

## 7. Existing V12B call graph (verified)

```
fastmcq_system.run_fastmcq_system  (only in --legacy-dynamic-full)
  -> select_v12b_targets(samples, base_predictions, max_qids)          # legacy feature-based router
  -> run_v12b_layer(samples, base_predictions, targets, *, local_backend, permutations=6, policy, ...)
       for each target:
         build_option_permutations(sample, n=6, seed=42)               # pure
         for each permutation:
           backend.generate_text(_prompt(perm, question))              # ONE model generation
           parse_json_object(content)                                  # JSON parse (not the hardened parser)
           map_permuted_answer_to_original(...)                        # pure; -> mapped original label + valid
           emit JSONL record
         summarize_permutation_votes(qid, current_answer, records)     # pure
         select_permutation_override(summary, policy)                  # pure; accept/reject + proposed
       -> V12BLayerResult(qid, proposed_answer, accept, reason, vote_counts, valid_votes, ...)
```

Key entry points / signatures:
- `select_v12b_targets(samples, base_predictions, *, max_qids=None) -> list[V12BTarget]`.
- `run_v12b_layer(samples, base_predictions, targets, *, model_path=None, local_backend=None,
  max_new_tokens=384, permutations=6, policy="conservative", work_dir=..., resume=False) -> list[V12BLayerResult]`.
- Required inputs: `samples` (qid/question/choices dicts), `base_predictions` (`BasePrediction` with
  `.qid/.answer/.source/.confidence/.risk_reason/.route`), `targets` (`V12BTarget`).
- Returned output: `V12BLayerResult(qid, proposed_answer, accept, reason, vote_counts, valid_votes,
  records_path, metadata)`.

## 8. Current permutation-generation behavior (verified)

`build_option_permutations(sample, n=6, seed=42)` yields up to 6 deterministic permutations, deduped
by ordering: `original`, `reverse`, `rotate+1`, `rotate+2`, `random_seed1`, `random_seed2` (the two
random ones seeded `42+1`, `42+2`). It permutes **option POSITIONS**, not labels: permuted position j
shows the original option at index `perm[j]` under the j-th canonical label. Each `OptionPermutation`
carries `permuted_to_original`/`original_to_permuted` maps and `permuted_choices`
(`{label, text, original_label}`). Supports any label count (beyond H). **Deterministic** (fixed seed;
dedup preserves order). The model prompt (`_prompt`) is a system+user **JSON-structured** prompt asking
for `selected_label`, `selected_option_text` (verbatim), `confidence`, `reason_type`,
`label_matches_option`, `evidence` — distinct from the BTC bare-label prompt and the Phase-1 scoring
suffix.

## 9. Current aggregation / tie / failure behavior (verified)

- **Mapping** (`map_permuted_answer_to_original`): invalid when the label is out of range, the model's
  own `label_matches_option` is False, the copied option text does not normalize-match the selected
  option, or the text matches a *different* option (`label_text_conflict` / `option_text_no_match`).
  Normalization = NFKD fold + casefold + strip punctuation + collapse whitespace.
- **Vote summary** (`summarize_permutation_votes`): counts only VALID records (parse ok + label/option
  match); reports `valid_records`, `vote_counts`, `current_votes`, `top_non_current_label/votes`,
  `mismatch_count`, `parse_failure_count`, `mean_support_confidence`. Tie-break for the top non-current
  label: `max(alt, key=(votes, -ord(label)))` → highest votes, then earliest label. Deterministic.
- **Override** (`select_permutation_override`, conservative): accept only when
  `valid_records ≥ 5 AND top_non_current_votes ≥ 4 AND current_votes ≤ 1`; a `balanced` policy adds a
  `mean_support_confidence ≥ 0.6` path; otherwise **keep Base**. Ties/insufficient votes → keep Base.
- **Per-permutation failure isolation**: a generation/parse exception yields a `local_error` record;
  one failed permutation does not abort the item.
- Exposed fields: per-permutation mapped label, `parse_status`, `label_option_match`, `valid`,
  `failure_reason`, per-permutation `confidence`; aggregate `vote_counts`, `valid_votes`,
  `proposed_answer`, `accept`, `reason`. **Not** exposed today: per-permutation latency, explicit
  runner-up label/margin (derivable), or a stable/unstable boolean (derivable).
- **Determinism**: the pure core is deterministic; the only nondeterminism is model generation
  (greedy/temp-0 → deterministic on fixed hardware). No global mutable state in the pure core; the
  layer uses the process-wide backend cache (avoidable by injecting a backend) and writes a JSONL
  side-artifact.

## 10. V12B reuse assessment

**Conclusion: reusable with a thin adapter; the pure core is reusable as-is.**

- `mcq_permutation_debiaser.py` (`build_option_permutations`, `map_permuted_answer_to_original`,
  `summarize_permutation_votes`, `select_permutation_override`) is **reusable as-is** — pure,
  deterministic, no coupling.
- `run_v12b_layer` is **reusable with a thin adapter**: Phase 3 must **not** use `select_v12b_targets`
  (it uses the Phase 2 confidence router's selected records instead), and would feed a minimal
  base-answer map (qid → Base answer) rather than the full legacy `BasePrediction`/`V12BTarget`
  pipeline. Recommendation: **do not modify** `v12b_dynamic_layer.py` or the legacy path; instead add a
  narrow `confidence_v12b_runner.py` that reuses the pure core + the shared backend directly (or calls
  a lightly-parameterized `run_v12b_layer` via an adapter), preserving legacy behavior and its tests.

## 11. Resource / cost analysis (verified where noted; else calculation-only)

- **Generations per selected record: 6** (one `backend.generate_text` per permutation) — verified.
- **Backend reuse:** `backend = local_backend or get_local_qwen_backend(...)` — reuses the injected
  loaded model (no duplicate load) when a backend is passed; verified. Phase 3 should inject the
  already-loaded predictor backend.
- Prompts are rebuilt per permutation (cheap, CPU-side string build). No batching is currently
  supported (sequential `generate_text` calls).
- **Theoretical maximum additional generations under `cap = ceil(N/8)`: `6 · ceil(N/8)`** (calculation
  only, not a benchmark): N=21 → **18**; N=100 → **78**; N=1,000 → **750**; N=10,000 → **7,500**.
- CUDA memory: V12B reuses the same loaded model; no measured VRAM/latency numbers exist for V12B on
  the RTX 4060 8 GB (Phase 1/2 measured only Base+scoring; ≈6.07 GiB peak). **No latency/VRAM figures
  are invented here.** V12B needs no dependency change to run inside the existing Docker image (it uses
  the same `generate_text`).

## 12. Option A vs Option B

- **Option A (direct answer-changing V12B):** selected records run V12B and may replace Base. Simple,
  but assumes an unvalidated merge rule, risks Base regressions, is threshold-dependent on the
  provisional 10.0, and — with only 21 synthetic items and no organizer ground truth — has **no
  evidence** to justify overriding answers. High regression risk. **Not recommended now.**
- **Option B (Phase 3A observational, then Phase 3B gated merge):** 3A runs V12B only for router-
  selected records, records diagnostics, and **keeps Base** (official CSV byte-identical); 3B enables
  an explicit opt-in calibrated merge only after permitted labeled evaluation. Safe, high experimental
  value, modest added complexity, and appropriate given the tiny current dataset and absent ground
  truth. **Recommended.**

## 13. Recommended Phase 3A / 3B split

**Adopt Option B.** Phase 3A = observational confidence-routed V12B (no answer change, V13 off).
Phase 3B = opt-in gated Base-replacement, only after permitted labeled calibration evidence. Do not
combine them.

## 14. Proposed Phase 3A module / API design (not implemented)

New narrow module `src/local_model/confidence_v12b_runner.py`, reusing `mcq_permutation_debiaser`
as-is and the Phase-2 router for selection. Proposed pure/data structures:

- `V12BRunInput`: `qid`, `input_index`, `question`, `choices`, `labels`, `base_answer`,
  `router_selected_rank`, `router_candidate_reasons`, `base_top1`, `base_top2`, `base_logit_margin`,
  `base_normalized_entropy`.
- `V12BPermutationResult`: `permutation_id`, `mapped_original_label`, `valid`, `parse_status`,
  `label_option_match`, `failure_reason` (no question/option text).
- `V12BAggregateResult`: `qid`, `input_index`, `valid_permutations`, `vote_counts`, `winning_label`,
  `winning_votes`, `runner_up_label`, `runner_up_votes`, `consensus_ratio`, `unique_answers`,
  `tie`, `stable` (bool), `base_v12b_agreement`, `hypothetical_answer`, `official_source="base"`.
- `V12BRunSummary`: totals, attempted/succeeded/failed, stable/unstable, disagreement count, vote/
  consensus distributions, additional-generation count, selected qids/items, observational-only note.
- `run_confidence_routed_v12b(inputs, *, backend, config) -> (per_record_results, summary)`: runs 6
  permutations per input via the injected backend, aggregates with the pure core, and returns
  observational results **without** touching official answers.

Inputs/outputs are numeric/categorical only; no question text or reasoning is carried through.

## 15. Proposed CLI / config design (not implemented)

CLI (opt-in): `--confidence-v12b-shadow` (implies router scoring + Phase-2 selection; runs V12B only
for selected records; keeps official Base answers), `--v12b-shadow-path`
(default `scratch/fastmcq_run/confidence_v12b.jsonl`), `--v12b-shadow-summary-path`
(default `scratch/fastmcq_run/confidence_v12b_summary.json`). No flag → unchanged; Phase-2 shadow flag
alone → unchanged; V13 stays off; `--legacy-dynamic-full` stays separate; invalid config → fail closed
(no V12B, official output intact); artifact-write failure → warn, official CSV intact.

Proposed config block (do not modify the YAML now):

```yaml
confidence_v12b:
  enabled: false             # structural invariant (opt-in; off by default)
  observational_only: true   # structural invariant for Phase 3A
  permutation_count: 6       # safe default (matches current V12B)
  require_router_selected: true   # structural invariant (only Phase-2-selected records)
  min_valid_permutations: 5  # provisional (mirrors current conservative rule; calibration-dependent)
  consensus_threshold: 4     # provisional (top-non-current votes; calibration-dependent)
  keep_base_on_tie: true     # structural invariant (observational: always keep Base)
  keep_base_on_invalid: true # structural invariant (observational: always keep Base)
```

Field classification: `enabled`, `observational_only`, `require_router_selected`, `keep_base_on_tie`,
`keep_base_on_invalid` = **structural invariants**; `permutation_count` = **safe default**;
`min_valid_permutations`, `consensus_threshold` = **provisional / calibration-dependent** (must not be
finalized without labeled evidence).

## 16. Proposed per-record artifact schema (privacy-safe)

JSONL per selected record (no question/choices/prompt/reasoning/expected/ground-truth/API-key):
`qid`, `input_index`, `router_selected_rank`, `router_candidate_reasons`, `base_answer`, `base_top1`,
`base_top2`, `base_logit_margin`, `base_normalized_entropy`, `permutations` (list of
`{permutation_id, mapped_label, valid, parse_status, label_option_match, failure_reason}`),
`vote_counts`, `valid_permutations`, `winning_label`, `winning_votes`, `runner_up_label`,
`runner_up_votes`, `consensus_ratio`, `unique_answers`, `tie`, `stable`, `base_v12b_disagreement`,
`hypothetical_answer`, `official_answer_source="base"`, `elapsed_sec` (if measured correctly),
`error_code`. All finite (writer must use `allow_nan=False`).

## 17. Proposed summary schema

`total_inputs`, `router_candidates`, `router_selected`, `v12b_attempted`, `v12b_succeeded`,
`v12b_invalid_or_failed`, `stable_count`, `unstable_count`, `base_v12b_disagreement_count`,
`vote_distribution`, `consensus_distribution`, `additional_generation_count`, `selected_qids`,
`selected_items` (qid/input_index/rank), `scoring_method`, and an explicit `observational_only: true`
note. Finite and privacy-safe.

## 18. Measurable stability signals

Permitted (measurable, non-self-reported): valid-permutation count, winning/runner-up vote counts,
consensus ratio, vote margin, number of unique canonical answers, tie status, Base/V12B agreement,
invalid-output rate, permutation-position sensitivity, cross-family answer consistency. **Excluded:**
model-written confidence statements, hidden-reasoning quality, vague semantic confidence, and
organizer leaderboard results as per-item ground truth. In Phase 3B these signals (e.g. high consensus
ratio + low invalid rate + Base disagreement + low Base margin) become **inputs to a calibrated merge
gate**, evaluated against permitted labels — never used to override answers in Phase 3A.

## 19. Candidate Phase 3B gated-merge policies (not finalized)

- **P1 — replace on any V12B unique majority.** Benefit: max coverage. Risk: high regression; ignores
  Base confidence. Data: labeled set. Not suitable first.
- **P2 — replace when V12B consensus > threshold and differs from Base.** Benefit: filters weak
  signals. Risk: threshold uncalibrated. Data: labeled set for consensus-vs-correctness. Moderate.
- **P3 — replace only when Base margin < calibrated threshold AND enough valid permutations AND strong
  consensus AND no tie AND valid.** Benefit: conservative, multi-signal, aligns with the existing
  conservative override. Risk: low coverage. Data: labeled Base-margin bins + consensus. **Recommended
  conservative candidate for later evaluation.**
- **P4 — keep Base unless V12B passes a strict correction gate.** Most conservative; lowest regression;
  lowest gain. Good fallback/first gate.

Recommend evaluating **P3/P4** on permitted labeled data; none is production-approved.

## 20. Permitted calibration-data strategy

No organizer ground truth exists; do **not** evaluate accuracy on organizer test data or infer
correctness from leaderboard changes, and do not store organizer expected answers. Build a permitted
calibration set from: self-created synthetic MCQs; manually annotated examples; competition-permitted
public-domain labeled MCQ datasets; clearly-marked weakly-labeled examples; adversarial
permutation-sensitivity examples; Vietnamese language/domain examples. Stratify by: choice count
(3/4/5/10), category (arithmetic, logical reasoning, Vietnamese language, factual, commonsense,
ambiguous/malformed, long questions, close distractors), label-position balance, difficulty, and
Base-margin bins. **Planning estimate (not a competition requirement):** staged sizes — ≈100 for an
initial diagnostic, ≈300–500 for a first calibration signal, ≈1,000+ (stratified) before any merge
threshold is proposed. The current 21-item set is diagnostic-only and far too small.

## 21. Evaluation metrics

- **Base:** overall accuracy; routed subset size/coverage; routed-subset Base accuracy; non-routed
  Base accuracy. (calibration)
- **V12B:** aggregate accuracy; valid-permutation rate; stable/unstable rate; Base/V12B agreement;
  consensus distribution. (diagnostic + calibration)
- **Correction:** Base-wrong→V12B-correct; Base-correct→V12B-wrong; net corrections; correction
  precision; regression rate; net accuracy delta; oracle upper bound; coverage-vs-gain curve.
  (calibration + promotion)
- **Router:** error concentration among selected; wrong-answer capture rate; selected-subset error
  rate; candidate-vs-selected counts; behavior by threshold and by budget divisor. (calibration)
- **Efficiency:** V12B attempts; additional generations (`6·selected`); elapsed per record; total added
  runtime; failures; peak GPU memory if measured. (diagnostic)

## 22. Promotion gates

- **Gate to implement Phase 3A:** design review complete (this audit + independent review); no official-
  output change; V12B callable independently (verified: pure core + injectable backend); deterministic
  mapping verified (verified for the pure core; model determinism from greedy decoding); privacy-safe
  artifact schema; fail-closed behavior specified. **Met after independent review of this plan.**
- **Gate 3A → 3B:** permitted labeled evidence that V12B diagnostics are reliable, correction precision
  acceptable, regressions bounded, consensus correlates with correctness, no parser/mapping defect,
  runtime cost acceptable. **NOT met by current evidence.**
- **Gate for default promotion:** substantially stronger — larger representative permitted validation
  set, calibrated thresholds, regression analysis, repeated real-model runs, Docker/runtime stability,
  official-output contract testing, no dependence on organizer test labels, explicit human approval.
  **NOT met.** Current Phase 2 evidence does **not** satisfy the 3B or default-promotion gates.

## 23. Risk register (with source references)

| Risk | Source | Severity | Mitigation | Test needed |
|---|---|---|---|---|
| Permutation→canonical mapping error | `mcq_permutation_debiaser.map_permuted_answer_to_original` | Med | reuse the pure, tested core unchanged | mapping test per permutation family |
| Duplicate qid/input_index in artifacts | new runner (cf. AUDIT 74) | Low | key per-record artifacts by ordinal/input_index, not qid | duplicate-qid/index artifact test |
| Invalid/out-of-range model label | mapping `_norm_label` | Low | already yields invalid record (fail-closed) | invalid-label test |
| Parser fallback hiding failures | V12B uses `parse_json_object`, **not** the hardened `parse_mcq_label` | Med | keep JSON parsing; count `parse_error`/`local_error` as invalid votes | JSON-parse-failure test |
| Tie / <6 valid permutations | `summarize_permutation_votes` / `select_permutation_override` | Low | keep Base on tie/insufficient (observational) | tie + partial-valid tests |
| Runner accidentally invokes V13/selector | must not import them | High if violated | new runner imports only the permutation core + backend (verified none today) | import/call-graph test |
| Duplicate model load | `run_v12b_layer` backend arg | Med | inject the already-loaded backend | one-load test |
| 6-generation cost | 6·ceil(N/8) | Med | bounded by router cap; measure on GPU | cost/runtime measurement |
| Long-context overflow | `generate_text` | Low | fail-closed per permutation (existing try/except) | long-input test |
| Artifact-write failure | new writer | Low | `try/except`, warn, official CSV intact | write-failure integration test |
| Official-answer override in observational mode | new runner | **High if violated** | runner never touches `rows`; official = Base | official-CSV byte-invariance test |
| Non-deterministic permutation order | `build_option_permutations(seed=42)` | Low (deterministic) | keep fixed seed | determinism test |
| Positional bias | the phenomenon V12B targets | n/a | measured via permutation votes | position-sensitivity diagnostic |
| Formula-bank interaction | single-pass Base has no formula bank (verified) | Low | none | n/a |
| Accidental API/OpenRouter fallback | none in V12B path (verified) | Low | keep local-only | no-network test |
| Malformed config | new config block | Low | validate + fail-closed | malformed-config integration test |
| Partial artifacts on crash | writer | Low | write once after run; document partial semantics | crash/partial test |
| Windows/Linux path differences | `Path`/scratch paths | Low | use `pathlib`; scratch dir | Windows path test |

## 24. Future unit-test plan (do not add now)

Only router-selected records run V12B; non-selected never do; exactly 6 permutations when configured;
canonical mapping for every permutation family; invalid labels → invalid; ties → keep Base; partial
valid outputs; deterministic aggregation; stable consensus calc; no V13 invocation; no selector
invocation; no ground-truth fields in artifacts; finite JSON; duplicate qid/input_index safety;
malformed config fail-closed.

## 25. Future integration-test plan (do not add now)

No flag unchanged; Phase-2 shadow-only unchanged; V12B observational mode keeps official CSV
byte-identical; only the selected subset incurs V12B calls; Base generation/scoring not duplicated;
V12B uses the existing loaded backend; V12B failure keeps Base; artifact-write failure keeps Base;
malformed config fails closed; legacy dynamic mode unchanged; no V13/selector/API call; artifact
privacy; Windows path compatibility.

## 26. Future Windows real-model test plan (do not run now)

1 selected record; 0 selected records; selected < cap; selected == cap; 3/4/10-choice examples; six
canonicalized permutation outputs; stable and unstable V12B examples; exact official-CSV invariance
for Phase 3A; GPU memory and runtime measurement (first real V12B cost data).

## 27. Exact implementation sequence

- **3A-0:** isolate/reuse the V12B runner (new `confidence_v12b_runner.py`) reusing the pure core +
  shared backend, under Linux fake-model unit tests. No legacy-path change.
- **3A-1:** add observational confidence-routed V12B behind `--confidence-v12b-shadow` (router-selected
  records only; Base unchanged; V13 off).
- **3A-2:** Linux fake-model integration tests + independent review.
- **3A-3:** Windows real-model observational validation (first V12B cost/behavior data).
- **3A-4:** permitted labeled calibration experiments (diagnostics only).
- **3B-0:** define a gated merge policy (e.g. P3/P4) from that evidence.
- **3B-1:** implement opt-in answer replacement behind a separate explicit flag.
- **3B-2:** independent review + regression testing.
- **3B-3:** real-model validation.

Each step is a separate task; do not combine.

## 28. Files expected to change in the FIRST future implementation task (3A-0/3A-1)

- New: `src/local_model/confidence_v12b_runner.py`; new unit/integration test files
  (`tests/unit/test_confidence_v12b_runner_*.py`, `tests/integration/test_confidence_v12b_shadow_*.py`).
- Modified: `predict.py` (opt-in flags + one-scored/one-selected reuse + observational V12B call +
  artifact writers); `configs/confidence_selective.yaml` (+`confidence_v12b` block);
  `src/local_model/confidence_config.py` (+`load_v12b_config`).

## 29. Files that must remain unchanged

`src/layers/mcq_permutation_debiaser.py` (reused as-is), `src/layers/v12b_dynamic_layer.py`,
`src/system/fastmcq_system.py`, the V13 modules, the selector, `dynamic_base_predictor`,
`build_mcq_prompt`, `parse_mcq_label`, `score_mcq_choices`, the Phase-2 shadow router, the Dockerfile,
dependencies, model settings, and the official CSV writer/schema.

## 30. Open decisions requiring evidence

- The final routing threshold (currently provisional 10.0).
- V12B acceptance thresholds (`min_valid_permutations`, `consensus_threshold`) — calibration-dependent.
- Whether V12B's own `mean_support_confidence` is discarded (recommended: use only vote-based signals).
- Whether Phase 3A shares the Base generation without re-generating for V12B (V12B uses a **different**
  JSON prompt, so it is a separate generation; Base is not re-run).
- The permitted calibration set composition/size.
- Whether the Phase-2 duplicate-qid ordinal pattern is mirrored in the V12B runner (recommended: yes).

## 31. Explicit confirmation

- No code/test/config change (only this audit created).
- No V12B execution; no V13 execution; no selector execution.
- No answer override; no final threshold declared.
- No organizer ground truth used.
- No API/OpenRouter call; no model download.
- No Git commit or push.

## 32. Current `git status --short`

```
?? docs/audits/78-phase3-confidence-routed-v12b-planning.md
```

## 33. Recommended next action

Independent review of this plan; then implement **Phase 3A-0** (isolate/reuse a `confidence_v12b_runner`
under Linux fake-model unit tests, reusing `mcq_permutation_debiaser` unchanged and injecting the
shared backend), as a standalone task — **before** any observational CLI wiring (3A-1). Do not begin
Phase 3B or any answer-changing behavior until permitted labeled evidence exists.

## 34. Final planning verdict

**PHASE 3 PLAN READY FOR INDEPENDENT REVIEW.**

The V12B core is verified reusable (pure `mcq_permutation_debiaser` as-is; `run_v12b_layer` via a thin
adapter), cleanly isolated (no V13/selector/API coupling), backend-reusable, deterministic, and costs a
bounded `6·ceil(N/8)` generations. The recommended path is **Option B**: Phase 3A observational
V12B (Base unchanged, official CSV byte-identical, V13 off), then Phase 3B gated merge only after
permitted labeled calibration. Phase 3 is **not** implemented, and current evidence does not authorize
Phase 3B or default promotion.

STOP — Phase 3 planning audit complete. No implementation; nothing committed or pushed.
