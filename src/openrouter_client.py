"""OpenRouter chat-completions provider (Round 1).

A thin, dependency-light client over OpenRouter's OpenAI-compatible
chat-completions endpoint. Used **only** with the competition-approved model
(default ``qwen/qwen3.5-9b``). No direct third-party model APIs (OpenAI, Gemini, Claude, etc.).

Design notes:
  * API key is read from ``OPENROUTER_API_KEY`` (env), or a git-ignored ``.env``
    if ``python-dotenv`` is installed. **The key is never logged.**
  * ``mock=True`` (or a ``responder`` callable) makes the client return canned
    responses without any network call — used by the test suite.
  * Retries with exponential backoff on transient errors (timeouts, 429, 5xx).
  * ``httpx`` is imported lazily, only when a real request is made.

A minimal :class:`ChatProvider` base keeps the door open for future providers
(direct/local) behind the same ``.chat()`` contract.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from .utils import log

DEFAULT_MODEL = "qwen/qwen3.5-9b"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
ENV_KEY = "OPENROUTER_API_KEY"


class OpenRouterError(RuntimeError):
    """Raised for missing key, exhausted retries, or bad responses."""


@dataclass
class ChatResult:
    """Normalised result of one chat call."""

    content: str
    model: str = ""
    response_id: str = ""
    usage: dict | None = None
    raw: dict | None = None


def _maybe_load_dotenv() -> None:
    """Load a git-ignored .env if python-dotenv is available (best effort)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path, override=False)


def resolve_api_key(explicit: str | None = None) -> str | None:
    """Return the API key from explicit arg → env → .env, or None if absent."""
    if explicit:
        return explicit
    if os.environ.get(ENV_KEY):
        return os.environ[ENV_KEY]
    _maybe_load_dotenv()
    return os.environ.get(ENV_KEY)


def api_key_available() -> bool:
    return bool(resolve_api_key())


class ChatProvider:
    """Minimal provider interface: turn messages into a :class:`ChatResult`."""

    def chat(self, messages: list[dict], *, response_format: dict | None = None,
             temperature: float | None = None, max_tokens: int | None = None) -> ChatResult:
        raise NotImplementedError


class OpenRouterClient(ChatProvider):
    """Chat client for OpenRouter (OpenAI-compatible schema)."""

    # HTTP statuses worth retrying.
    _RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}

    def __init__(self, *, model: str = DEFAULT_MODEL, api_key: str | None = None,
                 base_url: str = DEFAULT_BASE_URL, timeout_sec: float = 60.0,
                 max_retries: int = 3, temperature: float = 0.0, top_p: float = 1.0,
                 max_tokens: int = 512, reasoning_enabled: bool = False,
                 reasoning_effort: str | None = None, reasoning_max_tokens: int | None = None,
                 reasoning_exclude: bool = True, mock: bool = False, responder=None):
        self.model = model
        self.base_url = base_url
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        # Reasoning controls for reasoning-capable models (e.g. qwen3.5-9b). By
        # default OFF (no ``reasoning`` key) — the model decides. When enabled we
        # send a small, capped reasoning budget and exclude reasoning from output.
        self.reasoning_enabled = reasoning_enabled
        self.reasoning_effort = reasoning_effort
        self.reasoning_max_tokens = reasoning_max_tokens
        self.reasoning_exclude = reasoning_exclude
        self.mock = mock or (responder is not None)
        # ``responder(messages, **kw) -> str | dict`` lets tests script replies.
        self._responder = responder
        # Resolve (but never store/log) the key only for the real path.
        self._api_key = None if self.mock else resolve_api_key(api_key)

    def require_key(self) -> None:
        """Raise a clear error if no key is configured (no-op in mock mode)."""
        if self.mock:
            return
        if not self._api_key:
            raise OpenRouterError(
                f"{ENV_KEY} is not set. Export it (or put it in a git-ignored "
                ".env) to use the openrouter_graph solver. The key is never logged "
                "or committed; only OpenRouter is contacted."
            )

    def chat(self, messages: list[dict], *, response_format: dict | None = None,
             temperature: float | None = None, max_tokens: int | None = None) -> ChatResult:
        temp = self.temperature if temperature is None else temperature
        max_tok = self.max_tokens if max_tokens is None else max_tokens

        if self.mock:
            return self._mock_chat(messages, temperature=temp, max_tokens=max_tok)

        self.require_key()
        return self._http_chat(messages, response_format, temp, max_tok)

    # -- mock path ------------------------------------------------------------
    def _mock_chat(self, messages, *, temperature, max_tokens) -> ChatResult:
        if self._responder is not None:
            out = self._responder(messages, temperature=temperature, max_tokens=max_tokens)
            content = out if isinstance(out, str) else out.get("content", "")
            return ChatResult(content=content, model=self.model, response_id="mock",
                              usage=None, raw={"mock": True})
        # Default mock: an empty structured answer (caller will fallback).
        return ChatResult(content="{}", model=self.model, response_id="mock",
                          usage=None, raw={"mock": True})

    # -- request construction (pure; unit-testable without a network call) ----
    def build_payload(self, messages, response_format, temperature, max_tokens) -> dict:
        """Build the /chat/completions JSON body.

        Round-1 batch defaults: ``stream=False`` (non-streaming) and **no**
        ``reasoning`` field (reasoning tokens off — faster, and avoids storing
        private chain-of-thought). ``response_format`` is included only when
        structured output is requested.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": self.top_p,
            "max_tokens": max_tokens,
            "stream": False,           # explicit: non-streaming for batch CSV
        }
        if response_format is not None:
            payload["response_format"] = response_format
        # Reasoning control (correctness-first; evidence-based — Phase 2K.2).
        # `qwen/qwen3.5-9b` reasons BY DEFAULT: if the `reasoning` key is omitted,
        # it spends the whole completion budget on hidden reasoning and returns
        # EMPTY content (verified: omitting => 0/3 parseable; even enabling with a
        # max_tokens cap fails because the cap is ignored by the provider). The
        # only reliable fix is to send `reasoning.enabled` EXPLICITLY:
        #   * reasoning_enabled False (default) -> {"enabled": false}  => reasoning
        #     truly OFF -> non-empty content for every sample, fast, ~1 call.
        #   * reasoning_enabled True -> {"enabled": true, ...} plus configured
        #     exclude/max_tokens/effort (use a LARGE max_tokens so the answer fits).
        reasoning: dict = {"enabled": bool(self.reasoning_enabled)}
        if self.reasoning_enabled:
            if self.reasoning_exclude is not None:
                reasoning["exclude"] = bool(self.reasoning_exclude)
            if self.reasoning_max_tokens is not None:
                reasoning["max_tokens"] = int(self.reasoning_max_tokens)
            if self.reasoning_effort is not None:
                reasoning["effort"] = self.reasoning_effort
        payload["reasoning"] = reasoning
        return payload

    def build_headers(self) -> dict:
        """Build request headers. The API key is read here and never logged."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": "FastMCQ-Agent",  # optional attribution (no PII)
        }
        referer = os.environ.get("OPENROUTER_REFERER")
        if referer:  # optional HTTP-Referer if the user configures one
            headers["HTTP-Referer"] = referer
        return headers

    # -- real HTTP path -------------------------------------------------------
    def _http_chat(self, messages, response_format, temperature, max_tokens) -> ChatResult:
        import httpx  # lazy: only needed for real calls

        payload = self.build_payload(messages, response_format, temperature, max_tokens)
        headers = self.build_headers()

        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    resp = client.post(self.base_url, headers=headers, json=payload)
                if resp.status_code in self._RETRY_STATUS:
                    last_err = OpenRouterError(f"HTTP {resp.status_code}")
                    raise last_err
                if resp.status_code != 200:
                    # Non-retryable: surface a clean error without the key.
                    raise OpenRouterError(
                        f"OpenRouter returned HTTP {resp.status_code}: "
                        f"{resp.text[:300]}"
                    )
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage")
                log(f"openrouter ok: model={data.get('model', self.model)} "
                    f"id={data.get('id', '')} usage={usage}")
                return ChatResult(content=content, model=data.get("model", self.model),
                                  response_id=data.get("id", ""), usage=usage, raw=data)
            except OpenRouterError as exc:
                last_err = exc
            except Exception as exc:  # network/timeout/parse — retry
                last_err = OpenRouterError(f"{type(exc).__name__}: {exc}")

            if attempt < self.max_retries:
                backoff = 2 ** attempt
                log(f"openrouter retry {attempt + 1}/{self.max_retries} after {backoff}s "
                    f"({last_err})")
                time.sleep(backoff)

        raise OpenRouterError(f"OpenRouter request failed after "
                              f"{self.max_retries + 1} attempts: {last_err}")
