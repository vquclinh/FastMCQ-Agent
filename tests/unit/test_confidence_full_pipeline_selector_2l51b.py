"""Unit: Phase 3B deterministic selector (Base -> V12B -> V13 -> final answer).

Proves the conservative selector policy directly against ``run_full_pipeline``:
unselected records stay Base; a clean V12B ``valid_unique_majority`` accepts V12B
and never calls V13; ambiguous/invalid V12B outcomes route to V13; a valid V13
answer overrides; V13 failure/exception/invalid-label always falls back to Base;
selected-but-input-invalid records never reach V12B or V13; positional pairing
never associates by qid; every final answer is a valid canonical label. No
torch/GPU/network (fake backend only).
"""

from __future__ import annotations

import json

import pytest

import src.local_model.confidence_full_pipeline as fp_mod
from src.local_model.confidence_full_pipeline import (
    FINAL_SOURCE_BASE,
    FINAL_SOURCE_BASE_FALLBACK,
    FINAL_SOURCE_V12B,
    FINAL_SOURCE_V13,
    run_full_pipeline,
)
from src.utils.labels import is_valid_label, labels_for

_V12B_MARKER = "selected_label, selected_option_text, label_matches_option"


class _Decision:
    """Minimal stand-in for ShadowRoutingDecision (only the fields the pipeline reads)."""
    def __init__(self, *, qid, input_index, selected=True, candidate=True,
                 generated_answer="A", top1="A", top2="B", logit_margin=1.0,
                 normalized_entropy=0.3, selected_rank=1, candidate_reasons=("low_logit_margin",)):
        self.qid = qid
        self.input_index = input_index
        self.selected = selected
        self.candidate = candidate
        self.generated_answer = generated_answer
        self.top1 = top1
        self.top2 = top2
        self.logit_margin = logit_margin
        self.normalized_entropy = normalized_entropy
        self.selected_rank = selected_rank
        self.candidate_reasons = list(candidate_reasons)


class _Cfg:
    permutation_count = 6


def _sample(qid, choices, question=None):
    return {"qid": qid, "question": question or f"Q {qid}?", "choices": list(choices)}


def _text_of(prompt_or_messages):
    if isinstance(prompt_or_messages, list):
        return "".join(m.get("content", "") for m in prompt_or_messages if isinstance(m, dict))
    return str(prompt_or_messages)


def _option_lines(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 2 and s[1] == "." and s[0].isalpha():
            out.append((s[0], s[2:].strip()))
    return out


class _Backend:
    """Configurable fake backend: distinguishes V12B permutation prompts from V13
    prompts by the marker text V12B's own prompt builder always includes."""

    def __init__(self, *, v12b_target_text=None, v12b_mode="target", v13_mode="ok",
                 v13_target_text=None):
        self.calls = 0
        self.v12b_target_text = v12b_target_text
        self.v12b_mode = v12b_mode      # "target" | "raise" | "malformed"
        self.v13_mode = v13_mode        # "ok" | "raise" | "malformed" | "no_match"
        self.v13_target_text = v13_target_text

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        self.calls += 1
        text = _text_of(prompt_or_messages)
        if _V12B_MARKER in text:
            return self._v12b_response(text)
        return self._v13_response(text)

    def _v12b_response(self, text):
        if self.v12b_mode == "raise":
            raise RuntimeError("synthetic v12b failure")
        if self.v12b_mode == "malformed":
            return json.dumps({"nope": True})
        lines = _option_lines(text)
        for label, body in lines:
            if body == self.v12b_target_text:
                return json.dumps({"selected_label": label, "selected_option_text": body,
                                   "label_matches_option": True})
        if lines:
            label, body = lines[0]
            return json.dumps({"selected_label": label, "selected_option_text": body,
                               "label_matches_option": True})
        return json.dumps({})

    def _v13_response(self, text):
        if self.v13_mode == "raise":
            raise RuntimeError("synthetic v13 failure")
        if self.v13_mode == "malformed":
            return "not json at all"
        if self.v13_mode == "no_match":
            return json.dumps({"answer_content": "completely unrelated text", "answer_type": "phrase"})
        return json.dumps({"answer_content": self.v13_target_text, "answer_type": "term"})


def test_not_selected_stays_base():
    samples = [_sample("a", ["x", "y"])]
    decisions = [_Decision(qid="a", input_index=0, selected=False)]
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=_Backend(), v12b_config=_Cfg())
    r = records[0]
    assert r.final_source == FINAL_SOURCE_BASE
    assert r.final_answer == "A"
    assert r.router_selected is False
    assert r.v12b_status is None and r.v13_attempted is False
    assert summary.total_router_selected == 0


def test_selected_invalid_boundary_stays_base_and_skips_v12b_and_v13():
    samples = [_sample("a", ["only"])]   # 1 choice -> unsupported_choice_count
    decisions = [_Decision(qid="a", input_index=0, selected=True, generated_answer="A")]
    backend = _Backend()
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.final_source == FINAL_SOURCE_BASE
    assert r.v13_attempted is False
    assert backend.calls == 0                     # never reached V12B or V13
    assert summary.total_router_selected == 1
    assert summary.total_router_selected_valid == 0


def test_v12b_valid_unique_majority_accepted_and_v13_never_called():
    choices = ["alpha", "TARGET", "gamma", "delta"]
    samples = [_sample("a", choices)]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _Backend(v12b_target_text="TARGET", v12b_mode="target", v13_mode="raise")
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v12b_status == "valid_unique_majority"
    assert r.final_source == FINAL_SOURCE_V12B
    assert r.final_answer == "B"                   # TARGET is choices[1] -> label B
    assert r.v13_attempted is False and r.v13_status is None
    assert summary.total_v12b_accepted == 1
    assert summary.total_v13_attempted == 0        # V13 (which would raise) was never invoked


def test_v12b_all_invalid_routes_to_v13_success():
    samples = [_sample("a", ["x", "y"], question="def x")]  # 2 choices -> only 2 permutations
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _Backend(v12b_mode="malformed", v13_mode="ok", v13_target_text="y")
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v12b_status == "all_invalid"
    assert r.v13_attempted is True
    assert r.v13_layer == "content_first"
    assert r.final_source == FINAL_SOURCE_V13
    assert r.final_answer == "B"                   # "y" is choices[1] -> label B
    assert summary.total_v13_accepted == 1
    assert summary.v13_layer_counts == {"content_first": 1}


def test_v12b_insufficient_valid_permutations_routes_to_v13():
    samples = [_sample("a", ["x", "y"], question="def x")]   # 2 perms, both valid but < min(5)
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _Backend(v12b_target_text="x", v12b_mode="target", v13_mode="ok", v13_target_text="y")
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v12b_status == "insufficient_valid_permutations"
    assert r.v13_attempted is True
    assert r.final_source == FINAL_SOURCE_V13


def test_v13_invalid_output_falls_back_to_base():
    samples = [_sample("a", ["x", "y"], question="def x")]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _Backend(v12b_mode="malformed", v13_mode="no_match")
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v13_attempted is True
    assert r.final_source == FINAL_SOURCE_BASE_FALLBACK
    assert r.final_answer == "A"                    # reverted to Base
    assert summary.total_base_fallback == 1


def test_v13_exception_falls_back_to_base():
    samples = [_sample("a", ["x", "y"], question="def x")]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _Backend(v12b_mode="malformed", v13_mode="raise")
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.final_source == FINAL_SOURCE_BASE_FALLBACK
    assert r.final_answer == "A"


def test_ambiguous_v12b_and_failing_v13_falls_back_to_base():
    """'Tie/ambiguity always falls back to Base': an ambiguous V12B outcome
    (all_invalid) combined with a V13 that cannot resolve it either must still
    leave the official answer at Base, never a partial/guessed override."""
    samples = [_sample("a", ["x", "y"], question="def x")]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _Backend(v12b_mode="malformed", v13_mode="malformed")
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v12b_status == "all_invalid"
    assert r.final_source == FINAL_SOURCE_BASE_FALLBACK
    assert r.final_answer == r.base_answer == "A"


class _TieBackend(_Backend):
    """Forces a genuine V12BAggregateStatus.TIE (not merely an equivalent status
    path): alternates the V12B vote between two distinct original option texts on
    every permutation call, producing an even 3-3 split across the (up to six)
    permutations of a 4-choice question -- winner_votes == runner_up_votes with
    enough valid votes to clear min_valid_permutations, so the router's own
    ``_aggregate_status`` returns ``tie`` rather than ``insufficient_valid_permutations``."""

    def __init__(self, text_a, text_b, v13_mode="ok", v13_target_text=None):
        super().__init__(v13_mode=v13_mode, v13_target_text=v13_target_text or text_a)
        self.text_a, self.text_b = text_a, text_b
        self.v12b_call_index = 0

    def _v12b_response(self, text):
        target = self.text_a if self.v12b_call_index % 2 == 0 else self.text_b
        self.v12b_call_index += 1
        lines = _option_lines(text)
        for label, body in lines:
            if body == target:
                return json.dumps({"selected_label": label, "selected_option_text": body,
                                   "label_matches_option": True})
        if lines:
            label, body = lines[0]
            return json.dumps({"selected_label": label, "selected_option_text": body,
                               "label_matches_option": True})
        return json.dumps({})


def test_v12b_literal_tie_routes_to_v13():
    samples = [_sample("a", ["X", "Y", "p", "q"])]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _TieBackend("X", "Y", v13_mode="ok", v13_target_text="p")
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v12b_status == "tie"                  # the literal V12BAggregateStatus.TIE
    assert r.v13_attempted is True
    assert r.v13_layer == "content_first"
    assert r.final_source == FINAL_SOURCE_V13
    assert r.final_answer == "C"                    # "p" is choices[2] -> label C
    assert summary.v12b_aggregate_status_counts.get("tie") == 1
    assert summary.v13_layer_counts == {"content_first": 1}


def test_v12b_literal_tie_with_failing_v13_falls_back_to_base():
    samples = [_sample("a", ["X", "Y", "p", "q"])]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    backend = _TieBackend("X", "Y", v13_mode="raise")
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    r = records[0]
    assert r.v12b_status == "tie"
    assert r.final_source == FINAL_SOURCE_BASE_FALLBACK
    assert r.final_answer == r.base_answer == "A"


def test_pairing_valid_invalid_valid_never_misaligns():
    # A: V12B-accepted; B: invalid boundary (1 choice); C: routed to V13 and succeeds.
    samples = [
        _sample("A", ["alpha", "TARGET_A", "gamma", "delta"]),
        {"qid": "B", "question": "q", "choices": ["only"]},
        _sample("C", ["x", "y"], question="def x"),
    ]
    decisions = [
        _Decision(qid="A", input_index=0, generated_answer="A", selected_rank=1),
        _Decision(qid="B", input_index=1, generated_answer="A", selected_rank=2),
        _Decision(qid="C", input_index=2, generated_answer="A", selected_rank=3),
    ]

    class _MixedBackend(_Backend):
        def _v12b_response(self, text):
            lines = _option_lines(text)
            for label, body in lines:
                if body == "TARGET_A":
                    return json.dumps({"selected_label": label, "selected_option_text": body,
                                       "label_matches_option": True})
            return json.dumps({"nope": True})   # C's V12B attempt (2 choices) -> all_invalid

        def _v13_response(self, text):
            return json.dumps({"answer_content": "y", "answer_type": "term"})

    backend = _MixedBackend()
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    by_qid = {r.qid: r for r in records}
    assert by_qid["A"].final_source == FINAL_SOURCE_V12B and by_qid["A"].final_answer == "B"
    assert by_qid["B"].final_source == FINAL_SOURCE_BASE and by_qid["B"].v13_attempted is False
    assert by_qid["C"].final_source == FINAL_SOURCE_V13 and by_qid["C"].final_answer == "B"
    assert by_qid["A"].source_record_ordinal == 0
    assert by_qid["B"].source_record_ordinal == 1
    assert by_qid["C"].source_record_ordinal == 2


def test_duplicate_qid_and_input_index_stay_distinct():
    samples = [_sample("dup", ["x", "y"], question="def x"),
               _sample("dup", ["x", "y"], question="def x")]
    decisions = [_Decision(qid="dup", input_index=0, generated_answer="A", selected_rank=1),
                 _Decision(qid="dup", input_index=0, generated_answer="A", selected_rank=2)]
    backend = _Backend(v12b_mode="malformed", v13_mode="ok", v13_target_text="y")
    records, summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    assert len(records) == 2
    assert [r.source_record_ordinal for r in records] == [0, 1]
    assert summary.total_router_selected == 2 and summary.total_v13_attempted == 2


def test_every_final_answer_is_a_valid_canonical_label():
    samples = [
        _sample("a", ["p", "q", "r", "s"]),
        {"qid": "b", "question": "q", "choices": ["only"]},
        _sample("c", ["x", "y"], question="def x"),
        _sample("d", ["m", "n"], question="def m", ),
    ]
    decisions = [
        _Decision(qid="a", input_index=0, generated_answer="C", selected_rank=1),
        _Decision(qid="b", input_index=1, generated_answer="A", selected_rank=2),
        _Decision(qid="c", input_index=2, generated_answer="A", selected_rank=3),
        _Decision(qid="d", input_index=3, generated_answer="B", selected=False),
    ]
    backend = _Backend(v12b_mode="malformed", v13_mode="malformed")
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=backend, v12b_config=_Cfg())
    for record, sample in zip(records, samples):
        assert isinstance(record.final_answer, str)
        assert is_valid_label(record.final_answer, sample)
        assert record.final_answer in labels_for(len(sample["choices"]))


def test_non_canonical_base_answer_is_replaced_by_deterministic_fallback():
    """Defense-in-depth: even if a malformed decision carries a non-canonical
    ``generated_answer`` (a bug elsewhere, not reachable through predict.py's own
    coercion), the selector itself -- not just predict.py's caller-side check --
    must never emit a non-canonical final_answer."""
    samples = [_sample("a", ["p", "q"])]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="Z", selected=False)]
    records, _summary = run_full_pipeline(
        samples=samples, decisions=decisions, backend=_Backend(), v12b_config=_Cfg())
    r = records[0]
    assert r.final_answer == "A"                    # deterministic fallback (first label)
    assert r.final_source == FINAL_SOURCE_BASE_FALLBACK
    assert is_valid_label(r.final_answer, samples[0])


def test_decision_count_mismatch_raises_instead_of_silently_misaligning():
    samples = [_sample("a", ["x", "y"]), _sample("b", ["x", "y"])]
    decisions = [_Decision(qid="a", input_index=0)]   # one short -> must not silently misalign
    with pytest.raises(AssertionError):
        run_full_pipeline(samples=samples, decisions=decisions, backend=_Backend(), v12b_config=_Cfg())


def test_v12b_result_count_mismatch_fails_closed(monkeypatch):
    def _bad_v12b(inputs, **kwargs):
        from src.local_model.confidence_v12b_runner import V12BRunSummary
        return (), V12BRunSummary(
            total_selected_records=0, attempted_records=0, succeeded_records=0, failed_records=0,
            total_permutation_attempts=0, total_valid_permutations=0, parse_failure_total=0,
            generation_failure_total=0, aggregate_status_counts={}, base_v12b_disagreement_count=0,
            selected_qids=(), selected_items=())

    monkeypatch.setattr(fp_mod, "run_v12b_for_selected", _bad_v12b)
    samples = [_sample("a", ["alpha", "TARGET", "gamma", "delta"])]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    with pytest.raises(AssertionError):
        run_full_pipeline(samples=samples, decisions=decisions,
                          backend=_Backend(v12b_target_text="TARGET"), v12b_config=_Cfg())


def test_v13_result_count_mismatch_fails_closed(monkeypatch):
    def _bad_v13(inputs, **kwargs):
        from src.local_model.confidence_v13_runner import V13RunSummary
        return (), V13RunSummary(
            total_unresolved_records=0, attempted_records=0, valid_records=0, invalid_records=0,
            layer_counts={}, error_code_counts={})

    monkeypatch.setattr(fp_mod, "run_v13_for_unresolved", _bad_v13)
    samples = [_sample("a", ["x", "y"], question="def x")]
    decisions = [_Decision(qid="a", input_index=0, generated_answer="A")]
    with pytest.raises(AssertionError):
        run_full_pipeline(samples=samples, decisions=decisions,
                          backend=_Backend(v12b_mode="malformed"), v12b_config=_Cfg())
