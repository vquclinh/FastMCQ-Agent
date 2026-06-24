"""Tests for Phase 2L.39C — V13 empty-prompt guard, progress logging, incremental JSONL, resume.

No real API: a fake client is injected / monkeypatched. All deterministic.
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.api.selective_api_client import SelectiveAPIClient
import src.api.selective_api_client as sac
from src.layers.v12b_dynamic_layer import run_v12b_layer, select_v12b_targets
from src.layers.v13_dynamic_layer import run_v13_layer, select_v13_targets, build_messages
import src.layers.v13_dynamic_layer as v13mod
from src.base.dynamic_base_predictor import predict_base_answers


# --- fakes -------------------------------------------------------------------

class _FakeClient:
    """Stands in for SelectiveAPIClient during execute_api tests (no network)."""
    calls = 0

    def __init__(self, *a, **k):
        pass

    def chat(self, messages, **k):
        _FakeClient.calls += 1
        return ('{"selected_label": "A", "selected_option_text": "opt 0", '
                '"label_matches_option": true, "confidence": 0.9, '
                '"answer_content": "opt 0", "final_survivor_label": null}', {})

    @staticmethod
    def parse_json(content):
        try:
            return json.loads(content)
        except Exception:
            return None


def _samples(n=2, choices=4):
    return [{"qid": f"qq{i}", "question": "2 + 2 bằng bao nhiêu?",
             "choices": [f"opt {j}" for j in range(choices)]} for i in range(n)]


# --- Part B: empty-prompt guard ---------------------------------------------

def test_chat_empty_string_raises_before_api():
    class _Dummy:
        called = False
        def chat(self, *a, **k):
            _Dummy.called = True
            raise AssertionError("network must not be hit")
    c = SelectiveAPIClient(model="qwen/qwen3.5-9b-20260310", client=_Dummy())
    for bad in ("", "   ", None, [], [{"role": "user", "content": "  "}]):
        try:
            c.chat(bad)
            assert False, f"expected ValueError for {bad!r}"
        except ValueError as e:
            assert "empty prompt" in str(e).lower()
    assert _Dummy.called is False


def test_build_messages_valid_and_empty():
    s = _samples(1)[0]
    msgs, n = build_messages("content_first", s, "short_knowledge")
    assert isinstance(msgs, list) and msgs and n > 0
    # unknown layer -> safe generic prompt (non-empty)
    msgs2, n2 = build_messages("totally_unknown_layer", s, "x")
    assert msgs2 and n2 > 0


def test_v13_empty_prompt_is_skipped_not_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    monkeypatch.setattr(v13mod, "_prompt", lambda layer, s, route: "")   # force empty prompt
    _FakeClient.calls = 0
    s = _samples(1)
    base = predict_base_answers(s, model=None, execute_api=False, budget_usd=None,
                                work_dir=None, resume=False)
    targets = select_v13_targets(s, base, max_qids=None)
    res = run_v13_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                        budget_usd=1.0, work_dir=str(tmp_path / "w"), resume=False)
    assert res and all(r.reason == "skipped_empty_prompt" for r in res)
    assert _FakeClient.calls == 0           # never called the API with an empty prompt


# --- Part D: incremental JSONL ----------------------------------------------

def test_v13_writes_incremental_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    _FakeClient.calls = 0
    s = _samples(1)
    base = predict_base_answers(s, model=None, execute_api=False, budget_usd=None,
                                work_dir=None, resume=False)
    targets = select_v13_targets(s, base, max_qids=None)
    run_v13_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                  budget_usd=1.0, work_dir=str(tmp_path / "w"), resume=False)
    recs = (tmp_path / "w" / "v13_dynamic_records.jsonl").read_text().splitlines()
    assert recs and all(json.loads(l).get("qid") for l in recs)


def test_v12b_writes_incremental_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    _FakeClient.calls = 0
    s = _samples(1)
    base = predict_base_answers(s, model=None, execute_api=False, budget_usd=None,
                                work_dir=None, resume=False)
    targets = select_v12b_targets(s, base, max_qids=None)
    run_v12b_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                   budget_usd=1.0, permutations=6, policy="conservative",
                   work_dir=str(tmp_path / "w"), resume=False)
    recs = (tmp_path / "w" / "v12b_dynamic_records.jsonl").read_text().splitlines()
    assert recs and all(json.loads(l).get("original_qid") for l in recs)


# --- Part E: resume ----------------------------------------------------------

def test_v13_resume_skips_completed_units(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    s = _samples(1)
    base = predict_base_answers(s, model=None, execute_api=False, budget_usd=None,
                                work_dir=None, resume=False)
    targets = select_v13_targets(s, base, max_qids=None)
    wd = str(tmp_path / "w")
    _FakeClient.calls = 0
    run_v13_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                  budget_usd=1.0, work_dir=wd, resume=False)
    first_calls = _FakeClient.calls
    n_lines_1 = len((Path(wd) / "v13_dynamic_records.jsonl").read_text().splitlines())
    assert first_calls > 0
    # Resume: everything already completed -> 0 new calls, no duplicate lines.
    _FakeClient.calls = 0
    res2 = run_v13_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                         budget_usd=1.0, work_dir=wd, resume=True)
    n_lines_2 = len((Path(wd) / "v13_dynamic_records.jsonl").read_text().splitlines())
    assert _FakeClient.calls == 0 and n_lines_2 == n_lines_1
    assert len(res2) == sum(len(t.target_layers) for t in targets)


def test_v12b_resume_skips_completed_permutations(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    s = _samples(1)
    base = predict_base_answers(s, model=None, execute_api=False, budget_usd=None,
                                work_dir=None, resume=False)
    targets = select_v12b_targets(s, base, max_qids=None)
    wd = str(tmp_path / "w")
    _FakeClient.calls = 0
    run_v12b_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                   budget_usd=1.0, permutations=6, policy="conservative", work_dir=wd, resume=False)
    first = _FakeClient.calls
    n1 = len((Path(wd) / "v12b_dynamic_records.jsonl").read_text().splitlines())
    assert first > 0 and n1 == first
    _FakeClient.calls = 0
    run_v12b_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                   budget_usd=1.0, permutations=6, policy="conservative", work_dir=wd, resume=True)
    n2 = len((Path(wd) / "v12b_dynamic_records.jsonl").read_text().splitlines())
    assert _FakeClient.calls == 0 and n2 == n1   # no new calls, no duplicate records


# --- Part C: progress logs ---------------------------------------------------

def test_progress_logs_include_qid_layer_index(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    _FakeClient.calls = 0
    s = _samples(1)
    base = predict_base_answers(s, model=None, execute_api=False, budget_usd=None,
                                work_dir=None, resume=False)
    targets = select_v13_targets(s, base, max_qids=None)
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_v13_layer(s, base, targets, model="qwen/qwen3.5-9b-20260310", execute_api=True,
                      budget_usd=1.0, work_dir=str(tmp_path / "w"), resume=False)
    out = buf.getvalue()
    assert re.search(r"\[V13\] \d+/\d+ qid=\S+ layer=\S+ prompt_len=\d+", out)
    assert "[V13] done records=" in out


# --- hygiene -----------------------------------------------------------------

def test_no_qid_or_answer_hardcoding():
    for name in ("v13_dynamic_layer", "v12b_dynamic_layer", "dynamic_base_predictor",
                 "fastmcq_system", "selective_api_client"):
        src = (next(iter((_ROOT / "src").glob(f"**/{name}.py")))).read_text()
        assert not re.search(r"\btest_\d{4}\b", src), name
