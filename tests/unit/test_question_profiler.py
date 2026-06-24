"""Tests for the deterministic question profiler (no torch).

Runnable with pytest, or standalone: ``python tests/test_question_profiler.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.layers.question_profiler import profile_question  # noqa: E402


def _p(question, choices, qid="q"):
    return profile_question({"qid": qid, "question": question, "choices": choices})


def test_short_knowledge():
    p = _p("Thủ đô của Pháp là gì?", ["Paris", "Lyon", "Nice", "Marseille"])
    assert p.num_choices == 4
    assert not p.has_long_context_marker
    assert p.estimated_difficulty in ("easy", "medium")


def test_long_context_markers():
    q = "Đoạn thông tin:\nTiêu đề: X\nNội dung: " + ("dài " * 300) + " Câu hỏi?"
    p = _p(q, ["a", "b", "c", "d"])
    assert p.has_long_context_marker
    assert p.has_title_marker
    assert p.has_passage_marker


def test_calculation_signals():
    p = _p("Tính giá trị của $x$ khi $2x + 3 = 7$?", ["1", "2", "3", "4"])
    assert p.raw_signals["is_calculation"]
    assert p.latex_marker_count > 0 or p.math_symbol_count >= 2


def test_law_admin_keywords():
    p = _p("Theo quy định của luật và nghị định, cơ quan hành chính nào chịu trách nhiệm?",
           ["A", "B", "C", "D"])
    assert p.legal_keyword_count >= 2


def test_safety_ethics_keywords():
    p = _p("Hành vi nào là không nên vì lý do an toàn và đạo đức?",
           ["x", "y", "z"])
    assert (p.safety_keyword_count + p.ethics_keyword_count) >= 2


def test_duplicate_choices_detected():
    p = _p("Câu hỏi?", ["Hà Nội", "hà nội ", "Huế", "Đà Nẵng"])
    assert p.duplicate_choice_groups == [[0, 1]]


def test_ten_choice_sample():
    p = _p("Một bài toán?", [f"{i}.0 cm/s" for i in range(10)])
    assert p.num_choices == 10
    # numeric, many choices => hard (calculation-ish)
    assert p.estimated_difficulty in ("medium", "hard")


def test_numeric_density_nonnegative():
    p = _p("abc def", ["a", "b"])
    assert p.numeric_count == 0
    assert p.numeric_density == 0.0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
