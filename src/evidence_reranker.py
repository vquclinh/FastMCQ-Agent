"""In-question evidence reranking for long-context MCQA.

Reranks evidence **already present inside the question** to fight long-context
noise and "lost in the middle". It is **not** web retrieval and uses no ground
truth and no qid — it only reads one sample's ``question`` + ``choices``.

Pipeline: split the embedded context into chunks → score each chunk against a
choice-aware query (default: dependency-free hybrid lexical) → pack a
``[GLOBAL CONTEXT]`` overview + the top evidence chunks + the final question stem
(question last, to keep it near the choices). On any failure it returns
``matched=False`` so the caller falls back to the existing lexical compressor.

An optional embedding/reranker hook exists but is **off by default** and fails
closed to the lexical method; no heavy dependency is required or imported.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

# Markers that introduce an embedded passage / the title-content structure.
_CONTEXT_MARKERS = ("Đoạn thông tin", "Nội dung:", "Tiêu đề:", "-- Đoạn văn",
                    "Đọc đoạn", "Title:", "Content:")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


@dataclass
class EvidenceChunk:
    chunk_id: str
    text: str
    source_title: str | None = None
    source_index: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    kind: str = "paragraph"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RerankResult:
    selected_text: str
    selected_chunks: list
    global_context: str
    method: str
    scores: list
    matched: bool
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Keep chunk records light (no huge text blobs in logs).
        d["selected_chunks"] = [{"chunk_id": c.chunk_id, "source_title": c.source_title,
                                 "source_index": c.source_index, "kind": c.kind,
                                 "len": len(c.text)} for c in self.selected_chunks]
        return d


# --- text utilities ----------------------------------------------------------

def _tokens(text: str) -> list:
    return _WORD_RE.findall((text or "").lower())


def _char_ngrams(text: str, n: int = 3) -> set:
    t = re.sub(r"\s+", " ", (text or "").lower())
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def extract_question_stem(question: str, *, max_chars: int = 600) -> str:
    """Return the trailing interrogative (the actual question), best-effort."""
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(question or "") if s.strip()]
    if sentences:
        tail = []
        for s in reversed(sentences):
            tail.insert(0, s)
            joined = " ".join(tail)
            if "?" in s or len(joined) > max_chars:
                break
        stem = " ".join(tail).strip()
        if stem:
            return stem[-max_chars:]
    return (question or "")[-max_chars:].strip()


# --- chunking ----------------------------------------------------------------

def _split_titled_blocks(text: str) -> list:
    """Split '[n] Tiêu đề: T Nội dung: C' or 'Tiêu đề: T Nội dung: C' blocks."""
    chunks = []
    # Each block starts at a "Tiêu đề:" (optionally preceded by "[n]").
    pat = re.compile(r"(?:\[(\d+)\]\s*)?Tiêu đề:\s*(.*?)\s*Nội dung:\s*(.*?)"
                     r"(?=(?:\[\d+\]\s*)?Tiêu đề:|$)", re.DOTALL)
    for i, m in enumerate(pat.finditer(text)):
        idx = int(m.group(1)) if m.group(1) else i + 1
        title = (m.group(2) or "").strip()
        body = (m.group(3) or "").strip()
        if body:
            chunks.append(EvidenceChunk(
                chunk_id=f"src{idx}", text=body, source_title=title or None,
                source_index=idx, start_char=m.start(), end_char=m.end(),
                kind="titled_source"))
    return chunks


def _split_doan_van(text: str) -> list:
    """Split '-- Đoạn văn N --' blocks."""
    chunks = []
    pat = re.compile(r"--\s*Đoạn văn\s*(\d+)\s*--\s*(.*?)(?=--\s*Đoạn văn\s*\d+\s*--|$)",
                     re.DOTALL | re.IGNORECASE)
    for m in pat.finditer(text):
        idx = int(m.group(1)); body = (m.group(2) or "").strip()
        if body:
            chunks.append(EvidenceChunk(chunk_id=f"doan{idx}", text=body,
                                        source_index=idx, start_char=m.start(),
                                        end_char=m.end(), kind="doan_van"))
    return chunks


def _split_paragraphs(text: str, *, target: int = 500) -> list:
    """Fallback: paragraph windows (merge short sentences up to ~target chars)."""
    pieces = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if len(pieces) <= 1:
        pieces = [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]
    chunks, buf, start = [], "", 0
    for p in pieces:
        if buf and len(buf) + len(p) + 1 > target:
            chunks.append(EvidenceChunk(chunk_id=f"p{len(chunks)}", text=buf.strip(),
                                        kind="paragraph", start_char=start))
            buf, start = "", None
        buf = (buf + " " + p).strip() if buf else p
    if buf.strip():
        chunks.append(EvidenceChunk(chunk_id=f"p{len(chunks)}", text=buf.strip(),
                                    kind="paragraph"))
    return chunks


def _subdivide(chunks: list, *, window: int = 600) -> list:
    """Split any over-long chunk into paragraph/sentence windows.

    A single big source (e.g. one 5k-char [1] block) is otherwise un-rerankable;
    subdividing lets the reranker select the relevant span. Sub-chunks inherit the
    parent's title/index so the global overview and provenance are preserved.
    """
    out = []
    for c in chunks:
        if len(c.text) <= window * 1.6:
            out.append(c); continue
        sub = _split_paragraphs(c.text, target=window)
        if len(sub) <= 1:
            out.append(c); continue
        for j, s in enumerate(sub):
            out.append(EvidenceChunk(
                chunk_id=f"{c.chunk_id}.{j}", text=s.text,
                source_title=c.source_title, source_index=c.source_index,
                kind=(c.kind + "_window")))
    return out


def chunk_context(context: str) -> list:
    """Chunk the embedded context using the most specific structure available,
    then subdivide any over-long chunk so single big sources are rerankable."""
    titled = _split_titled_blocks(context)
    if len(titled) >= 1 and "Tiêu đề:" in context:
        return _subdivide(titled)
    doan = _split_doan_van(context)
    if len(doan) >= 1:
        return _subdivide(doan)
    return _split_paragraphs(context)


# --- scoring (hybrid lexical, dependency-free) -------------------------------

def _bm25_idf(chunks_tokens: list, qset: set) -> dict:
    n = len(chunks_tokens) or 1
    df = {t: 0 for t in qset}
    for toks in chunks_tokens:
        present = set(toks)
        for t in qset:
            if t in present:
                df[t] += 1
    return {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in qset}


def _score_chunks_lexical(chunks: list, query: str, choices) -> list:
    """Return a list of score dicts (one per chunk), higher = more relevant."""
    q_tokens = _tokens(query)
    q_ngrams = _char_ngrams(query)
    qset = set(q_tokens)
    chunk_tokens = [_tokens(c.text) for c in chunks]
    idf = _bm25_idf(chunk_tokens, qset)
    avg_len = (sum(len(t) for t in chunk_tokens) / len(chunk_tokens)) if chunk_tokens else 1.0
    k1, b = 1.5, 0.75

    scored = []
    for c, toks in zip(chunks, chunk_tokens):
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        dl = len(toks) or 1
        bm25 = 0.0
        for t in qset:
            f = tf.get(t, 0)
            if f:
                denom = f + k1 * (1 - b + b * dl / max(avg_len, 1e-9))
                bm25 += idf[t] * (f * (k1 + 1)) / denom
        # char-trigram overlap (robust to Vietnamese morphology/accents)
        cg = _char_ngrams(c.text)
        ngram = (len(q_ngrams & cg) / len(q_ngrams)) if q_ngrams else 0.0
        # title relevance bonus
        title_bonus = 0.0
        if c.source_title:
            t_tokens = set(_tokens(c.source_title))
            if qset and t_tokens:
                title_bonus = len(qset & t_tokens) / len(qset)
        # length penalty for very long boilerplate-ish chunks
        length_pen = 1.0 / (1.0 + max(0, len(c.text) - 1200) / 1200.0)
        score = (bm25 + 2.0 * ngram + 1.5 * title_bonus) * length_pen
        scored.append({"chunk_id": c.chunk_id, "score": round(score, 4),
                       "bm25": round(bm25, 4), "ngram": round(ngram, 4),
                       "title_bonus": round(title_bonus, 4),
                       "source_index": c.source_index, "source_title": c.source_title})
    return scored


# --- global context ----------------------------------------------------------

def _build_global_context(chunks: list, full_context: str, *, max_chars: int) -> str:
    """Deterministic global overview: source titles, else the context head."""
    titles = [f"[{c.source_index}] {c.source_title}" for c in chunks
              if c.source_title]
    if titles:
        overview = "Các nguồn: " + " | ".join(titles)
        return overview[:max_chars]
    return (full_context or "").strip()[:max_chars]


# --- optional embedding hook (off by default; fails closed) ------------------

def _embedding_available(model_path) -> bool:
    """True only if a model path is given AND the dep is importable. No download."""
    if not model_path:
        return False
    try:
        import importlib.util
        return importlib.util.find_spec("sentence_transformers") is not None \
            or importlib.util.find_spec("FlagEmbedding") is not None
    except Exception:
        return False


# --- main API ----------------------------------------------------------------

def has_long_context(sample: dict) -> bool:
    q = str(sample.get("question", "") or "")
    return any(m in q for m in _CONTEXT_MARKERS) or len(q) > 1500


def rerank_evidence_for_sample(sample: dict, *, max_chars: int = 4500, top_k: int = 4,
                               method: str = "hybrid_lexical",
                               include_global_context: bool = True,
                               global_context_chars: int = 800,
                               optional_embedding_model=None,
                               optional_reranker_model=None) -> RerankResult:
    """Rerank in-question evidence for one sample. Never uses web/qid/ground truth.

    Returns ``matched=False`` (caller falls back) if there is no usable structured
    context or reranking cannot improve on the raw question.
    """
    question = str(sample.get("question", "") or "")
    choices = sample.get("choices", []) or []
    diagnostics = {"original_chars": len(question)}

    if not question:
        return RerankResult("", [], "", "none", [], False, {"reason": "empty_question"})

    stem = extract_question_stem(question)
    # The "context" is everything before the trailing stem (best-effort).
    context = question[: question.rfind(stem)] if stem and stem in question else question
    context = context.strip() or question

    try:
        chunks = chunk_context(context)
    except Exception as exc:
        return RerankResult("", [], "", "none", [], False,
                            {"reason": f"chunk_error:{type(exc).__name__}"})

    if len(chunks) < 2:
        # Not enough structure to rerank meaningfully -> let the compressor handle it.
        return RerankResult("", [], "", "none", [], False,
                            {"reason": "insufficient_chunks", "chunks": len(chunks)})

    # Choice-aware query: question stem + all choice texts.
    query = stem + " " + " ".join(str(c) for c in choices)

    used_method = "hybrid_lexical"
    # Optional embedding/reranker hook — only if explicitly configured AND present.
    if method in ("embedding", "reranker") and _embedding_available(
            optional_embedding_model or optional_reranker_model):
        try:
            scored = _score_chunks_embedding(chunks, query,
                                             optional_embedding_model or optional_reranker_model)
            used_method = method
        except Exception:
            scored = _score_chunks_lexical(chunks, query, choices)  # fail closed
            used_method = "hybrid_lexical_fallback"
    else:
        scored = _score_chunks_lexical(chunks, query, choices)

    order = sorted(range(len(chunks)), key=lambda i: scored[i]["score"], reverse=True)
    # Pack top chunks (by score) until the budget, then restore reading order.
    budget = max_chars - (global_context_chars if include_global_context else 0) - len(stem) - 64
    budget = max(budget, 400)
    kept_idx, used = [], 0
    for i in order[: max(top_k, 1) * 3]:  # consider a few extra, bounded by budget
        if len(kept_idx) >= top_k:
            break
        c = chunks[i]
        if used + len(c.text) + 1 > budget:
            continue
        kept_idx.append(i)
        used += len(c.text) + 1
    if not kept_idx:               # at least keep the single best chunk (trimmed)
        kept_idx = [order[0]]
    kept_idx.sort()
    selected_chunks = [chunks[i] for i in kept_idx]

    global_ctx = _build_global_context(chunks, context, max_chars=global_context_chars) \
        if include_global_context else ""

    parts = []
    if global_ctx:
        parts.append("[NGỮ CẢNH TỔNG QUAN]\n" + global_ctx)
    evidence = "\n\n".join(c.text for c in selected_chunks)
    parts.append("[BẰNG CHỨNG LIÊN QUAN]\n" + evidence)
    parts.append("[CÂU HỎI]\n" + stem)   # question last (near the choices)
    selected_text = "\n\n".join(parts).strip()

    # Never return empty; never return longer than the original question.
    if not selected_text:
        return RerankResult("", [], "", "none", [], False, {"reason": "empty_selection"})
    if len(selected_text) >= len(question):
        # Reranking didn't shrink it; still valid, but mark for diagnostics.
        diagnostics["no_shrink"] = True

    diagnostics.update({"chunks_total": len(chunks), "chunks_kept": len(selected_chunks),
                        "selected_chars": len(selected_text),
                        "kept_chunk_ids": [c.chunk_id for c in selected_chunks]})
    return RerankResult(selected_text=selected_text, selected_chunks=selected_chunks,
                        global_context=global_ctx, method=used_method, scores=scored,
                        matched=True, diagnostics=diagnostics)


def _score_chunks_embedding(chunks, query, model_path):  # pragma: no cover - optional
    """Optional embedding similarity scoring. Only reached if a dep is installed.

    Intentionally minimal and lazy; raises on any problem so the caller fails
    closed to the lexical method. No model is downloaded (local path expected).
    """
    raise NotImplementedError("optional embedding reranker not wired in this phase")
