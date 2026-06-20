"""Tests for the OpenRouter client (no live API).

Runnable with pytest, or standalone: ``python tests/test_openrouter_client.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.openrouter_client import (  # noqa: E402
    DEFAULT_MODEL,
    OpenRouterClient,
    OpenRouterError,
    resolve_api_key,
)


def test_default_model():
    assert DEFAULT_MODEL == "qwen/qwen3.5-9b"


def test_missing_key_raises_clearly():
    # Ensure no key in env for this check.
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        client = OpenRouterClient(mock=False)
        raised = False
        try:
            client.require_key()
        except OpenRouterError as exc:
            raised = True
            assert "OPENROUTER_API_KEY" in str(exc)
        assert raised
    finally:
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved


def test_mock_responder_returns_content():
    def responder(messages, **kw):
        return '{"answer": "B", "confidence": 0.8}'
    client = OpenRouterClient(responder=responder)
    result = client.chat([{"role": "user", "content": "hi"}])
    assert result.content == '{"answer": "B", "confidence": 0.8}'
    assert result.model == DEFAULT_MODEL


def test_mock_mode_needs_no_key():
    # mock=True must not require a key and must not touch the network.
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    try:
        client = OpenRouterClient(mock=True)
        client.require_key()  # no-op in mock mode
        out = client.chat([{"role": "user", "content": "x"}])
        assert out.content == "{}"  # default mock content
    finally:
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved


def test_resolve_api_key_prefers_explicit():
    assert resolve_api_key("explicit-key") == "explicit-key"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
