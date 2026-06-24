"""Safe arithmetic / generic numeric tool solver (Phase 2L.25).

Tries (1) an explicit arithmetic expression extracted from the question, evaluated by
the AST-whitelisted ``pot_lite.safe_eval_arithmetic`` and mapped to a unique option;
then (2) the generic numeric formula-bank rules. Declines on ambiguity. No qid logic.
"""

from __future__ import annotations

import re

from src.selector.candidate_answer import AnswerCandidate
from src.utils.labels import labels_for
from src.solvers.pot_lite import map_to_option, safe_eval_arithmetic
from src.tool_solvers import _candidate_from_rule
from src.solvers.formula_bank_solver import (try_expected_value, try_pythagorean_distance,
                                     try_circle_area_circumference, try_triangle_area)

# A self-contained arithmetic expression: digits/operators only (no letters except the
# whitelisted sqrt/log10/pi handled by pot_lite). Conservative: needs an operator.
_EXPR_RE = re.compile(r"[-+(]?\s*\d[\d\s.,]*(?:[-+*/^()]\s*(?:sqrt|log10|pi|\d)[\d\s.,]*)+")
_DATE_RE = re.compile(r"\d+\s*/\s*\d+\s*/\s*\d{2,4}")
_CONTEXT_MARKERS = ("đoạn thông tin", "document", "title:", "nội dung", "tiêu đề",
                    "đoạn văn", "-- ")
_WORD_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)   # alphabetic words (len>=2)
_TRIGGER_WORDS = {"tính", "giá", "trị", "của", "kết", "quả", "bằng", "bao", "nhiêu",
                  "biểu", "thức", "phép", "compute", "evaluate", "value", "of", "the",
                  "result", "là"}


def _try_expression(sample):
    """Evaluate ONLY a bare-arithmetic question (not a word problem / prose / dates).

    Guards (any failing -> decline): a clear compute trigger; no embedded date; no
    long-context markers; short question; and the question must be essentially the
    expression itself (<=3 residual content words), so dates/coefficients embedded in
    prose can never be grabbed. Fires only on exactly one unambiguous bare match.
    """
    q = str(sample.get("question", "") or "")
    low = q.lower()
    choices = sample.get("choices", []) or []
    if not choices:
        return None
    labels = labels_for(len(choices))
    if not any(k in low for k in ("tính", "bằng bao nhiêu", "giá trị của", "kết quả",
                                  "biểu thức", "compute", "evaluate", "=")):
        return None
    if _DATE_RE.search(q) or any(mk in low for mk in _CONTEXT_MARKERS) or len(q) > 160:
        return None
    candidates = []
    for m in _EXPR_RE.finditer(q.replace(",", ".")):
        expr = m.group(0).strip()
        if len(re.sub(r"[\d.\s]", "", expr)) < 1:    # must contain an operator
            continue
        residual = q[:m.start()] + q[m.end():]
        words = [w for w in _WORD_RE.findall(residual.lower()) if w not in _TRIGGER_WORDS]
        if len(words) > 3:                           # prose/word problem -> skip
            continue
        r = safe_eval_arithmetic(expr)
        if r.ok and r.value is not None:
            lbl = map_to_option(r.value, choices, labels)
            if lbl:
                candidates.append(AnswerCandidate(
                    qid=sample.get("qid"), answer=lbl, source="tool:safe_math",
                    confidence=0.97, risk_level="low",
                    rationale=f"safe_eval({expr})={r.value:g}", proof_text=f"{expr} = {r.value:g}",
                    rule_id="safe_math_expression"))
    return candidates[0] if len(candidates) == 1 else None


def solve(sample):
    cand = _try_expression(sample)
    if cand is not None:
        return cand
    return _candidate_from_rule(sample, (try_expected_value, try_pythagorean_distance,
                                         try_circle_area_circumference, try_triangle_area),
                                "tool:safe_math")
