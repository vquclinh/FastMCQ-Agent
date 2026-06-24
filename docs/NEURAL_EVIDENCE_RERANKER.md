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

## Backends (`method`) — competition-compliant, transformers-native

The primary backends use **`transformers` + `torch` only** (no FlagEmbedding, no
sentence-transformers required) with the local competition-compliant models:

| method | backend | dependency | local model |
|---|---|---|---|
| `hybrid_lexical` (default) | `HybridLexicalScorer` | none | none |
| `embedding` | `TransformersBgeM3EmbeddingScorer` (CLS pool + cosine) | `transformers`+`torch` | `models/bge-m3` (`BAAI/bge-m3`) |
| `reranker` | `TransformersQwen3RerankerScorer` (causal-LM yes/no) | `transformers`+`torch` | `models/qwen3-reranker-0.6b` (`Qwen/Qwen3-Reranker-0.6B`) |

Optional legacy fallbacks (`SentenceTransformerEmbeddingScorer`,
`FlagEmbeddingRerankerScorer`) are used only if those packages happen to be
installed and the transformers path does not apply — they are **not required**.

- **BGE-M3 embedding**: `AutoTokenizer`+`AutoModel` (XLM-RoBERTa), pools the last
  hidden state (CLS per the model's `1_Pooling` config), L2-normalizes, scores each
  chunk by cosine vs the query.
- **Qwen3-Reranker**: `AutoTokenizer`+`AutoModelForCausalLM`, builds the official
  system/Instruct/Query/Document prompt, reads the last-position logits, and returns
  `P("yes")` over {"no","yes"} as the relevance score. The `<think>` block is left
  empty — no hidden reasoning is generated or logged.

`build_neural_scorer(method, embedding_model, reranker_model)` returns
`(scorer, available, fallback_reason)`. A backend is built **only** when the LOCAL
path exists, its config/name matches the expected model shape (so an unrelated
directory is never silently used), and `transformers`+`torch` import. Explicit
fallback reasons include `embedding_model_path_not_found`,
`unsupported_embedding_model_path`, `unsupported_reranker_model_path`,
`dependency_missing:transformers`, `unsupported_qwen_reranker_scoring_format`,
`load_error:<Type>`.

## Local-only / no-download guarantee

- Model paths are local directories; **every** `from_pretrained` call uses
  `local_files_only=True` (asserted by a source-inspection test). No network, no
  download, no install performed by code; no `hf_hub_download`/`snapshot_download`.
- Any missing dep / missing path / unsupported model / load error / scoring error is
  caught and the pipeline falls back to lexical (unless
  `neural_fallback_to_lexical: false`, in which case the long-context node defers to
  the lexical compressor).
- CUDA is used when available; otherwise CPU. Model weights are gitignored under
  `models/` and never committed.

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
python scripts/check_neural_reranker_env.py          # shallow (no weight load)
python scripts/check_neural_reranker_env.py --deep   # loads weights locally, scores a probe
```
Reports `transformers`/`torch`/CUDA, whether `models/bge-m3` and
`models/qwen3-reranker-0.6b` are present and shape-match, and whether each method is
usable. `--deep` additionally loads the local weights (`local_files_only`, no
network) and scores a tiny probe.

**Current environment (Phase 2L.10): both methods USABLE.** `transformers`+`torch`
installed, CUDA (RTX 4060). Deep check probe: BGE-M3 ranks the relevant chunk above
noise (≈0.68 vs 0.29); Qwen3-Reranker ≈0.997 vs 0.0.

## CLI usage (exact)

```bash
# BGE-M3 embedding
--evidence-reranker --evidence-reranker-method embedding \
  --evidence-embedding-model models/bge-m3 --evidence-candidate-top-k 12
# Qwen3-Reranker
--evidence-reranker --evidence-reranker-method reranker \
  --evidence-reranker-model models/qwen3-reranker-0.6b --evidence-candidate-top-k 12
```

Chunk-selection smoke (no OpenRouter, no CSV):

```bash
python scripts/compare_neural_vs_lexical_chunks.py --input public-test_1780368312.json \
  --method embedding --model-path models/bge-m3 \
  --max-samples 30 --top-k 4 --candidate-top-k 12 \
  --output output/neural_vs_lexical_bge_m3_chunk_report.jsonl
```

## Performance & model caching (Phase 2L.12)

The v6 full run (37.99 s/sample avg) exposed two costs. Fixes:

- **Model caching** — the scorer was rebuilt **per long-context sample**, reloading
  the 1.2 GB Qwen reranker every time (the repeated "Loading weights"). Scorers are
  now cached by `(scorer type, resolved model path, device)` so weights load **once
  per process**. Benchmark (RTX 4060, 20 long-context samples): cold load **16.75 s
  once**, then **20/20 cache hits**, warm rerank **~0.57 s/sample**, peak CUDA 4.6 GB.
  `clear_neural_model_cache()` / `neural_model_cache_size()` are exposed for tests.
- **Batched scoring** — Qwen3-Reranker scores all `candidate_top_k` pairs in batches
  (`neural_batch_size`, default 8; left-padded so the last-token logits stay
  correct). On CUDA OOM the batch size auto-halves down to 1 before any lexical
  fallback. CLI: `--evidence-neural-batch-size N`.
- **Overlong/malformed JSON** — 58/463 v6 samples (12.5%) hit `no_json`/
  `partial_answer_key` and averaged **59.8 s** vs 35.9 s for clean JSON (generations
  running to the 1024-token cap). `reason_type` is now a strict **enum**,
  `additionalProperties:false` rejects repeated/extra keys, and the prompt demands
  compact single-occurrence keys. Recommended **v6b** main-call cap: lower
  `--openrouter-max-tokens` to ~512 (the JSON answer needs far less than 1024).

New trace fields: `evidence_reranker_cache_hit`, `evidence_reranker_load_seconds`,
`evidence_reranker_score_seconds`, `evidence_reranker_pair_count`,
`evidence_reranker_batch_size`, plus `openrouter_call_seconds`,
`openrouter_completion_tokens`, `openrouter_total_tokens`, `raw_response_chars`,
`parsed_answer_source`, `parsed_answer_error`, `verifier_call_seconds`.

Speed benchmark (no OpenRouter, no CSV):

```bash
python scripts/benchmark_neural_reranker_speed.py --input public-test_1780368312.json \
  --method reranker --model-path models/qwen3-reranker-0.6b \
  --max-samples 20 --candidate-top-k 12 --batch-size 8
```

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
