"""Tests for the OpenRouter client (no live API).

Runnable with pytest, or standalone: ``python tests/test_openrouter_client.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.api.openrouter_client import (  # noqa: E402
    DEFAULT_MODEL,
    OpenRouterClient,
    OpenRouterError,
    resolve_api_key,
)


def test_default_model():
    assert DEFAULT_MODEL == "qwen/qwen3.5-9b"


def test_missing_key_raises_clearly():
    # Hermetic "no key": pop env AND disable .env loading (a real .env may exist).
    import src.api.openrouter_client as oc
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    orig_dotenv = oc._maybe_load_dotenv
    oc._maybe_load_dotenv = lambda: None
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
        oc._maybe_load_dotenv = orig_dotenv
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


# --- Payload / header compatibility (no network) -----------------------------

def _client(**kw):
    return OpenRouterClient(api_key="dummy-key-not-real", **kw)


def test_endpoint_is_chat_completions():
    c = _client()
    assert c.base_url == "https://openrouter.ai/api/v1/chat/completions"
    assert "/responses" not in c.base_url and "/messages" not in c.base_url


def test_payload_uses_default_model():
    c = _client()
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 256)
    assert p["model"] == "qwen/qwen3.5-9b"


def test_payload_disables_stream_by_default():
    c = _client()
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 256)
    assert p.get("stream") is False


def test_payload_disables_reasoning_by_default():
    # Correctness-first: default explicitly sends {"enabled": false} so the
    # reasoning model does not eat the output budget (omitting it returns empty
    # content). Verified empirically in Phase 2K.2.
    c = _client()
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 256)
    assert p["reasoning"] == {"enabled": False}


def test_payload_reasoning_enabled_includes_exclude():
    c = _client(reasoning_enabled=True)  # reasoning_exclude defaults True
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 1024)
    assert p["reasoning"]["enabled"] is True
    assert p["reasoning"]["exclude"] is True


def test_payload_reasoning_max_tokens_included_when_set():
    c = _client(reasoning_enabled=True, reasoning_max_tokens=512)
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 2048)
    assert p["reasoning"]["max_tokens"] == 512
    assert p["reasoning"]["exclude"] is True


def test_payload_reasoning_effort_included_when_set():
    c = _client(reasoning_enabled=True, reasoning_effort="low")
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 1024)
    assert p["reasoning"]["effort"] == "low"


def test_payload_reasoning_disabled_ignores_other_fields():
    # When disabled, only {"enabled": false} is sent — no effort/max_tokens leak.
    c = _client(reasoning_enabled=False, reasoning_max_tokens=64, reasoning_effort="low")
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 256)
    assert p["reasoning"] == {"enabled": False}


def test_payload_includes_response_format_when_structured():
    from src.utils.structured_answer import response_format_schema
    c = _client()
    rf = response_format_schema()
    p = c.build_payload([{"role": "user", "content": "x"}], rf, 0.0, 256)
    assert p["response_format"] == rf
    # And omits it when not requested.
    p2 = c.build_payload([{"role": "user", "content": "x"}], None, 0.0, 256)
    assert "response_format" not in p2


def test_payload_core_fields_present():
    c = _client()
    p = c.build_payload([{"role": "user", "content": "x"}], None, 0.2, 128)
    for key in ("model", "messages", "temperature", "top_p", "max_tokens"):
        assert key in p
    assert p["temperature"] == 0.2 and p["max_tokens"] == 128


def test_headers_have_auth_and_content_type():
    c = _client()
    h = c.build_headers()
    assert h["Authorization"].startswith("Bearer ")
    assert h["Content-Type"] == "application/json"
    assert "X-Title" in h


def test_optional_http_referer_only_when_env_set():
    c = _client()
    saved = os.environ.pop("OPENROUTER_REFERER", None)
    try:
        assert "HTTP-Referer" not in c.build_headers()
        os.environ["OPENROUTER_REFERER"] = "https://example.org"
        assert c.build_headers().get("HTTP-Referer") == "https://example.org"
    finally:
        os.environ.pop("OPENROUTER_REFERER", None)
        if saved is not None:
            os.environ["OPENROUTER_REFERER"] = saved


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
