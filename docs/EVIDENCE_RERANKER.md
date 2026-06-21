# In-Question Evidence Reranker

`src/evidence_reranker.py` improves long-context MCQA by reranking the evidence
**already inside the question** and packing a focused context for the model. It
targets long-context noise and the "lost in the middle" effect.

## What it is / is not

- **In-question only.** It reads one sample's `question` + `choices` and reranks
  the embedded passage. **No web/external retrieval. No ground truth. No qid.**
- **No public-test hardcoding.** Generic chunking + scoring; a private question
  matching the same structure is handled identically.
- **Dependency-safe.** Default method is dependency-free **hybrid lexical**.
  Optional **local** neural backends (embedding / cross-encoder reranker) are off
  by default and **fail closed** to lexical if a model/dependency is absent
  (nothing is downloaded). See [NEURAL_EVIDENCE_RERANKER.md](NEURAL_EVIDENCE_RERANKER.md).

## Pipeline

```text
question
  → split off the trailing question stem
  → chunk the embedded context
  → score chunks against a choice-aware query (hybrid lexical)
  → pack: [NGỮ CẢNH TỔNG QUAN] + [BẰNG CHỨNG LIÊN QUAN] + [CÂU HỎI] (question LAST)
```

Putting the question last (next to the choices) is the deliberate
lost-in-the-middle mitigation; the global overview preserves document structure.

## Chunking formats supported

- `[n] Tiêu đề: … Nội dung: …` multi-source blocks (title + index preserved)
- `-- Đoạn văn N --` blocks
- single `Tiêu đề: … Nội dung: …`
- fallback paragraph/sentence windows for unstructured context
- **subdivision:** an over-long single source is split into windows (inheriting its
  title/index) so even one big passage is rerankable

## Scoring (default: hybrid lexical)

Query = question stem + all choice texts (choice-aware). Per-chunk score combines:

- **BM25-lite** token relevance (rare-term/idf weighted across chunks),
- **char-trigram overlap** (robust to Vietnamese morphology/accents),
- **title relevance** bonus,
- **length penalty** for very long boilerplate-ish chunks.

Top-`k` chunks are selected by score, then re-ordered into reading order and
packed within `max_chars`.

## Global + factual packing (dual perspective)

- **Global context:** deterministic overview — the list of source titles, or the
  head of the context when untitled (no LLM summarization).
- **Factual chunks:** the top-scoring evidence windows.

## Optional two-stage neural reranking (Phase 2L.6)

`method: embedding|reranker` enables a **two-stage** pipeline: hybrid lexical
selects the top `candidate_top_k` chunks (stage 1, always), then a **local** neural
model reranks only those candidates (stage 2). The primary backends are
**transformers-native** (no FlagEmbedding / sentence-transformers required):
`embedding` → **BGE-M3** (`models/bge-m3`, CLS pooling + cosine); `reranker` →
**Qwen3-Reranker-0.6B** (`models/qwen3-reranker-0.6b`, causal-LM yes/no). Backends
are lazy-imported, loaded `local_files_only=True`, and **fail closed** to hybrid
lexical unless `transformers`+`torch` import **and** the local path shape-matches
the expected model. No model is downloaded; tests never require real weights.
**Current env: both usable** (transformers+torch+CUDA, both models staged). Full
design, fallback reasons, and trace fields:
[NEURAL_EVIDENCE_RERANKER.md](NEURAL_EVIDENCE_RERANKER.md).

## Config (`openrouter:` block)

```yaml
evidence_reranker:
  enabled: true
  apply_routes: ["long_context"]
  method: "hybrid_lexical"        # hybrid_lexical | embedding | reranker
  optional_embedding_model: null  # local path only; never downloaded
  optional_reranker_model: null   # local path only; never downloaded
  candidate_top_k: 12             # stage-1 candidates fed to the neural stage
  top_k: 4
  max_chars: 4500
  include_global_context: true
  global_context_chars: 800
  neural_fallback_to_lexical: true
```

CLI: `--evidence-reranker` / `--no-evidence-reranker`,
`--evidence-reranker-method`, `--evidence-embedding-model`,
`--evidence-reranker-model`, `--evidence-candidate-top-k`,
`--evidence-neural-batch-size`.

**Performance (Phase 2L.12):** neural scorers are cached by
`(type, model path, device)` so weights load **once per process** (not per sample),
and Qwen3-Reranker scores candidates in batches (`neural_batch_size`, default 8,
OOM auto-shrinks). See [NEURAL_EVIDENCE_RERANKER.md](NEURAL_EVIDENCE_RERANKER.md) for
the benchmark and the v6 runtime fix.

## Integration

Called from `openrouter_graph`'s evidence node **only on the `long_context`
route**. On a match it sets the prompt's question body to the reranked text; if it
declines (too little structure) or errors, the pipeline **falls back to the
existing lexical compressor**, then to the raw question — behavior is never worse
than before. Trace fields: `evidence_reranker_enabled`, `evidence_reranker_method`,
`evidence_selected_chunk_count`, `evidence_selected_chars`, `evidence_fallback_used`
(+ chunk ids/scores in diagnostics, not full text).

## Public-set behavior (dry-run, diagnostic only)

100/100 long-context samples reranked with `hybrid_lexical` (0 fallback); average
context reduced **~41%** (5766 → 3400 chars), dropping low-relevance chunks. No
prediction CSV was produced; no accuracy is claimed (leaderboard decides).

## Limitations

- Lexical scoring can miss semantically-relevant-but-lexically-different chunks;
  the optional neural two-stage rerank is the remedy when a local model is staged.
- Question-stem extraction is heuristic (trailing interrogative).
- Reranking never *adds* information; it only selects/orders what's present.

## How to disable

`--no-evidence-reranker` or `evidence_reranker.enabled: false` → the long-context
path reverts to the lexical compressor exactly as before.

## Use in a future v2/v3 run

Combine with the calculation override: deterministic answers for matched
calculation questions, reranked evidence for long-context questions, LLM for the
rest. A/B against the v1 leaderboard score before adopting.
