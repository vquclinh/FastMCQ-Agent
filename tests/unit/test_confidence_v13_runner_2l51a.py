"""Unit: clean in-memory V13 runner (Base->V12B->V13 pipeline, V13 stage only).

Proves per-record layer choice, success paths for all three V13 layers, closed
failure codes (empty prompt / generation error / parse error / no match / invalid
label / runner error), one record's failure never aborts the batch, the injected
backend is used (no second model load), record_ordinal reflects list position (not
qid), and results/summary are text-free. No torch/GPU/network (fake backend only).
"""

from __future__ import annotations

import json

from src.local_model.confidence_v13_runner import (
    DEFAULT_MAX_NEW_TOKENS,
    V13ErrorCode,
    V13RunInput,
    run_v13_for_unresolved,
)
from src.layers import content_first_answerer as CF


class _FakeBackend:
    def __init__(self, handler=None, mode="ok"):
        self.handler = handler
        self.mode = mode
        self.calls = 0
        self.max_new_tokens_seen = []

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        self.calls += 1
        self.max_new_tokens_seen.append(max_new_tokens)
        if self.mode == "raise":
            raise RuntimeError("synthetic v13 generation failure")
        text = "".join(m.get("content", "") for m in prompt_or_messages) \
            if isinstance(prompt_or_messages, list) else str(prompt_or_messages)
        if self.handler is not None:
            return self.handler(text)
        return "not json at all"


def _input(qid, question, choices, input_index=0):
    return V13RunInput(qid=qid, input_index=input_index, question=question,
                       choices=tuple(choices), canonical_labels=())


def test_layer_selection_programmatic():
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"operation": "arithmetic", "expression": "2+2", "operands": {}, "result_hint": 4}))
    results, _ = run_v13_for_unresolved(
        [_input("q1", "2 + 2 = ?", ["3", "4", "5", "6"])], backend=backend)
    assert results[0].layer == "programmatic_solver"
    assert results[0].valid is True
    assert results[0].mapped_label == "B"
    assert results[0].error_code == V13ErrorCode.OK


def test_layer_selection_content_first_by_hint():
    backend = _FakeBackend()
    results, _ = run_v13_for_unresolved(
        [_input("q2", "What is the definition of photosynthesis?", ["a", "b", "c"])], backend=backend)
    assert results[0].layer == "content_first"


def test_layer_selection_least_to_most_by_hint():
    backend = _FakeBackend()
    results, _ = run_v13_for_unresolved(
        [_input("q3", "Which of the following statements is true?", ["a", "b", "c"])], backend=backend)
    assert results[0].layer == "least_to_most"


def test_layer_selection_default_is_content_first():
    backend = _FakeBackend()
    results, _ = run_v13_for_unresolved(
        [_input("q4", "A plain question with no special hints.", ["a", "b", "c"])], backend=backend)
    assert results[0].layer == "content_first"


def test_content_first_success():
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"answer_content": "Paris", "answer_type": "term", "numeric_value": None,
         "evidence": "x", "confidence": 0.9}))
    results, _ = run_v13_for_unresolved(
        [_input("q5", "What is the definition of the capital of France?",
                ["Paris", "Rome", "Berlin"])],
        backend=backend)
    assert results[0].layer == "content_first"
    assert results[0].valid is True
    assert results[0].mapped_label == "A"


def test_least_to_most_success():
    backend = _FakeBackend(handler=lambda t: json.dumps({
        "constraints": ["c1", "c2"],
        "option_evaluations": [
            {"label": "A", "passes_constraints": [True, True], "eliminated": False},
            {"label": "B", "passes_constraints": [True, False], "eliminated": True,
             "elimination_reason": "fails c2"},
        ],
        "final_survivor_label": "A",
        "confidence": 0.8,
        "contradiction_check": True,
    }))
    results, _ = run_v13_for_unresolved(
        [_input("q6", "Which of the following statements is true?", ["yes", "no"])],
        backend=backend)
    assert results[0].layer == "least_to_most"
    assert results[0].valid is True
    assert results[0].mapped_label == "A"


def test_empty_prompt_never_calls_backend():
    class _EmptyPromptBackend(_FakeBackend):
        pass

    backend = _EmptyPromptBackend()
    # An empty choices/question combination cannot build any layer prompt meaningfully;
    # force it via a layer with an empty question (content_first prompt is never truly
    # empty in practice, so simulate via monkeypatched builder instead).
    import src.local_model.confidence_v13_runner as runner_mod
    original = runner_mod._build_prompt
    try:
        runner_mod._build_prompt = lambda layer, sample: ""
        results, _ = run_v13_for_unresolved([_input("q7", "irrelevant", ["a", "b"])], backend=backend)
    finally:
        runner_mod._build_prompt = original
    assert results[0].error_code == V13ErrorCode.EMPTY_PROMPT
    assert results[0].attempted is False
    assert backend.calls == 0


def test_generation_error_reports_exception_class_only():
    backend = _FakeBackend(mode="raise")
    results, _ = run_v13_for_unresolved(
        [_input("q8", "2 + 2 = ?", ["3", "4", "5", "6"])], backend=backend)
    r = results[0]
    assert r.error_code == V13ErrorCode.GENERATION_ERROR
    assert r.attempted is True and r.valid is False
    assert r.exception_class_name == "RuntimeError"
    assert "synthetic" not in json.dumps(r.as_dict())   # no exception message text


def test_parse_error_on_non_json_output():
    backend = _FakeBackend(handler=lambda t: "I cannot answer this in JSON.")
    results, _ = run_v13_for_unresolved(
        [_input("q9", "2 + 2 = ?", ["3", "4", "5", "6"])], backend=backend)
    assert results[0].error_code == V13ErrorCode.PARSE_ERROR
    assert results[0].valid is False


def test_no_match_when_layer_cannot_resolve():
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"answer_content": "totally unrelated content", "answer_type": "phrase"}))
    results, _ = run_v13_for_unresolved(
        [_input("q10", "What is the definition of gravity?", ["apple", "orange", "banana"])],
        backend=backend)
    assert results[0].error_code == V13ErrorCode.NO_MATCH
    assert results[0].valid is False
    assert results[0].mapped_label is None


def test_invalid_label_path(monkeypatch):
    """Force a layer interpreter to propose a label outside the sample's range."""
    class _FakeMatch:
        ok = True
        mapped_label = "Z"

    monkeypatch.setattr(CF, "match_content_to_options", lambda content_answer, sample: _FakeMatch())
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"answer_content": "x", "answer_type": "term"}))
    results, _ = run_v13_for_unresolved(
        [_input("q11", "What is the definition of x?", ["a", "b"])], backend=backend)
    assert results[0].error_code == V13ErrorCode.INVALID_LABEL
    assert results[0].valid is False
    assert results[0].mapped_label is None


def test_one_record_failure_does_not_abort_others(monkeypatch):
    import src.local_model.confidence_v13_runner as runner_mod
    original_choose = runner_mod._choose_layer
    calls = {"n": 0}

    def _boom_once(sample):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return original_choose(sample)

    monkeypatch.setattr(runner_mod, "_choose_layer", _boom_once)
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"operation": "arithmetic", "expression": "1+1", "result_hint": 2}))
    inputs = [_input("a", "1 + 1 = ?", ["1", "2", "3"], input_index=0),
              _input("b", "1 + 1 = ?", ["1", "2", "3"], input_index=1),
              _input("c", "1 + 1 = ?", ["1", "2", "3"], input_index=2)]
    results, summary = run_v13_for_unresolved(inputs, backend=backend)
    assert len(results) == 3
    assert results[1].error_code == V13ErrorCode.RUNNER_ERROR
    assert results[1].exception_class_name == "RuntimeError"
    assert results[0].valid is True and results[2].valid is True
    assert summary.total_unresolved_records == 3


def test_record_ordinal_reflects_list_position_not_qid():
    backend = _FakeBackend()
    inputs = [_input("dup", "def word one", ["a", "b"], input_index=0),
              _input("dup", "def word two", ["a", "b"], input_index=0)]
    results, _ = run_v13_for_unresolved(inputs, backend=backend)
    assert [r.record_ordinal for r in results] == [0, 1]
    assert len(results) == 2   # duplicate qid/input_index still produce distinct records


def test_max_new_tokens_default_and_override():
    backend = _FakeBackend()
    run_v13_for_unresolved([_input("q", "def x", ["a", "b"])], backend=backend)
    assert backend.max_new_tokens_seen == [DEFAULT_MAX_NEW_TOKENS]

    backend2 = _FakeBackend()
    run_v13_for_unresolved([_input("q", "def x", ["a", "b"])], backend=backend2, max_new_tokens=99)
    assert backend2.max_new_tokens_seen == [99]


def test_summary_layer_and_error_counts():
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"operation": "arithmetic", "expression": "1+1", "result_hint": 2}))
    inputs = [_input("a", "1 + 1 = ?", ["1", "2"]), _input("b", "def y", ["a", "b"])]
    results, summary = run_v13_for_unresolved(inputs, backend=backend)
    assert summary.total_unresolved_records == 2
    assert summary.layer_counts.get("programmatic_solver") == 1
    assert summary.layer_counts.get("content_first") == 1
    assert summary.valid_records + summary.invalid_records == 2


def test_results_and_summary_are_text_free():
    backend = _FakeBackend(handler=lambda t: json.dumps(
        {"answer_content": "Paris", "answer_type": "term"}))
    results, summary = run_v13_for_unresolved(
        [_input("q", "What is the definition of the capital of France?",
                ["Paris", "Rome", "Berlin"])],
        backend=backend)
    blob = json.dumps([r.as_dict() for r in results]) + json.dumps(summary.as_dict())
    for banned in ("Paris", "Rome", "Berlin", "capital of France", "prompt", "reasoning", "evidence"):
        assert banned not in blob
