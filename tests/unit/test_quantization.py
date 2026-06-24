"""Tests for optional quantization plumbing (no real bitsandbytes / model).

Covers the config builder's error paths, the no-op default, and factory
passthrough (via monkeypatched model loading). Dependency-requiring checks skip
gracefully if torch/transformers are absent.

Runnable with pytest, or standalone: ``python tests/test_quantization.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.solvers import hf_common  # noqa: E402
from src.solvers.hf_common import (  # noqa: E402
    HFDependencyError,
    bitsandbytes_available,
)

_HEAVY = (importlib.util.find_spec("torch") is not None
          and importlib.util.find_spec("transformers") is not None)
_BNB = bitsandbytes_available()


def _torch_tf():
    import torch
    import transformers
    return torch, transformers


def test_bitsandbytes_available_returns_bool():
    assert isinstance(bitsandbytes_available(), bool)


def test_default_config_is_none():
    if not _HEAVY:
        print("SKIP test_default_config_is_none: torch/transformers absent"); return
    torch, tf = _torch_tf()
    # None and mode=null both mean "no quantization" — and must not need bnb.
    assert hf_common._build_quantization_config(None, torch, tf, "cuda") is None
    assert hf_common._build_quantization_config({"mode": None}, torch, tf, "cuda") is None
    assert hf_common._build_quantization_config({}, torch, tf, "cpu") is None


def test_invalid_mode_raises():
    if not _HEAVY:
        print("SKIP test_invalid_mode_raises: torch/transformers absent"); return
    torch, tf = _torch_tf()
    raised = False
    try:
        hf_common._build_quantization_config({"mode": "3bit"}, torch, tf, "cuda")
    except HFDependencyError as exc:
        raised = True
        assert "unknown quantization mode" in str(exc)
    assert raised


def test_quant_requires_cuda():
    if not _HEAVY:
        print("SKIP test_quant_requires_cuda: torch/transformers absent"); return
    torch, tf = _torch_tf()
    raised = False
    try:
        hf_common._build_quantization_config({"mode": "4bit"}, torch, tf, "cpu")
    except HFDependencyError as exc:
        raised = True
        assert "requires a CUDA GPU" in str(exc)
    assert raised


def test_4bit_without_bnb_raises():
    if not _HEAVY:
        print("SKIP test_4bit_without_bnb_raises: torch/transformers absent"); return
    if _BNB:
        print("SKIP test_4bit_without_bnb_raises: bitsandbytes IS installed"); return
    torch, tf = _torch_tf()
    raised = False
    try:
        hf_common._build_quantization_config({"mode": "4bit"}, torch, tf, "cuda")
    except HFDependencyError as exc:
        raised = True
        assert "bitsandbytes" in str(exc)
    assert raised


def test_8bit_without_bnb_raises():
    if not _HEAVY:
        print("SKIP test_8bit_without_bnb_raises: torch/transformers absent"); return
    if _BNB:
        print("SKIP test_8bit_without_bnb_raises: bitsandbytes IS installed"); return
    torch, tf = _torch_tf()
    raised = False
    try:
        hf_common._build_quantization_config({"mode": "8bit"}, torch, tf, "cuda")
    except HFDependencyError as exc:
        raised = True
        assert "bitsandbytes" in str(exc)
    assert raised


def test_invalid_compute_dtype_raises():
    if not _HEAVY:
        print("SKIP test_invalid_compute_dtype_raises: torch/transformers absent"); return
    if _BNB:
        print("SKIP test_invalid_compute_dtype_raises: bnb installed (would pass dep check)"); return
    torch, tf = _torch_tf()
    # compute_dtype is validated; but the bnb-missing check fires first on this
    # machine. Validate the dtype mapper directly instead.
    raised = False
    try:
        hf_common._resolve_compute_dtype("float64", torch, "cuda")
    except HFDependencyError as exc:
        raised = True
        assert "compute_dtype" in str(exc)
    assert raised


# --- Factory passthrough (monkeypatch load_model; no real model) -------------

def _patch_load_model(module):
    """Replace module.load_model with a recorder; return (captured, restore)."""
    captured = {}
    original = module.load_model

    def fake(model_path, *, device="auto", trust_remote_code=False, quantization=None):
        captured["quantization"] = quantization
        captured["model_path"] = model_path
        return object()  # solvers only touch ._loaded lazily at predict time

    module.load_model = fake
    return captured, (lambda: setattr(module, "load_model", original))


def test_factory_passes_quantization_to_option_score():
    from src.solvers import hf_option_score_solver as oss
    from src.solvers import hf_generate_solver as gen
    from src.base.solver_factory import build_solver

    cap_oss, restore_oss = _patch_load_model(oss)
    cap_gen, restore_gen = _patch_load_model(gen)
    try:
        q = {"mode": "4bit", "compute_dtype": "float16"}
        solver = build_solver("hf_option_score", model_path="/fake/model", quantization=q)
        assert solver is not None
        assert cap_oss["quantization"] == q  # scorer received the quant config
    finally:
        restore_oss(); restore_gen()


def test_factory_passes_quantization_to_generate():
    from src.solvers import hf_generate_solver as gen
    from src.base.solver_factory import build_solver

    cap, restore = _patch_load_model(gen)
    try:
        q = {"mode": "8bit"}
        build_solver("hf_generate", model_path="/fake/model", quantization=q)
        assert cap["quantization"] == q
    finally:
        restore()


def test_default_solver_unaffected_by_quant():
    from src.base.baseline_solver import AlwaysASolver
    from src.base.solver_factory import build_solver
    # always_a ignores quantization entirely and needs no model.
    solver = build_solver("always_a", quantization={"mode": "4bit"})
    assert isinstance(solver, AlwaysASolver)


def test_existing_solver_constructs_with_default_quant():
    from src.solvers import hf_option_score_solver as oss
    from src.base.solver_factory import build_solver

    cap, restore = _patch_load_model(oss)
    try:
        build_solver("hf_option_score", model_path="/fake/model")  # no quantization arg
        assert cap["quantization"] is None  # default is no quantization
    finally:
        restore()


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
