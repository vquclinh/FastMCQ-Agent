"""Computer-science tool solver (Phase 2L.25).

Binary/decimal conversion, cache AMAT / hit rate, Big-O simple loops, paging logical
address (concept). DB-key / normalization remain card/hint territory (not auto-solved).
"""

from __future__ import annotations

from src.candidate_answer import AnswerCandidate
from src.labels import labels_for
from src.tool_solvers import _candidate_from_rule
from src.formula_bank_solver import (try_binary_decimal, try_cache_amat, try_cache_hit_rate,
                                     try_time_complexity_nested_loops, try_hex_decimal,
                                     try_subnet_hosts)
from src.concept_solver import try_paging_logical_address


def solve(sample):
    cand = _candidate_from_rule(
        sample,
        (try_binary_decimal, try_hex_decimal, try_subnet_hosts, try_cache_amat,
         try_cache_hit_rate, try_time_complexity_nested_loops),
        "tool:cs")
    if cand is not None:
        return cand
    # paging concept rule lives in concept_solver (returns ConceptResult).
    q = str(sample.get("question", "") or "")
    choices = sample.get("choices", []) or []
    if not choices:
        return None
    labels = labels_for(len(choices))
    try:
        res = try_paging_logical_address(q, choices, labels)
    except Exception:
        res = None
    if res is not None and res.matched and res.safe_to_override and res.answer in labels:
        return AnswerCandidate(qid=sample.get("qid"), answer=res.answer, source="tool:cs",
                               confidence=0.97, risk_level="low", rationale=res.reason,
                               proof_text=res.reason, rule_id=res.rule_id)
    return None
