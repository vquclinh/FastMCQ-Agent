# Neural Evidence Reranker (optional, local-only)

Phase 2L.6 upgrades the long-context evidence reranker from lexical-only to an
optional **two-stage** pipeline that can use a **local** neural model (BGE-M3
embedding or BGE/Qwen cross-encoder reranker). It **fails closed to the existing
hybrid-lexical reranker** whenever the dependency or local model is absent — so
default behavior is unchanged and nothing is ever downloaded.

## Why neural reranking helps long-context MCQA

Lexical scoring (BM25/trigram) misses evidence that is semantically relevant but
lexically different from the question/choices. A neural embedding/cross-encoder
captures semantic similarity, so the chunk that actually answers the question is
more likely to rank first — reducing "lost in the middle" errors.

## Two-stage retrieval

```text
Stage 1 (always): hybrid lexical scores all chunks → keep top candidate_top_k (12)
Stage 2 (optional): neural rerank ONLY those candidates → pack top_k (4)
```

Lexical stage is cheap/robust and bounds the work; the neural model only scores a
small candidate set. If neural is unavailable, Stage 1's lexical order is used —
identical to the previous behavior.

## Backends (`method`)

| method | backend | dependency | model |
|---|---|---|---|
| `hybrid_lexical` (default) | `HybridLexicalScorer` | none | none |
| `embedding` | `SentenceTransformerEmbeddingScorer` (cosine) | `sentence-transformers` | local BGE-M3-style path |
| `reranker` | `FlagEmbeddingRerankerScorer` (cross-encoder) | `FlagEmbedding` | local bge-reranker / Qwen-rerank path |

`build_neural_scorer(method, embedding_model, reranker_model)` returns
`(scorer, available, fallback_reason)` — a backend is built **only** when a LOCAL
model path is given AND the dependency is importable; both are lazy-imported.

## Local-only / no-download guarantee

- Model paths are local directories; `sentence-transformers` is loaded with
  `local_files_only=True`. No network, no download, no install performed by code.
- Any missing dep / missing path / load error / scoring error is caught and the
  pipeline falls back to lexical (unless `neural_fallback_to_lexical: false`, in
  which case the long-context node defers to the lexical compressor).

## Config (`openrouter.evidence_reranker`)

```yaml
evidence_reranker:
  enabled: true
  apply_routes: ["long_context"]
  method: "hybrid_lexical"         # hybrid_lexical | embedding | reranker
  optional_embedding_model: null   # LOCAL path (method=embedding)
  optional_reranker_model: null    # LOCAL path (method=reranker)
  candidate_top_k: 12              # stage-1 candidates fed to the neural stage
  top_k: 4
  max_chars: 4500
  include_global_context: true
  global_context_chars: 800
  neural_fallback_to_lexical: true
```

## CLI

`--evidence-reranker-method hybrid_lexical|embedding|reranker`,
`--evidence-embedding-model <local_path>`, `--evidence-reranker-model <local_path>`,
`--evidence-candidate-top-k <int>` (plus `--no-evidence-reranker`).

## Trace fields

`evidence_reranker_requested_method`, `evidence_reranker_effective_method`,
`evidence_neural_available`, `evidence_neural_fallback_reason`,
`evidence_candidate_chunk_count`, `evidence_selected_chunk_count`,
`evidence_selected_chars` (+ existing reranker fields).

## Environment check

```bash
python scripts/check_neural_reranker_env.py
```
Reports dep availability, CUDA, and local candidate model dirs (read-only). In the
current environment: `sentence_transformers`/`FlagEmbedding` **not installed** →
neural **not usable** → effective method stays `hybrid_lexical`.

## Limitations

- Requires the user to install a dep AND stage a **local** compliant model; this
  repo does neither.
- Cross-encoder reranking adds latency per candidate; bounded by `candidate_top_k`.
- No ground truth — net accuracy effect is confirmed only by the leaderboard.

## Recommended future controlled experiment (v4)

1. `pip install FlagEmbedding` (or `sentence-transformers`) and place a **local**
   compliant reranker/embedding model; re-run `check_neural_reranker_env.py`.
2. Run a **long-context smoke** with `--evidence-reranker-method reranker
   --evidence-reranker-model <path>` into a **new** file; compare the selected
   chunks and answers vs the lexical baseline (v2/v3).
3. Full **v4** run into a new file, validated, A/B vs v1/v2/v3 — no leaderboard
   claim without validation.
