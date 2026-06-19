"""Tests for answer-label parsing.

Runnable with pytest, or standalone: ``python tests/test_output_parser.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.output_parser import parse_answer_label  # noqa: E402

ABCD = ["A", "B", "C", "D"]
ABCDE = ["A", "B", "C", "D", "E"]


def test_bare_and_punctuated_labels():
    assert parse_answer_label("A", ABCD) == "A"
    assert parse_answer_label("A.", ABCD) == "A"
    assert parse_answer_label("(A)", ABCD) == "A"
    assert parse_answer_label("[B]", ABCD) == "B"


def test_explicit_vietnamese_patterns():
    assert parse_answer_label("Đáp án: A", ABCD) == "A"
    assert parse_answer_label("Câu trả lời là B", ABCD) == "B"
    assert parse_answer_label("Tôi chọn E", ABCDE) == "E"
    assert parse_answer_label("Đáp án đúng là D.", ABCD) == "D"


def test_explicit_english_patterns():
    assert parse_answer_label("The answer is C", ABCD) == "C"
    assert parse_answer_label("Answer: D", ABCD) == "D"


def test_case_insensitive():
    assert parse_answer_label("đáp án: c", ABCD) == "C"
    assert parse_answer_label("b", ABCD) == "B"


def test_rejects_out_of_range_label():
    # "E" is not valid for a 4-choice question.
    assert parse_answer_label("E", ABCD) is None
    assert parse_answer_label("Đáp án: E", ABCD) is None


def test_no_valid_label_returns_none():
    assert parse_answer_label("Tôi không biết.", ABCD) is None
    assert parse_answer_label("", ABCD) is None
    assert parse_answer_label("Z", ABCD) is None


def test_does_not_pick_letters_inside_words():
    # "Animal" starts with A but is a word, not a standalone label. With an
    # explicit answer present, that should win; here there is none, so the lone
    # "B." should be chosen rather than the A in "Animal".
    assert parse_answer_label("Animal facts. Đáp án: B.", ABCD) == "B"


def test_explicit_pattern_beats_stray_label():
    # A stray "C" earlier should not override an explicit "Đáp án: A".
    assert parse_answer_label("Xét phương án C trước. Đáp án: A", ABCD) == "A"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
