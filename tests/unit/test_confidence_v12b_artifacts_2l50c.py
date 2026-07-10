"""Unit: Phase 3A-1 V12B artifact boundary — validation, safe pairing, privacy.

Proves closed input-validation codes, that invalid selected records never reach the
runner, that valid entries pair with runner results by list position only (A-valid /
B-invalid / C-valid never misaligns), duplicate qid/input_index stay distinct, and
persisted rows carry no private text. No torch/GPU/network (fake backend only).
"""

from __future__ import annotations

import json

from src.local_model import confidence_v12b_artifacts as art
from src.local_model.confidence_v12b_artifacts import (
    build_selected_entries,
    run_and_write_v12b_shadow,
)


class _Decision:
    """Minimal stand-in for ShadowRoutingDecision (only the fields the boundary reads)."""
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


class _FakeBackend:
    """Echoes the first presented option so every permutation maps to a valid vote."""
    def __init__(self):
        self.calls = 0

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        self.calls += 1
        user = ""
        if isinstance(prompt_or_messages, list):
            user = "".join(m.get("content", "") for m in prompt_or_messages if isinstance(m, dict))
        else:
            user = str(prompt_or_messages)
        text = "unknown"
        for line in user.splitlines():
            s = line.strip()
            if s[:2] == "A.":
                text = s[2:].strip()
                break
        return json.dumps({"selected_label": "A", "selected_option_text": text,
                           "label_matches_option": True})


class _Cfg:
    permutation_count = 6


def _sample(qid, n=4):
    return {"qid": qid, "question": f"Q {qid}?",
            "choices": [f"opt{i}" for i in range(n)]}


def test_validation_codes_cover_bad_records():
    samples = [
        _sample("ok", 4),                                   # ok
        "not-a-dict",                                       # invalid_record_shape
        {"qid": "nq", "question": 123, "choices": ["a", "b"]},   # invalid_question
        {"qid": "cs", "question": "q", "choices": "ABCD"},       # invalid_choices (string)
        {"qid": "one", "question": "q", "choices": ["only"]},    # unsupported_choice_count (<2)
        {"qid": "bad", "question": "q", "choices": ["a", "b"]},  # invalid_base_answer (below)
    ]
    decisions = [
        _Decision(qid="ok", input_index=0, selected_rank=1),
        _Decision(qid="nd", input_index=1, selected_rank=2),
        _Decision(qid="nq", input_index=2, selected_rank=3),
        _Decision(qid="cs", input_index=3, selected_rank=4),
        _Decision(qid="one", input_index=4, selected_rank=5),
        _Decision(qid="bad", input_index=5, selected_rank=6, generated_answer="Z"),
    ]
    selected, valid = build_selected_entries(samples, decisions)
    codes = [e["code"] for e in selected]
    assert codes == ["ok", "invalid_record_shape", "invalid_question",
                     "invalid_choices", "unsupported_choice_count", "invalid_base_answer"]
    assert [e["decision"].qid for e in valid] == ["ok"]


def test_invalid_router_rank_and_score_diagnostic():
    samples = [_sample("r", 4), _sample("s", 4)]
    decisions = [
        _Decision(qid="r", input_index=0, selected_rank=0),          # invalid_router_rank
        _Decision(qid="s", input_index=1, selected_rank=1, top1="Z"),  # invalid_score_diagnostic
    ]
    selected, valid = build_selected_entries(samples, decisions)
    assert [e["code"] for e in selected] == ["invalid_router_rank", "invalid_score_diagnostic"]
    assert valid == []


def test_non_selected_records_are_ignored():
    samples = [_sample("a"), _sample("b")]
    decisions = [_Decision(qid="a", input_index=0, selected=False),
                 _Decision(qid="b", input_index=1, selected=True)]
    selected, valid = build_selected_entries(samples, decisions)
    assert [e["decision"].qid for e in selected] == ["b"]


def test_pairing_valid_invalid_valid_never_misaligns(tmp_path):
    # A valid, B invalid (1 choice), C valid — result of C must never attach to B.
    samples = [_sample("A", 4),
               {"qid": "B", "question": "q", "choices": ["only"]},
               _sample("C", 4)]
    decisions = [_Decision(qid="A", input_index=0, selected_rank=1),
                 _Decision(qid="B", input_index=1, selected_rank=2),
                 _Decision(qid="C", input_index=2, selected_rank=3)]
    backend = _FakeBackend()
    jp = tmp_path / "v.jsonl"; sp = tmp_path / "v.json"
    run_and_write_v12b_shadow(samples=samples, decisions=decisions, router_summary=None,
                              backend=backend, v12b_config=_Cfg(),
                              jsonl_path=str(jp), summary_path=str(sp))
    rows = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    by_qid = {r["qid"]: r for r in rows}
    assert by_qid["A"]["v12b_attempted"] is True and by_qid["A"]["input_validation_status"] == "ok"
    assert by_qid["C"]["v12b_attempted"] is True and by_qid["C"]["input_validation_status"] == "ok"
    assert by_qid["B"]["v12b_attempted"] is False
    assert by_qid["B"]["input_validation_status"] == "unsupported_choice_count"
    assert "aggregate" not in by_qid["B"]
    # each valid record's nested aggregate belongs to its own qid
    assert by_qid["A"]["aggregate"]["qid"] == "A"
    assert by_qid["C"]["aggregate"]["qid"] == "C"
    # source identity is distinct from the runner-local record_ordinal
    assert by_qid["A"]["source_record_ordinal"] == 0
    assert by_qid["C"]["source_record_ordinal"] == 2
    assert by_qid["A"]["aggregate"]["record_ordinal"] == 0     # runner-local (filtered index)
    assert by_qid["C"]["aggregate"]["record_ordinal"] == 1     # C is 2nd VALID input


def test_duplicate_qid_and_input_index_stay_distinct(tmp_path):
    samples = [_sample("dup", 4), _sample("dup", 4)]
    decisions = [_Decision(qid="dup", input_index=0, selected_rank=1),
                 _Decision(qid="dup", input_index=0, selected_rank=2)]
    backend = _FakeBackend()
    jp = tmp_path / "v.jsonl"; sp = tmp_path / "v.json"
    run_and_write_v12b_shadow(samples=samples, decisions=decisions, router_summary=None,
                              backend=backend, v12b_config=_Cfg(),
                              jsonl_path=str(jp), summary_path=str(sp))
    rows = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    assert len(rows) == 2                                       # counted as records, not merged
    assert [r["source_record_ordinal"] for r in rows] == [0, 1]
    summary = json.loads(sp.read_text())
    assert summary["total_router_selected"] == 2 and summary["total_v12b_attempted"] == 2


def test_artifacts_are_privacy_safe_and_finite(tmp_path):
    samples = [_sample("p", 4)]
    decisions = [_Decision(qid="p", input_index=0, selected_rank=1)]
    jp = tmp_path / "v.jsonl"; sp = tmp_path / "v.json"
    run_and_write_v12b_shadow(samples=samples, decisions=decisions, router_summary=None,
                              backend=_FakeBackend(), v12b_config=_Cfg(),
                              jsonl_path=str(jp), summary_path=str(sp))
    blob = jp.read_text() + sp.read_text()
    for banned in ("question", "choices", "prompt", "selected_option_text",
                   "opt0", "opt1", "reasoning", "evidence"):
        assert banned not in blob
    for line in jp.read_text().splitlines():
        if line.strip():
            json.loads(line)
            json.dumps(json.loads(line), allow_nan=False)      # finite
    row = json.loads(jp.read_text().splitlines()[0])
    assert row["official_answer_source"] == "base"
    assert row["aggregate"]["official_answer_source"] == "base"
