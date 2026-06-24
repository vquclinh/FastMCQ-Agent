"""Tests for the confidence module (no torch).

Runnable with pytest, or standalone: ``python tests/test_confidence.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.confidence import assess_confidence  # noqa: E402

TH = {"high_margin": 0.3, "medium_margin": 0.1}


def test_high_margin_accepts():
    d = assess_confidence(margin=0.5, thresholds=TH)
    assert d.level == "high"
    assert d.should_accept and not d.should_fallback


def test_medium_margin_accept_by_default():
    d = assess_confidence(margin=0.15, thresholds=TH, accept_medium=True)
    assert d.level == "medium"
    assert d.should_accept


def test_medium_margin_can_verify():
    d = assess_confidence(margin=0.15, thresholds=TH, accept_medium=False)
    assert d.level == "medium"
    assert not d.should_accept
    assert d.should_fallback


def test_low_margin_falls_back():
    d = assess_confidence(margin=0.02, thresholds=TH, allow_fallback=True)
    assert d.level == "low"
    assert d.should_fallback


def test_unknown_when_no_margin():
    d = assess_confidence(margin=None, thresholds=TH, allow_fallback=True)
    assert d.level == "unknown"
    assert d.should_fallback


def test_invalid_label_is_low():
    d = assess_confidence(margin=0.9, has_valid_label=False, thresholds=TH)
    assert d.level == "low"
    assert not d.should_accept


def test_duplicate_choices_block_high():
    d = assess_confidence(margin=0.9, duplicate_choice_groups=[[0, 1]], thresholds=TH)
    # High margin but duplicates => not "high"; demoted to medium handling.
    assert d.level != "high"


def test_no_fallback_means_accept_unknown():
    # If we cannot fall back, an unknown-margin case is accepted (best effort).
    d = assess_confidence(margin=None, allow_fallback=False, thresholds=TH)
    assert d.should_accept


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
