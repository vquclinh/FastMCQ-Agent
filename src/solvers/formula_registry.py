"""Formula registry — metadata-only eligibility over the formula cards.

Selects which formula cards are *eligible* for a question based purely on generic
trigger keywords, target intent (e.g. γ vs momentum), and ``do_not_use_when``
guards. This is a metadata layer for diagnostics/orchestration — it does NOT compute
answers and never reads a qid or any external answer sheet. The numeric executors
remain in ``src/calculation_solver.py``.
"""

from __future__ import annotations

from src.formula_cards import CARDS

_REGISTRY = {c.formula_id: c for c in CARDS}


def all_formula_ids() -> list:
    return list(_REGISTRY.keys())


def get_card(formula_id: str):
    return _REGISTRY.get(formula_id)


def _has_any(low: str, tokens) -> bool:
    return any(t.lower() in low for t in tokens)


def is_eligible(card, question: str) -> bool:
    """Metadata-only eligibility: trigger present, no do-not-use guard, intent matches.

    For cards with ``target_intents`` (e.g. relativity), at least one intent token
    must appear so γ-questions and momentum-questions select different cards.
    """
    low = str(question or "").lower()
    if not _has_any(low, card.trigger_keywords):
        return False
    if card.do_not_use_when and _has_any(low, card.do_not_use_when):
        return False
    if card.target_intents and not _has_any(low, card.target_intents):
        return False
    return True


def eligible_cards(question: str) -> list:
    """Cards eligible for this question (metadata only; order = registry order)."""
    return [c for c in CARDS if is_eligible(c, question)]


def eligible_formula_ids(question: str) -> list:
    return [c.formula_id for c in eligible_cards(question)]
