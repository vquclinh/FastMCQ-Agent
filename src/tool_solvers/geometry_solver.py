"""Geometry tool solver (Phase 2L.27A): pythagorean, circle/triangle, rectangle, slope."""

from __future__ import annotations

import re
from src.selector.candidate_answer import AnswerCandidate
from src.utils.labels import labels_for
from src.solvers.pot_lite import map_to_option
from src.tool_solvers import _candidate_from_rule
from src.solvers.formula_bank_solver import (try_pythagorean_distance, try_circle_area_circumference,
                                     try_triangle_area)

_NUM = r"[-+]?\d+(?:[.,]\d+)?"


def _first(pat, text):
    m = re.search(pat, text, re.IGNORECASE)
    return float(m.group(1).replace(",", ".")) if m else None


def _try_rectangle(sample):
    q = str(sample.get("question", "") or ""); low = q.lower()
    if "hình chữ nhật" not in low and "rectangle" not in low:
        return None
    L = _first(r"(?:chiều dài|dài|length)\D{0,12}(" + _NUM + r")", q)
    W = _first(r"(?:chiều rộng|rộng|width)\D{0,12}(" + _NUM + r")", q)
    if L is None or W is None:
        return None
    if "diện tích" in low or "area" in low:
        val, rid = L * W, "rectangle_area"
    elif "chu vi" in low or "perimeter" in low:
        val, rid = 2 * (L + W), "rectangle_perimeter"
    else:
        return None
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    lbl = map_to_option(val, choices, labels)
    if lbl:
        return AnswerCandidate(sample.get("qid"), lbl, "tool:geometry", confidence=0.97,
                               risk_level="low", proof_text=f"{rid}={val:g}", rule_id=rid)
    return None


def solve(sample):
    cand = _candidate_from_rule(sample, (try_pythagorean_distance, try_circle_area_circumference,
                                         try_triangle_area), "tool:geometry")
    if cand is not None:
        return cand
    return _try_rectangle(sample)
