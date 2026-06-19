"""Tests for the solver factory.

Runnable with pytest, or standalone: ``python tests/test_solver_factory.py``.
HF solver construction is only exercised if torch+transformers are installed;
otherwise those checks are skipped gracefully.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.baseline_solver import AlwaysASolver  # noqa: E402
from src.solver_factory import build_solver  # noqa: E402

_HF_AVAILABLE = True
try:  # detect heavy deps without importing them heavily
    import importlib.util
    _HF_AVAILABLE = (importlib.util.find_spec("torch") is not None
                     and importlib.util.find_spec("transformers") is not None)
except Exception:  # pragma: no cover
    _HF_AVAILABLE = False


def test_default_returns_always_a():
    solver = build_solver("always_a")
    assert isinstance(solver, AlwaysASolver)
    # And it behaves as expected.
    assert solver.predict_one({"qid": "q", "question": "?", "choices": ["a", "b"]}) == "A"


def test_unknown_solver_raises():
    raised = False
    try:
        build_solver("does_not_exist")
    except ValueError as exc:
        raised = True
        assert "unknown solver" in str(exc)
    assert raised, "expected ValueError for unknown solver"


def test_hf_solver_without_model_path_raises():
    for name in ("hf_generate", "hf_option_score"):
        raised = False
        try:
            build_solver(name, model_path=None)
        except ValueError as exc:
            raised = True
            assert "model-path" in str(exc) or "model_path" in str(exc)
        assert raised, f"expected ValueError for {name} without model_path"


def test_hf_solver_with_bad_path():
    # With a nonexistent path: if HF deps are present we expect a clear
    # "does not exist" error; if absent, a clear dependency error. Either way it
    # must raise, never silently succeed.
    raised = False
    try:
        build_solver("hf_generate", model_path="/no/such/model/dir")
    except Exception as exc:
        raised = True
        msg = str(exc).lower()
        assert ("does not exist" in msg) or ("not installed" in msg)
    assert raised, "expected an error for a bad model path"


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
    if not _HF_AVAILABLE:
        print("NOTE: torch/transformers not installed — HF model loading paths "
              "were exercised only for their error handling.")
    raise SystemExit(1 if failures else 0)
