"""Tests for the shared local Qwen backend without loading real weights."""

from __future__ import annotations

from src.local_model.local_qwen_backend import (
    build_mcq_prompt,
    get_local_qwen_backend,
    parse_json_object,
    parse_mcq_label,
    reset_local_qwen_backend_cache,
)
from src.local_model.qwen_mcq_predictor import QwenMCQPredictor


def test_singleton_reuses_one_backend_per_model_path_device():
    reset_local_qwen_backend_cache()
    a = get_local_qwen_backend("/tmp/model", device="auto")
    b = get_local_qwen_backend("/tmp/model", device="auto")
    c = get_local_qwen_backend("/tmp/model", device="cpu")
    assert a is b
    assert c is not a


def test_mcq_prompt_and_parser_preserve_answer_only_contract():
    prompt, labels = build_mcq_prompt({
        "question": "2 + 2 = ?",
        "choices": ["3", "4", "5", "6"],
    })
    assert "Đáp án (chỉ một chữ cái):" in prompt
    assert labels == ["A", "B", "C", "D"]
    assert parse_mcq_label("Đáp án: B", labels) == "B"
    assert parse_mcq_label("Z", labels) is None


def test_json_parser_handles_fenced_and_embedded_json():
    assert parse_json_object('{"answer":"A"}') == {"answer": "A"}
    assert parse_json_object('```json\n{"answer":"B"}\n```') == {"answer": "B"}
    assert parse_json_object('text {"answer":"C"} tail') == {"answer": "C"}
    assert parse_json_object("no json") is None


def test_qwen_predictor_facade_reuses_shared_backend():
    reset_local_qwen_backend_cache()
    p1 = QwenMCQPredictor("/tmp/model")
    p2 = QwenMCQPredictor("/tmp/model")
    assert p1._backend is p2._backend
