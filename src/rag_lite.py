"""RAG-lite retrieval over the local knowledge cards (Phase 2L.25).

Lexical card retrieval for a question and per-option, with optional embedding/rerank
hooks (BGE-M3 / Qwen-rerank) that are OFF by default and fail closed to lexical — no
external corpus is required and no network is contacted here. Retrieval selects NO
answer; an answer is only ever suggested when a single card maps uniquely to one
option AND the strict verifier policy accepts it (caller's responsibility). No qid
logic, no answer table, no ground truth.
"""

from __future__ import annotations

from src.knowledge_cards import retrieve_cards, score_card, CARDS


def retrieve_cards_for_question(question, choices=None, top_k: int = 5):
    """Return up to ``top_k`` (card, score) pairs most relevant to the question."""
    return retrieve_cards(question, top_k=top_k)


def retrieve_cards_per_option(question, choices, top_k: int = 2) -> dict:
    """label -> up to ``top_k`` (card, score) pairs scored against question + option."""
    labels = [chr(ord("A") + i) for i in range(len(choices or []))]
    out = {}
    for lbl, opt in zip(labels, choices or []):
        scored = [(c, score_card(c, f"{question} {opt}")) for c in CARDS]
        scored = [(c, s) for c, s in scored if s > 0]
        scored.sort(key=lambda cs: cs[1], reverse=True)
        out[lbl] = scored[: max(0, top_k)]
    return out


def best_card(question, choices=None):
    """The single most relevant card (card, score) or None."""
    hits = retrieve_cards_for_question(question, choices, top_k=1)
    return hits[0] if hits else None
