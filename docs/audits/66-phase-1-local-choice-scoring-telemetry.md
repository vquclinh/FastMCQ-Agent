# AUDIT 66 — Phase 1: Local Per-Choice Scoring & Uncertainty Telemetry (observational)

Audit number 66 (no prior `66-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD before changes

- Date: 2026-07-10
- Branch: `main`
- HEAD before changes: `90ea59dec3c2c20c18657233ef3b0401c0af12e5` ("document historical OpenRouter 79.7 pipeline")
- TARGET_PHASE = 1, PROMOTE_DEFAULT = false.

## 2. Initial working-tree state

Clean (`git status --short` empty). Prerequisites verified: Docker CRLF fix present (`1d791e3`);
hardened MCQ parser from AUDIT 65 committed (in `90ea59d`; `_MARKER_LABEL_RE` present in
`src/local_model/local_qwen_backend.py`); AUDIT 64 and AUDIT 65 present under `docs/audits/`;
parser test files committed. Full-suite baseline (post parser fix): **16 failed, 647 passed**.

## 3. Target phase

Phase 1 only — add per-choice scoring and uncertainty telemetry with **zero** change to any final
answer, routing decision, V12B/V13 execution, or official output. Observational shadow mode behind
an explicit opt-in flag. Phases 2–5 were NOT implemented.

## 4. Current architecture call graph (verified from code)

**BTC default (no-flag):** `predict.py:main` (else branch) → `_build_predictor` →
`QwenMCQPredictor.predict_one` → `LocalQwenBackend.predict_mcq` → `generate_text` (torch, lazy) →
hardened `parse_mcq_label` → `_coerce_label` (caller fallback = first label) → `submission.csv`
(`qid,answer`) + `submission_time.csv` (`qid,answer,time`, per-sample around `predict_one`).

**Legacy selective (`--legacy-dynamic-full`):** `predict.py` → `scripts/tools/final_infer.py
--profile local_selective_auto` → `run_fastmcq_system` (one shared backend via
`get_local_qwen_backend`) → dynamic Base (`formula_bank` → `dynamic_local_qwen` conf 0.6 →
`dynamic_fallback`) → V12B targets `select_v12b_targets(...)[:ceil(N/8)]`, 6 permutations →
V13 targets `select_v13_targets(...)[:ceil(N/8)]` (programmatic/content-first/least-to-most) →
`select_system_overrides` (conservative). Confirmed: one shared backend reused; formula-bank takes
precedence before the local model in Base; Base confidence is a fixed heuristic (0.6 for
`dynamic_local_qwen`, `None` for fallback); `ceil(N/8)` computed in `final_infer._resolve_maxq`;
V12B votes are per-permutation JSONL records aggregated by `summarize_permutation_votes`; V13
candidates are `V13LayerResult`; the selector accepts overrides only under conservative agreement
rules. **Phase 1 touches none of this** — it adds a shadow scorer alongside the default path.

## 5. Scope and non-goals

In scope: a pure scoring-math module, a torch-isolated backend `score_mcq_choices`, a validated
opt-in config, and a `--confidence-telemetry` shadow mode on `predict.py` that writes a diagnostics
JSONL while emitting the byte-identical official CSV. Explicit non-goals (not done): no score-based
answer replacement, no Base/route change, no V12B/V13 invocation or routing change, no selector
change, no formula-bank change, no default-mode change, no `--legacy-dynamic-full` change.

## 6. Files changed

New:
- `src/local_model/choice_scoring.py` — `ChoiceScoreResult` dataclass + pure `compute_choice_scores`.
- `src/local_model/confidence_config.py` — validated `load_choice_scoring_config`.
- `configs/confidence_selective.yaml` — opt-in config (only `choice_scoring` block for Phase 1).
- `tests/unit/test_choice_scoring_2l48b.py` — 20 unit tests.
- `tests/integration/test_confidence_telemetry_2l48c.py` — 5 integration tests.
- `docs/audits/66-phase-1-local-choice-scoring-telemetry.md` — this audit.

Modified (pure additions):
- `src/local_model/local_qwen_backend.py` (+68) — import + `_encode_ids` + `score_mcq_choices`,
  `_scoring_prompt`, `_default_logprob_fn`. Existing functions byte-intact (zero deletions).
- `src/local_model/qwen_mcq_predictor.py` (+5) — `score_choices` passthrough.
- `predict.py` (+67/−1; the −1 is a same-line comment) — `--confidence-telemetry` /
  `--telemetry-path` flags, `_score_telemetry_record`, `_write_telemetry`, guarded loop hook.

## 7. Data structures added

`ChoiceScoreResult` (dataclass): `allowed_labels`, `scores_by_label`, `probabilities_by_label`,
`top1_label`, `top2_label`, `top1_score`, `top2_score`, `logit_margin`, `probability_margin`,
`normalized_entropy`, `scoring_method`, `valid`, `error`, plus `as_dict()` (numeric/categorical
only — no question text, no reasoning). No existing dataclass was modified; `BasePrediction` and
official CSV schemas are untouched (the richer `BasePrediction` fields in the master plan are
deferred to a later phase).

## 8. Algorithms and formulas

Per allowed label, the backend computes a raw score = summed conditional log-probability of the
label's canonical continuation given the prompt. `compute_choice_scores` then (pure math):
- stable log-softmax over ONLY the allowed labels → `probabilities_by_label` (Σp = 1);
- `top1/top2` by score desc, ties broken by allowed-label order (deterministic);
- `logit_margin = top1_score − top2_score`; `probability_margin = P(top1) − P(top2)`;
- `normalized_entropy = −Σ p·ln p / ln(n)` (0.0 for n ≤ 1);
- explicit invalid result (no fabricated label) on missing/NaN/inf scores or zero labels.

## 9. Tokenization handling

`score_mcq_choices` renders the same MCQ prompt used for generation (chat template via
`_render_prompt`, fallback to raw prompt). For each label it encodes `prompt + prefix + label` and
takes the continuation tokens beyond the encoded prompt (`canonical_answer_prefix` default `" "`).
It is **robust to multi-token labels** (sums their teacher-forced log-probs) and to boundary
merges (if the full encoding does not start with the prompt ids, it re-encodes the label alone).
A **single-token fast path** is detected via the invariant "every label encodes to exactly one
continuation token" and is recorded as `scoring_method="single_token"`; otherwise
`"sequence_logprob"`. Equivalence of the two paths is unit-tested on deterministic fakes (identical
`scores_by_label` and ranking). The production forward (`_default_logprob_fn`) imports torch lazily
and is never exercised in CPU tests; all tests inject a fake `logprob_fn`.

## 10. Config fields and defaults

`configs/confidence_selective.yaml` → `choice_scoring`: `enabled` (true), `canonical_answer_prefix`
(`" "`), `normalization` (`"softmax"`, the only supported value), `batch_size` (8, reserved).
`load_choice_scoring_config(source)` accepts a dict, a path, or None (default file if present else
safe defaults), validates types/values with clear errors, and returns a frozen `ChoiceScoringConfig`.
Later-phase blocks (`confidence_router`, `v12b`, `v13`, `selector`) are intentionally omitted until
their phase.

## 11. Runtime path

Opt-in only: `python predict.py --confidence-telemetry [--telemetry-path PATH]`. It runs the normal
single-pass prediction path unchanged, and for each item additionally calls
`predictor.score_choices(item)` (shadow), appending a record to the JSONL (default
`scratch/fastmcq_run/choice_score_telemetry.jsonl`). The official `submission.csv` and
`submission_time.csv` are written exactly as the baseline. The no-flag default never enters this
code (flag defaults False).

## 12. Failure / fallback behavior (fail closed)

- Scoring is wrapped so any error yields an invalid `ChoiceScoreResult` (recorded, never raised).
- `_score_telemetry_record` additionally try/excepts around the call; a raising scorer produces
  `scoring_valid=False` + `scoring_error`, and the submission still completes correctly (tested).
- `_write_telemetry` swallows `OSError` with a warning; it never aborts the run.
- The existing per-item generation fallback (`_coerce_label` → first label) is unchanged, so every
  qid still gets exactly one valid label. Telemetry cannot change or drop any answer.

## 13. Telemetry schema (per JSONL record)

`qid`, `generated_answer`, `scored_top1`, `scored_top2`, `scores_by_label`,
`probabilities_by_label`, `logit_margin`, `probability_margin`, `normalized_entropy`,
`generated_vs_scored_agree`, `scoring_method`, `scoring_valid`, `scoring_error`, `elapsed_sec`.
No question text or reasoning is stored (numeric/categorical diagnostics only). `elapsed_sec` is the
shadow-scoring time, measured separately and **not** added to the official `submission_time.csv`.

## 14. Unit tests

`tests/unit/test_choice_scoring_2l48b.py` (20): 3/4/10-choice ranking; margins; softmax sum;
deterministic ties; uniform entropy = 1.0 and peaked ≈ 0; invalid (missing/NaN/inf/empty);
single-label (no top2, entropy 0); JSON-safe `as_dict` with no question text; backend multi-token
path; single-token path equivalence; backend 10-choice; fail-closed on scorer error; no-choices
invalid; generated-vs-scored agreement; config defaults/file/dict/validation-errors/missing-path.

## 15. Integration tests

`tests/integration/test_confidence_telemetry_2l48c.py` (5): official `submission.csv`
**byte-identical** with vs without `--confidence-telemetry`; JSONL schema + agreement (q1 generated
B vs scored top1 A → disagree; q2 agree) + no question text; telemetry fails closed without breaking
the submission; no JSONL written in the default (flag-off) path.

## 16. Focused-suite result

`pytest tests/integration/test_btc_submission_contract_2l47a.py
tests/integration/test_full_system_output_contract_2l41a.py tests/unit/test_data_io.py
tests/unit/test_labels.py -q` → **38 passed**.

## 17. Full-suite result and baseline comparison

- Baseline: **16 failed, 647 passed**.
- After Phase 1: **16 failed, 672 passed** (passed +25 = the 25 new tests). No test regressed.
- The 16 failures are the identical pre-existing missing-frozen-artifact / public-replay class
  (`best_candidate_manifest.json`, `pred_v10_full_production_user_run.csv`,
  `pred_v11_independent_rerun1.csv` ×3, `pred_v13_multilayer_candidate_api30_from_v12b.csv`, and the
  tests chaining off them). **No new failure category.**
- `python -m compileall -q src scripts tests predict.py` → PASS.
- Existing backend/parser tests (`test_local_qwen_backend`, `test_local_qwen_answer_parser`,
  `test_local_parser_pipeline_2l48a`) → 86 passed (unchanged behavior).

## 18. Performance considerations

Phase 1 scoring is opt-in and off the default hot path. It reuses the one shared loaded backend (no
extra model load). Operation counts in telemetry mode per item: 1 Base generation (unchanged) + up
to `#labels` scoring forwards (generic path) or a single-token fast path when the invariant holds
(recorded for future batching). `_default_logprob_fn` uses `torch.no_grad`. Batching across
labels/questions is reserved (`batch_size`) and not yet enabled; noted as a Phase-5 performance item.
Official timing-file contract is preserved (scoring time excluded from `submission_time.csv`).

## 19. Official-output compatibility

`submission.csv` is byte-identical with and without telemetry (proven by test). `submission_time.csv`
keeps its `qid,answer,time` schema and per-generation timing. No confidence/telemetry field is added
to any official CSV. BTC input/output paths unchanged.

## 20. Confirmation — default mode unchanged

The no-flag BTC default path is unchanged (telemetry defaults off; answer/CSV logic is pure-addition
around it). Default promotion is NOT performed (PROMOTE_DEFAULT = false).

## 21. Confirmation — legacy-dynamic-full unchanged

`--legacy-dynamic-full` and `run_fastmcq_system` are untouched (not in the diff).

## 22. Confirmation — no OpenRouter/API request

No OpenRouter or external API call; no API key read or printed. The scoring forward is local only
(torch, lazy) and never runs in tests.

## 23. Confirmation — no model downloaded

No model weights downloaded; `local_files_only` behavior unchanged; all tests use fakes.

## 24. Confirmation — no Docker build/push

No Docker image built, tagged, or pushed; Dockerfile and `.gitattributes` untouched.

## 25. Confirmation — no Git commit/push

No Git commit or push performed.

## 26. Risks and caveats

- **Real-model behavior unverified.** The torch forward (`_default_logprob_fn`) and the
  single-token fast path were not run on a GPU/real tokenizer; only the pure math and the
  fake-injected paths are tested. Real per-choice score quality, latency, and the actual
  single-token invariant for Qwen3-4B labels remain to be confirmed on GPU (Phase 5 evidence).
- **Boundary-merge caveat.** Continuation extraction assumes prefix-consistent tokenization and
  falls back to encoding the label alone otherwise; exotic tokenizer merges could still shift a
  score. Because Phase 1 is observational, worst case is a mis-recorded diagnostic, never a changed
  answer.
- **Batching not yet enabled** (correctness-first); a performance item for later phases.
- Config currently exposes only the `choice_scoring` block; router/V12B/V13/selector config arrives
  with their phases.

## 27. Current `git status --short`

```
 M predict.py
 M src/local_model/local_qwen_backend.py
 M src/local_model/qwen_mcq_predictor.py
?? configs/confidence_selective.yaml
?? docs/audits/66-phase-1-local-choice-scoring-telemetry.md
?? src/local_model/choice_scoring.py
?? src/local_model/confidence_config.py
?? tests/integration/test_confidence_telemetry_2l48c.py
?? tests/unit/test_choice_scoring_2l48b.py
```

(Also present but from earlier tasks/commits: none untracked besides the above; audits 64/65 are
committed.)

## 28. Recommended next step and STOP

Recommended next step: **independent review of Phase 1**, then commit Phase 1 separately (scoring
module + config + telemetry + tests + this audit). Only after that review and explicit user
approval should Phase 2 (confidence-aware router in shadow mode) be started by re-running the master
prompt with `TARGET_PHASE = 2`.

**STOP.** Phase 1 is complete. Do not begin Phase 2. No later phase was implemented; no commit,
push, Docker build/push, model download, or API call was performed.
