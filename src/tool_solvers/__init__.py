"""Domain tool solvers (Phase 2L.25) — each returns an AnswerCandidate or declines.

Thin, domain-partitioned wrappers over the already-tested deterministic rules in
``formula_bank_solver`` / ``calculation_solver`` / ``concept_solver`` / ``pot_lite``.
A tool solver runs only its domain's rules and wraps the first SAFE unique match as an
``AnswerCandidate`` (risk_level="low", with proof text). No qid logic, no answer
table, no network.
"""

from __future__ import annotations

from src.selector.candidate_answer import AnswerCandidate
from src.utils.labels import labels_for


def _candidate_from_rule(sample, rules, source):
    """Run domain ``rules`` (formula-bank try_* funcs) on the sample; wrap first match."""
    q = str(sample.get("question", "") or "")
    choices = sample.get("choices", []) or []
    if not choices:
        return None
    labels = labels_for(len(choices))
    for rule in rules:
        try:
            res = rule(q, choices, labels)
        except Exception:
            res = None
        if res is not None and res.safe_to_override and res.selected_answer in labels:
            return AnswerCandidate(
                qid=sample.get("qid"), answer=res.selected_answer, source=source,
                confidence=float(getattr(res, "confidence", 0.97)), risk_level="low",
                rationale=res.reason, proof_text=res.reason, rule_id=res.rule_id,
                metadata={"extracted": getattr(res, "extracted_values", {})})
    return None
