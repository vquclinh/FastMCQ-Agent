"""Statistics tool solver: mean/median/mode, range, expected value (Phase 2L.25)."""

from __future__ import annotations

import re

from src.candidate_answer import AnswerCandidate
from src.labels import labels_for
from src.pot_lite import map_to_option
from src.tool_solvers import _candidate_from_rule
from src.formula_bank_solver import try_mean_median_mode, try_expected_value

_NUM = r"[-+]?\d+(?:[.,]\d+)?"


def _try_range(sample):
    q = str(sample.get("question", "") or "")
    low = q.lower()
    if "khoảng biến thiên" not in low and "phạm vi" not in low and "range" not in low:
        return None
    m = re.search(r"(?:dãy|tập|các giá trị|dữ liệu)[^0-9]{0,12}([-+0-9.,\s]+)", q, re.IGNORECASE)
    if not m:
        return None
    data = [float(x.replace(",", ".")) for x in re.findall(_NUM, m.group(1))]
    if len(data) < 2:
        return None
    rng = max(data) - min(data)
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    lbl = map_to_option(rng, choices, labels)
    if lbl:
        return AnswerCandidate(qid=sample.get("qid"), answer=lbl, source="tool:stats",
                               confidence=0.97, risk_level="low",
                               rationale=f"range=max-min={rng:g}", proof_text=f"range={rng:g}",
                               rule_id="stats_range")
    return None


def solve(sample):
    cand = _try_range(sample)
    if cand is not None:
        return cand
    return _candidate_from_rule(sample, (try_mean_median_mode, try_expected_value), "tool:stats")
