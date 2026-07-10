# AUDIT 69 — Pre-Phase-2 Correction: One-Forward Bare-Label Next-Token Logit Scoring

Audit number 69 (no prior `69-*` existed under `docs/audits/`).

## 1. Date, branch, starting HEAD

- Date: 2026-07-10
- Branch: `main`
- Starting HEAD: `b5953d41f0eaa0aedd502a6a6d74e79919049bde` ("add local choice scoring telemetry")
- Scope: correct the Phase 1 choice-scoring implementation only. **Phase 2 was NOT implemented.**

## 2. Initial working-tree state

Clean at start (`git status --short` empty). AUDIT 66 (Phase 1), AUDIT 67 (independent review), and
the Phase 1 code/tests are committed at `b5953d4`.

## 3. Real-model blocker (summarized from AUDIT 68)

A user-run Windows Docker validation (RTX 4060, torch 2.7.1+cu128, transformers 5.12.1, model baked)
showed the committed scorer was invalid:
- The model's real first answer token is a **bare** label (e.g. token 33 = `"B"`), the same token
  greedy generation emits and the hardened parser reads.
- The committed scorer used `canonical_prefix=" "`, scoring the **space-prefixed** token family
  (`" B"`=425) — a **different token family** from generation. Its confidence/margins therefore
  measured the wrong event and must not drive routing.
- Bare A–J are each exactly one token (ids 32–41; `Qwen2Tokenizer`); contextual extraction was
  prefix-consistent 17/17; 0 boundary fallbacks; no length bias among A–J.
- The old method reported `scoring_method="single_token"` but still ran **one forward per label**
  (≈1.19 s / 1.17 s / 3.10 s for 3/4/10 choices; peak ≈ 6.19 GiB).
- AUDIT 68 verdict: **NOT READY FOR PHASE 2 — SCORING METHOD INVALID.**

(The current Linux environment has no torch/transformers and no baked model, so these GPU numbers
were not reproduced here; see AUDIT 68.)

## 4. Root cause

Two coupled defects in `LocalQwenBackend.score_mcq_choices`:
1. **Wrong token family** — it appended a canonical `" "` and teacher-forced the `" "+label`
   continuation, evaluating tokens the model does not emit as its first answer token.
2. **Wrong forward count** — it looped one teacher-forced forward per candidate label, so
   `scoring_method="single_token"` was a misnomer (N forwards, not one).

## 5. Files changed

- `src/local_model/local_qwen_backend.py` — replaced the old scorer + `_default_logprob_fn` with
  `score_mcq_choices(item, *, logits_fn=None)`, `_default_next_token_logits_fn`,
  `_bare_label_token_id`, `_generation_prefix` (renamed from `_scoring_prompt`, alias kept), and a
  `SCORING_METHOD` constant.
- `src/local_model/choice_scoring.py` — docstrings/semantics updated (raw logits; genuine
  `logit_margin`); default `scoring_method="next_token_logits_one_forward"`.
- `src/local_model/confidence_config.py` — dropped the invalid `canonical_answer_prefix`; added a
  fixed `scoring_method`; old prefix key accepted-but-ignored.
- `configs/confidence_selective.yaml` — removed `canonical_answer_prefix`; documented the corrected
  method.
- `predict.py` — telemetry now loads the confidence config and honors `enabled` (records
  `disabled_by_config` when off).
- `tests/unit/test_choice_scoring_2l48b.py`, `tests/integration/test_confidence_telemetry_2l48c.py`
  — updated to the new API and extended (forward-count, bare-id, fail-closed, config, no-selective).
- New: `docs/audits/68-…md`, `docs/audits/69-…md`.

Untouched (verified, zero deletions): `build_mcq_prompt`, `parse_mcq_label`, `generate_text`,
`predict_mcq`, `load`/`from_pretrained`, the official CSV writers, and the whole legacy/V12B/V13/
selector path.

## 6. Exact old scoring flow

`build_mcq_prompt` → render prefix → for each label: `encode(prefix + " " + label)`, extract
continuation (or fallback to encoding `" "+label` alone), **one teacher-forced forward per label**,
sum continuation log-probs → softmax → margins. Scores were space-prefixed sequence log-probs;
`logit_margin` was a log-prob margin; `scoring_method ∈ {single_token, sequence_logprob}`.

## 7. Exact corrected scoring flow

1. `build_mcq_prompt(item)` → labels (A..).
2. `_generation_prefix(item)` = the exact rendered generation prefix (`_render_prompt`, chat template,
   `add_generation_prompt`).
3. `prompt_ids = _encode_ids(tok, prefix)` — the same tokens generation feeds the model.
4. For each label, derive the **bare** single-token id via
   `tok.encode(label, add_special_tokens=False)`; require exactly one token.
5. Reject duplicate label token ids.
6. `logits_fn(prompt_ids, token_ids)` runs the model **exactly once**, reads the **next-token
   position** (`logits[0, -1]`) — the same position greedy generation samples its first token from —
   and returns the raw logit for each bare label token.
7. `compute_choice_scores` → softmax over only those label logits, top-1/top-2, raw-logit margin,
   probability margin, normalized entropy.
8. Any problem → explicit invalid result (fail closed).

## 8. Exact generation/scoring prompt equivalence

Both generation (`generate_text`) and scoring (`score_mcq_choices`) build the prefix through the
single shared helper `_generation_prefix` = `build_mcq_prompt` + `_render_prompt([user])`, then
tokenize with the same `_encode_ids`/tokenizer call. A unit test asserts the scorer's `prompt_ids`
equal `_encode_ids(tok, _generation_prefix(item))` and that the prefix equals the generation render —
so scoring adds no whitespace and inserts no label before the one-forward logits are read; the
next-token position is identical to where greedy generation picks its first token.

## 9. Bare-label token validation

`_bare_label_token_id` uses `add_special_tokens=False` (no BOS) and requires exactly one token; a
multi-token label → `label_not_single_token:<L>` (fail closed). Duplicate token ids across labels →
`duplicate_label_token_ids`. Token ids are **derived from the active tokenizer**, never hardcoded
(the real ids 32–41 are evidence only, not in code).

## 10. One-forward implementation details

`score_mcq_choices` calls `logits_fn(prompt_ids, token_ids)` **once** with all label token ids;
`_default_next_token_logits_fn` does a single `self._model(ids)` forward under `torch.no_grad`, reads
`logits[0, -1].float()`, and gathers the requested token logits. No per-label loop over the model.

## 11. Forward-count evidence (3, 4, 10 choices)

Deterministic test `test_backend_exactly_one_forward_per_item[3|4|10]` instruments `logits_fn` and
asserts it is called **exactly once** for 3-, 4-, and 10-choice items. The test fails if the
implementation ever regresses to one forward per label.

## 12. New meaning of `scores_by_label`

Raw next-token **logits** of the bare labels (e.g. `{"A": 25.75, "B": 53.5, ...}`), higher = more
likely — the same distribution greedy generation argmaxes over.

## 13. New meaning of `logit_margin`

Genuinely `top1_raw_logit − top2_raw_logit` (e.g. 53.5 − 30.0 = 23.5). No longer a log-prob margin.

## 14. Probability and entropy semantics

`probabilities_by_label` = softmax over **only** the valid-label logits (Σ = 1);
`probability_margin` = `P(top1) − P(top2)`; `normalized_entropy` = `−Σ p·ln p / ln n` over that
valid-label distribution (0.0 for n ≤ 1). Non-finite logits → invalid; NaN/Inf can never enter JSON
(`_round`→None).

## 15. Configuration wiring

`ChoiceScoringConfig` now exposes `enabled`, `normalization` (`softmax`), `batch_size` (reserved),
and a fixed `scoring_method="next_token_logits_one_forward"`; the invalid `canonical_answer_prefix`
was removed (an old config key is accepted but ignored). `predict.py --confidence-telemetry` loads
the config once and **honors `enabled`**: when false, records carry `scoring_error="disabled_by_config"`
and the model is not scored. A malformed config only warns and falls back to defaults (never breaks
the run). No routing thresholds, no qid selection, no follow-up reasoning were added.

## 16. Fail-closed behavior

Explicit invalid result (no answer change, no exception escaping) for: no choices; fewer than two
labels; a label encoding to ≠1 token; duplicate label token ids; model-forward exception; wrong
logit-vector length (`logits_shape_invalid`); NaN/Inf logits; empty prompt; tokenizer/model
unavailable (load error). All exercised by unit tests. No scoring failure drops a qid, emits an
invalid official label, overwrites generation, triggers V12B/V13, or reorders rows.

## 17. Official-output invariance evidence

`test_official_csv_identical_with_and_without_telemetry` asserts `submission.csv` is **byte-identical**
with vs without `--confidence-telemetry`; `test_telemetry_fails_closed_without_breaking_submission`
and `test_config_disabled_skips_scoring` confirm the official CSV stays correct when scoring raises or
is disabled; `submission_time.csv` schema/timing unchanged.

## 18. Confirmation telemetry is still observational

Scoring runs only after the official answer is computed and appended; it writes only to the opt-in
JSONL; the flag defaults off; `test_telemetry_never_invokes_legacy_selective_pipeline` monkeypatches
the legacy runner to raise and confirms it is never called in telemetry mode. Records contain only
qid, generated answer, top1/top2, raw label logits, valid-label probabilities, margins, entropy,
scoring method/validity/error, agreement, and elapsed time — **no question text, prompts, or
reasoning**.

## 19. Tests added/updated

`tests/unit/test_choice_scoring_2l48b.py` (now 26 tests): pure math on raw logits; **bare vs
space-prefixed ids** (proves bare used); **one forward for 3/4/10**; raw-logit top1/top2 + margin;
softmax over valid labels + prob margin + entropy; greedy-argmax agreement; **prompt-prefix ==
generation render**; fail-closed for multi-token / duplicate / non-finite / forward-exception /
invalid-shape / <2-choice / 0-choice; config defaults/file/dict/validation/missing-path/method/
deprecated-prefix-ignored. `tests/integration/test_confidence_telemetry_2l48c.py` (now 9 tests):
byte-identical CSV; JSONL schema + agreement + no question text; fail-closed; no JSONL when off;
**scoring_method recorded**; **config-disabled skips scoring**; **legacy/selective never invoked**.

## 20. Regression-test results

- `compileall src scripts tests predict.py` → PASS.
- Phase 1 tests → **37 passed** (was 25; +12 net).
- Parser/backend group → **86 passed** (unchanged).
- Focused suite → **38 passed** (unchanged).
- Full suite → **16 failed, 684 passed** (was 16 failed / 672 passed; +12 = new Phase 1 tests).

## 21. Full-suite failure comparison

The 16 failing node IDs are **identical** to the pre-change baseline — the missing-frozen-artifact /
public-replay class: `test_btc_short_2l31b` (2), `test_fastmcq_dynamic_system_2l36b` (3),
`test_final_package_2l31a` (6), `test_run_profiles_2l38c` (1), `test_v12b_permutation_2l34b` (2),
`test_v13_dynamic_integration_2l37a` (1), `test_v13_multilayer_2l35a` (1). All open a missing
`output/pred_v1*.csv` or `experiments/best_candidate_manifest.json`. **No new failure introduced.**

## 22. Remaining risks and caveats

- **Not rerun on the real model here** (no torch/transformers/weights in this Linux env). The
  corrected logic must be revalidated on the Windows GPU image before Phase 2.
- **`add_special_tokens=False` assumption**: bare-label ids are derived without special tokens; if a
  tokenizer variant still injects tokens, the label fails closed (invalid), not miscounted — safe.
- **Prompt tokenization vs generation**: scoring uses `tok.encode(prefix)`; `generate_text` uses
  `tok(text)` — both default `add_special_tokens=True` on the same text, so ids match on real Qwen,
  but this equivalence should be reconfirmed on the real tokenizer (a unit test asserts it for the
  fake).
- **Latency**: now one forward per item (vs N), so scoring cost should drop, but real latency/memory
  are unmeasured here.
- Config exposes only Phase-1 knobs; router/V12B/V13/selector config remains out of scope.

## 23. Explicit confirmations

- Phase 2 was NOT implemented; no confidence router; no uncertain-qid selection.
- V12B and V13 behavior was not changed and is not invoked by telemetry.
- Generation prompts were not changed (`build_mcq_prompt` untouched).
- Parser behavior was not changed (`parse_mcq_label` untouched).
- Model settings/ID/path, generation params, dtype/device were not changed.
- Docker files and dependencies were not changed.
- No real model was downloaded; no external API/OpenRouter call; no API key inspected/printed.
- No Git commit or push was performed.

## 24. Current `git status --short`

```
 M configs/confidence_selective.yaml
 M predict.py
 M src/local_model/choice_scoring.py
 M src/local_model/confidence_config.py
 M src/local_model/local_qwen_backend.py
 M tests/integration/test_confidence_telemetry_2l48c.py
 M tests/unit/test_choice_scoring_2l48b.py
?? docs/audits/68-real-gpu-tokenizer-validation-choice-scoring.md
?? docs/audits/69-pre-phase2-next-token-logit-scoring.md
```

## 25. Required Windows real-model revalidation steps

1. Build/run the source-built image (bare-label scorer) on the RTX 4060.
2. Confirm bare A–J are single tokens (ids 32–41) and `scoring_method="next_token_logits_one_forward"`.
3. On the `2+2` item, confirm scorer top-1 == greedy generated first token == bare `B`, and the raw
   `scores_by_label` equal the bare next-token logits (A=25.75, B=53.5, C=28.875, D=30.0 order).
4. Instrument/verify **exactly one** model forward per item for 3/4/10 choices; record latency and
   peak GPU memory.
5. On a permitted labeled synthetic set (≥20 items), collect margin/entropy distributions and
   generated-vs-scored agreement (diagnostic only; no organizer answers).
6. Confirm official `submission.csv` byte-identical with/without telemetry on the real run.

## 26. Readiness verdict

**READY FOR WINDOWS REAL-MODEL REVALIDATION.**

The correction is implemented, fully unit/integration tested with fakes, scope-contained, and
regression-clean (same 16 pre-existing failures). Phase 2 readiness cannot be declared here — it
depends on the real-model revalidation in §25 passing on the Windows GPU image.

STOP — correction and audits complete. Phase 2 not implemented.
