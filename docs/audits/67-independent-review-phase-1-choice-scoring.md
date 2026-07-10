# AUDIT 67 — Independent Adversarial Review of Phase 1 (Local Per-Choice Scoring & Telemetry)

Audit number 67 (no prior `67-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD

- Date: 2026-07-10
- Branch: `main`
- HEAD: `90ea59dec3c2c20c18657233ef3b0401c0af12e5` ("document historical OpenRouter 79.7 pipeline")
- Read-only verification. The only file created is this audit. No production code, test, or config
  was modified; the Phase 1 working-tree changes were left exactly as found (not staged/reset).

## 2. Initial working-tree state

`git status --short`: 3 modified (`predict.py`, `src/local_model/local_qwen_backend.py`,
`src/local_model/qwen_mcq_predictor.py`) + 6 untracked (`configs/confidence_selective.yaml`,
`src/local_model/choice_scoring.py`, `src/local_model/confidence_config.py`,
`tests/unit/test_choice_scoring_2l48b.py`, `tests/integration/test_confidence_telemetry_2l48c.py`,
`docs/audits/66-…md`). `git diff --check` clean; `git diff --summary` empty (no mode/type changes);
nothing staged. This matches Phase 1 + AUDIT 66 exactly; no unrelated changes.

## 3. Files reviewed

All nine Phase 1 files in full, plus `src/utils/labels.py`, `src/utils/data_io.py`, and the
committed baseline (`git show HEAD:predict.py`, etc.) for diff comparison.

## 4. Independent methodology

Full-source re-read (not audit prose); pure re-derivation of the scoring math; a hand-worked
teacher-forcing index example; adversarial fake-tokenizer simulations (10 boundary cases);
forward-count instrumentation; an independent fresh-run official-CSV byte-equivalence + telemetry
lifecycle harness; config edge-case probing; and the full test battery. Temporary scripts ran under
the session scratchpad and were deleted.

## 5. Current call graphs (verified from code)

- **No-flag default:** `predict.py:main` (else) → `_build_predictor` → `QwenMCQPredictor.predict_one`
  → `LocalQwenBackend.predict_mcq` → `generate_text` → `parse_mcq_label` → `_coerce_label` →
  `submission.csv` + `submission_time.csv`. Unchanged by Phase 1.
- **Confidence telemetry:** same single-pass path; after `ans` is computed and appended, a shadow
  `predictor.score_choices(item)` record is collected and written to a JSONL at the end. Official
  output identical.
- **Legacy selective:** `--legacy-dynamic-full` → `final_infer --profile local_selective_auto`.
  Unchanged and, notably, telemetry does NOT run in this branch (see I1).

## 6. Scope verification

| File | Purpose | Functional change | Runtime impact | Scope |
|---|---|---|---|---|
| `choice_scoring.py` (new) | `ChoiceScoreResult` + pure `compute_choice_scores` | additive | none unless called | in-scope |
| `local_qwen_backend.py` (+68) | `score_mcq_choices`, `_scoring_prompt`, `_default_logprob_fn`, `_encode_ids` | pure additions; zero deletions | none unless called | in-scope |
| `qwen_mcq_predictor.py` (+5) | `score_choices` passthrough | additive | none unless called | in-scope |
| `confidence_config.py` (new) | validated loader | additive | **not wired to runtime** (M2) | in-scope |
| `configs/confidence_selective.yaml` (new) | opt-in config | additive | inert in Phase 1 (M2) | in-scope |
| `predict.py` (+67/−1) | `--confidence-telemetry`/`--telemetry-path`, telemetry helpers, guarded loop hook | additive; −1 is a same-line comment on `dt` | telemetry only when flag set | in-scope |
| test files ×2 (new) | 25 tests | additive | test-only | in-scope |
| `docs/audits/66-…md` | audit | doc | none | in-scope |

Diff grep for `Base|V12B|V13|selector|router|formula|prompt|model|Dockerfile|CUDA|torch|transformers|
private_test|submission|legacy-dynamic-full|LOCAL_MODEL_PATH|max_new_tokens|temperature|
generation_config` found only comment lines and the two `parse_json_object`-adjacent reuse lines —
no functional change to any of those areas. `build_mcq_prompt`, `parse_mcq_label`, `generate_text`,
`predict_mcq`, and the whole legacy path are byte-intact. **Phase 1 is truly observational**:
generated answer, parser output, caller fallback, Base output, V12B/V13 targets, selector decisions,
official CSV contents, no-flag default, and `--legacy-dynamic-full` are all unchanged (proven in §18).

## 7. Scoring-math review

`compute_choice_scores` verified correct: per-label raw score = summed conditional log-prob; stable
`_log_softmax` (subtracts max); Σ probabilities ≈ 1 (tested 1e-9); top-1/top-2 by score desc with
ties broken by allowed-label index (deterministic); `logit_margin = top1_score − top2_score`;
`probability_margin = P(top1) − P(top2)`; `normalized_entropy = −Σ p·ln p / ln n` (guards p>0; 0.0
for n ≤ 1); missing/NaN/±inf/empty → explicit invalid result (no fabricated label); `_round` maps
non-finite → None so NaN/Inf can never enter the JSON. Uniform-4 entropy = 1.0, peaked ≈ 0 confirmed.
**Correct.** Terminology caveat: `logit_margin` is a *summed sequence log-probability* margin, not a
raw-logit margin (see L5).

## 8. Teacher-forcing / index-shift review

`_default_logprob_fn` uses `torch.no_grad`; `logits[0].float()` before `log_softmax(dim=-1)` (vocab
dim); tensor on `self._model.device`; `full = prompt_ids + cont_ids`; cont token k scored at
`pos = len(prompt_ids) − 1 + k`. Hand-worked example (prompt len 2, 2-token cont) confirms this reads
`P(cont_k | prompt + cont_0..k−1)` and never scores prompt tokens; multi-token labels sum their
per-token log-probs. Single unpadded sequence (batch=1) → no padding/attention-mask hazard. Failures
propagate to the caller's `try/except` → invalid result. **Indexing correct.** Not run on real torch
(absent). Caveats: no max-length/truncation handling — over-long prompts fail closed rather than
truncate (L4, safe); no explicit EOS append (fine).

## 9. Prompt-context equivalence

`_scoring_prompt` = `build_mcq_prompt` → `_render_prompt([user])` — **identical** to the generation
context (`generate_text` renders the same messages with the same `add_generation_prompt`). Simulation
confirmed `scoring_prefix == generation_render` byte-for-byte. So labels are scored at the exact
answer position/context used for generation. **Classification: equivalent, with one caveat** — the
canonical continuation is assumed to be `" " + label`; the model's true first answer token (space vs
letter, special boundary) is unverified on the real tokenizer (L3). Because the same prefix is used
for every label, relative ranking/margins remain meaningful even if the absolute continuation differs
slightly.

## 10. Token-boundary analysis (10 adversarial tokenizers)

`cont = full[len(prompt):]` when the full encoding starts with the prompt ids and is longer; else a
fallback encodes the label (with prefix) alone. Simulated: (1) single-token `[65]`; (2) multi-token
`[32,65]`; (3) space+label merged into one id → handled as single-token; (4) prompt-final merge that
breaks prefix consistency → **fallback path taken**, valid, but the isolated `" A"` encoding is
appended to the unchanged prompt ids — an **approximation** of the true in-context continuation, not
a faithful conditional (L1); (5) auto-BOS shared in the prefix, not double-counted in cont;
(9) unequal A–J token lengths (J=2) accepted → sequence-length bias (L2). Verdict: boundary handling
is a **safe observational approximation** (never crashes, never fabricates a label), but the
merge-fallback and unequal-length cases can yield misleading margins and should be validated/hardened
before Phase 2 routing.

## 11. Single-token fast-path analysis

`single_token = all(len(cont)==1 …)` sets `scoring_method`, but scoring still calls
`fn(prompt_ids, cont)` **once per label**. Forward-count instrumentation:

| case | labels | tokenizer form | forward passes | method |
|---|---|---|---|---|
| 3-choice | A–C | single-token | **3** | single_token |
| 4-choice | A–D | single-token | **4** | single_token |
| 10-choice | A–J | single-token | **10** | single_token |
| 4-choice | A–D | space+label (2 tok) | 4 | sequence_logprob |

So `scoring_method="single_token"` is a **descriptive label only — it does NOT reduce model forwards**
(no single-forward batched read of A–J logits). Rankings are correct in both paths (equivalence
unit-tested). This is a **performance/naming discrepancy** (M1), not a correctness defect.

## 12. Sequence-length bias analysis

Summed log-prob scoring penalizes labels that tokenize into more tokens. For canonical single
uppercase A–J preceded by a space, most tokenizers emit one token each (no bias), but this is
**unverified on the real Qwen tokenizer** (absent). If any label is multi-token (sim case 9), its
score sums ≥2 non-positive log-probs and is systematically lower. Alternatives: mean-token log-prob,
length-normalized score, or true contextual single-token label scoring. **Acceptable for Phase 1
observation; a Phase 2 routing risk** (L2) — margins could be biased for multi-token labels.

## 13. Config review

`yaml.safe_load` (safe); frozen dataclass; safe defaults when file/key absent; `normalization` must
be `"softmax"`; `batch_size` must be int ≥ 1; explicit missing-path `FileNotFoundError`; non-mapping
top level → `ValueError`. Findings: (M2) **the config is not wired into the runtime** —
`score_mcq_choices` hardcodes `canonical_prefix=" "` and nothing reads `enabled`/
`canonical_answer_prefix`/`batch_size`; the yaml knobs are inert (defaults happen to match). (L6) a
malformed `choice_scoring` block that is a *list* raises a raw `AttributeError` rather than a clear
message. (I2) unknown fields are silently ignored. (I4) `batch_size` is validated but unused
(documented "reserved"). No unsafe loader, no scattered duplicate constants.

## 14. Telemetry lifecycle review

JSONL opened with `"w"` → **truncated each run** (verified: rerun with 1 sample → 1 record, no stale
mixing); records written once after the full loop (a mid-run crash leaves no partial file); parent
dir created safely; **one record per qid, in input order**; duplicate qids → one record each
(consistent); all values JSON-valid, **no NaN/Infinity** (`_round`→None); **no question text/choices/
reasoning** stored; write failure caught (`OSError`) and only warns — cannot affect official output.
Absent fields: no `run_id`/timestamp/model-id/config fingerprint (L7) — makes cross-run threshold
calibration ambiguous for Phase 2. `--telemetry-path` is unvalidated → could overwrite an arbitrary
file (L8, dev flag).

## 15. Timing / performance review

Scoring elapsed is measured separately and **excluded** from `submission_time.csv` (schema/values
verified unchanged); it is recorded per-record as `elapsed_sec`. One shared predictor/backend is
reused for both `predict_one` and `score_choices` — **no duplicate model load**. `torch.no_grad`,
no retained graph, batch=1 forwards. **Real end-to-end runtime nevertheless increases** in telemetry
mode by ≈ (#labels) extra forward passes per item (3–10×), since there is no batched single-token
path (M1). No real-GPU measurement exists — no speed claim can be made yet.

## 16. Optional real-tokenizer/model smoke result

`import torch` fails (torch not installed) and `/models/qwen3-4b-instruct-2507` is **absent**;
`LOCAL_MODEL_PATH` unset. No download attempted. Therefore the real tokenizer's A–J token behavior,
the single-token invariant, the canonical-prefix assumption, `_default_logprob_fn` on real logits,
latency, and memory are **all unverified**. This is an environment limitation, not a source defect.

## 17. Adversarial simulations (summary)

Equal scores → margin 0, deterministic top1 by order; extreme/large gaps → entropy≈0; NaN/±inf/
missing → invalid; 3/4/10 labels OK; multi-token & unequal lengths OK (bias noted); duplicate/lower/
unsupported labels handled by `compute_choice_scores` normalization/validation; scorer exception →
invalid (fail closed); telemetry-write exception → warn only; malformed/Unicode error text → JSON-safe;
one-choice → valid, no top2, entropy 0. No crash or fabricated label in any case.

## 18. Official-output-equivalence proof

Independent fresh run (fake predictor, 3 samples incl. a duplicate-shaped case): `submission.csv`
**byte-identical** with vs without `--confidence-telemetry` (`qid,answer\nq1,B\nq2,A\nq3,A\n`);
`submission_time.csv` keeps `qid,answer,time` with one row per qid; parser-failure and
scoring-failure paths both leave the official CSV correct; telemetry-write failure only warns.
**Phase 1 core invariant holds.**

## 19. Test results

- `compileall src scripts tests predict.py` → PASS.
- Phase 1 tests → **25 passed**.
- Parser/backend group (`test_local_qwen_backend`, `test_local_qwen_answer_parser`,
  `test_local_parser_pipeline_2l48a`) → **86 passed**.
- Focused suite → **38 passed**.
- Full suite → **16 failed, 672 passed**. The 16 are the identical pre-existing missing-frozen-artifact
  class (`best_candidate_manifest.json`, `pred_v10…`, `pred_v11…`×3, `pred_v13…`). No new failure
  category; none related to Phase 1.

## 20. AUDIT 66 discrepancy table

| Claim | Actual evidence | Status | Severity |
|---|---|---|---|
| Exact files changed | matches `git status` | Accurate | — |
| +25 tests (647→672) | full suite 672 passed | Accurate | — |
| Default path unchanged | byte-identical CSV; diff pure-additions | Accurate | — |
| Legacy path unchanged | not in diff | Accurate | — |
| Official CSV byte equality | independently reproduced | Accurate | — |
| No question text in telemetry | verified | Accurate | — |
| No duplicate model loading | one shared backend | Accurate | — |
| Multi-token handling | verified | Accurate | — |
| "single-token fast path when invariant holds" (§9/§18) | still N forwards; label only | **Partially accurate** | Medium (M1) |
| Operation counts "or a single-token fast path" (§18) | N forwards in both paths | **Partially accurate** | Medium (M1) |
| Config behavior (§10) | loader correct, but not wired to runtime; §10 omits this | **Partially accurate** (omission) | Medium (M2) |
| Telemetry failure behavior | fail-closed verified | Accurate | — |
| Full-suite result 16/672 | verified | Accurate | — |
| Git status | matches | Accurate | — |

## 21. Findings by severity

**Critical / High:** none.

**Medium**
- **M1 — `single_token` is not a real fast path.** `local_qwen_backend.py:356–360`. It only sets the
  method string; scoring still runs one forward per label (3/4/10 forwards). Consequence: no speed
  gain; AUDIT 66's "fast path"/operation-count wording overstates. Repro: forward-count instrumentation
  (§11). Blocks commit? No. Blocks Phase 2? No. Correction: either implement a true batched
  last-position read for the single-token case, or rename to a neutral descriptor and drop the
  "fast path" wording; required for the Phase 5 runtime budget.
- **M2 — Confidence config is not wired into the runtime.** `confidence_config.py` +
  `configs/confidence_selective.yaml` are loaded/validated/tested but never read by
  `score_mcq_choices` or `predict.py`; `enabled`/`canonical_answer_prefix`/`batch_size` are inert.
  Consequence: documented knobs have no effect (safe now because defaults match). Blocks commit? No.
  Blocks Phase 2? No, but **wiring the config is a Phase 2 prerequisite** (thresholds must be
  config-driven).

**Low**
- **L1 — Boundary-merge fallback is an approximation.** `local_qwen_backend.py:349–352`. When the
  prompt+label encoding doesn't share the prompt prefix, the label is encoded in isolation and
  appended — not the true in-context continuation. Safe/observational now; can bias margins in
  Phase 2. Repro: fake-tokenizer case 4 (§10).
- **L2 — Sequence-length bias for multi-token labels.** Summed log-prob penalizes longer labels.
  Unverified whether real Qwen keeps A–J single-token. Safe for Phase 1; **Phase 2 routing risk**.
  Consider mean-token log-prob or contextual single-token scoring.
- **L3 — `canonical_prefix=" "` assumption unvalidated** against the real tokenizer's first answer
  token. Consistent across labels (ranking robust) but should be confirmed before Phase 2.
- **L4 — No max-length/truncation handling.** Over-long prompts fail closed (invalid scoring) rather
  than truncate. Safe (no wrong answer), but scoring is unavailable for very long items.
- **L5 — `logit_margin` misnomer.** The stored scores are summed sequence log-probs, so the field is
  a log-probability / sequence-score margin. Rename to `logprob_margin` (or document) before Phase 2
  threshold docs. Not renamed in this review per instructions.
- **L6 — Unclear error on malformed `choice_scoring` block.** A non-dict block raises raw
  `AttributeError` instead of a clear message. `confidence_config.py:_validate`.
- **L7 — No run/model/config fingerprint in telemetry records.** Cross-run threshold calibration for
  Phase 2 can't disambiguate model/config; recommend adding `run_id`/model path/config hash.
- **L8 — `--telemetry-path` unvalidated** → could overwrite an arbitrary file (dev flag; user
  responsibility).

**Informational**
- **I1 — `--confidence-telemetry` is silently ignored with `--legacy-dynamic-full`** (telemetry lives
  only in the single-pass branch). Benign; document the interaction.
- **I2 — Unknown config fields silently ignored.**
- **I3 — torch/model/GPU absent** → no real smoke test possible (not a defect).
- **I4 — `batch_size` validated but unused** (documented "reserved").

## 22. Phase 1 commit verdict

**SAFE TO COMMIT WITH CAVEATS.** The observational invariant is proven (byte-identical official CSV;
fail-closed; no default/legacy/Base/V12B/V13/selector change; math and teacher-forcing indexing
correct; no NaN/Inf; no private text). The caveats (M1 naming/perf, M2 unwired config, L1–L8) are
documentation/robustness items, none of which change any answer or output. Recommend committing Phase
1 as-is (optionally addressing M1/L5 wording and M2 wiring in the Phase-2 change) with this review
attached.

## 23. Phase 2 readiness verdict

**NOT READY FOR PHASE 2 — REAL MODEL VALIDATION REQUIRED.** No source defect independently blocks
progress, but the scoring *signal's* soundness is unverified on the real Qwen3-4B tokenizer/model:
the single-token invariant (L2/L3), the canonical-prefix assumption (L3), boundary merges (L1), and
real margin/entropy distributions must be measured on GPU before any routing threshold depends on
them. Additionally, before Phase 2 routing: wire the config (M2), decide summed-vs-mean scoring
(L2), and clarify the `logit_margin`/`single_token` naming (L5/M1).

## 24. Exact remaining validation required before Phase 2

1. Real-GPU/tokenizer run: token IDs/counts for `A`/` A`/…/`J`/` J`; confirm (or refute) the
   single-token invariant and the model's true first answer token → fix `canonical_prefix` / scoring
   accordingly.
2. On a permitted labeled validation set: distributions of `logit_margin`/`probability_margin`/
   `normalized_entropy`, and `generated_vs_scored_agree` rate; check summed-scoring length bias in
   practice.
3. Wire `ChoiceScoringConfig` into `score_mcq_choices`/telemetry (M2); add telemetry run/model/config
   fingerprint (L7).
4. Decide/rename margin terminology (L5) and either implement or rename the single-token path (M1).

## 25. Confirmations

- No production code was modified.
- No existing test was modified.
- No config was modified.
- No later phase (2–5) was implemented.
- No external API/OpenRouter call was made.
- No API key was inspected or printed.
- No model was downloaded.
- No Docker image was built or pushed.
- No Git commit or push occurred; the Phase 1 working-tree changes were not staged, reset, or
  restored. Temporary review scripts ran in the scratchpad and were deleted.

## 26. Current `git status --short`

```
 M predict.py
 M src/local_model/local_qwen_backend.py
 M src/local_model/qwen_mcq_predictor.py
?? configs/confidence_selective.yaml
?? docs/audits/66-phase-1-local-choice-scoring-telemetry.md
?? docs/audits/67-independent-review-phase-1-choice-scoring.md
?? src/local_model/choice_scoring.py
?? src/local_model/confidence_config.py
?? tests/integration/test_confidence_telemetry_2l48c.py
?? tests/unit/test_choice_scoring_2l48b.py
```

## 27. Recommended next step

Commit Phase 1 (with this review) as an observational baseline, then run the **real-GPU/tokenizer
validation** in §24 before starting Phase 2. Address M2 (config wiring) and the M1/L5 naming as part
of the Phase 2 change, not as an emergency fix to Phase 1.

STOP — independent review complete. No fix applied; Phase 2 not started.
