"""Unit: QwenMCQPredictor.backend read-only accessor (Phase 3A-1 injection).

Proves the accessor returns the EXACT backend instance already used by predict_one /
score_choices, triggers no second get_local_qwen_backend lookup, and has no setter.
No torch/GPU/network (the backend is never loaded).
"""

from __future__ import annotations

import pytest

import src.local_model.qwen_mcq_predictor as qp
from src.local_model.qwen_mcq_predictor import QwenMCQPredictor


def test_backend_property_returns_exact_private_instance(monkeypatch):
    p = QwenMCQPredictor(model_path="/tmp/does-not-load", device="cpu", max_new_tokens=64)
    assert p.backend is p._backend
    # same object as the one predict_one/score_choices delegate to
    assert p.backend is p._backend


def test_backend_property_does_not_relookup_backend(monkeypatch):
    p = QwenMCQPredictor(model_path="/tmp/does-not-load", device="cpu")
    calls = {"n": 0}
    real = qp.get_local_qwen_backend

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(qp, "get_local_qwen_backend", _counting)
    _ = p.backend
    _ = p.backend
    assert calls["n"] == 0                       # accessor never re-resolves the cache


def test_backend_property_is_read_only():
    p = QwenMCQPredictor(model_path="/tmp/does-not-load", device="cpu")
    with pytest.raises(AttributeError):
        p.backend = object()                     # no setter
