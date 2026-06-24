"""Evidence-grounded candidate ranker (Phase 2L.25) — conservative, keeps v10 by default.

Scores candidates by evidence strength and selects a final answer. The base (v10)
answer is kept UNLESS another candidate clearly beats it: a deterministic proof with a
unique option is strongest; multiple independent non-LLM tools agreeing is strong; a
knowledge card alone rarely overrides; raw LLM/self-consistency confidence is weak.
Never overrides against a deterministic proof; never overrides on a single
medium/high-risk candidate. No qid logic, no answer table, no network.
"""

from __future__ import annotations

# Sources whose agreement constitutes independent deterministic evidence.
_DETERMINISTIC_SOURCES = {"formula_bank", "concept", "tool:safe_math", "tool:stats",
                          "tool:finance_econ", "tool:cs", "tool:physics",
                          "tool:probability", "tool:geometry"}
_BASE_SOURCE = "v10_base"
# Minimum number of INDEPENDENT non-base sources that must agree (with evidence) to
# trigger a non-deterministic consensus override (flagged for manual review).
_MIN_CONSENSUS_SOURCES = 3


def _is_deterministic(c) -> bool:
    return c.source in _DETERMINISTIC_SOURCES and c.risk_level == "low"


def score_candidate(candidate, pool, sample) -> float:
    """Heuristic evidence score (higher = stronger). Pure function of the pool."""
    votes = pool.answer_votes()
    agree = votes.get(candidate.answer, 0)
    det_sources = {c.source for c in pool.candidates
                   if _is_deterministic(c) and c.answer == candidate.answer}
    score = 0.0
    if _is_deterministic(candidate):
        score += 5.0                       # deterministic proof + unique option
    score += 1.5 * max(0, len(det_sources) - 1)   # extra independent deterministic tools
    score += 0.5 * max(0, agree - 1)              # general agreement
    if candidate.source == "card":
        score += 1.0                       # card evidence is supportive, not decisive
    if candidate.source == _BASE_SOURCE:
        score += 0.5 + 1.5 * min(candidate.confidence, 1.0)   # base anchored, conf-weighted
    return round(score, 4)


def select_answer(pool, sample, base_answer):
    """Return (selected_answer, decision_record). Conservative: keep v10 unless beaten."""
    rec = {"decision": "keep_base", "selected_source": _BASE_SOURCE, "score": 0.0,
           "risk_level": "low", "reason": "no candidate clearly beats v10",
           "candidate_summary": [{"source": c.source, "answer": c.answer,
                                  "risk": c.risk_level} for c in pool.candidates]}
    if not pool.candidates:
        return base_answer, rec

    # Deterministic candidates that DIFFER from base.
    det_diff = [c for c in pool.candidates if _is_deterministic(c) and c.answer != base_answer]
    det_support_base = any(_is_deterministic(c) and c.answer == base_answer
                           for c in pool.candidates)

    # A deterministic proof overrides — unless another deterministic proof backs base
    # (contradiction → keep base, never fight a proof).
    if det_diff and not det_support_base:
        # Require the deterministic answers to agree among themselves (no split).
        det_answers = {c.answer for c in det_diff}
        if len(det_answers) == 1:
            winner = max(det_diff, key=lambda c: score_candidate(c, pool, sample))
            rec.update({"decision": "override", "selected_source": winner.source,
                        "score": score_candidate(winner, pool, sample),
                        "risk_level": winner.risk_level,
                        "reason": f"deterministic proof ({winner.rule_id or winner.source}) "
                                  f"with unique option overrides v10"})
            return winner.answer, rec
        rec["reason"] = "deterministic candidates disagree -> keep v10"
        return base_answer, rec

    if det_diff and det_support_base:
        rec["reason"] = "candidate contradicts a deterministic proof supporting v10 -> keep v10"
        return base_answer, rec

    # Multi-agent consensus override (for API candidates): allowed ONLY when several
    # INDEPENDENT non-base sources agree on the same alternative, EACH passing the
    # answer/evidence consistency guard (no placeholder evidence, no numeric mismatch),
    # at least one carries real evidence/proof, and no deterministic proof supports the
    # base. Flagged for manual review.
    from src.selector.candidate_consistency import is_candidate_consistent
    alt_sources = {}
    inconsistent = 0
    for c in pool.candidates:
        if c.source == _BASE_SOURCE or c.answer == base_answer:
            continue
        if not is_candidate_consistent(c, sample):   # inconsistent -> never counts toward consensus
            inconsistent += 1
            continue
        alt_sources.setdefault(c.answer, set()).add(c.source)
    rec["inconsistent_candidates"] = inconsistent
    for ans, srcs in alt_sources.items():
        if len(srcs) >= _MIN_CONSENSUS_SOURCES:
            has_evidence = any((c.proof_text or c.evidence_text)
                               for c in pool.candidates if c.answer == ans
                               and c.source != _BASE_SOURCE
                               and is_candidate_consistent(c, sample))
            if has_evidence and not det_support_base:
                rec.update({"decision": "override", "selected_source": "multi_agent_consensus",
                            "score": float(len(srcs)), "risk_level": "medium",
                            "reason": f"{len(srcs)} independent sources agree on {ans} with evidence",
                            "requires_manual_review": True})
                return ans, rec

    # No deterministic override. Card-only / medium-risk / lone candidate never overrides.
    rec["reason"] = "only weak/medium evidence differs from v10 -> keep v10"
    return base_answer, rec
