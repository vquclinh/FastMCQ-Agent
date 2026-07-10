# AUDIT 70 — Independent Review of the Pre-Phase-2 Logit-Scoring Correction

Audit number 70 (no prior `70-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD

- Date: 2026-07-10
- Branch: `main`
- HEAD: `b5953d41f0eaa0aedd502a6a6d74e79919049bde` ("add local choice scoring telemetry")
- Read-only independent review. The only file created is this audit. No production code, test, or
  config was modified; the working-tree changes were left exactly as found (not staged/reset).

## 2. Initial working-tree state

`git status --short`: 7 modified (`configs/confidence_selective.yaml`, `predict.py`,
`src/local_model/choice_scoring.py`, `src/local_model/confidence_config.py`,
`src/local_model/local_qwen_backend.py`, `tests/integration/test_confidence_telemetry_2l48c.py`,
`tests/unit/test_choice_scoring_2l48b.py`) + 2 untracked audits (68, 69). `git diff --check` clean;
`git diff --stat` = 289 insertions / 125 deletions across the 7 files. This is exactly the Audit 69
corrective change set; no unrelated changes; nothing staged.

## 3. Scope and independence statement

Independent verification of the uncommitted Audit 69 correction — not a re-read of its prose. I
inspected full diffs, the current source, and swept the whole repo for stale references; verified
the scoring math by inspection + the byte-identical committed math body; ran the full test battery;
and ran independent fresh-run harnesses (official-CSV invariance, config robustness, default-fn
structure). No real model/tokenizer/torch is available in this Linux env (confirmed absent), so
real-GPU behavior was not exercised — that is the Windows revalidation, not this review.

## 4. Files and call sites reviewed

Diffs of all 7 changed files; `qwen_mcq_predictor.py`, `compute_choice_scores` body; repo-wide
`git grep` for `score_mcq_choices`, `logits_fn`, `logprob_fn`, `_default_next_token_logits_fn`,
`_default_logprob_fn`, `_generation_prefix`, `_scoring_prompt`, `canonical_prefix`,
`canonical_answer_prefix`, `SCORING_METHOD`, `scoring_method`, `single_token`, `sequence_logprob`,
`scores_by_label`, `logit_margin`, `load_choice_scoring_config`.

## 5. Summary of Audit 68 blocker

Real Windows-Docker evidence: the model's true first answer token is a **bare** label (id 33=`"B"`);
the committed scorer used `canonical_prefix=" "`, scoring the **space-prefixed** token family
(`" B"`=425) — a different token from the one greedy generation emits — and ran **one forward per
label** despite reporting `scoring_method="single_token"`. Verdict: NOT READY — SCORING METHOD
INVALID.

## 6. Summary of Audit 69 correction claims

Replace with: exact generation prefix → one model forward → raw next-token logits at the first
generated-token position → gathered only for bare single-token labels A–J → top1/top2, raw-logit
margin, probability margin, entropy → observational only. Remove the old teacher-forced/space-prefixed
path; wire the config; rename the method; keep telemetry opt-in and official output byte-identical.

## 7. Root-cause correction verification — **CONFIRMED**

- No production path appends `" "` or scores `" A".." J"`: `score_mcq_choices` gathers logits for
  **bare** label token ids only (`_bare_label_token_id`). ✓
- The old `_default_logprob_fn` (teacher-forced per-label) is **removed**. ✓
- `canonical_prefix` parameter is **removed** from `score_mcq_choices`; **zero** call sites pass it
  (repo-wide grep). ✓
- No production per-label model loop: `score_mcq_choices` calls the logits fn **once** with all label
  token ids. ✓
- Config cannot restore the invalid path: `scoring_method` is **hardcoded** to
  `next_token_logits_one_forward` in `_validate` (not user-selectable); `canonical_answer_prefix` is
  accepted-but-ignored. ✓
- `_scoring_prompt` is a harmless alias of `_generation_prefix` (same prefix render); it is **unused**
  by production (production calls `_generation_prefix`). It cannot reactivate the invalid path. ✓

## 8. Active/stale reference classification

| Reference | Where | Class |
|---|---|---|
| `canonical_prefix` | none | fully removed |
| `canonical_answer_prefix` | yaml comment, config comment, one unit test | documentation/test-only (deprecated, ignored) |
| `logprob_fn` / `_default_logprob_fn` | audits only | documentation-only (removed from code) |
| `scoring_method="single_token"`/`"sequence_logprob"` | none in code (only `label_not_single_token` error string) | fully removed |
| `_scoring_prompt` | alias def only | harmless compatibility alias (unused) |
| `score_mcq_choices` production caller | `qwen_mcq_predictor.score_choices(item)` (no args) | active, compatible with new signature |

No **dangerous stale path** found.

## 9. Generation/scoring context-equivalence review

- **Prefix render:** both generation and scoring build the prefix through the single shared helper
  `_generation_prefix` = `build_mcq_prompt` + `_render_prompt([user])` (chat template,
  `add_generation_prompt=True`). Structurally identical — same code path. ✓
- **Tokenization:** generation uses `self._tokenizer(text, return_tensors="pt")` (`__call__`);
  scoring uses `_encode_ids` = `self._tokenizer.encode(text)`. For a standard HF tokenizer these are
  a documented equivalence (`encode(text)` == `self(text).input_ids`, both default
  `add_special_tokens=True`) on the **same** text, so IDs are identical in production. This is a
  **guaranteed-for-HF** equivalence via two different API calls rather than one shared code path — a
  Low-severity robustness caveat (F2), not a functional defect. Audit 68 corroborates alignment (17/17
  prefix-consistent; greedy first token = bare `B`).
- Scoring adds no whitespace after the prefix and inserts no label before reading logits — it reads
  `logits[0, -1]` directly from the prefix forward. A unit test asserts `prompt_ids ==
  _encode_ids(tok, _generation_prefix(item))` and `prefix == _render_prompt([...])`.

Classification: **equivalent** (prefix render structurally shared; tokenization guaranteed for HF,
recommend a shared tokenization helper for defense-in-depth).

## 10. One-forward review

`score_mcq_choices` calls `fn(prompt_ids, token_ids)` **once** with all label ids; no per-label loop,
no retry, no hidden model call in `_bare_label_token_id` (pure tokenizer `encode`). Inspection of
`_default_next_token_logits_fn`: exactly **one** `self._model(` call, no `for`/`while` around it,
`torch.no_grad()`, gather via list comprehension (pure indexing). Unit tests
`test_backend_exactly_one_forward_per_item[3|4|10]` assert the injected `logits_fn` is called once.

**Test limitation (F1, Low):** the tests count calls to the **injected** `logits_fn`, proving the
orchestration issues one call per item; they do **not** exercise the real
`_default_next_token_logits_fn` (needs torch, absent here). The single real model forward is verified
by **code inspection only** and must be confirmed on Windows. The tests *would* catch: one forward
per label, two forwards per item, and a fallback loop (all change the injected-fn call count). They
would **not** catch a hidden repeated `self._model()` call *inside* the default fn (that path is
untested here); inspection shows there is none.

## 11. Next-token logit extraction review

`logits = self._model(ids).logits` (`[1, seq, vocab]`), `row = logits[0, -1].float()`. `logits[0, -1]`
is the distribution over the token *following* the last prompt token — exactly the position greedy
generation samples its first answer token from (no off-by-one; it does **not** read the last-prompt
token's own logits). `.float()` upcasts for precision. Token logits gathered by
`float(row[int(t)])`. Findings: relies on the model output exposing `.logits` (standard HF
CausalLMOutput; a tuple/dict-only return would raise → caught → fail closed, so safe but not
explicitly handled — Low F3). Token-id bounds are not explicitly checked, but ids come from the
tokenizer's own vocab so they are in range; an out-of-range id would raise IndexError → fail closed
(so Audit 69's "bounds-checked" is technically "implicitly safe via fail-closed" — Low F4). Device:
input tensor placed on `self._model.device`; correct for the single-GPU target; multi-GPU `device_map`
offload relies on HF hooks (Informational). `no_grad` used; a plain forward does not mutate generation
state.

## 12. Bare-label token handling review

Valid labels = `labels_for(len(choices))` (A–C / A–D / A–J by count). Bare ids derived via
`tokenizer.encode(label, add_special_tokens=False)` (dynamic, **not hardcoded**), require exactly one
token else `label_not_single_token:<L>` (fail closed); duplicate ids → `duplicate_label_token_ids`;
labels/logits kept in the same `labels` order for gather and scoring (no drift — a single `labels`
list drives both `token_ids` and `zip(labels, logit_vals)`). `<2` labels and `0` labels fail closed.
The `_Tok` test fake uses **distinct** bare (`ord`) vs space-prefixed (`300+ord`) ids and asserts the
gathered ids are the bare ones — this genuinely proves the bare family is used.

## 13. Score-math review

`compute_choice_scores` body is **byte-identical** to the committed version (only docstrings/method
default changed). Verified (independently and in AUDIT 67): raw scores stored; top1/top2 by score
desc with deterministic index tie-break; `logit_margin = top1 − top2` (raw); label-only stable
log-softmax → probabilities (Σ≈1); `probability_margin = P(top1) − P(top2)`; `normalized_entropy =
−Σ p·ln p / ln n ∈ [0,1]` (0 for n≤1); non-finite/missing/empty → invalid; `_round`→None keeps
NaN/Inf out of JSON. Hand-check: logits A=25.75,B=53.5,C=28.875,D=30.0 → top1 B, top2 D, margin 23.5
(matches test). No stale "sequence log-probability" wording remains in code.

## 14. API/call-site compatibility review

Only production caller is `QwenMCQPredictor.score_choices(item)` → `score_mcq_choices(item)` (no
kwargs) — compatible with the new signature. No script/legacy/V12B/V13/selector/benchmark code
imports `choice_scoring`, `score_mcq_choices`, or the config (grep confirms). No caller expects
`logprob_fn`, `canonical_prefix`, `scoring_method="single_token"`, or sequence-log-prob scores. No
compatibility risk found.

## 15. Configuration-wiring review

`predict.py --confidence-telemetry` loads `load_choice_scoring_config()` once and honors `enabled`
(`disabled_by_config` recorded, scoring skipped, official output intact — tested). Missing config →
safe defaults; **malformed config → warn + defaults, run completes** (independently verified: rc=0,
official CSV correct). `scoring_method` is fixed/non-selectable (cannot be set to an unsupported
method). `canonical_answer_prefix` in an old config is ignored (cannot restore invalid behavior).
`normalization` validated to `softmax`; `batch_size` validated ≥1 and documented reserved/unused. No
routing threshold, no qid selection. Config path is the repo-relative default
`configs/confidence_selective.yaml` (working-directory dependent, as before — Informational). Caveat
(F5, Low): if config load raises, `score_enabled` stays `True` (telemetry scores with defaults) — a
visible WARN is printed, so it is not silent; this is fail-open for *telemetry only* and never affects
official output.

## 16. Telemetry observational-invariance review

Independently verified on a fresh run: official `submission.csv` **byte-identical** with vs without
`--confidence-telemetry`; records carry `scoring_method="next_token_logits_one_forward"`; **no
question text/choices**; all JSON-safe (no NaN/Inf). Scoring runs only after the official answer is
appended; the flag defaults off; `test_telemetry_never_invokes_legacy_selective_pipeline` monkeypatches
the legacy runner to raise and confirms it is never called; scoring/telemetry-write failures only warn
and never drop a qid, reorder rows, or emit an invalid label (tested).

## 17. Fail-closed review

Explicit invalid result (answer preserved, no exception escaping the telemetry path) verified for: no
choices; <2 labels; empty prompt; label ≠ 1 token; duplicate label ids; forward exception; wrong
logit-vector length; NaN/Inf logits; disabled config; telemetry-write error. **Context-overflow is
NOT explicitly checked** — the code relies on the model forward raising, caught by the outer
`try/except` → fail closed (Audit 69 §22 discloses this). Safe (no wrong answer) but implicit
(F3/F6, Low). Tokenizer/model-unavailable → `load()` raises → caught → invalid (fail closed).

## 18. Test-quality review

Tests are behavior-oriented, not implementation-encoding: the distinct bare/space-prefixed fake
tokenizer genuinely proves the bare family is used; forward-count tests would catch per-label or
double forwards; the prompt-equivalence test pins `prompt_ids == encode(generation prefix)`; official
invariance, config-disabled, and no-legacy tests are strong. Gaps (non-blocking): (a) the real
`_default_next_token_logits_fn` single-model-call and `logits[0,-1]` position are untested here
(need torch — Windows); (b) no test asserts generation's `tokenizer(text)` and scoring's
`encode(text)` produce identical ids on the **real** tokenizer (fake tokenizer makes them identical
by construction). Both are Windows checks. Recommend (do not add): a real-tokenizer id-equivalence
assertion and a fake-model forward-count assertion for the default fn.

## 19. Regression-test results

- `compileall src scripts tests predict.py` → PASS.
- Phase 1 tests → **37 passed** (matches Audit 69).
- Parser/backend group → **86 passed**.
- Focused suite → **38 passed**.
- Full suite → **16 failed, 684 passed**.

## 20. Full-suite failure-identity comparison

The 16 failing node IDs are **identical** to the pre-change baseline (frozen-artifact / public-replay
class): `test_btc_short_2l31b` (2), `test_fastmcq_dynamic_system_2l36b` (3), `test_final_package_2l31a`
(6), `test_run_profiles_2l38c` (1), `test_v12b_permutation_2l34b` (2), `test_v13_dynamic_integration_2l37a`
(1), `test_v13_multilayer_2l35a` (1). All open a missing `output/pred_v1*.csv` or
`experiments/best_candidate_manifest.json`. **No new failure introduced by the correction.**

## 21. Scope/diff review

Diff is confined to the scoring/config/telemetry files + their tests + the two audits. No change to
Dockerfile, `.gitattributes`, CUDA/torch/transformers versions, model ID/path, `build_mcq_prompt`,
`parse_mcq_label`, `generate_text`, `predict_mcq`, `load`, official CSV writers, or the
legacy/V12B/V13/selector path (all verified byte-intact / absent from the diff). No Phase 2, no
routing thresholds, no qid selection.

## 22. Findings (ordered by severity)

No **Critical** or **High** findings.

| ID | Sev | File/function | Evidence | Impact | Blocks commit? | Blocks Windows reval? | Recommended correction |
|---|---|---|---|---|---|---|---|
| F1 | Low | tests / `_default_next_token_logits_fn` | tests count injected `logits_fn` calls, not real model calls | one-model-forward guarantee for the real fn is inspection-only in Linux | No | No (it *is* a Windows check) | Add a fake-model forward-count test; confirm on Windows |
| F2 | Low | `local_qwen_backend.generate_text` vs `_encode_ids` | generation uses `tokenizer(text)`, scoring uses `tokenizer.encode(text)` | guaranteed-identical for HF but via two API calls, not a shared path | No | No | Share one tokenization helper; assert id-equality on the real tokenizer |
| F3 | Low | `_default_next_token_logits_fn` | assumes `.logits`; context-overflow relies on model raising | non-standard output or over-long prompt → exception → fail closed (safe, implicit) | No | No | Optional explicit prompt-length guard + output-shape check before Phase 2 |
| F4 | Low | `_default_next_token_logits_fn` | `row[int(t)]` not explicitly bounds-checked | out-of-range id → IndexError → fail closed (ids are tokenizer-valid) | No | No | Optional explicit bounds check; soften Audit 69's "bounds-checked" wording |
| F5 | Low | `predict.py main` | config-load exception → `score_enabled=True` (scores w/ defaults) + WARN | telemetry fail-open on malformed config (official output unaffected; warned) | No | No | Optionally default to disabled on load failure |
| F6 | Info | `score_mcq_choices` | no explicit max-context check | long prompts fail closed via model error | No | No | Explicit length check if long items are common in Phase 2 |
| F7 | Info | `_scoring_prompt` alias | unused compatibility alias | dead code | No | No | Remove alias in a later cleanup |

## 23. Required corrections before commit

**None.** The correction is functionally sound, scope-contained, and regression-clean.

## 24. Required corrections before Windows validation

**None required.** Recommended (non-blocking): F1 (fake-model forward-count test) and F2 (shared
tokenization helper) would strengthen guarantees but are not prerequisites.

## 25. Remaining Windows-only checks

Confirm on the real GPU image: bare A–J single-token ids (32–41) and `scoring_method=
next_token_logits_one_forward`; scorer top-1 == greedy first token == bare `B` on the `2+2` item, with
`scores_by_label` == the bare next-token logits; **exactly one** model forward per item for 3/4/10
choices (instrumented); generation `tokenizer(text)` ids == scoring `encode(text)` ids; margin/entropy
distributions and agreement on a permitted labeled synthetic set; official `submission.csv`
byte-identical with/without telemetry on the real run; latency and peak GPU memory.

## 26. Confirmation

No production code, test, config, prompt, parser, model, Docker, dependency, routing, V12B, V13,
selector, commit, or push change was performed in this review. No model was downloaded; no external
API/OpenRouter call; no API key inspected/printed. Temporary review scripts ran in the scratchpad and
were deleted.

## 27. Current `git status --short`

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
?? docs/audits/70-independent-review-pre-phase2-logit-scoring.md
```

## 28. Final verdict

**SAFE TO COMMIT WITH NON-BLOCKING CAVEATS; READY FOR WINDOWS REAL-MODEL REVALIDATION.**

The invalid space-prefixed / per-label teacher-forced scoring is fully removed; the corrected scorer
reads raw next-token logits at the correct position for dynamically-derived, validated bare labels in
one forward per item; the math is unchanged and correct; the config is wired safely; telemetry stays
observational with byte-identical official output; fail-closed holds for all tested modes. The
caveats (F1–F7) are Low/Informational and are Windows-revalidation or defense-in-depth items, none
blocking commit. **Phase 2 is NOT declared ready** — that decision awaits the Windows real-model
revalidation in §25.

STOP — independent review complete. No fixes applied; nothing committed or pushed; Phase 2 not
implemented.
