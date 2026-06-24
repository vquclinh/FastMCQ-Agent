"""Tests for the deterministic router (no torch).

Runnable with pytest, or standalone: ``python tests/test_question_router.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.layers.question_router import route_question  # noqa: E402


def _r(question, choices, **kw):
    return route_question({"qid": "q", "question": question, "choices": choices}, **kw)


def test_short_knowledge_route():
    d = _r("Thủ đô của Pháp là gì?", ["Paris", "Lyon", "Nice", "Hue"])
    assert d.route == "short_knowledge"
    assert d.recommended_budget_tier == 0


def test_long_context_route():
    q = "Đoạn thông tin:\nNội dung: " + ("văn bản " * 400) + " Câu hỏi cuối?"
    d = _r(q, ["a", "b", "c", "d"])
    assert d.route == "long_context"
    assert d.recommended_budget_tier == 1


def test_calculation_route():
    d = _r("Tính $x$ nếu $2x=10$?", ["3", "4", "5", "6"])
    assert d.route == "calculation"
    assert d.recommended_budget_tier == 1


def test_law_admin_route():
    d = _r("Theo luật và nghị định, cơ quan hành chính nào? Quy định tại điều nào?",
           ["A", "B", "C", "D"])
    assert d.route == "law_admin"


def test_safety_ethics_route():
    d = _r("Vì lý do an toàn và đạo đức, hành vi nào là không nên và nguy hiểm?",
           ["x", "y", "z", "w"])
    assert d.route == "safety_ethics"


def test_ambiguous_route_on_duplicate_choices():
    d = _r("Câu hỏi?", ["Hà Nội", "hà nội", "Huế", "Đà Nẵng"])
    assert d.route == "ambiguous"
    # Tier 2 is clamped to 1 unless explicitly allowed.
    assert d.recommended_budget_tier == 1
    d2 = _r("Câu hỏi?", ["Hà Nội", "hà nội", "Huế", "Đà Nẵng"],
            allow_tier2_ambiguous=True)
    assert d2.recommended_budget_tier == 2


def test_decision_has_strategies():
    d = _r("Thủ đô của Pháp?", ["Paris", "Lyon"])
    assert d.primary_strategy
    assert d.fallback_strategy
    assert d.route in (
        "short_knowledge", "long_context", "calculation",
        "law_admin", "safety_ethics", "ambiguous", "unknown",
    )


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
