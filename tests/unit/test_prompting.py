"""Tests for prompt construction.

Runnable with pytest, or standalone: ``python tests/test_prompting.py``.
No torch/transformers needed — everything uses char-based budgets.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.prompting import (  # noqa: E402
    build_mcq_prompt,
    detect_question_shape,
    format_choices,
    truncate_question,
)


def test_format_choices_dynamic_labels():
    assert format_choices(["x", "y"]).splitlines() == ["A. x", "B. y"]
    four = format_choices(["a", "b", "c", "d"]).splitlines()
    assert four == ["A. a", "B. b", "C. c", "D. d"]
    # 10 and 11 choices must extend past D, into E..K.
    ten = format_choices([str(i) for i in range(10)]).splitlines()
    assert ten[0] == "A. 0" and ten[-1] == "J. 9"
    eleven = format_choices([str(i) for i in range(11)]).splitlines()
    assert eleven[-1] == "K. 10"


def test_detect_question_shape():
    long_ctx = {"question": "Đoạn thông tin: ... Tiêu đề: X", "choices": ["a", "b"]}
    assert detect_question_shape(long_ctx) == "long_context"

    calc = {"question": "Tính đạo hàm của hàm số", "choices": ["1", "2", "3", "4"]}
    assert detect_question_shape(calc) == "calculation"

    numeric = {"question": "Kết quả là gì?", "choices": ["0.5", "1.0", "2.0"]}
    assert detect_question_shape(numeric) == "calculation"

    short = {"question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon"]}
    assert detect_question_shape(short) == "short_knowledge"


def test_prompt_includes_all_choices():
    sample = {"question": "Câu hỏi?", "choices": ["alpha", "beta", "gamma", "delta"]}
    prompt = build_mcq_prompt(sample)
    for label, text in zip("ABCD", sample["choices"]):
        assert f"{label}. {text}" in prompt


def test_prompt_asks_for_single_label():
    sample = {"question": "Q?", "choices": ["a", "b", "c"]}
    prompt = build_mcq_prompt(sample, mode="direct").lower()
    assert "một" in prompt  # "đúng MỘT chữ cái"
    assert "không giải thích" in prompt


def test_score_prompt_ends_with_stem():
    sample = {"question": "Q?", "choices": ["a", "b"]}
    prompt = build_mcq_prompt(sample, mode="score")
    assert prompt.rstrip().endswith("Đáp án đúng là:")


def test_long_question_truncation_keeps_choices():
    # Build a very long question; choices must still appear in full after truncation.
    long_q = "Đoạn thông tin: " + ("rất dài " * 5000) + " Câu hỏi cuối cùng ở đây?"
    sample = {"question": long_q, "choices": ["lựa chọn một", "lựa chọn hai",
                                              "lựa chọn ba", "lựa chọn bốn"]}
    prompt = build_mcq_prompt(sample)  # char-budget path (no tokenizer)
    for label, text in zip("ABCD", sample["choices"]):
        assert f"{label}. {text}" in prompt
    # Head-tail truncation should keep both the start and the trailing question.
    assert "[...]" in prompt
    assert "Câu hỏi cuối cùng ở đây?" in prompt


def test_truncate_question_short_passthrough():
    q = "Một câu hỏi ngắn."
    assert truncate_question(q, max_chars=1000) == q


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
