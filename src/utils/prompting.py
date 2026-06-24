"""Prompt construction for MCQ solvers.

All prompts are in Vietnamese, enumerate every choice with a dynamic label
(A, B, C, ... sized to the actual number of choices), and instruct the model to
output only a single label.

Two prompt modes:
  * ``"direct"`` — for the generation solver: the model is asked to reply with
    just the label.
  * ``"score"``  — for the option-scoring solver: the prompt ends with
    ``"Đáp án đúng là:"`` so each candidate label can be scored as a continuation.

The module has **no** torch/transformers dependency. A ``tokenizer`` may be
passed for token-accurate truncation, but everything also works with plain
character budgets so it is fully testable without heavy deps.
"""

from __future__ import annotations

import re

from src.utils.labels import labels_for

# Keywords that mark an embedded long-context passage (same set as the profiler).
CONTEXT_KEYWORDS = ("Đoạn thông tin", "Nội dung:", "Tiêu đề:", "-- Đoạn văn")

# Signals that a question is a calculation/STEM item.
_LATEX_RE = re.compile(r"\$.+?\$|\\frac|\\sqrt|\\times|\\sum|\\int")
_DIGIT_RE = re.compile(r"\d")
_CALC_KEYWORDS = (
    "tính", "đạo hàm", "tích phân", "phương trình", "xác suất", "vận tốc",
    "gia tốc", "bao nhiêu", "giá trị của", "nồng độ", "khối lượng",
)

# When no explicit budget is given, this character cap keeps prompts sane.
DEFAULT_MAX_CHARS = 6000


def format_choices(choices: list[str]) -> str:
    """Render choices as ``A. text`` lines with dynamic labels, one per line."""
    labels = labels_for(len(choices))
    return "\n".join(f"{label}. {str(text).strip()}" for label, text in zip(labels, choices))


def _choices_are_numeric(choices: list[str]) -> bool:
    if not choices:
        return False
    numeric = sum(1 for c in choices if _DIGIT_RE.search(str(c)))
    return numeric / len(choices) > 0.6


def detect_question_shape(sample: dict) -> str:
    """Classify a sample as ``long_context``, ``calculation`` or ``short_knowledge``.

    Priority: an embedded passage wins (it dominates prompt budgeting), then
    calculation signals, otherwise a short knowledge question.
    """
    question = sample.get("question", "") or ""
    choices = sample.get("choices", []) or []

    if any(kw in question for kw in CONTEXT_KEYWORDS):
        return "long_context"

    lowered = question.lower()
    if (_LATEX_RE.search(question)
            or _choices_are_numeric(choices)
            or any(kw in lowered for kw in _CALC_KEYWORDS)):
        return "calculation"

    return "short_knowledge"


def _measure(text: str, tokenizer) -> int:
    """Length of ``text`` in tokens (if a tokenizer is given) else characters."""
    if tokenizer is None:
        return len(text)
    return len(tokenizer.encode(text, add_special_tokens=False))


def truncate_question(question, tokenizer=None, max_input_tokens=None, max_chars=None) -> str:
    """Head-tail truncate a question to fit a budget, preserving its ends.

    Long passage questions usually carry the actual question at the *end*, after
    the passage. So when we must cut, we keep the **beginning** of the passage
    (topic/setup) and the **final** section (the question itself), dropping the
    middle and marking it with an ellipsis.

    Budget: ``max_input_tokens`` (token-based, needs a tokenizer) takes priority;
    otherwise ``max_chars`` (or :data:`DEFAULT_MAX_CHARS`) is used. The budget
    here is for the *question only* — callers reserve room for choices and the
    instruction separately.
    """
    question = str(question)

    use_tokens = tokenizer is not None and max_input_tokens is not None
    budget = max_input_tokens if use_tokens else (max_chars or DEFAULT_MAX_CHARS)
    measure = (lambda t: _measure(t, tokenizer)) if use_tokens else len

    if measure(question) <= budget:
        return question

    marker = "\n[...]\n"
    marker_cost = measure(marker)
    remaining = max(budget - marker_cost, 0)
    # Give ~60% to the head (passage setup) and ~40% to the tail (the question).
    head_budget = int(remaining * 0.6)
    tail_budget = remaining - head_budget

    if use_tokens:
        ids = tokenizer.encode(question, add_special_tokens=False)
        head_ids = ids[:head_budget]
        tail_ids = ids[len(ids) - tail_budget:] if tail_budget else []
        head = tokenizer.decode(head_ids)
        tail = tokenizer.decode(tail_ids)
    else:
        head = question[:head_budget]
        tail = question[len(question) - tail_budget:] if tail_budget else ""

    return f"{head}{marker}{tail}"


def _instruction(shape: str, mode: str) -> str:
    """Return the shape-aware instruction line(s) for the prompt."""
    if shape == "long_context":
        guidance = "Chỉ dựa vào đoạn thông tin được cung cấp ở trên để trả lời."
    elif shape == "calculation":
        guidance = "Bạn có thể tính toán trong đầu, nhưng chỉ in ra nhãn đáp án."
    else:
        guidance = "Hãy chọn đáp án đúng nhất."

    if mode == "score":
        # The score prompt ends with the stem; no "output only the label" line,
        # because we score label continuations rather than read generated text.
        return guidance
    return (
        f"{guidance}\n"
        "Chỉ trả lời bằng đúng MỘT chữ cái nhãn đáp án (ví dụ: A). "
        "Không giải thích, không viết gì thêm."
    )


def build_mcq_prompt(sample: dict, mode: str = "direct", tokenizer=None,
                     max_input_tokens=None) -> str:
    """Build a full MCQ prompt for ``sample``.

    Choices are always included in full (never truncated); only the question
    text is trimmed, head-tail, to fit ``max_input_tokens`` when needed.
    """
    if mode not in ("direct", "score"):
        raise ValueError(f"unknown prompt mode {mode!r} (expected 'direct' or 'score')")

    choices = sample.get("choices", []) or []
    shape = detect_question_shape(sample)
    choices_block = format_choices(choices)
    instruction = _instruction(shape, mode)

    # Reserve budget for everything that is NOT the question, so choices and the
    # instruction always survive. Static scaffolding is small; we add a margin.
    question = sample.get("question", "") or ""
    if max_input_tokens is not None:
        fixed = (
            _measure(choices_block, tokenizer)
            + _measure(instruction, tokenizer)
            + 64  # margin for headers, labels, special tokens
        )
        question_budget = max(max_input_tokens - fixed, 64)
        question = truncate_question(
            question, tokenizer=tokenizer, max_input_tokens=question_budget
        )
    else:
        question = truncate_question(question, max_chars=DEFAULT_MAX_CHARS)

    header = "Hãy đọc câu hỏi trắc nghiệm sau và chọn đáp án đúng."
    body = (
        f"{header}\n\n"
        f"Câu hỏi:\n{question}\n\n"
        f"Các lựa chọn:\n{choices_block}\n\n"
        f"{instruction}"
    )

    if mode == "score":
        body += "\nĐáp án đúng là:"
    else:
        body += "\nĐáp án:"
    return body
