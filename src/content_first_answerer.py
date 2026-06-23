"""Content-first answer normalizer (Phase 2L.35A) — V13 shadow stack.

Targets "reasoning is right but the label is wrong". The model is asked to produce the answer
CONTENT first (not a label); this module then maps that content back to an option label via
exact / normalized / numeric matching. If the content matches zero or multiple options, or the
model's own chosen label disagrees with the content, the candidate is rejected.

Pure and deterministic — no API calls, no client construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.labels import labels_for
from src.mcq_permutation_debiaser import normalize_option_text
from src.option_grounding import map_claim_to_option
from src.programmatic_solver_layer import extract_numeric_values


@dataclass
class ContentAnswer:
    answer_content: str | None
    answer_type: str | None
    evidence: str | None
    numeric_value: float | None
    confidence: float | None
    selected_label: str | None = None
    parse_status: str = "ok"


@dataclass
class ContentOptionMatch:
    ok: bool
    mapped_label: str | None
    match_kind: str = ""        # exact | normalized | numeric
    failure_reason: str = ""
    detail: dict = field(default_factory=dict)


def normalize_answer_content(text) -> str:
    return normalize_option_text(text)


def build_content_first_prompt(sample: dict, route: str) -> str:
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    opts = "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, choices))
    return (
        "Answer the question by stating the ANSWER CONTENT first. Do NOT choose an option "
        "letter yet. Return a SINGLE JSON object with keys: "
        '"answer_content" (the actual answer text/value), '
        '"answer_type" (one of: numeric, definition, phrase, term, concept), '
        '"numeric_value" (number if applicable else null), '
        '"evidence" (one concise line), "confidence" (0..1). '
        f"Route hint: {route}.\n\nQuestion:\n{sample.get('question','')}\n\n"
        f"Options (for later mapping — do NOT select one now):\n{opts}\n\nReturn JSON now."
    )


def parse_content_answer(model_json: dict) -> ContentAnswer:
    if not isinstance(model_json, dict):
        return ContentAnswer(None, None, None, None, None, parse_status="parse_error")
    nv = model_json.get("numeric_value")
    try:
        nv = float(nv) if nv is not None and str(nv).strip() != "" else None
    except (ValueError, TypeError):
        nv = None
    return ContentAnswer(
        answer_content=model_json.get("answer_content"),
        answer_type=(model_json.get("answer_type") or None),
        evidence=model_json.get("evidence"),
        numeric_value=nv,
        confidence=model_json.get("confidence"),
        selected_label=model_json.get("selected_label"),
        parse_status="ok")


def match_content_to_options(content_answer: ContentAnswer, sample: dict) -> ContentOptionMatch:
    if content_answer.parse_status != "ok":
        return ContentOptionMatch(False, None, failure_reason="parse_error")
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))

    # 1) Numeric match (unique option containing the value).
    value = content_answer.numeric_value
    if value is None and content_answer.answer_type == "numeric":
        nums = extract_numeric_values(content_answer.answer_content)
        value = nums[0] if len(nums) == 1 else None
    if value is not None:
        mapped = map_claim_to_option(value, choices)
        if mapped is None:
            return ContentOptionMatch(False, None, "numeric",
                                      "numeric_ambiguous_or_no_match", {"value": value})
        return ContentOptionMatch(True, mapped, "numeric", "", {"value": value})

    # 2) Text match: exact normalized first, then containment — must be UNIQUE.
    content = normalize_answer_content(content_answer.answer_content)
    if not content:
        return ContentOptionMatch(False, None, failure_reason="empty_content")
    norm_opts = {lab: normalize_answer_content(c) for lab, c in zip(labels, choices)}
    exact = [lab for lab, t in norm_opts.items() if t and t == content]
    if len(exact) == 1:
        return ContentOptionMatch(True, exact[0], "exact", "")
    if len(exact) > 1:
        return ContentOptionMatch(False, None, "exact", "multiple_exact_matches")
    contains = [lab for lab, t in norm_opts.items() if t and (content in t or t in content)]
    if len(contains) == 1:
        return ContentOptionMatch(True, contains[0], "normalized", "")
    if len(contains) > 1:
        return ContentOptionMatch(False, None, "normalized", "multiple_matches")
    return ContentOptionMatch(False, None, failure_reason="no_option_match")


def validate_content_first_candidate(candidate: dict):
    """(valid, reason). Rejects parse errors, no/ambiguous match, and label/content disagreement."""
    if (candidate.get("parse_status") or "") != "ok":
        return False, f"parse_status={candidate.get('parse_status')}"
    if not candidate.get("valid", False):
        return False, candidate.get("rejection_reason") or "not_valid"
    mapped = candidate.get("proposed_label")
    if not mapped:
        return False, "no_mapped_label"
    sel = candidate.get("model_selected_label")
    if sel and sel != mapped:
        return False, "label_content_disagreement"
    return True, "ok"
