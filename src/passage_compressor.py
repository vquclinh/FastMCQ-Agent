"""Deterministic, pure-Python long-context compressor (v1).

Selects the passage sentences most relevant to the final question + choices,
using a BM25-lite lexical score. **No** embeddings, rerankers, torch, or
external retrieval — that keeps it deterministic, dependency-free, and fast.

Guarantees:
  * deterministic output for the same input,
  * safe on already-short input (returns it unchanged),
  * never returns empty text,
  * operates only on the *question* text — **choices are never touched** (they
    live in ``sample["choices"]`` and are only read to build query terms),
  * preserves the title/head and the final-question/tail, and places the kept
    evidence next to the question to mitigate lost-in-the-middle.
"""

from __future__ import annotations

import math
import re

# Sentence-ish splitter: break on ., !, ? and newlines, keeping it simple.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"\w+", re.UNICODE)
# Title line: stop at a newline or sentence terminator, and hard-cap the length
# so a passage without newlines cannot swallow the whole text as the "title".
_TITLE_RE = re.compile(r"(Tiêu đề:\s*[^\n.!?]{0,150})", re.IGNORECASE)


def _tokens(text: str) -> list:
    return _WORD_RE.findall(text.lower())


def _split_sentences(text: str) -> list:
    parts = [s.strip() for s in _SENT_SPLIT_RE.split(text)]
    return [s for s in parts if s]


def _extract_head(text: str) -> str:
    """Return a title/head line to always preserve, if one is present."""
    m = _TITLE_RE.search(text)
    return m.group(1).strip() if m else ""


def _extract_tail(text: str, max_tail_chars: int = 600) -> str:
    """Return the final-question segment (kept verbatim).

    Heuristic: prefer the last sentence(s) containing a question mark; otherwise
    fall back to the trailing slice of the text.
    """
    sentences = _split_sentences(text)
    if sentences:
        # Walk from the end, collecting until we include a '?' or hit the cap.
        tail_parts: list = []
        for s in reversed(sentences):
            tail_parts.insert(0, s)
            if "?" in s:
                break
            if sum(len(p) for p in tail_parts) > max_tail_chars:
                break
        tail = " ".join(tail_parts).strip()
        if tail:
            return tail[-max_tail_chars:] if len(tail) > max_tail_chars else tail
    return text[-max_tail_chars:].strip()


def _bm25_scores(chunks: list, query_terms: list, k1: float = 1.5,
                 b: float = 0.75) -> list:
    """BM25-lite score of each chunk against the query terms (chunks = docs)."""
    tokenized = [_tokens(c) for c in chunks]
    n = len(tokenized)
    avg_len = sum(len(t) for t in tokenized) / n if n else 0.0

    # Document frequency for idf.
    qset = set(query_terms)
    df = {t: 0 for t in qset}
    for toks in tokenized:
        present = set(toks)
        for t in qset:
            if t in present:
                df[t] += 1

    def idf(t: str) -> float:
        # BM25 idf with +1 smoothing to stay non-negative.
        return math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))

    scores = []
    for toks in tokenized:
        if not toks:
            scores.append(0.0)
            continue
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        dl = len(toks)
        s = 0.0
        for t in qset:
            f = tf.get(t, 0)
            if f == 0:
                continue
            denom = f + k1 * (1 - b + b * dl / avg_len) if avg_len else f + k1
            s += idf(t) * (f * (k1 + 1)) / denom
        scores.append(s)
    return scores


def compress_passage(question: str, choices=None, *, max_context_chars: int = 3000,
                     marker: str = "\n[...]\n") -> dict:
    """Compress a long question, returning the text plus stats.

    Returns a dict: ``compressed_question`` and ``stats`` with keys
    ``original_chars, compressed_chars, compression_ratio, chunks_total,
    chunks_kept, kept_chunk_indices, method, was_compressed``.
    """
    question = str(question or "")
    choices = choices or []
    original_chars = len(question)

    base_stats = {
        "original_chars": original_chars,
        "compressed_chars": original_chars,
        "compression_ratio": 1.0,
        "chunks_total": 0,
        "chunks_kept": 0,
        "kept_chunk_indices": [],
        "method": "none",
        "was_compressed": False,
    }

    # Already short enough: return unchanged.
    if original_chars <= max_context_chars:
        return {"compressed_question": question, "stats": base_stats}

    head = _extract_head(question)
    tail = _extract_tail(question)

    # The "body" we compress is everything; we score its sentences and keep the
    # most query-relevant ones. Head and tail are always retained.
    chunks = _split_sentences(question)
    if len(chunks) <= 1:
        # Cannot sentence-split meaningfully: hard head/tail truncation.
        budget = max(max_context_chars - len(marker), len(tail))
        head_room = max(budget - len(tail), 0)
        compressed = (question[:head_room] + marker + tail).strip()
        compressed = compressed or tail or question[:max_context_chars]
        stats = {**base_stats, "compressed_chars": len(compressed),
                 "compression_ratio": round(len(compressed) / max(1, original_chars), 3),
                 "chunks_total": len(chunks), "method": "head_tail_truncate",
                 "was_compressed": True}
        return {"compressed_question": compressed, "stats": stats}

    query_terms = _tokens(tail + " " + " ".join(str(c) for c in choices))
    scores = _bm25_scores(chunks, query_terms)

    # Reserve budget for head + tail + marker; fill the rest with top evidence.
    reserved = len(head) + len(tail) + 2 * len(marker)
    evidence_budget = max(max_context_chars - reserved, 0)

    # Rank chunks by score (desc), tie-break by original order for determinism.
    ranked = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    kept_indices: list = []
    used = 0
    for i in ranked:
        chunk = chunks[i]
        if used + len(chunk) + 1 > evidence_budget:
            continue
        kept_indices.append(i)
        used += len(chunk) + 1
    kept_indices.sort()  # restore reading order
    evidence = " ".join(chunks[i] for i in kept_indices).strip()

    # Assemble: head, then evidence, then the final question (evidence sits right
    # before the question — near the end — to fight lost-in-the-middle).
    pieces = [p for p in (head, evidence) if p]
    compressed = (marker.join(pieces) + marker + tail).strip() if pieces else tail
    compressed = compressed or tail or question[:max_context_chars]

    # Invariant: never return text longer than the input. If assembly somehow
    # overshoots (degenerate structure), fall back to a hard head-tail truncate.
    if len(compressed) > original_chars:
        head_room = max(max_context_chars - len(tail) - len(marker), 0)
        compressed = (question[:head_room] + marker + tail).strip()
        compressed = compressed or question[:max_context_chars]

    stats = {
        "original_chars": original_chars,
        "compressed_chars": len(compressed),
        "compression_ratio": round(len(compressed) / max(1, original_chars), 3),
        "chunks_total": len(chunks),
        "chunks_kept": len(kept_indices),
        "kept_chunk_indices": kept_indices,
        "method": "bm25_lite_sentence_select",
        "was_compressed": True,
    }
    return {"compressed_question": compressed, "stats": stats}
