"""Candidate-agent parser quality tests."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.local_model import candidate_agents as agents  # noqa: E402

_S = {"qid": "x", "question": "Cournot? P=20-Q, C(q)=2q.",
      "choices": ["q_X=4,q_Y=4", "q_X=5,q_Y=5", "q_X=6,q_Y=6"]}


def test_parser_rejects_placeholder():
    r = agents.parse_candidate(
        '{"answer":"A","confidence":0.9,"evidence":"some evidence","rationale":"r","risk":"low"}',
        _S)
    assert r["parse_status"] == "placeholder_evidence"


def test_parser_rejects_numeric_mismatch():
    r = agents.parse_candidate(
        '{"answer":"A","confidence":0.9,"evidence":"q=(20-2)/3=6","risk":"low"}',
        _S)
    assert r["parse_status"] == "numeric_mismatch"


def test_parser_accepts_valid_evidence():
    r = agents.parse_candidate(
        '{"answer":"C","confidence":0.9,"evidence":"q=(20-2)/3=6 theo đối xứng Cournot","risk":"low"}',
        _S)
    assert r["parse_status"] == "ok" and r["answer"] == "C"
