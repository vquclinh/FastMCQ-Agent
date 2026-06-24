"""Multi-agent candidate factory (Phase 2L.25) — builds a CandidatePool, no API.

Collects answer candidates for one question from the v10 base answer, the formula
bank, the concept solver, the five domain tool solvers, and knowledge-card/RAG-lite
retrieval. Future API agents are present only as NO-OP STUBS that never call the
network. Every candidate carries source / confidence / risk / proof-or-evidence.
No qid logic, no answer table, no ground truth.
"""

from __future__ import annotations

from src.selector.candidate_answer import AnswerCandidate, CandidatePool
from src.solvers.concept_solver import solve_concept_sample
from src.evidence.evidence_verifier_policy import evaluate_override
from src.solvers.formula_bank_solver import solve_formula_bank_sample
from src.utils.labels import labels_for
from src.evidence.rag_lite import retrieve_cards_per_option
from src.tool_solvers import (cs_solver, finance_econ_solver, geometry_solver, physics_solver,
                              probability_solver, safe_math_solver, stats_solver)

_TOOLS = (safe_math_solver, stats_solver, finance_econ_solver, cs_solver, physics_solver,
          probability_solver, geometry_solver)


# --- future API agents: STUBS ONLY (never call the network) -------------------

def direct_route_prompt_agent_stub(sample, base_answer=None):
    """Placeholder for a future route-prompt API agent. Returns None (no API)."""
    return None


def self_consistency_agent_stub(sample, base_answer=None):
    """Placeholder for a future self-consistency API agent. Returns None (no API)."""
    return None


def pairwise_judge_agent_stub(sample, base_answer=None):
    """Placeholder for a future pairwise-judge API agent. Returns None (no API)."""
    return None


def build_candidate_pool(sample, base_answer, base_record=None) -> CandidatePool:
    qid = sample.get("qid")
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    route = (base_record or {}).get("route", "")
    pool = CandidatePool(qid=qid)

    # 1) v10 base LLM answer.
    if base_answer in labels:
        conf = (base_record or {}).get("confidence")
        pool.add(AnswerCandidate(qid=qid, answer=base_answer, source="v10_base", route=route,
                                 confidence=float(conf) if isinstance(conf, (int, float)) else 0.5,
                                 risk_level="medium", rationale="v10 production answer",
                                 metadata={"api_calls": (base_record or {}).get("api_calls")}))

    # 2) formula bank (calc + concept + new rules), if it produces a safe match.
    fb = solve_formula_bank_sample(sample)
    if fb is not None and fb.safe_to_override and fb.selected_answer in labels:
        pool.add(AnswerCandidate(qid=qid, answer=fb.selected_answer, source="formula_bank",
                                 route=route, confidence=fb.confidence, risk_level="low",
                                 rationale=fb.reason, proof_text=fb.reason, rule_id=fb.rule_id))

    # 3) concept solver (paging, mc_vs_avc) — may overlap with formula bank.
    con = solve_concept_sample(sample, labels)
    if con.matched and con.safe_to_override and con.answer in labels:
        pool.add(AnswerCandidate(qid=qid, answer=con.answer, source="concept", route=route,
                                 confidence=0.97, risk_level="low", rationale=con.reason,
                                 proof_text=con.reason, rule_id=con.rule_id))

    # 4) domain tool solvers.
    for tool in _TOOLS:
        try:
            cand = tool.solve(sample)
        except Exception:
            cand = None
        if cand is not None:
            cand.route = route
            pool.add(cand)

    # 5) knowledge-card / RAG-lite support: attach a card-backed candidate ONLY when a
    #    single card maps uniquely to one option (rare). Evidence-only otherwise.
    per_opt = retrieve_cards_per_option(sample.get("question", ""), choices, top_k=1)
    supported = [(lbl, hits[0]) for lbl, hits in per_opt.items() if hits and hits[0][1] >= 1.5]
    if len(supported) == 1:
        lbl, (card, score) = supported[0]
        pool.add(AnswerCandidate(qid=qid, answer=lbl, source="card", route=route,
                                 confidence=min(0.85, 0.5 + 0.1 * score), risk_level="medium",
                                 rationale=f"card {card.id} supports option {lbl}",
                                 evidence_text=card.statement, card_id=card.id))

    # 6) API agent stubs (no network; currently always None).
    for agent in (direct_route_prompt_agent_stub, self_consistency_agent_stub,
                  pairwise_judge_agent_stub):
        c = agent(sample, base_answer)
        if c is not None:        # pragma: no cover - stubs return None this phase
            pool.add(c)

    return pool.deduplicate()


def card_candidate_passes_policy(candidate: AnswerCandidate, base_answer) -> bool:
    """Whether a card candidate would pass the strict override policy (diagnostic)."""
    decision = evaluate_override({
        "evidence_kind": "retrieved_card", "card_support": True, "unique_option": True,
        "confidence": candidate.confidence, "selected_answer": candidate.answer,
        "current_answer": base_answer})
    return decision.allow
