"""Unit tests for the hardened local MCQ answer-label parser (AUDIT 65).

`parse_mcq_label` must never scan arbitrary prose for the first A–K letter and
must never silently pick 'A'. It returns exactly one allowed label or None so the
caller applies its own deterministic fallback. No model, GPU, network, or API.
"""

from __future__ import annotations

import pytest

from src.local_model.local_qwen_backend import parse_mcq_label

ABCD = list("ABCD")
ABC = list("ABC")
AJ = list("ABCDEFGHIJ")


# --- Priority 2: bare labels ------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("A", "A"), ("b", "B"), ("C.", "C"), ("(D)", "D"), ("[B]", "B"),
    ("  b  ", "B"), ("B,", "B"), ("B:", "B"),
])
def test_bare_labels(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


def test_brace_wrapped_is_treated_as_json_not_label():
    # "{B}" is malformed JSON with no answer field -> conservative no-match.
    assert parse_mcq_label("{B}", ABCD) is None


# --- Priority 1: structured JSON --------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ('{"answer":"B"}', "B"),
    ('{"label":"c"}', "C"),
    ('{"choice":"D"}', "D"),
    ('{"ANSWER":"A"}', "A"),
    ('{"answer":"Option D"}', "D"),
    ('```json\n{"answer":"A"}\n```', "A"),
    ('```\n{"choice":"B"}\n```', "B"),
])
def test_structured_json(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


@pytest.mark.parametrize("text", [
    '{"answer":"Grace Hopper"}',
    '{"answer":"A or B"}',
    '{"answer":"Z"}',
    '{"answer":""}',
    '{"reason":"no answer key here"}',
    '{"answer":"maybe B maybe C"}',
])
def test_structured_json_rejected(text):
    assert parse_mcq_label(text, ABCD) is None


# --- Priority 3: explicit Vietnamese markers --------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Đáp án: B", "B"),
    ("Đáp án là C", "C"),
    ("Đáp án đúng là D.", "D"),
    ("Lựa chọn đúng là A", "A"),
    ("Lựa chọn: C", "C"),
    ("Tôi chọn B", "B"),
    ("Chọn đáp án C", "C"),
])
def test_vietnamese_markers(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


# --- Priority 3: explicit English markers -----------------------------------
@pytest.mark.parametrize("text,expected", [
    ("Answer: B", "B"),
    ("The answer is B.", "B"),
    ("Final answer: C", "C"),
    ("Final answer: (D)", "D"),
    ("Option D", "D"),
    ("Choice A", "A"),
    ("The answer is clearly option B.", "B"),
    ("The answer is clearly option C.", "C"),
    ("The answer is option A", "A"),
])
def test_english_markers(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


# --- Confirmed regressions from AUDIT 64 ------------------------------------
def test_audit64_regressions():
    # "The answer is ... B" must be B, never A (the 'a' in "answer").
    assert parse_mcq_label("The answer is clearly option B.", ABCD) == "B"
    assert parse_mcq_label("The answer is clearly option C.", ABCD) == "C"
    # A person's name must not be mined for a label.
    assert parse_mcq_label("Grace Hopper", ABCD) is None
    assert parse_mcq_label("Grace Hopper", AJ) is None   # even when G is allowed


# --- Ambiguous / invalid ----------------------------------------------------
@pytest.mark.parametrize("text", [
    "A or B", "A/B", "ABC", "No answer", "The answer cannot be determined",
    "Answer: Z", "Either A or C", "It may be B, but perhaps C",
    "The model is uncertain", "Because the answer depends on context",
    "Answer", "Because", "Banana", "Candidate", "",
])
def test_ambiguous_or_invalid_return_none(text):
    assert parse_mcq_label(text, ABCD) is None


# --- Multiple mentions with a clear final answer ----------------------------
@pytest.mark.parametrize("text,expected", [
    ("A seems possible, but final answer: B", "B"),
    ("Option C was considered. The answer is D.", "D"),
])
def test_final_answer_overrides_earlier_mentions(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


# --- Priority 4: conservative isolated final label --------------------------
@pytest.mark.parametrize("text,expected", [
    ("Sau khi phân tích, tôi chọn B", "B"),
    ("Therefore: C", "C"),
])
def test_isolated_final_label(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


# --- Dynamic allowed-label ranges -------------------------------------------
def test_three_choice_range():
    for lab in ("A", "B", "C"):
        assert parse_mcq_label(lab, ABC) == lab
    assert parse_mcq_label("D", ABC) is None
    assert parse_mcq_label("Answer: D", ABC) is None


def test_four_choice_range():
    for lab in ("A", "B", "C", "D"):
        assert parse_mcq_label(lab, ABCD) == lab
    assert parse_mcq_label("E", ABCD) is None
    assert parse_mcq_label("Answer: E", ABCD) is None


def test_ten_choice_range():
    for lab in AJ:
        assert parse_mcq_label(lab, AJ) == lab
    assert parse_mcq_label("K", AJ) is None
    assert parse_mcq_label("Đáp án: J", AJ) == "J"
    assert parse_mcq_label("Đáp án: K", AJ) is None


# --- Words containing label characters must not match -----------------------
@pytest.mark.parametrize("text", ["Answer", "Because", "Grace Hopper", "Banana", "Candidate"])
def test_words_with_label_chars_return_none(text):
    assert parse_mcq_label(text, ABCD) is None


# --- Case / whitespace / punctuation / Unicode / newlines -------------------
@pytest.mark.parametrize("text,expected", [
    ("  b  ", "B"),
    ("\r\n C \r\n", "C"),
    ("đáp án: d", "D"),
    ("ĐÁP ÁN: A", "A"),
    ("answer:\tB", "B"),
    ("(b).", "B"),
])
def test_case_whitespace_unicode(text, expected):
    assert parse_mcq_label(text, ABCD) == expected


# --- Empty / missing labels -------------------------------------------------
def test_empty_inputs():
    assert parse_mcq_label("", ABCD) is None
    assert parse_mcq_label("B", []) is None
    assert parse_mcq_label(None, ABCD) is None  # type: ignore[arg-type]
