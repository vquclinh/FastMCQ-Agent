"""Tests for the structured-answer parser (no API, no torch).

Runnable with pytest, or standalone: ``python tests/test_structured_answer.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.structured_answer import parse_structured_answer  # noqa: E402

ABCD = ["A", "B", "C", "D"]


def test_valid_strict_json():
    r = parse_structured_answer(
        '{"answer": "B", "confidence": 0.9, "evidence": "x", '
        '"reason_type": "lookup", "needs_review": false}', ABCD)
    assert r.ok and r.answer == "B"
    assert r.confidence == 0.9 and r.reason_type == "lookup"


def test_json_in_markdown_fence():
    text = "Here you go:\n```json\n{\"answer\": \"C\", \"confidence\": 0.7}\n```\nthanks"
    r = parse_structured_answer(text, ABCD)
    assert r.ok and r.answer == "C" and r.source == "json_in_fence"


def test_embedded_json_object():
    text = 'blah blah {"answer":"D","confidence":0.5} trailing'
    r = parse_structured_answer(text, ABCD)
    assert r.ok and r.answer == "D" and r.source == "embedded"


def test_answer_with_punctuation_normalized():
    r = parse_structured_answer('{"answer": "(A)"}', ABCD)
    assert r.ok and r.answer == "A"


def test_invalid_label_rejected():
    r = parse_structured_answer('{"answer": "Z", "confidence": 1.0}', ABCD)
    assert not r.ok and r.answer is None and r.needs_review


def test_partial_answer_key_recovery_from_truncated_json():
    # Trailing evidence truncated (no closing brace) -> recover the explicit
    # answer key, marked as a degraded (needs_review) success.
    truncated = '{"answer": "C", "confidence": 1.0, "evidence": "Độ co giãn = (250-150)/150 / (3-5)/5 = 0.66'
    r = parse_structured_answer(truncated, ABCD)
    assert r.ok and r.answer == "C"
    assert r.source == "partial_answer_key" and r.needs_review


def test_no_recovery_from_standalone_letter():
    # A bare Vietnamese declaration is NOT recovered (no JSON, no `answer:` key).
    r = parse_structured_answer("Đáp án: C chắc chắn", ABCD)
    assert not r.ok and r.answer is None


def test_no_recovery_from_letter_in_prose():
    r = parse_structured_answer("Tôi nghĩ rằng đáp án đúng là C.", ABCD)
    assert not r.ok and r.answer is None


def test_answer_key_recovery_validates_label():
    # `answer: Z` is recovered-shaped but Z is not a valid label -> failure.
    r = parse_structured_answer('{"answer": "Z", "evidence": "trunc', ABCD)
    assert not r.ok and r.answer is None


def test_unparseable_returns_failure():
    r = parse_structured_answer("tôi không biết", ABCD)
    assert not r.ok and r.answer is None and r.error == "unparseable"


def test_confidence_clamped():
    r = parse_structured_answer('{"answer":"A","confidence": 5}', ABCD)
    assert r.ok and r.confidence == 1.0
    r2 = parse_structured_answer('{"answer":"A","confidence": "bad"}', ABCD)
    assert r2.ok and r2.confidence == 0.0


def test_label_beyond_abcd():
    labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K"]
    r = parse_structured_answer('{"answer": "K"}', labels)
    assert r.ok and r.answer == "K"


def test_duplicate_choice_text_uses_label():
    # The parser works purely on the label, so duplicate choice *text* is moot.
    r = parse_structured_answer('{"answer": "B"}', ABCD)
    assert r.ok and r.answer == "B"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
