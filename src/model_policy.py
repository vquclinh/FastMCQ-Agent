"""Competition model-policy guard (Phase 2L.26A).

Single source of truth for which LLM and embedding/rerank models are allowed by the
competition rules. Every API / model-loading path MUST call the assert_* guards
BEFORE constructing or sending a request, so a disallowed model can never be used —
no GPT/OpenAI, Claude/Anthropic, Gemini, DeepSeek, Llama/Mistral, or Qwen models
larger than 9B, and no arbitrary "gemma" string.

Allowed LLMs:
  * Qwen3.5 Series, size <= 9B  (e.g. qwen/qwen3.5-9b, qwen/qwen3.5-9b-20260310)
  * Gemma-4 Series — ONLY via explicit approved aliases in APPROVED_GEMMA_ALIASES
Allowed embedding/rerank:
  * BGE-M3, Qwen-Rerank (incl. local models/qwen3-reranker-0.6b)
"""

from __future__ import annotations

import re

# Vendors / families that are never allowed (substring match, case-insensitive).
_BANNED_TOKENS = (
    "gpt", "openai", "o1", "o3", "o4",
    "claude", "anthropic",
    "gemini", "palm", "bison",
    "deepseek", "llama", "mistral", "mixtral", "grok", "command-r", "cohere",
    "phi-", "yi-", "glm", "ernie",
)

# Explicit, competition-approved Gemma-4 aliases (size <= 9B). Empty unless configured;
# add only ids the rules explicitly approve. Arbitrary "gemma" strings are rejected.
APPROVED_GEMMA_ALIASES = (
    "google/gemma-4-9b", "google/gemma-4-9b-it", "gemma-4-9b", "gemma-4-9b-it",
)

# Allowed embedding/rerank substrings.
_ALLOWED_RERANK = ("bge-m3", "bge_m3", "qwen3-reranker", "qwen-reranker", "qwen-rerank",
                   "models/qwen3-reranker-0.6b")

_SIZE_RE = re.compile(r"-(\d+(?:\.\d+)?)\s*b\b")


def _norm(name) -> str:
    return str(name or "").strip().lower()


def _size_billions(name: str):
    """Parse the parameter size in billions from an id like 'qwen3.5-9b' -> 9.0."""
    m = _SIZE_RE.search(name)
    return float(m.group(1)) if m else None


def is_allowed_llm_model(model_name: str) -> bool:
    name = _norm(model_name)
    if not name:
        return False
    if any(tok in name for tok in _BANNED_TOKENS):
        return False
    # Gemma-4: only explicit approved aliases.
    if "gemma" in name:
        return name in {a.lower() for a in APPROVED_GEMMA_ALIASES}
    # Qwen3.5 series, size <= 9B.
    if "qwen3.5" in name or "qwen-3.5" in name or "qwen3_5" in name:
        size = _size_billions(name)
        return size is None or size <= 9.0
    return False


def assert_allowed_llm_model(model_name: str) -> None:
    if not is_allowed_llm_model(model_name):
        raise ValueError(
            f"disallowed LLM model {model_name!r}: competition allows only Qwen3.5 "
            f"(<=9B) or approved Gemma-4 aliases. No GPT/Claude/Gemini/DeepSeek/Llama "
            f"and no Qwen >9B.")


def is_allowed_rerank_model(model_name: str) -> bool:
    name = _norm(model_name)
    if not name:
        return False
    if any(tok in name for tok in _BANNED_TOKENS):
        return False
    return any(tok in name for tok in _ALLOWED_RERANK)


def assert_allowed_rerank_model(model_name: str) -> None:
    if not is_allowed_rerank_model(model_name):
        raise ValueError(
            f"disallowed rerank/embedding model {model_name!r}: competition allows only "
            f"BGE-M3 / Qwen-Rerank (e.g. models/qwen3-reranker-0.6b).")
