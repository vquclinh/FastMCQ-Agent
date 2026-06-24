"""Tests for Phase 2L.27B: pairwise judge fix, adaptive runner, parser quality."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src import api_candidate_agents as agents  # noqa: E402

_S = {"qid": "x", "question": "Cournot? P=20-Q, C(q)=2q.",
      "choices": ["q_X=4,q_Y=4", "q_X=5,q_Y=5", "q_X=6,q_Y=6"]}


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


# --- Part C: parser quality gates --------------------------------------------

def test_parser_rejects_placeholder():
    r = agents.parse_candidate('{"answer":"A","confidence":0.9,"evidence":"some evidence","rationale":"r","risk":"low"}', _S)
    assert r["parse_status"] == "placeholder_evidence"


def test_parser_rejects_numeric_mismatch():
    r = agents.parse_candidate('{"answer":"A","confidence":0.9,"evidence":"q=(20-2)/3=6","risk":"low"}', _S)
    assert r["parse_status"] == "numeric_mismatch"   # A is q=4, evidence says 6


def test_parser_accepts_valid_evidence():
    r = agents.parse_candidate('{"answer":"C","confidence":0.9,"evidence":"q=(20-2)/3=6 theo đối xứng Cournot","risk":"low"}', _S)
    assert r["parse_status"] == "ok" and r["answer"] == "C"


# --- fakes for the runners ----------------------------------------------------

def _tiny(d, v10="A"):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Thủ đô Pháp?", "choices": ["Paris", "Lyon", "Nice"]}]))
    base = Path(d) / "v10.csv"; base.write_text(f"qid,answer\nq1,{v10}\n")
    plan = Path(d) / "plan.csv"; plan.write_text("qid\nq1\n")
    return str(inp), str(base), str(plan)


class _FakeSelective:
    """Returns a fixed answer with valid evidence; tracks calls. No network."""
    def __init__(self, model, answer="B", **kw):
        from src.model_policy import assert_allowed_llm_model
        assert_allowed_llm_model(model)
        self.model = model; self.total_calls = 0; self.total_tokens = 0; self.answer = answer

    def chat(self, messages, **kw):
        self.total_calls += 1
        return (json.dumps({"answer": self.answer, "winner_answer": self.answer, "confidence": 0.9,
                            "evidence": "Lyon là đáp án đúng theo lập luận chi tiết của tác nhân.",
                            "risk": "low", "requires_manual_review": False}), {"total_tokens": 5})


# --- Part A: pairwise judge fix ----------------------------------------------

def test_judge_runs_on_conflict(monkeypatch):
    import src.selective_api_client as sac
    mod = _load("run_selective_multicandidate_api.py")
    d = tempfile.mkdtemp(); inp, base, plan = _tiny(d, v10="A")
    out = Path(d) / "scratch" / "run"
    monkeypatch.setattr(sac, "SelectiveAPIClient", lambda *a, **k: _FakeSelective(*a, answer="B", **k))
    rc = mod.main(["--input", inp, "--base-pred", base, "--plan", plan, "--output-dir", str(out),
                   "--max-qids", "1", "--agents", "challenger", "--judge", "pairwise",
                   "--temperature-grid", "0", "--execute"])
    assert rc == 0
    recs = [json.loads(l) for l in (out / "api_candidates.jsonl").read_text().splitlines() if l.strip()]
    assert any(r["agent"] == "pairwise_judge" for r in recs)         # judge ran
    summ = json.loads((out / "api_run_summary.json").read_text())
    assert summ["judge_ran"] == 1


def test_judge_skipped_when_no_alternative(monkeypatch):
    import src.selective_api_client as sac
    mod = _load("run_selective_multicandidate_api.py")
    d = tempfile.mkdtemp(); inp, base, plan = _tiny(d, v10="B")   # v10 == agent answer "B"
    out = Path(d) / "scratch" / "run"
    monkeypatch.setattr(sac, "SelectiveAPIClient", lambda *a, **k: _FakeSelective(*a, answer="B", **k))
    mod.main(["--input", inp, "--base-pred", base, "--plan", plan, "--output-dir", str(out),
              "--max-qids", "1", "--agents", "challenger", "--judge", "pairwise",
              "--temperature-grid", "0", "--execute"])
    summ = json.loads((out / "api_run_summary.json").read_text())
    assert summ["judge_ran"] == 0 and summ["judge_skipped"] == 1
    assert "q1" in summ["judge_skip_reasons"]


def test_dry_run_calls_match_execute(monkeypatch):
    import src.selective_api_client as sac
    mod = _load("run_selective_multicandidate_api.py")
    d = tempfile.mkdtemp(); inp, base, plan = _tiny(d, v10="A")
    # dry-run upper bound: 1 agent * 1 temp + 1 judge = 2
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main(["--input", inp, "--base-pred", base, "--plan", plan,
                  "--output-dir", "scratch/_t", "--max-qids", "1", "--agents", "challenger",
                  "--judge", "pairwise", "--temperature-grid", "0"])
    assert "upper-bound calls: 2" in buf.getvalue()
    out = Path(d) / "scratch" / "run"
    fake = _FakeSelective("qwen/qwen3.5-9b", answer="B")
    monkeypatch.setattr(sac, "SelectiveAPIClient", lambda *a, **k: fake)
    mod.main(["--input", inp, "--base-pred", base, "--plan", plan, "--output-dir", str(out),
              "--max-qids", "1", "--agents", "challenger", "--judge", "pairwise",
              "--temperature-grid", "0", "--execute"])
    assert fake.total_calls == 2     # 1 agent + 1 judge (conflict) == dry-run upper bound


def test_judge_rejects_disallowed_model():
    mod = _load("run_selective_multicandidate_api.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--judge", "pairwise",
                  "--model", "gpt-4o"])
        assert False
    except ValueError:
        pass


# --- Part B: adaptive runner --------------------------------------------------

def _plan_file(d):
    p = Path(d) / "plan.csv"
    p.write_text("qid,route,recommended_layer,est_api_calls\n"
                 "q1,calculation,cheap_api,2\nq2,calculation,rich_api,5\nq3,calculation,tool_only,0\n")
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": f"q{i}", "question": "Q?", "choices": ["A", "B"]} for i in (1, 2, 3)]))
    base = Path(d) / "v10.csv"; base.write_text("qid,answer\nq1,A\nq2,A\nq3,A\n")
    return str(inp), str(base), str(p)


def test_adaptive_dry_run_no_api():
    mod = _load("run_adaptive_selective_api.py")
    d = tempfile.mkdtemp(); inp, base, plan = _plan_file(d)
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--input", inp, "--base-pred", base, "--plan", plan,
                       "--output-dir", "scratch/_ta", "--mode", "cheap", "--max-qids", "10"])
    assert rc == 0 and "DRY-RUN" in buf.getvalue()


def test_adaptive_cheap_fewer_than_rich():
    mod = _load("run_adaptive_selective_api.py")
    d = tempfile.mkdtemp(); inp, base, plan = _plan_file(d)
    import io
    from contextlib import redirect_stdout

    def _upper(mode):
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.main(["--input", inp, "--base-pred", base, "--plan", plan,
                      "--output-dir", "scratch/_ta", "--mode", mode, "--max-qids", "10"])
        for line in buf.getvalue().splitlines():
            if "upper-bound calls:" in line:
                return int(line.split("upper-bound calls:")[1].split()[0])
        return 0
    assert _upper("cheap") < _upper("rich")    # cheap schedules fewer calls


def test_adaptive_refuses_outputs_and_mutual_exclusive():
    mod = _load("run_adaptive_selective_api.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--output-dir", "output/z"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--dry-run", "--execute"])
        assert False
    except SystemExit as e:
        assert "mutually exclusive" in str(e)


def test_adaptive_rejects_disallowed_model():
    mod = _load("run_adaptive_selective_api.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--model", "claude-3"])
        assert False
    except ValueError:
        pass
