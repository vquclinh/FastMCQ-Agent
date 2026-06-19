"""Tests for the model-compliance checker logic.

Runnable with pytest, or standalone: ``python tests/test_model_compliance.py``.
No torch/transformers needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.utils import load_config  # noqa: E402
from check_model_compliance import evaluate  # noqa: E402

CONFIG = load_config(str(ROOT / "configs" / "allowed_models.yaml"))


def test_config_loads():
    assert CONFIG, "allowed_models.yaml should load (PyYAML available)"
    assert "generation_llms" in CONFIG


def test_allowed_qwen_passes():
    verdict, _ = evaluate("Qwen3.5-7B", None, CONFIG)
    assert verdict == "PASS"


def test_allowed_gemma_passes():
    verdict, _ = evaluate("gemma-4-9b-it", None, CONFIG)
    assert verdict == "PASS"


def test_embedding_family_passes():
    assert evaluate("bge-m3", None, CONFIG)[0] == "PASS"


def test_disallowed_family_fails():
    for name in ("DeepSeek-7B", "Llama-3-8B", "Mistral-7B", "phi-3"):
        verdict, _ = evaluate(name, None, CONFIG)
        assert verdict == "FAIL", f"{name} should FAIL"


def test_oversized_qwen_fails():
    verdict, msgs = evaluate("Qwen3.5-14B", None, CONFIG)
    assert verdict == "FAIL"
    assert any("exceeds" in m for m in msgs)


def test_unknown_model_warns():
    verdict, _ = evaluate("MysteryModel-3B", None, CONFIG)
    assert verdict == "WARNING"


def test_path_basename_is_checked():
    verdict, _ = evaluate(None, "/models/Qwen3.5-7B-Instruct", CONFIG)
    assert verdict == "PASS"


def test_empty_input_fails():
    verdict, _ = evaluate(None, None, CONFIG)
    assert verdict == "FAIL"


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
