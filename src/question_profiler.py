"""Deterministic question profiling — cheap features, no LLM call.

Computes a :class:`QuestionProfile` of transparent, reproducible signals used by
the router and budget controller. There is **no** torch/transformers dependency
here, so this module is fully testable without a model.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# --- Signal vocabularies (Vietnamese) ----------------------------------------

LONG_CONTEXT_MARKERS = (
    "Đoạn thông tin", "Nội dung:", "Tiêu đề:", "-- Đoạn văn",
    "Đọc đoạn", "Dựa vào đoạn", "Theo đoạn",
)
TITLE_MARKERS = ("Tiêu đề:",)
PASSAGE_MARKERS = ("Đoạn thông tin", "Nội dung:", "-- Đoạn văn", "Đọc đoạn")

# Math / calculation symbols (LaTeX handled separately).
MATH_SYMBOLS = ("%", "=", "+", "×", "*", "/", "^", "√")
MATH_FUNCS = ("log", "sin", "cos", "tan")
LATEX_MARKERS = (r"\(", r"\)", r"\frac", r"\sqrt", "$")

LEGAL_KEYWORDS = (
    "luật", "nghị định", "thông tư", "điều", "khoản", "quy định",
    "cơ quan", "hành chính", "chính phủ", "bộ trưởng",
)
SAFETY_KEYWORDS = ("an toàn", "nguy hiểm", "rủi ro", "bảo mật", "riêng tư")
ETHICS_KEYWORDS = ("đạo đức", "không nên", "phù hợp")

_DIGIT_RE = re.compile(r"\d")


def _count_occurrences(text: str, needles) -> int:
    """Total number of (case-insensitive) occurrences of any needle in text."""
    low = text.lower()
    return sum(low.count(n.lower()) for n in needles)


def _normalize_choice(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


@dataclass
class QuestionProfile:
    """Cheap, deterministic features describing one MCQ sample."""

    qid: str
    question_length: int
    num_choices: int
    choice_lengths: list
    has_long_context_marker: bool
    has_title_marker: bool
    has_passage_marker: bool
    numeric_count: int
    numeric_density: float
    math_symbol_count: int
    latex_marker_count: int
    legal_keyword_count: int
    safety_keyword_count: int
    ethics_keyword_count: int
    duplicate_choice_groups: list
    estimated_difficulty: str
    raw_signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _duplicate_choice_groups(choices) -> list:
    """Return groups of labels (0-based indices) whose normalized text is equal.

    Only groups with >1 member are returned, e.g. ``[[1, 3]]`` if choices B and D
    are identical after normalization.
    """
    buckets: dict[str, list] = {}
    for i, c in enumerate(choices):
        buckets.setdefault(_normalize_choice(c), []).append(i)
    return [idx for idx in buckets.values() if len(idx) > 1]


def profile_question(sample: dict) -> QuestionProfile:
    """Compute the :class:`QuestionProfile` for a normalized sample."""
    qid = str(sample.get("qid", ""))
    question = str(sample.get("question", "") or "")
    choices = sample.get("choices", []) or []

    q_len = len(question)
    num_choices = len(choices)
    choice_lengths = [len(str(c)) for c in choices]

    has_long = any(m in question for m in LONG_CONTEXT_MARKERS)
    has_title = any(m in question for m in TITLE_MARKERS)
    has_passage = any(m in question for m in PASSAGE_MARKERS)

    numeric_count = len(_DIGIT_RE.findall(question))
    numeric_density = numeric_count / max(1, q_len)

    math_symbol_count = _count_occurrences(question, MATH_SYMBOLS) \
        + _count_occurrences(question, MATH_FUNCS)
    latex_marker_count = sum(question.count(m) for m in LATEX_MARKERS)

    legal = _count_occurrences(question, LEGAL_KEYWORDS)
    safety = _count_occurrences(question, SAFETY_KEYWORDS)
    ethics = _count_occurrences(question, ETHICS_KEYWORDS)

    dup_groups = _duplicate_choice_groups(choices)

    # Fraction of choices that look numeric (used by difficulty + router).
    numeric_choices = sum(1 for c in choices if _DIGIT_RE.search(str(c)))
    numeric_choice_ratio = numeric_choices / max(1, num_choices)

    is_calculation = (
        latex_marker_count > 0
        or math_symbol_count >= 2
        or (numeric_density > 0.02 and numeric_choice_ratio > 0.5)
    )

    difficulty = _estimate_difficulty(
        has_long=has_long, is_calculation=is_calculation,
        num_choices=num_choices, q_len=q_len,
    )

    raw_signals = {
        "numeric_choice_ratio": round(numeric_choice_ratio, 3),
        "is_calculation": is_calculation,
        "long_context_markers_hit": [m for m in LONG_CONTEXT_MARKERS if m in question],
        "legal_keyword_count": legal,
        "safety_keyword_count": safety,
        "ethics_keyword_count": ethics,
    }

    return QuestionProfile(
        qid=qid,
        question_length=q_len,
        num_choices=num_choices,
        choice_lengths=choice_lengths,
        has_long_context_marker=has_long,
        has_title_marker=has_title,
        has_passage_marker=has_passage,
        numeric_count=numeric_count,
        numeric_density=round(numeric_density, 4),
        math_symbol_count=math_symbol_count,
        latex_marker_count=latex_marker_count,
        legal_keyword_count=legal,
        safety_keyword_count=safety,
        ethics_keyword_count=ethics,
        duplicate_choice_groups=dup_groups,
        estimated_difficulty=difficulty,
        raw_signals=raw_signals,
    )


def _estimate_difficulty(*, has_long: bool, is_calculation: bool,
                         num_choices: int, q_len: int) -> str:
    """Transparent difficulty heuristic: easy / medium / hard."""
    many_choices = num_choices >= 8
    if (has_long and many_choices) or (is_calculation and many_choices):
        return "hard"
    if has_long or is_calculation or num_choices >= 6 or q_len > 800:
        return "medium"
    return "easy"
