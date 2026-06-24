"""Tests for the competition model-policy guard + repo audit (Phase 2L.26A)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.model_policy import (assert_allowed_llm_model, assert_allowed_rerank_model,
                              is_allowed_llm_model, is_allowed_rerank_model)


def test_allowed_llms():
    for m in ("qwen/qwen3.5-9b", "qwen/qwen3.5-9b-20260310", "gemma-4-9b", "google/gemma-4-9b-it"):
        assert is_allowed_llm_model(m), m


def test_rejected_llms():
    for m in ("gpt-4o", "openai/gpt-4", "claude-opus-4-8", "anthropic/claude-3",
              "gemini-1.5-pro", "deepseek-chat", "meta-llama/llama-3-70b",
              "qwen/qwen2.5-14b", "qwen/qwen3.5-32b", "qwen/qwen3.5-72b", "gemma-2-9b",
              "mistral-large", ""):
        assert not is_allowed_llm_model(m), m


def test_assert_llm_raises_on_disallowed():
    assert_allowed_llm_model("qwen/qwen3.5-9b")           # no raise
    for bad in ("gpt-4o", "claude-3", "gemini-1.5", "qwen/qwen3.5-14b"):
        try:
            assert_allowed_llm_model(bad)
            assert False, f"should raise for {bad}"
        except ValueError:
            pass


def test_allowed_rerank():
    for m in ("BAAI/bge-m3", "models/qwen3-reranker-0.6b", "Qwen-Rerank", "bge_m3"):
        assert is_allowed_rerank_model(m), m


def test_rejected_rerank():
    for m in ("openai/text-embedding-3-large", "sentence-transformers/all-MiniLM", "random"):
        assert not is_allowed_rerank_model(m), m
    try:
        assert_allowed_rerank_model("openai/text-embedding-3")
        assert False
    except ValueError:
        pass


# --- repo audit scanner -------------------------------------------------------

def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "amp", _ROOT / "scripts" / "tools" / "audit_model_policy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_passes_on_clean_repo():
    mod = _load_audit()
    assert mod.main([]) == 0       # current repo references only allowed models


def test_audit_detects_disallowed_in_runtime_file():
    mod = _load_audit()
    d = Path(tempfile.mkdtemp())
    bad = d / "bad_config.yaml"
    bad.write_text("base_solver: openrouter_graph\nmodel: gpt-4o\n")
    findings = mod._scan_file(bad)
    assert findings, "scanner must flag a disallowed model id in a runtime file"
    assert any("gpt" in f[2].lower() for f in findings)


def test_audit_ignores_external_sheet_columns():
    mod = _load_audit()
    d = Path(tempfile.mkdtemp())
    ok = d / "diag.py"
    ok.write_text('fields = ["gemini_answer", "gpt_answer", "claude_answer"]\n')
    # column names (no version/slash) are NOT flagged as model selection
    assert mod._scan_file(ok) == []
