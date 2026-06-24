"""Tests for option-scoring score modes (no torch/transformers required).

Exercises the pure-Python parts: the continuation builder, the mode constants,
and that an invalid score_mode is rejected without loading a model.

Runnable with pytest, or standalone: ``python tests/test_score_mode.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.solvers.hf_option_score_solver import (  # noqa: E402
    DEFAULT_SCORE_MODE,
    SCORE_MODES,
    HFOptionScoreSolver,
    _continuation,
)


def test_score_mode_constants():
    assert DEFAULT_SCORE_MODE == "label_plus_choice"
    assert set(SCORE_MODES) == {"label_only", "label_plus_choice", "choice_only"}


def test_continuation_label_only():
    assert _continuation("label_only", "A", "Paris") == " A"


def test_continuation_label_plus_choice():
    assert _continuation("label_plus_choice", "B", "  Lyon ") == " B. Lyon"


def test_continuation_choice_only():
    assert _continuation("choice_only", "C", "Hanoi") == " Hanoi"


def test_invalid_score_mode_rejected_before_model_load():
    # Constructing with a bad score_mode must raise ValueError *before* any
    # attempt to load a model (so no torch/model path is needed).
    raised = False
    try:
        HFOptionScoreSolver("/unused/path", score_mode="nonsense")
    except ValueError as exc:
        raised = True
        assert "score_mode" in str(exc)
    except Exception as exc:  # pragma: no cover - would indicate wrong order
        raised = True
        assert False, f"expected ValueError first, got {type(exc).__name__}: {exc}"
    assert raised, "expected ValueError for invalid score_mode"


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
