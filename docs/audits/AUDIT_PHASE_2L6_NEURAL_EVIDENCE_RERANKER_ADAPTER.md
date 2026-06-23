# Audit — Phase 2L.6: Neural Evidence-Reranker Adapter (local-only, fail-closed)

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Goal

Upgrade the long-context evidence reranker from lexical-only into an optional
**two-stage** pipeline that can use a **local** neural model (BGE-M3 embedding or
BGE/Qwen cross-encoder reranker), while guaranteeing it **fails closed to
hybrid-lexical** when no dependency/model is present. No downloads, no installs, no
behavior change by default.

## Repo state at audit

`git status --short`:

```
 M configs/default.yaml
 M docs/EVIDENCE_RERANKER.md
 M run.py
 M src/evidence_reranker.py
 M src/openrouter_graph_solver.py
 M tests/test_evidence_reranker.py
 M tests/test_openrouter_graph_solver.py
?? docs/NEURAL_EVIDENCE_RERANKER.md
?? scripts/check_neural_reranker_env.py
```

## Files created

- `docs/NEURAL_EVIDENCE_RERANKER.md` — design doc (two-stage, backends, local-only
  guarantee, config/CLI/trace, limitations, v4 plan).
- `scripts/check_neural_reranker_env.py` — read-only dependency/model inventory.
- `docs/AUDIT_PHASE_2L6_NEURAL_EVIDENCE_RERANKER_ADAPTER.md` — this file.

## Files modified

- `src/evidence_reranker.py` — backend abstraction (`_dep_available`,
  `HybridLexicalScorer`, `SentenceTransformerEmbeddingScorer`,
  `FlagEmbeddingRerankerScorer`, `build_neural_scorer`), two-stage
  `rerank_evidence_for_sample` (lexical candidates → optional neural rerank → pack),
  diagnostics keys, `neural_scorer=` injection for tests.
- `src/openrouter_graph_solver.py` — new config fields `evidence_candidate_top_k`,
  `evidence_neural_fallback_to_lexical`; `_evidence_node` passes them + captures
  trace fields; `_init_state` seeded with matching fields.
- `run.py` — CLI flags `--evidence-reranker-method`, `--evidence-embedding-model`,
  `--evidence-reranker-model`, `--evidence-candidate-top-k`; nested→flat mapping for
  `candidate_top_k` / `neural_fallback_to_lexical`.
- `configs/default.yaml` — `evidence_reranker.candidate_top_k: 12`,
  `neural_fallback_to_lexical: true`.
- `docs/EVIDENCE_RERANKER.md` — clarified lexical=default, neural optional/two-stage,
  fallback behavior, new config/CLI.
- `tests/test_evidence_reranker.py`, `tests/test_openrouter_graph_solver.py` — new
  neural-adapter tests using fakes only.

## Backend design

`build_neural_scorer(method, embedding_model, reranker_model) → (scorer, available,
fallback_reason)`:

- Builds a backend **only** when a LOCAL model path is given AND the dependency
  imports; lazy import inside the call.
- Returns `(None, False, reason)` for any missing path / missing dep — reasons like
  `no_reranker_model_path`, `dependency_<mod>_not_installed`.
- `embedding` → `sentence-transformers` cosine (`local_files_only=True`);
  `reranker` → `FlagEmbedding` cross-encoder pair scores.

Two-stage flow: hybrid lexical scores all chunks → top `candidate_top_k` →
neural reranks only candidates → pack `top_k` within `max_chars`, question last.
Any neural error → lexical fallback (default) or unmatched (if
`neural_fallback_to_lexical=False`).

## Dependency inventory (`scripts/check_neural_reranker_env.py`)

```
sentence_transformers : NOT installed
FlagEmbedding         : NOT installed
torch                 : installed
CUDA                  : available (NVIDIA GeForce RTX 4060 Laptop GPU)
candidate model dirs  : 1
  - /mnt/vquclinh/models/Qwen3.5-9B  [config.json]
embedding method usable now : False
reranker  method usable now : False
=> Neural rerank NOT usable now. The pipeline will fail closed to hybrid_lexical.
```

The one candidate dir is the **generation** model (Qwen3.5-9B), not a reranker; it
matched the name hint only. **Neural rerank is not usable in this environment** →
effective method stays `hybrid_lexical`. Confirmed by behavior, not just config.

## Dry-run inventory (diagnostic only; no CSV, no API)

100/100 `long_context` samples chunked. Avg **7.1** chunks/sample (max 15); **95%**
have ≤ `candidate_top_k` (12), so the candidate stage covers nearly all chunks for
nearly all samples. Avg **3.69** kept chunks under lexical packing. No predictions
produced.

## Tests

`pytest` → **206 passed** (198 prior + 8 new). New tests assert: lexical default
effective method; missing-dep → lexical fallback with reason; `build_neural_scorer`
unavailable; injected fake scorer changes ranking (effective_method=`reranker`);
`candidate_top_k` limits stage-1; neural error + `no_fallback` → unmatched; neural
error → lexical by default; solver-level neural method falls back to lexical. All
neural tests use fakes — **no real model or dep required**. `compileall` OK.

## Frozen-output validation

`validate_submission.py` on both frozen files → **PASS**:
`outputs/pred.csv` (v1), `outputs/pred_v2_calc_rerank.csv` (v2). Neither modified.

## No-hardcoding / safety confirmation

- `grep -nE "qid|eval\(|exec\(|requests|urllib|httpx" src/evidence_reranker.py` →
  `qid` appears only in a docstring/comment ("no qid"), **no qid access**, no
  `eval`/`exec`, no network client.
- Test `test_no_web_or_eval_in_source` enforces this on every run.
- No public-test answers, no qids, no ground truth referenced anywhere.

## Constraints honored

No OpenRouter call; no full public inference; no CSV created/overwritten; no
v1/v2/v3 file touched; no leaderboard upload; no commit; no API key read/printed;
no `.env` read; **no model downloaded**; **no dependency installed**; `.venv`/model
dirs touched read-only (existence checks only); neural backends tested with fakes.

## Remaining risks

- Net accuracy effect of neural rerank is unverified (no ground truth; leaderboard
  decides). Code only changes *which* in-question chunks are selected.
- `embedding`/`reranker` paths are exercised only by fakes here; a first real run
  needs a staged local model and a smoke comparison before any full run.

## Recommended next step

1. Outside Claude: `pip install FlagEmbedding` (or `sentence-transformers`) and
   stage a **local** compliant reranker/embedding model; re-run
   `scripts/check_neural_reranker_env.py` until "usable now: True".
2. Long-context **smoke** with `--evidence-reranker-method reranker
   --evidence-reranker-model <path>` into a **new** file; diff selected chunks/answers
   vs the lexical baseline.
3. Only then a controlled **v4** full run into a new file, validated and A/B'd
   against v1/v2/v3 — no leaderboard claim without validation.

Everything left **uncommitted** for review.
