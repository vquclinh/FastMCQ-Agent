"""Probability tool solver (Phase 2L.27A): expected value + simple cases."""

from __future__ import annotations

import re
from src.candidate_answer import AnswerCandidate
from src.labels import labels_for
from src.pot_lite import map_to_option
from src.tool_solvers import _candidate_from_rule
from src.formula_bank_solver import try_expected_value

_NUM = r"[-+]?\d+(?:[.,]\d+)?"


def _try_independent_and(sample):
    """P(A and B) = P(A)*P(B) for explicitly independent events."""
    q = str(sample.get("question", "") or ""); low = q.lower()
    if "độc lập" not in low and "independent" not in low:
        return None
    if not ("cùng" in low or "đồng thời" in low or "and" in low or "cả hai" in low or "và" in low):
        return None
    probs = [float(x.replace(",", ".")) for x in re.findall(_NUM, q)]
    probs = [p for p in probs if 0 < p <= 1]
    if len(probs) != 2:
        return None
    val = probs[0] * probs[1]
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    lbl = map_to_option(val, choices, labels)
    if lbl:
        return AnswerCandidate(sample.get("qid"), lbl, "tool:probability", confidence=0.96,
                               risk_level="low", proof_text=f"P(A)·P(B)={val:g}",
                               rule_id="independent_and")
    return None


def solve(sample):
    cand = _candidate_from_rule(sample, (try_expected_value,), "tool:probability")
    if cand is not None:
        return cand
    return _try_independent_and(sample)
