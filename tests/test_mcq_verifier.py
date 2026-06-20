"""Tests for the selective MCQ verifier (no network, no model, no qid)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mcq_verifier import (  # noqa: E402
    build_verifier_messages,
    parse_verification,
    should_run_verifier,
)

ABCD = ["A", "B", "C", "D"]


class _Cfg:
    """Minimal stand-in for OpenRouterConfig verifier fields."""
    mcq_verifier_enabled = True
    mcq_verifier_apply_routes = ["long_context", "ambiguous", "law_admin", "safety_ethics"]
    mcq_verifier_trigger_below_confidence = 0.70
    mcq_verifier_trigger_on_partial_parse = True
    mcq_verifier_trigger_on_repair = True
    mcq_verifier_trigger_on_reranked_long_context = True


def test_prompt_includes_choices_and_original_answer():
    msgs = build_verifier_messages("long_context", "Đoạn văn ... Câu hỏi?",
                                   ["Paris", "Lyon", "Nice", "Hue"], "B")
    user = msgs[-1]["content"]
    assert "Paris" in user and "Đáp án ban đầu: B" in user
    assert "A. Paris" in user  # labelled choices


def test_parse_valid_verification():
    txt = ('{"original_answer_supported": false, "best_answer": "C", '
           '"should_override": true, "confidence": 0.9, '
           '"option_assessments": [{"label":"C","status":"supported","confidence":0.9,"reason":"x"}], '
           '"rationale": "C khớp bằng chứng"}')
    r = parse_verification(txt, ABCD, original_answer="B")
    assert r.verified_answer == "C" and r.should_override and r.confidence == 0.9
    assert r.disagreement and r.assessments[0].label == "C"


def test_invalid_label_rejected():
    r = parse_verification('{"best_answer": "Z", "should_override": true, "confidence": 1.0}',
                           ABCD, original_answer="A")
    assert r.verified_answer is None and not r.should_override


def test_should_override_false_keeps_intent():
    r = parse_verification('{"best_answer": "A", "should_override": false, "confidence": 0.9}',
                           ABCD, original_answer="A")
    assert not r.should_override  # same label, no override


def test_override_requires_different_label():
    # best == original => not an override even if should_override true.
    r = parse_verification('{"best_answer": "B", "should_override": true, "confidence": 0.95}',
                           ABCD, original_answer="B")
    assert not r.should_override and not r.disagreement


def test_unparseable_keeps_original():
    r = parse_verification("không phải json", ABCD, original_answer="A")
    assert r.verified_answer is None and not r.should_override and r.error == "unparseable"


def test_assessment_reasons_bounded():
    long_reason = "x" * 500
    txt = ('{"best_answer":"A","should_override":false,"confidence":0.5,'
           f'"option_assessments":[{{"label":"A","status":"supported","confidence":0.5,"reason":"{long_reason}"}}]}}')
    r = parse_verification(txt, ABCD, original_answer="A")
    assert len(r.assessments[0].brief_reason) <= 160


def test_trigger_low_confidence_long_context():
    state = {"route": "long_context", "final_answer": "A", "confidence": 0.4,
             "parsed_answer": {"source": "json"}}
    run, reason = should_run_verifier(state, _Cfg())
    assert run and "low_confidence" in reason


def test_trigger_partial_parse():
    state = {"route": "ambiguous", "final_answer": "A", "confidence": 0.9,
             "parsed_answer": {"source": "partial_answer_key"}}
    run, reason = should_run_verifier(state, _Cfg())
    assert run and "partial_parse" in reason


def test_no_trigger_for_calc_override():
    state = {"route": "calculation", "final_answer": "B", "confidence": 1.0,
             "strategy": "calculation_override:cylinder_rate", "parsed_answer": {}}
    run, reason = should_run_verifier(state, _Cfg())
    assert not run and reason == "calc_override"


def test_no_trigger_out_of_scope_route():
    state = {"route": "short_knowledge", "final_answer": "A", "confidence": 0.4,
             "parsed_answer": {"source": "json"}}
    run, reason = should_run_verifier(state, _Cfg())
    assert not run and reason == "route_not_in_scope"


def test_disabled_never_runs():
    class Off(_Cfg):
        mcq_verifier_enabled = False
    state = {"route": "long_context", "final_answer": "A", "confidence": 0.1,
             "parsed_answer": {"source": "partial_answer_key"}}
    run, reason = should_run_verifier(state, Off())
    assert not run and reason == "disabled"


def test_no_valid_answer_defers():
    state = {"route": "long_context", "final_answer": None, "confidence": 0.0,
             "parsed_answer": {}}
    run, reason = should_run_verifier(state, _Cfg())
    assert not run and reason == "no_valid_answer"


def test_source_no_qid_or_eval():
    import re as _re
    src = Path(__file__).resolve().parent.parent.joinpath("src/mcq_verifier.py").read_text()
    assert "eval(" not in src and "exec(" not in src and "__import__" not in src
    for pat in (r'\[\s*["\']qid', r'\.get\(\s*["\']qid', r'qid\s*=='):
        assert not _re.search(pat, src)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
