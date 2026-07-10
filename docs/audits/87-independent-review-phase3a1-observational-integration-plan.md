# AUDIT 87 — Independent Review of the Phase 3A-1 Observational V12B Integration Plan (AUDIT 86)

Audit number 87 (no prior `87-*` existed under `docs/audits/`).

> **Governing rule.** Where AUDIT 86 is ambiguous or conflicts with this review's binding corrections,
> **AUDIT 87 governs the Phase 3A-1 implementation contract.** AUDIT 86 is preserved unchanged as the
> plan; AUDIT 87 supersedes only the portions corrected below.

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `77e940d3075405361e264019f7c5afa3e80038d6` ("add in-memory confidence-routed V12B runner")

## 2. Initial repository state

Preflight (`git branch --show-current`, `git rev-parse HEAD`, `git status --short`, `git log`,
`git diff --check`, `git diff --stat`, `git diff --name-only`, and the `--cached` variants) confirmed:
branch `main`; HEAD exactly `77e940d…`; only `?? docs/audits/86-…md` untracked; nothing staged; no
tracked source/test/config modification; both `--check` runs clean. No reset/stage/commit/push.

## 3. Independent / read-only statement

This is an independent, adversarial, read-only planning review. I modified no production source, tests,
YAML/config, or existing audits (78–86); implemented no Phase 3A-1; ran no real V12B inference; loaded
no model weights; executed no V13/selector/legacy path; altered no official answer; finalized no
threshold; used no organizer ground truth; called no external API; downloaded no model; did not commit
or push. The only file created is this audit.

## 4. Claude Code takeover / context reconstruction

Claude Code has resumed this repository from Git and the audit trail (Codex authored AUDIT 86). State
reconstructed from committed source and audits 78–85: Phase 1 (one-forward bare-label scoring) and
Phase 2 (opt-in observational shadow router) are complete and validated; Phase 3A-0
(`confidence_v12b_runner.py`) is committed and independently approved by AUDIT 85; Phase 3A-1 is not
implemented. Phase 3B, V13, selector, answer replacement, and default promotion remain unauthorized.

## 5. Source and governing audits reviewed

Read completely: `predict.py`; `src/local_model/qwen_mcq_predictor.py`;
`src/local_model/local_qwen_backend.py`; `src/local_model/confidence_v12b_runner.py`;
`src/local_model/confidence_shadow_router.py`; `src/local_model/confidence_config.py`;
`configs/confidence_selective.yaml`; `src/utils/labels.py`; `docs/audits/80`, `85`, `86`. Ran (fake/pure
only, no weights): `test_confidence_v12b_runner_2l49a.py`, `test_choice_scoring_2l48b.py`,
`test_confidence_telemetry_2l48c.py`, `test_confidence_shadow_router_2l48d.py`,
`test_confidence_shadow_router_2l48e.py`, `test_local_qwen_backend.py` → **140 passed in 0.83s**.

## 6. Verified current predict.py call graph

AUDIT 86 §7 is **accurate**. Verified no-legacy path (`predict.py` `else` branch, lines 277–347):

1. `parse_known_args`; resolve input/output paths.
2. `--legacy-dynamic-full` → delegate to `scripts/tools/final_infer.py` and return (separate branch).
3. `want_score = confidence_telemetry or confidence_shadow_router` (line 281).
4. If `want_score`: load `choice_scoring` config → `score_enabled = cfg.enabled` (fail-soft to defaults).
5. If `--confidence-shadow-router` and `score_enabled`: load `shadow_router` config into `shadow_cfg`
   (fail-closed to `None` on error). **`shadow_cfg.enabled` is NOT consulted** — the CLI flag is the opt-in.
6. `samples = load_dataset(inp)`; `predictor = _build_predictor(args)` (one `QwenMCQPredictor`, one
   cached backend, `backend.load()`).
7. `for idx, item in enumerate(samples)`: `predict_one` → `_coerce_label` → append `(qid, ans)` to
   `rows` and `dt` to `times`; if telemetry or shadow active, `_compute_score` **once** → telemetry
   record and/or `_shadow_input`.
8. `_write_telemetry` (optional); `run_shadow_router(shadow_inputs, shadow_cfg)` + `_write_shadow`
   (optional), the whole shadow block wrapped in `try/except` (lines 339–347).
9. Write `submission.csv` and `submission_time.csv` from `rows`/`times` (lines 350–362).
10. Legacy mirrors `--output`/`$OUTPUT_FILE` and `/output/pred.csv` (best-effort).

**Note (see §22):** the shadow artifact write currently occurs **before** the official CSV write, but
is fully guarded and pure. V12B adds real model inference, so the ordering contract tightens below.

## 7. Exact Phase 3A-1 integration point

Inside the `else` (offline-model) branch only, after the sample loop has produced `rows`, `times`, the
per-item `score`, and one router decision set — and **before** the official CSV write — construct valid
`V12BRunInput`s from router-**selected** decisions, call `run_v12b_for_selected(backend=predictor.backend)`
**once**, and write artifacts best-effort. Base row creation, official CSV, and timing CSV are never
gated on any V12B outcome. No official row may ever receive `hypothetical_answer`.

## 8. Score reuse contract (item A — verified)

`_compute_score` is called at most once per record today. Binding: extend
`want_score = confidence_telemetry or confidence_shadow_router or confidence_v12b_shadow`. The single
`score` dict feeds telemetry, shadow-router input, and V12B routing. If `score_enabled` is false or the
config is malformed, V12B fails closed (no V12B, official output unchanged, privacy-safe warning).
Score/router failure cannot mutate a Base row (rows are appended before scoring; scoring/router run under
`try/except`; the official CSV is written from `rows`). No association may rely on `qid` alone.

## 9. Router reuse and actual decision schema (item B — corrected)

`ShadowRoutingDecision` actual fields (verified): `qid`, `input_index`, `candidate`, `selected`,
`selected_rank`, `candidate_reasons` (**list**), `generated_answer`, `top1`, `top2`, `logit_margin`,
`probability_margin`, `normalized_entropy`, `scoring_valid`, `scoring_error`, `risk_tier`, `risk_margin`,
`provisional_threshold`, `budget_cap`, `scoring_method`.

AUDIT 86 field assumptions verdict:
- `selected_rank`, `candidate_reasons`, `top1`, `top2`, `logit_margin`, `normalized_entropy`, selected
  status (`selected`) — **all real**.
- **`private/internal ordinal` — DOES NOT EXIST on the decision.** `run_shadow_router` keeps the ordinal
  internal; it never surfaces on `ShadowRoutingDecision`.

Return shape (verified): `run_shadow_router` returns `(decisions, summary)` where **`decisions` is one
per input record, in input order** (`for ordinal, inp in enumerate(inputs)`), and `summary.selected_items`
is a separate per-selected collection (`{qid, input_index, selected_rank}` in risk-rank order). The router
runs **once**; when both Phase 2 shadow and V12B shadow are active, the same single decision list serves
both. Duplicate router execution is a Medium defect and is prohibited.

## 10. Governing identity contract (items C, D — corrected, binding)

Because the decision exposes no ordinal, **the authoritative internal identity is the decision-list
position, which equals the `enumerate(samples)` index.** Bind the following names and never conflate them:

- **`source_record_ordinal`** — `idx` from `enumerate(samples)` (== position in `decisions`). Authoritative
  per-record identity. This is the artifact's stable occurrence identity.
- **`router_selected_rank`** — `decision.selected_rank`. **Risk-rank** metadata only; NOT input order and
  NOT an identity.
- **`selected_sequence_ordinal`** — position in the filtered ordered list of valid selected inputs actually
  passed to the runner (input order among valid-selected).
- **`v12b_runner_record_ordinal`** — the runner's own `V12BAggregateResult.record_ordinal` (== position in
  the list passed to `run_v12b_for_selected`, i.e. equals `selected_sequence_ordinal`). It is **runner-local**
  and must **not** be used as the record's global identity.
- `qid`, `input_index` — non-unique metadata only; never join keys. Duplicate qids and duplicate
  input_indexes must remain distinct records; summaries count records, not unique qids.

## 11. Valid / invalid selected-entry pairing contract (item C — binding)

Define an explicit ordered wrapper and pair by list position only:

```text
ValidSelectedEntry(
    source_record_ordinal,      # enumerate(samples) index
    router_selected_rank,       # decision.selected_rank (risk rank, metadata)
    selected_sequence_ordinal,  # position among valid-selected inputs
    qid, input_index,           # non-unique metadata
    v12b_input,                 # V12BRunInput
)
```

Rules (binding):
- iterate `decisions` in input order; for each `decision.selected is True`, validate the corresponding
  source record (§12);
- collect **valid** entries into one dedicated ordered list; collect **invalid** selected records into a
  separate validation-error list (never sent to the runner);
- call `run_v12b_for_selected([e.v12b_input for e in valid_entries], backend=…)`;
- pair results by **list position only**: `for e, agg in zip(valid_entries, results)` — never by qid,
  input_index, question, or choices;
- **assert `len(results) == len(valid_entries)`** (the runner returns one result per input, in order);
- do not let a valid entry (e.g. C) attach to an invalid selected record (e.g. B): B is never in the
  valid list, so positional pairing over `valid_entries` cannot misalign;
- **field-name collision fix (Medium, F1):** the runner's `as_dict()` already emits `"record_ordinal"`
  (= `v12b_runner_record_ordinal`, filtered index). The per-record artifact **must** carry the source
  identity under the distinct key **`source_record_ordinal`** and must not overwrite or reuse the bare key
  `record_ordinal` for source identity. The nested aggregate's `record_ordinal` stays as-is and is
  documented as the runner-local filtered index.

## 12. Input-validation contract (item F — corrected)

Validate every router-selected record at the Phase 3A-1 boundary **before** constructing `V12BRunInput`:
- source record is a mapping with expected keys;
- `question` is a `str`;
- `choices` is a non-`str`, non-`bytes` sequence;
- **choice count is in `2..26`** — corrected from AUDIT 86 §12's `1..26`. Source basis: the Phase 1 scorer
  returns `need_at_least_two_labels` for `<2` labels, and `labels_for` caps at 26 (`0..26`); the dataset
  contract is 2–11 options. `<2` or `>26` → `unsupported_choice_count`;
- canonical labels equal `tuple(labels_for(len(choices)))`, with no duplicates;
- Base answer is a valid label for the record (or a documented invalid-base code);
- Base `top1`/`top2` are valid labels or `None`; non-`None` `logit_margin`/`normalized_entropy` are finite;
- `router_selected_rank` is a positive integer.

Invalid selected records: **do not call V12B**, **do not abort** valid records, retain the Base official
answer, and emit only a **closed** privacy-safe validation code (no text, no `str(exc)`):
`ok`, `invalid_record_shape`, `invalid_question`, `invalid_choices`, `unsupported_choice_count`,
`invalid_canonical_labels`, `invalid_base_answer`, `invalid_score_diagnostic`, `invalid_router_rank`,
`input_validation_error`.

## 13. AUDIT 85 L1 resolution (input validation at the boundary)

Resolve L1 in `predict.py` via a Phase-3A-1-only helper (e.g. `_build_v12b_inputs_from_router(...)`)
that returns the valid-entry list, wrapper metadata, and closed input-validation error records. **Do not
modify the approved Phase 3A-0 runner** for L1 in this pass; the integration boundary owns the raw-record
→ `V12BRunInput` conversion.

## 14. AUDIT 85 L2 resolution (thresholds — Option A)

Call the runner with its approved defaults `min_valid_permutations = 5`, `consensus_votes = 4`
(verified `DEFAULT_MIN_VALID_PERMUTATIONS`/`DEFAULT_CONSENSUS_VOTES`). Do **not** expose either in CLI or
YAML in the first pass; label all statuses provisional/observational; do not modify the runner. This
avoids the known custom-threshold mismatch.

## 15. CLI activation contract (item G — binding)

Verified Phase 2 convention: `predict.py` uses the **CLI flag** as the opt-in and never consults
`shadow_router.enabled` (only `choice_scoring.enabled` gates scoring). Binding single-gate rule:
- `--confidence-v12b-shadow` is the **only** execution opt-in;
- `confidence_v12b.enabled` in YAML is a structural/default-disabled marker, **not** a second independent
  activation gate; when the CLI flag is off, V12B never runs regardless of YAML; when on, the block (if
  present) must validate;
- path flags (`--v12b-shadow-path`, `--v12b-shadow-summary-path`) without the execution flag are inert
  (no artifact written), consistent with Phase 2;
- `--legacy-dynamic-full` + `--confidence-v12b-shadow` → **explicit error before model load**;
- malformed scoring/router/V12B config → fail closed to Base-only official output.

## 16. Config contract (item, §16 of AUDIT 86 — refined)

Minimal `confidence_v12b` block: `enabled: false` (marker), `observational_only: true` (must be true),
`require_router_selected: true` (must be true), `permutation_count` (`1..6`, default 6). **Do not expose**
`min_valid_permutations`, `consensus_votes`, or `max_new_tokens` as tunable thresholds in the first pass
(see §17). Absent block → V12B still runs when the CLI flag is on, using defaults, fail-soft. Malformed
block → disable V12B, preserve Base output. Forbidden fields (reject/ignore, never honor): answer
override, merge threshold, balanced policy, self-reported confidence, V13, selector, Phase 3B threshold,
and consensus/min-valid configurability.

## 17. Final max_new_tokens decision (item H — binding)

Verified: the Phase 3A-0 runner's tested default is `DEFAULT_MAX_NEW_TOKENS = 192`. AUDIT 86's proposed
192 therefore **matches the runner's own approved default** (it is not an arbitrary new value). Binding:
call `run_v12b_for_selected` **without overriding `max_new_tokens`** (use the runner default 192); do not
expose it as configurable in the first pass. It is a safe implementation default, not a calibrated
threshold. (predict.py's Base `--max-new-tokens=64` is a separate concern and stays unchanged.)

## 18. Privacy-safe per-record artifact schema (item 7 — binding)

**Whitelist-only serialization.** Emit only: `observational_only: true`; `source_record_ordinal`;
`selected_sequence_ordinal`; `qid`; `input_index`; `router_selected_rank`; `router_candidate_reasons`
(closed router set); Base answer; Base `top1`/`top2`/`logit_margin`/`normalized_entropy`;
`input_validation_status`; `v12b_attempted`; `official_answer_source: "base"`; and the runner's
`V12BAggregateResult.as_dict()` (which nests `V12BPermutationResult.as_dict()` — verified text-free:
`permutation_id`, labels-only `permuted_to_original`, mapped label, parse status, validity,
`label_option_match`, closed `error_code`, optional `exception_class_name`).

**Never** serialize `V12BRunInput` (it carries question/choices), any dataclass `__dict__`, or arbitrary
field values. Forbidden fields: question, choices, option text, selected option text, prompt, raw
response, evidence, reasoning, model confidence, expected answer, correctness, ground truth, API keys,
arbitrary exception text. `json.dumps(..., allow_nan=False)`; non-finite → fail closed or serialize `null`
under a documented rule.

## 19. Summary schema (binding)

Emit only: `observational_only: true`; total input records; total router candidates; total selected;
V12B attempted/skipped-invalid/failed records; total permutation attempts; total valid permutations;
parse/generation failure totals; input-validation error counts; aggregate-status counts; Base/V12B
disagreement count; selected qids in risk-rank order (duplicates allowed); `selected_items` with qid,
input_index, selected rank, and `source_record_ordinal`; per-file artifact writer status. No ground
truth, expected answers, text, or raw exception messages.

## 20. Artifact writing and per-file failure semantics (items I, J — binding)

- Build all per-record dicts in memory; validate `json.dumps(..., allow_nan=False)`.
- Write JSONL and summary as **two independently atomic files** (temp file + rename each), each with its
  own status; do **not** claim cross-file atomicity (the filesystem cannot guarantee it).
- Catch `OSError`, `ValueError`, and serialization errors; warn with **exception class name only**, never
  `str(exc)`.
- The **entire V12B section** — selected-input construction, `run_v12b_for_selected`, serialization,
  directory creation, temp write, rename, JSONL write, summary write — must run under a broad fail-closed
  boundary that never re-raises past the official CSV write.
- **Ordering (F6):** write `submission.csv` and `submission_time.csv` from untouched Base `rows`/`times`
  **before** writing V12B artifacts (defense-in-depth beyond the fail-closed boundary). Mirrors follow the
  official CSV as today.

## 21. Official-output ordering and byte-invariance contract (item 8)

Official byte invariance = identical Base-row sequence, identical CSV writer, identical row order,
header, encoding, and newline behavior; V12B mode never reconstructs or mutates official rows;
`hypothetical_answer` is never copied into an official row. Fake integration tests must compare **exact
official CSV bytes** against the corresponding Base-only run (test surfaces exist:
`test_btc_submission_contract_2l47a.py`, `test_full_system_output_contract_2l41a.py`,
`test_submission_variants_2l29a.py`). `submission_time.csv` and diagnostic files are excluded from the
byte-equality claim. Real-model validation compares official Base rows/hashes under a controlled run and
documents model nondeterminism.

## 22. No-V13 / no-selector / no-legacy guarantees (verified)

Verified `predict.py` imports neither `run_v12b_layer` nor `select_v12b_targets` (they live only in
`src/layers/v12b_dynamic_layer.py` and `src/system/fastmcq_system.py`). Phase 3A-1 must not import/call
V13 modules, selector code, `run_v12b_layer`, `select_v12b_targets`, legacy V12B writers,
`src/system/fastmcq_system.py`, or external APIs. Add static-import and monkeypatch guard tests.

## 23. Recommended single-pass implementation scope (item 9 — binding)

No unresolved Critical/High/Medium **architectural** blocker remains after §§8–22 (the three Medium
items are contract-resolvable and are resolved above). Therefore authorize **one tightly scoped Phase
3A-1 implementation pass** containing: backend read-only accessor; config validation; CLI flag + mode
conflict; score/router reuse; selected-entry validation and safe positional pairing; Phase 3A-0 runner
call; privacy-safe JSONL + summary writer; fail-closed artifact behavior; comprehensive fake integration
tests; official CSV byte-invariance tests. Do **not** split into 3A-1a/1b/1c. After implementation:
implementation audit → one independent code review → Windows real-model observational validation.

## 24. Exact allowed implementation files

- `predict.py` (CLI flag, mode conflict, score/router reuse, selected-entry construction, runner call,
  fail-closed artifact section);
- `src/local_model/confidence_config.py` (add `load_v12b_config` / `confidence_v12b` validation);
- `configs/confidence_selective.yaml` (add the `confidence_v12b` block);
- `src/local_model/qwen_mcq_predictor.py` (read-only `backend` property only, §25);
- optional new `src/local_model/confidence_v12b_artifacts.py` (privacy-safe writer, if factored out);
- new focused unit tests + Phase 3A-1 fake integration tests + accessor test.

## 25. Backend accessor / injection contract (item E — binding)

Verified: `QwenMCQPredictor` owns one private `self._backend`; both `predict_one` and `score_choices`
use it; no public accessor exists; the backend cache key `(resolved_path, device)` is unnormalized, so a
differently spelled path can create a second instance. Binding: add a **read-only property**:

```python
@property
def backend(self) -> LocalQwenBackendProtocol:
    return self._backend
```

No setter; no `get_local_qwen_backend` call; no path/cache lookup; returns the exact existing instance
(verified type `LocalQwenBackendProtocol`, which declares the `generate_text(prompt_or_messages, *,
max_new_tokens, temperature)` signature the runner's `V12BBackendProtocol` requires). `predict.py` must
call `run_v12b_for_selected(..., backend=predictor.backend)` and must not touch `predictor._backend`.
Unit test asserts object identity. The accessor is **part of this single 3A-1 pass** (no cleaner existing
injection path exists).

## 26. Required fake unit/integration tests (item 10)

Unit: no-flag unchanged; path-only flags inert; absent/invalid/disabled config; legacy conflict before
model load; valid 3/4/5/10-choice records; string/bytes/`<2`/`>26` choices; canonical-label mismatch;
duplicate labels; invalid Base answer; non-finite score diagnostics; duplicate qid / duplicate
input_index / both duplicated; invalid-selected-then-valid ordering; accessor identity; no second
`get_local_qwen_backend`; `allow_nan=False`; closed error codes only; labels-only mappings; no private
text; no `str(exc)`; temp-write failure; `source_record_ordinal` ≠ `v12b_runner_record_ordinal` name
separation. Integration (fake predictor/backend): Base generation not duplicated; exactly one score call
per record across combined modes; exactly one router call; single backend identity; up-to-six V12B calls
per selected record; A-valid/B-invalid/C-valid pairing never attaches C to B; `zip` length assertion; no
selected records → empty artifacts + unchanged CSV; one/all V12B failures preserve CSV; selected-input
construction / JSON serialization / directory / JSONL / summary / rename failures preserve CSV; malformed
config fails closed; **official CSV exact-byte equality** across no-flag / Phase-2-only / V12B /
telemetry+V12B / Phase-2+V12B / V12B-exception / malformed-input / writer-failure / no-selected /
below-cap / at-cap; qid order + answers + row count unchanged; no V13 / selector / legacy V12B / external
API call; permutation-count range; source-vs-runner ordinal distinction.

## 27. Future Windows real-model validation

Deferred; observational only. Cover the 21-item synthetic set; ≥1 selected record; no-selected case;
below- and at-cap selection; valid and invalid structured V12B outputs; actual permutation call counts;
elapsed runtime; peak GPU memory; artifact privacy; official CSV byte invariance; no V13/selector/legacy.
Do not claim accuracy improvement.

## 28. Findings table

| ID | Severity | Source evidence | Impact | Blocks AUDIT 86 commit? | Blocks 3A-1 impl? | Binding correction (in AUDIT 87) |
|---|---|---|---|---|---|---|
| F1 | Medium | Runner `as_dict()` emits `"record_ordinal"` (runner-local filtered index) at runner.py:186,223; AUDIT 86 §17/§18 also wants a wrapper source ordinal | Same key, two meanings → misidentified records in artifacts | No | Yes | §10/§11: wrapper uses `source_record_ordinal`; runner `record_ordinal` documented runner-local; never conflate |
| F2 | Medium | AUDIT 86 §12 says `1..26`; scorer returns `need_at_least_two_labels` for `<2` (backend.py:359); dataset 2–11; `labels_for` caps 26 | `<2`-choice record could reach the runner as a degenerate case | No | Yes | §12: valid range `2..26`; `<2` or `>26` → `unsupported_choice_count`, fail closed |
| F3 | Medium | `ShadowRoutingDecision` has no ordinal attr; decisions returned in input order; `selected_rank` is risk-rank | Identity/pairing could be anchored on rank or qid | No | Yes | §10: identity = `source_record_ordinal` (= enumerate index); rank is metadata only |
| F4 | Low | Runner default 192 (runner.py:25); AUDIT 86 §16 exposes `max_new_tokens` as config | Arbitrary tunable/threshold drift | No | No | §17: use runner default 192; not exposed in first pass |
| F5 | Low | predict.py ignores `shadow_router.enabled`; CLI flag is opt-in | Two independent activation gates would contradict Phase 2 | No | No | §15: CLI flag is the only gate; `enabled` is a marker |
| F6 | Low | predict.py writes shadow artifacts before official CSV (lines 339–362); V12B adds model inference | A V12B write path could precede official CSV | No | No | §20: broad fail-closed boundary + write official CSV before V12B artifacts |
| F7 | Low | Runner `as_dict()` are hand-written whitelists; `V12BRunInput` carries question/choices | Arbitrary `__dict__`/input serialization would leak text | No | No | §18: whitelist-only; never serialize `V12BRunInput`/`__dict__`; `allow_nan=False` |
| I1 | Informational | Linux env, no weights | No real-model evidence yet | No | No | §27: deferred Windows validation |

Counts: **Critical 0 / High 0 / Medium 3 / Low 4 / Informational 1.** All Medium/Low findings are
resolved by the binding corrections above; none is an unresolved architectural blocker.

## 29. Binding corrections to AUDIT 86 (summary)

§12 choice range `1..26` → **`2..26`** (F2). §16/§17 `max_new_tokens` exposed → **runner default 192, not
exposed** (F4). §17/§18 wrapper "record_ordinal" → **`source_record_ordinal`**, distinct from the runner's
runner-local `record_ordinal` (F1). §11/§22 identity → **`source_record_ordinal` = enumerate index; rank
is metadata; runner ordinal is filtered-local** (F3). §20 ordering → **official CSV before V12B artifacts,
whole V12B section under a broad fail-closed boundary** (F6). §18 serialization → **whitelist-only, never
`V12BRunInput`/`__dict__`** (F7). §16 activation → **single CLI gate; `enabled` is a marker** (F5). §29's
3-way split → **one single-pass implementation** (§23).

## 30. Unresolved blockers

None. No unresolved Critical, High, or Medium architectural blocker remains after the binding corrections.

## 31. Recommended immediate next implementation task

Implement Phase 3A-1 as **one tightly scoped pass** per §§23–26: add the read-only `backend` property;
add `confidence_v12b` config validation + CLI flag + `--legacy-dynamic-full` conflict (rejected before
model load); extend `want_score` and reuse one score + one router decision set; build validated
`ValidSelectedEntry` list (range `2..26`, positional pairing, `source_record_ordinal`); call
`run_v12b_for_selected(backend=predictor.backend)` with runner defaults; write official CSV first, then
privacy-safe JSONL + summary best-effort under a broad fail-closed boundary; add the fake unit + integration
tests including exact official-CSV byte equality. Then: implementation audit → independent review →
Windows observational validation.

## 32. Authorization confirmation

This review and the authorized single 3A-1 pass do **not** authorize Phase 3B, answer replacement, V13,
selector behavior, legacy V12B, default promotion, or final threshold selection. Official answers remain
Base; V12B remains observational.

## 33. Explicit confirmation

No source/test/config/AUDIT-86 modification; no Phase 3A-1 implementation; no real model/V12B/V13/selector
execution; no model weights loaded; no answer override; no final threshold; no organizer ground truth; no
API/OpenRouter call; no model download; no commit or push. Only AUDIT 87 was created.

## 34. Current git status

```
?? docs/audits/86-phase3a1-observational-v12b-integration-plan.md
?? docs/audits/87-independent-review-phase3a1-observational-integration-plan.md
```

## 35. Final verdict

**PHASE 3A-1 PLAN READY FOR FAST-TRACK IMPLEMENTATION WITH BINDING CORRECTIONS IN AUDIT 87**

AUDIT 86 is compatible with committed source and, with the binding corrections in §§8–29 (three Medium,
four Low resolved directly here), is precise enough for one tightly scoped Phase 3A-1 implementation pass.
A separate documentation-only correction pass is unnecessary. This verdict authorizes only that single
observational Phase 3A-1 pass — not Phase 3B, answer replacement, V13, selector behavior, legacy V12B,
default promotion, or final threshold selection.
