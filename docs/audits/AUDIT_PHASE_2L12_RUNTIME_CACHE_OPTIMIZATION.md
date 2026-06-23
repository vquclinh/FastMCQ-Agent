# Audit — Phase 2L.12: Runtime Audit, Neural Reranker Cache & Output-Schema Speed Fix

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Diagnosed the v6 runtime (37.99 s/sample) and applied targeted fixes: **cache neural
models** (were reloaded per long-context sample), **batch** Qwen3-Reranker scoring
with OOM retry, **tighten the OpenRouter output schema** (the slowest samples were
malformed/overlong JSON), and add **timing/token instrumentation**. No OpenRouter
call, no full inference, no output CSV overwritten.

## v6 runtime summary (from `outputs/run_v6_qwen_rerank_calc_verifier.jsonl`)

- 463 samples, total **17 589.75 s**, avg **37.99 s/sample**, max 153 s.
- api_calls: 438×1, 13×2, 12×0 (calc overrides). Sum 464 OpenRouter calls.
- 246 rows > 20 s, 224 > 60 s, 7 > 100 s.

## v6 route / runtime analysis (`scripts/analyze_v6_runtime.py`)

| route | n | avg elapsed |
|---|---|---|
| short_knowledge | 190 | 36.39 s |
| calculation | 159 | 36.91 s |
| long_context | 100 | 42.37 s |
| law_admin | 7 | 47.40 s |
| ambiguous | 7 | 33.99 s |

## Root cause(s) found

1. **Dominant cost = OpenRouter per-call latency (~36 s/call)** — present on *every*
   route, including routes that never touch the reranker. The reranker adds only
   ~6 s to long_context (42.4 vs 36.4). So the reranker is **not** the main cost.
2. **Malformed/overlong generations** — 58/463 (12.5%) hit
   `no_json`/`partial_answer_key`; these averaged **59.8 s** vs **35.9 s** for clean
   JSON. The 1024-token cap + a free-string `reason_type` let the model run long and
   emit repeated/garbage fields. This is the biggest *controllable* latency lever.
3. **Reranker reloaded per sample** — confirmed in code: `_evidence_node` →
   `rerank_evidence_for_sample` → `build_neural_scorer` was called for **every**
   long_context sample, reloading the 1.2 GB Qwen reranker each time (the repeated
   "Loading weights"). Wasteful even if masked by OS page cache.

## Was the reranker being loaded repeatedly?

**Yes.** No caching existed; the scorer (and its weights) were constructed once per
long-context sample (100×). Fixed by a process-level cache.

## Files created / modified

- **A** `scripts/analyze_v6_runtime.py` — read-only v6 JSONL analyzer.
- **A** `scripts/benchmark_neural_reranker_speed.py` — neural speed benchmark (no API).
- **M** `src/evidence_reranker.py` — model cache (`_NEURAL_CACHE`, `_cached`,
  `clear_neural_model_cache`, `neural_model_cache_size`); `_resolve_neural_scorer`
  (cache-aware, returns cache_hit + load_seconds); `build_neural_scorer` now a
  back-compat 3-tuple wrapper; `TransformersQwen3RerankerScorer` batched scoring
  (left padding, `batch_size`, OOM auto-shrink, `_is_oom`); `rerank_evidence_for_sample`
  gained `neural_batch_size` + timing/cache diagnostics.
- **M** `src/openrouter_graph_solver.py` — `evidence_neural_batch_size` config;
  passes batch size; new reranker + OpenRouter timing/token/parse trace fields;
  `verifier_call_seconds`.
- **M** `src/structured_answer.py` — `reason_type` strict enum + `additionalProperties:false`.
- **M** `src/openrouter_prompts.py` — compact-JSON, single-occurrence-keys, enum reason_type.
- **M** `run.py` — `--evidence-neural-batch-size` + config flatten.
- **M** `configs/default.yaml` — `evidence_reranker.neural_batch_size: 8`.
- **M** `docs/NEURAL_EVIDENCE_RERANKER.md`, `docs/EVIDENCE_RERANKER.md`.
- **M** `tests/test_evidence_reranker.py` — cache/batch/OOM/fail-closed tests.

## Caching design

Module-level `_NEURAL_CACHE` keyed by `(scorer class name, resolved model path,
device)` — dtype is derived from device for our backends, so device captures it.
`_cached(cls, path)` constructs once on miss (timing the load), reuses on hit, and
returns `(scorer, cache_hit, load_seconds)`. `local_files_only=True` is preserved.
Load failure → caught upstream → fails closed to lexical. `clear_neural_model_cache()`
lets tests assert load-once behavior; no hidden global state leaks into results.

## Batching design

`TransformersQwen3RerankerScorer` formats all candidate prompts, tokenizes with
**left padding** (so last-token logits are correct across a batch), and runs batched
forwards of `batch_size` (default 8). On CUDA OOM it halves the batch (8→4→2→1,
`empty_cache` between) and only a batch size of 1 failing propagates → lexical
fallback. Scoring semantics unchanged: `P("yes")` over {"no","yes"}.

## Output-schema / prompt changes

`reason_type` → enum `[lookup, reading, calculation, elimination, other]`;
`additionalProperties:false`; prompt now requires compact JSON, each key exactly
once, no extra keys, end right after the closing brace. Robust partial-parse
fallback is **preserved** (not removed). Recommended v6b: `--openrouter-max-tokens
512` for main calls (answer JSON needs far less than 1024).

## Timing instrumentation added

`evidence_reranker_cache_hit / load_seconds / score_seconds / pair_count /
batch_size`; `openrouter_call_seconds`; `openrouter_completion_tokens /
total_tokens` (from `ChatResult.usage`); `raw_response_chars`;
`parsed_answer_source`; `parsed_answer_error`; `verifier_call_seconds`. Verified
populated via a mock-client run (e.g. completion_tokens=42, total_tokens=128,
parsed_answer_source=json). CSV format unchanged.

## Speed benchmark result (RTX 4060; no OpenRouter)

`benchmark_neural_reranker_speed.py --method reranker --model-path
models/qwen3-reranker-0.6b --max-samples 20 --batch-size 8`:

- model load (cold): **16.75 s, once**
- rerank cache hits/misses: **20 / 0**; final cache size **1** (weights loaded once: True)
- first sample 0.968 s; **avg warm 0.573 s/sample**; min/max 0.268 / 1.093 s
- total candidate pairs 150; peak CUDA mem **4 642 MB**

**Before:** the reranker was reconstructed per long-context sample (100 reloads).
**After:** one load + ~0.57 s/sample. Reranker is no longer a meaningful cost.

## Chunk smoke result (behavior preserved)

`compare_neural_vs_lexical_chunks.py … --max-samples 20` →
`outputs/neural_vs_lexical_qwen3_reranker_speedfix_smoke.jsonl`: 20/20 usable,
**0 fallback**, **8/20 changed** chunk selections (consistent ~40% rate with the
pre-fix run) — batching + left-padding did not change scoring semantics.

## Tests added/updated

`test_model_cache_prevents_repeated_loads`, `test_cache_key_includes_path_and_type`,
`test_cache_clear_helper_resets`, `test_qwen_reranker_batched_oom_retry_shrinks_batch`
(real retry loop, no weights), `test_is_oom_detection`,
`test_cached_load_error_propagates_and_fails_closed`,
`test_rerank_sets_batch_size_and_records_timing`. Source test still asserts
`local_files_only=True` on every `from_pretrained` and bans
`hf_hub_download`/`snapshot_download`. **No real weights required in pytest.** Full
suite: **247 passed** (was 240); `compileall` OK; standalone runner passes.

## Validation results

- `compileall -q src tests scripts`: OK
- `pytest -q`: **247 passed**
- `validate_submission.py` on `outputs/pred_v6_qwen_rerank_calc_verifier.csv`: **PASS** (not modified)

## Confirmations

- No OpenRouter API call made; no full inference run.
- No output CSV overwritten (`pred.csv`, v1/v2/v6 untouched); no new full prediction CSV.
- No leaderboard upload.
- `.env` not read; no `OPENROUTER_API_KEY` printed/exposed.
- Model files untouched and gitignored (`.gitignore:20:models/`); no weights in git.
- No qid hardcoding, no public-test answer table; **no external Gemini/GPT/Claude
  answer sheet used as ground truth** (analysis is timing/parse only).

## Remaining risks

- The schema/prompt tightening should cut malformed JSON and per-call tokens, but the
  **net** per-call latency is OpenRouter-side and only confirmable on a real v6b run.
- Left-padding + batching match per-pair scoring in the smoke; a different provider
  build of transformers could pad differently — OOM retry and lexical fallback bound
  the downside.
- v6b accuracy parity vs v6 is unverified until rerun; the calc/verifier paths are
  unchanged, so deltas should come only from cleaner JSON parsing.

## Recommended next command — fast v6b rerun into NEW files (user runs; calls OpenRouter)

```bash
.venv/bin/python run.py \
  --solver openrouter_graph \
  --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 \
  --openrouter-max-tokens 512 \
  --config configs/verifier_selective.yaml \
  --calculation-solver \
  --evidence-reranker \
  --evidence-reranker-method reranker \
  --evidence-reranker-model models/qwen3-reranker-0.6b \
  --evidence-candidate-top-k 12 \
  --evidence-neural-batch-size 8 \
  --mcq-verifier \
  --input public-test_1780368312.json \
  --output outputs/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
  --save-raw \
  --log-path outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl
```

After: `analyze_v6_runtime.py --log outputs/run_v6b_...jsonl` to confirm the reranker
loads once (cache_hit=true) and malformed-JSON count drops, then A/B-diff
`pred_v6b` vs `pred_v6`/`pred_v2` before any leaderboard claim.

## git status

```
 M configs/default.yaml
 M docs/EVIDENCE_RERANKER.md
 M docs/NEURAL_EVIDENCE_RERANKER.md
 M run.py
 M src/evidence_reranker.py
 M src/openrouter_graph_solver.py
 M src/openrouter_prompts.py
 M src/structured_answer.py
 M tests/test_evidence_reranker.py
?? docs/AUDIT_PHASE_2L11A_OUTPUTS_CLEANUP.md
?? docs/AUDIT_PHASE_2L12_RUNTIME_CACHE_OPTIMIZATION.md
?? scripts/analyze_v6_runtime.py
?? scripts/benchmark_neural_reranker_speed.py
```

Do not commit. All changes left uncommitted for user review.
