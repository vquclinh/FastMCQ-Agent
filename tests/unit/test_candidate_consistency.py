"""Tests for the candidate consistency guard + ranker integration (Phase 2L.26B)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate, CandidatePool  # noqa: E402
from src.candidate_consistency import (candidate_matches_option, detect_placeholder_evidence,
                                       extract_numeric_claims, extract_option_numeric_values,
                                       strong_claim, validate_candidate_consistency)

_S = {"qid": "c1", "question": "Cournot? P=20-Q, C(q)=2q.",
      "choices": ["q_X = 4, q_Y = 4", "q_X = 5, q_Y = 5", "q_X = 6, q_Y = 6"]}
_KNOW = {"qid": "k", "question": "Thủ đô Pháp?", "choices": ["Paris", "Lyon", "Nice"]}


# --- unit helpers -------------------------------------------------------------

def test_detect_placeholder_evidence():
    for bad in ("", "r", "x", "n/a", "none", "some evidence", "   ", "..."):
        assert detect_placeholder_evidence(bad) is True
    assert detect_placeholder_evidence("q = (20-2)/3 = 6 by Cournot symmetry") is False


def test_extract_numeric_claims_and_strong_claim():
    assert 6.0 in extract_numeric_claims("q = (20-2)/(2+1) = 6")
    assert strong_claim("q = (20-2)/(2+1) = 6") == 6.0
    assert strong_claim("no numbers here") is None


def test_extract_option_numeric_values():
    assert extract_option_numeric_values("q_X = 4, q_Y = 4") == [4.0, 4.0]


# --- candidate_matches_option / validate -------------------------------------

def test_numeric_mismatch_rejected():
    # evidence derives 6 but selected option C-index says 4 -> mismatch
    cand = AnswerCandidate("c1", "A", "api:route_specialist", evidence_text="q = (20-2)/3 = 6")
    assert candidate_matches_option(cand, _S) is False
    rec = validate_candidate_consistency(cand, _S)
    assert rec.ok is False and rec.severity == "numeric_mismatch"


def test_numeric_match_accepted():
    cand = AnswerCandidate("c1", "C", "api:route_specialist", evidence_text="q = (20-2)/3 = 6")
    assert candidate_matches_option(cand, _S) is True
    assert validate_candidate_consistency(cand, _S).ok is True


def test_placeholder_evidence_rejected_for_non_deterministic():
    cand = AnswerCandidate("k", "B", "api:route_specialist", evidence_text="some evidence", rationale="r")
    rec = validate_candidate_consistency(cand, _KNOW)
    assert rec.ok is False and rec.severity == "placeholder"


def test_deterministic_tool_candidate_trusted():
    cand = AnswerCandidate("c1", "C", "tool:finance_econ", proof_text="q_i=6", rule_id="cournot_duopoly")
    assert validate_candidate_consistency(cand, _S).ok is True


# --- ranker integration -------------------------------------------------------

def test_ranker_rejects_consensus_with_placeholder_evidence():
    pool = CandidatePool(qid="k")
    pool.add(AnswerCandidate("k", "A", "v10_base", confidence=0.6))
    for ag in ("api:route_specialist", "api:challenger", "api:option_elimination"):
        pool.add(AnswerCandidate("k", "B", ag, evidence_text="some evidence", rationale="r"))
    ans, rec = select_answer(pool, _KNOW, "A")
    assert ans == "A" and rec["decision"] == "keep_base"      # placeholder -> no consensus


def test_ranker_rejects_consensus_with_numeric_mismatch():
    # three agents agree on option A (q=4) but their evidence derives 6 -> inconsistent
    pool = CandidatePool(qid="c1")
    pool.add(AnswerCandidate("c1", "C", "v10_base", confidence=0.6))   # base = C (q=6)
    for ag in ("api:route_specialist", "api:challenger", "api:option_elimination"):
        pool.add(AnswerCandidate("c1", "A", ag, evidence_text="q = (20-2)/3 = 6"))  # picks q=4
    ans, rec = select_answer(pool, _S, "C")
    assert ans == "C" and rec["decision"] == "keep_base"


def test_ranker_consensus_overrides_when_consistent():
    pool = CandidatePool(qid="c1")
    pool.add(AnswerCandidate("c1", "A", "v10_base", confidence=0.5))   # base A (q=4)
    for ag in ("api:route_specialist", "api:challenger", "api:option_elimination"):
        # consistent: evidence result 6 matches option C (q=6)
        pool.add(AnswerCandidate("c1", "C", ag, evidence_text="q = (20-2)/3 = 6"))
    ans, rec = select_answer(pool, _S, "A")
    assert ans == "C" and rec["decision"] == "override"
    assert rec["selected_source"] == "multi_agent_consensus"


def test_ranker_deterministic_proof_still_works():
    pool = CandidatePool(qid="c1")
    pool.add(AnswerCandidate("c1", "A", "v10_base", confidence=0.6))
    pool.add(AnswerCandidate("c1", "C", "formula_bank", confidence=0.97, risk_level="low",
                             proof_text="q_i=6", rule_id="cournot_duopoly"))
    ans, rec = select_answer(pool, _S, "A")
    assert ans == "C" and rec["decision"] == "override" and rec["selected_source"] == "formula_bank"
