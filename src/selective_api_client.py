"""Thin OpenRouter wrapper for selective multi-candidate calls (Phase 2L.26A).

Enforces the competition model policy (``assert_allowed_llm_model``) at construction
AND on every call, retries transient failures, and exposes a strict-JSON helper +
usage. The underlying client is injected (the real ``OpenRouterClient`` for execution,
a fake in tests) — this module never hard-codes a network call and is import-safe.
"""

from __future__ import annotations

import json
import re
import time

from src.model_policy import assert_allowed_llm_model


def _valid_messages(messages) -> bool:
    """True iff ``messages`` is a non-empty prompt: a non-empty/whitespace string, or a
    non-empty list of {role, content} dicts with at least one non-empty content."""
    if messages is None:
        return False
    if isinstance(messages, str):
        return bool(messages.strip())
    if isinstance(messages, (list, tuple)):
        if not messages:
            return False
        ok = False
        for m in messages:
            if not isinstance(m, dict):
                return False
            if str(m.get("content") or "").strip():
                ok = True
        return ok
    return False


class SelectiveAPIClient:
    def __init__(self, model: str, *, client=None, temperature: float = 0.0,
                 max_tokens: int = 768, max_retries: int = 2):
        # Hard guard: refuse to even construct with a disallowed model.
        assert_allowed_llm_model(model)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._client = client
        self.total_calls = 0
        self.total_tokens = 0

    def _ensure_client(self):
        if self._client is None:   # pragma: no cover - real client only at execute time
            from src.openrouter_client import OpenRouterClient
            self._client = OpenRouterClient(model=self.model)
        return self._client

    def chat(self, messages, *, temperature=None, max_tokens=None):
        """Make one chat call (guarded, retried). Returns (content, usage_dict)."""
        # Defensive guard (raised BEFORE the retry loop so it is not swallowed/retried):
        # never send an empty/invalid prompt to the API.
        if not _valid_messages(messages):
            raise ValueError(
                "empty prompt passed to SelectiveAPIClient.chat: expected a non-empty "
                "messages list [{'role','content'}, ...] or a non-empty string; got "
                f"{type(messages).__name__}")
        assert_allowed_llm_model(self.model)   # re-assert on every call
        client = self._ensure_client()
        temp = self.temperature if temperature is None else temperature
        mt = self.max_tokens if max_tokens is None else max_tokens
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                res = client.chat(messages, response_format={"type": "json_object"},
                                  temperature=temp, max_tokens=mt)
                self.total_calls += 1
                usage = getattr(res, "usage", None) or {}
                self.total_tokens += int(usage.get("total_tokens") or 0)
                return getattr(res, "content", ""), usage
            except Exception as exc:        # pragma: no cover - transient/path varies
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"chat failed after {self.max_retries + 1} attempts: {last_exc}")

    @staticmethod
    def parse_json(content):
        if not content:
            return None
        txt = content.strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", txt).strip()
        try:
            return json.loads(txt)
        except Exception:
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
        return None
