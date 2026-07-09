# AUDIT 65 — Harden the Local MCQ Answer-Label Parser

Audit number 65 (no prior `65-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD before changes

- Date: 2026-07-10
- Branch: `main`
- HEAD before changes: `92dc9635a91e7f6d9936b62a906b3943026f7178` (`Merge pull request #2 from vquclinh/selective-migration`)
- Scope: parser-hardening only. No routing, Base/V12B/V13 architecture, formula-bank, selector,
  prompt, model, Docker, dependency, I/O-contract, or runtime-mode change.

## 2. Initial working-tree state

At task start the local `main` branch was stale at `87d5d71` (pre-migration), where the target file
`src/local_model/local_qwen_backend.py` **did not exist**. The selective-migration work was already
merged into `origin/main` (`92dc963`, PR #2), so local `main` was fast-forwarded to its
already-merged remote head (`git merge --ff-only origin/main` — no new commit, no push, stayed on
`main`) to obtain the merged tree. After that the working tree was clean except one untracked file
from the previous task, `docs/audits/64-forensic-reconstruction-openrouter-79-7-vs-local-legacy.md`.

## 3. Confirmed parser defect

`src/local_model/local_qwen_backend.py` `parse_mcq_label` (pre-change) uppercased the whole
generated text and returned the first `A–K` character that was also an allowed label:

```python
for m in re.finditer(r"[A-K]", text.upper()):
    if m.group(0) in allowed:
        return m.group(0)
```

Reproduced failures (before the fix):
- `"The answer is clearly option B."` → **A** (the "a" in "answer" precedes "B").
- `"Grace Hopper"` → **A** (4-choice) / **G** (10-choice).
- Any prose containing A/B/C/D letters could be mined into a fabricated label.

## 4. Exact affected call paths

Call-site map (from `git grep`):

- `parse_mcq_label` is called only by `LocalQwenBackend.predict_mcq`
  (`local_qwen_backend.py`), which powers:
  1. **BTC default single-pass** — `predict.py` → `QwenMCQPredictor.predict_one`
     (`src/local_model/qwen_mcq_predictor.py`) → `backend.predict_mcq` → `parse_mcq_label`.
  2. **Dynamic Base** — `src/base/dynamic_base_predictor.py` `_local_answer` → `backend.predict_mcq`
     → `parse_mcq_label`.
- `parse_label` in `qwen_mcq_predictor.py` is a re-export alias of `parse_mcq_label`.
- **V12B / V13 do NOT use `parse_mcq_label`.** They call `parse_json_object` and extract specific
  structured fields (`selected_label`, `answer_content`, `final_survivor_label`) in
  `src/layers/v12b_dynamic_layer.py` / `v13_dynamic_layer.py`. They were not affected by the defect
  and are not changed here.
- No other unsafe first-letter scanner exists (`calculation_solver.py` `finditer` calls are numeric,
  unrelated).

Conclusion: **fixing the single function `parse_mcq_label` is sufficient**; `parse_json_object` is
left byte-identical because V12B/V13 depend on it.

## 5. Old parsing behavior

First allowed `A–K` letter anywhere in the uppercased text → label; else `None`. Position-based,
prose-blind, no structure awareness.

## 6. New parser precedence

`parse_mcq_label(text, labels) -> str | None`, deterministic and conservative. It never scans prose
for the first letter and never returns a silent `A`. Precedence:

1. **Structured JSON** answer field.
2. **Exact bare label** (whole output is one label, optionally wrapped).
3. **Explicit answer marker** + label (Vietnamese/English; last marker wins).
4. **Single isolated final label**, only when unambiguous.

Otherwise `None` (caller applies its own deterministic fallback).

## 7. Structured JSON handling

`_json_label` reuses the existing shared `parse_json_object` (no second JSON parser created). It
reads an `answer` / `label` / `choice` field (case-insensitive keys, priority order), and resolves
the value via `_bare_label` then `_marker_label` so only an explicit label survives. A whole-output
JSON object (`text` starting with `{` or a ```` ``` ```` fence) that yields no safe answer field
returns `None` rather than being prose-scanned.

- `{"answer":"B"}`→B, `{"ANSWER":"c"}`→C, `{"choice":"D"}`→D, `{"label":"Option D"}`→D,
  fenced `{"answer":"A"}`→A.
- `{"answer":"Grace Hopper"}`, `{"answer":"A or B"}`, `{"answer":"Z"}`, `{"reason":…}` → no match.

## 8. Bare-label handling

`_BARE_LABEL_RE = ^\s*[\(\[]?\s*([A-Za-z])\s*[\)\]\.:,]?\s*$` — the whole output is a single label
optionally wrapped in `()`/`[]` and/or trailed by `. : ,`. Brace wrapping is excluded so `{…}` is
treated as JSON. `A`, `b`, `C.`, `(D)`, `[B]`, `  b  ` resolve; `Banana`, `ABC` do not.

## 9. Explicit-marker handling

`_MARKER_LABEL_RE` matches a marker phrase, then a **required** separator `[\s:.\-]+` (+ optional
open bracket), then a single label with a right word-boundary `(?![A-Za-z])`. The required separator
prevents `optionB` and `answer cannot…` from matching; the boundary prevents matching a letter
inside a word. Markers (longest-first): `the answer is [clearly] [option]`, `final answer`,
`đáp án [đúng] [là]`, `lựa chọn [đúng] [là]`, `tôi chọn`, `chọn đáp án`, `chọn`, `answer`, `choice`,
`option`. All matches are collected; the **last** valid one wins (a final answer overrides earlier
mentions). A `"… B or C"` / `"… B/C"` continuation immediately after the label is rejected as
ambiguous (`_OR_AFTER_RE`).

- `The answer is clearly option B.`→B, `Đáp án đúng là C.`→C, `Final answer: (D)`→D, `Option C`→C,
  `Tôi chọn B`→B.

## 10. Ambiguity handling

- Last explicit marker wins: `A seems possible, but final answer: B`→B;
  `Option C was considered. The answer is D.`→D.
- Marker followed by `or/hoặc//` + another label → no match.
- Priority 4 (`_isolated_final_label`) only fires when **exactly one distinct** allowed label
  appears as a standalone token AND it is the final meaningful token: `Therefore: C`→C,
  `… tôi chọn B`→B. `A or B`, `A/B`, `Either A or C`, `It may be B, but perhaps C` → no match
  (two distinct isolated labels).

## 11. Mandatory rejection behavior (all return None)

`Grace Hopper`, `The model is uncertain`, `A or B`, `A/B`, `ABC`, `No answer`,
`Because the answer depends on context`, `The answer cannot be determined`, `Answer`, `Because`,
`Banana`, `Candidate`, `Answer: Z`, `Either A or C`, `It may be B, but perhaps C`, `""` — all `None`.
Verified.

## 12. Dynamic allowed-label behavior

Validation uses the passed allowed-label collection (`_allowed_labels`), never a hardcoded A–D.
- 3-choice: A–C accepted; `D`, `Answer: D` → None.
- 4-choice: A–D accepted; `E`, `Answer: E` → None.
- 10-choice: A–J accepted; `Đáp án: J`→J; `K`, `Đáp án: K` → None.

## 13. Fallback location and preserved semantics

The parser itself returns `None` on failure — **no fallback added inside the parser**. Caller-level
deterministic fallback is unchanged:
- **BTC default:** `predict.py` `_coerce_label(ans, item)` → `_fallback_answer` = first valid label
  (`labels_for(n)[0]`, i.e. `A`) when the parser returns `None`/invalid.
- **Dynamic Base:** `dynamic_base_predictor._local_answer` returns `None` → Base emits a
  `BasePrediction` with `source="dynamic_fallback"` and answer = first label, `risk_reason` weak.
Complete qid coverage, `qid,answer` / `qid,answer,time` schemas, `/code/private_test.json` input and
`/code/submission.csv` + `/code/submission_time.csv` outputs, default no-flag mode,
`--legacy-dynamic-full` mode, model loading, prompt text, and generation settings are all preserved
(verified byte-identical: `LocalQwenBackend` class, `build_mcq_prompt`, `parse_json_object`).

## 14. Files changed

- `src/local_model/local_qwen_backend.py` — rewrote `parse_mcq_label` + added private helpers
  (`_allowed_labels`, `_bare_label`, `_marker_label`, `_isolated_final_label`, `_json_label`) and
  four module-level compiled regexes. (+139 / −6.)
- `tests/unit/test_local_qwen_answer_parser.py` — new (73 tests).
- `tests/integration/test_local_parser_pipeline_2l48a.py` — new (9 tests).
- `docs/audits/65-harden-local-mcq-answer-parser.md` — this audit.

No other file changed. `parse_json_object`, the `LocalQwenBackend` class (generation/load/device/
`from_pretrained`/cache), and `build_mcq_prompt` are byte-identical to HEAD.

## 15. Exact regression examples and results

| Input (4-choice A–D) | Before | After |
|---|---|---|
| `The answer is clearly option B.` | A (wrong) | **B** |
| `The answer is clearly option C.` | A (wrong) | **C** |
| `Grace Hopper` | A/G (fabricated) | **None → caller fallback A** |
| `Đáp án: B` | B | B (preserved) |
| `Answer: Z` | (would scan) | **None** |
| `A or B` | A | **None** |

## 16. Unit tests added

`tests/unit/test_local_qwen_answer_parser.py` — 73 tests: bare labels; structured JSON (accept +
reject); Vietnamese markers; English markers; the AUDIT-64 regressions; ambiguous/invalid; final-
answer-overrides; isolated final label; 3/4/10-choice ranges; words-with-label-chars; case/
whitespace/Unicode/newlines; empty/missing labels; brace-as-JSON.

## 17. Integration tests added

`tests/integration/test_local_parser_pipeline_2l48a.py` — 9 tests using a `ScriptedBackend`
subclass of the real `LocalQwenBackend` (overrides only `generate_text`; no torch/weights/network),
so the real `predict_mcq` → real `parse_mcq_label` runs:
1. `predict_mcq("The answer is clearly option B.")` → B (not A).
2. `predict_mcq("Grace Hopper")` → None.
3. JSON output supported (`{"answer":"C"}`→C).
4. 10-choice `Đáp án: J`→J; out-of-range `Đáp án: K`→None.
5. **BTC single-pass** (`QwenMCQPredictor.predict_one`) uses the hardened parser → B.
6. BTC `Grace Hopper` → parser None, and `predict.py._coerce_label(None, item)` → A (caller fallback).
7. **Dynamic Base** prose answer → B, `source=dynamic_local_qwen`.
8. Dynamic Base `Grace Hopper` → `source=dynamic_fallback`, answer A (not G).
9. Dynamic Base out-of-range `Đáp án: K` → `dynamic_fallback`, answer A.

All GPU/weights/network/OpenRouter-free.

## 18. Validation commands and outputs

- `python -m compileall -q src scripts tests` → **PASS**.
- `pytest tests/unit/test_local_qwen_answer_parser.py tests/integration/test_local_parser_pipeline_2l48a.py -q`
  → **82 passed**.
- `pytest tests/unit/test_local_qwen_backend.py -q` (existing) → **4 passed** (unchanged behavior).
- Catastrophic-backtracking probe on 35k-char adversarial inputs → all parse in < 5 ms (no
  pathological regex).

## 19. Focused-suite result

`pytest tests/integration/test_btc_submission_contract_2l47a.py
tests/integration/test_full_system_output_contract_2l41a.py tests/unit/test_data_io.py
tests/unit/test_labels.py -q` → **38 passed**.

## 20. Full-suite comparison with the historical baseline

- Baseline (before this change): **16 failed, 565 passed**.
- After this change: **16 failed, 647 passed**.
- Passed increased by exactly **82** = the 82 new parser tests. No test regressed.

## 21. Remaining failure classification

All 16 failures are the pre-existing missing-frozen-artifact / public-replay class; node IDs are
identical to the baseline set. Independently classified by opening error: `FileNotFoundError` for
`output/pred_v11_independent_rerun1.csv` (×3), `experiments/best_candidate_manifest.json`,
`output/pred_v13_multilayer_candidate_api30_from_v12b.csv`,
`output/pred_v10_full_production_user_run.csv` (and the tests that chain off them). **No failure was
introduced by this parser change**, and no new failure category appeared.

## 22. Static / scope review

- `git diff --check` → clean.
- `git diff --stat` → only `src/local_model/local_qwen_backend.py` (+139 / −6).
- Diff searched for `Base/V12B/V13/selector/router/formula/prompt/model/Dockerfile/CUDA/torch/
  transformers/private_test/submission/legacy-dynamic-full/LOCAL_MODEL_PATH/max_new_tokens` — the
  only matches are comment lines and the two lines that reuse `parse_json_object`. No generation/
  model/device/prompt/Docker/runtime line changed.
- `parse_json_object`, the `LocalQwenBackend` class, and `build_mcq_prompt` are byte-identical to
  HEAD (verified by diff/md5).
- No new imports (no import cycle); no duplicated JSON utility (reused shared `parse_json_object`);
  no broad "last A–J character" rule; regexes use simple char classes and single-char captures with
  no nested quantifiers (no catastrophic backtracking, empirically confirmed); no marker matches a
  letter inside a word (required separator + right boundary); no hardcoded four-choice assumption
  (uses the allowed-label set); no hidden fallback to `A` inside the parser.

## 23. Diagnostics (section 7 of the task)

Internal parse-reason statuses (`json_answer`/`bare_label`/`explicit_marker`/`isolated_final_label`/
`ambiguous`/`no_match`/`invalid_label`) were **not** added: the public `parse_mcq_label` signature
returns `str | None`, and exposing statuses would require changing the return type or callers,
broadening scope beyond this task. **Recommendation (not implemented):** if selector/telemetry later
needs parse provenance, add an optional sibling function (e.g. `parse_mcq_label_with_reason`) rather
than changing the existing contract.

## 24. Confirmation — no architecture/behavior change

No change was made to: Base routing, V12B or V13 logic, formula-bank behavior, selector thresholds,
model prompts, model IDs/paths, generation parameters, Dockerfile/`.gitattributes`, CUDA/PyTorch/
Transformers versions, BTC paths or CSV schemas, or default/selective runtime selection. Only the
answer-label parser and its tests changed.

## 25. Confirmation — no Docker build/push

No Docker image was built, tagged, or pushed.

## 26. Confirmation — no commit/push

No Git commit or push was performed. (The only Git operation was the read-forward
`git merge --ff-only origin/main`, which advanced local `main` to the already-merged remote head
without creating a commit or pushing — required to obtain the merged working tree the task targets.)

## 27. Risks and remaining caveats

- **Real-model behavior unverified.** Tests use scripted/fake backends; actual Qwen3-4B output
  distributions were not exercised on GPU. The parser is conservative (prefers `None` → deterministic
  fallback), so the worst realistic regression is "falls back to A" rather than "fabricates a wrong
  label" — a strict improvement over the old first-letter scan.
- **Marker recall is intentionally bounded.** Unusual phrasings without a listed marker and without a
  clean isolated final label return `None` (→ fallback). This is deliberate (conservative), but a
  terse model that answers with only the letter (as the BTC prompt requests) is fully covered by the
  bare-label rule.
- **`"marker: X or Y"` beyond the immediate-next-token guard** (e.g. distant "or") could still take
  X; considered acceptable and documented, as such outputs are rare and the deterministic fallback
  bounds the downside.
- Diagnostics not wired (section 23) — recommended as a separate, non-breaking follow-up.

## 28. Current `git status --short`

```
 M src/local_model/local_qwen_backend.py
?? docs/audits/64-forensic-reconstruction-openrouter-79-7-vs-local-legacy.md
?? docs/audits/65-harden-local-mcq-answer-parser.md
?? tests/integration/test_local_parser_pipeline_2l48a.py
?? tests/unit/test_local_qwen_answer_parser.py
```

(`docs/audits/64-…md` is the untracked artifact carried over from the previous task; it was not
created by this task.)

## 29. Recommended next steps

1. Independently review this parser fix (precedence, regexes, tests).
2. Commit the parser fix separately (parser + its tests + this audit).
3. Evaluate enforced structured JSON output for local Qwen (grammar/constrained decoding) so the
   backend emits `{"answer":"X"}` reliably — the JSON precedence rule already supports it.
4. Create a permitted labeled validation set (self-annotated/synthetic; never organizer answers).
5. Only afterward run the architecture ablations (AUDIT 64 §23) and decide the final architecture.
```
