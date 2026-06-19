"""Tests for label conversion and validation.

Runnable with pytest, or standalone: ``python tests/test_labels.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.labels import index_to_label, is_valid_label, label_to_index, labels_for  # noqa: E402


def test_index_to_label():
    assert index_to_label(0) == "A"
    assert index_to_label(1) == "B"
    assert index_to_label(4) == "E"
    assert index_to_label(10) == "K"  # 11-choice questions exist in the public test


def test_label_to_index_roundtrip():
    for i in range(26):
        assert label_to_index(index_to_label(i)) == i


def test_label_to_index_is_case_insensitive():
    assert label_to_index("a") == 0
    assert label_to_index(" C ") == 2


def test_labels_for():
    assert labels_for(4) == ["A", "B", "C", "D"]
    assert labels_for(6) == ["A", "B", "C", "D", "E", "F"]
    assert labels_for(0) == []


def test_is_valid_label_respects_choice_count():
    four = {"choices": ["w", "x", "y", "z"]}
    assert is_valid_label("A", four)
    assert is_valid_label("D", four)
    assert not is_valid_label("E", four)  # out of range for 4 choices

    six = {"choices": list("abcdef")}
    assert is_valid_label("E", six)
    assert is_valid_label("F", six)
    assert not is_valid_label("G", six)


def test_is_valid_label_rejects_junk():
    sample = {"choices": ["a", "b"]}
    assert not is_valid_label("", sample)
    assert not is_valid_label("AB", sample)
    assert not is_valid_label("1", sample)


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
