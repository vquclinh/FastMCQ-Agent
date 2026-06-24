"""Tests for Phase 2L.28A: pilot selector, pilot runner, decision report, full-run gate."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), (_ROOT / "scripts" / "legacy" / name if (_ROOT / "scripts" / "legacy" / name).exists() else _ROOT / "scripts" / name))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _plan(d, n_cheap=25, n_tool=5):
    p = Path(d) / "plan.csv"
    lines = ["qid,route,v10_answer,has_tool_candidate,tool_answer,evidence_pack_status,"
             "consistency_issues,recommended_layer,est_api_calls,priority_score,reason"]
    routes = ["calculation", "short_knowledge", "long_context"]
    for i in range(n_cheap):
        lines.append(f"q{i},{routes[i % 3]},A,False,,True,0,cheap_api,2,{2.0 - (i % 3) * 0.5},calc")
    for i in range(n_tool):
        lines.append(f"t{i},calculation,B,True,B,True,0,tool_only,0,0.0,deterministic")
    p.write_text("\n".join(lines) + "\n")
    return str(p)


# --- Part A: selector ---------------------------------------------------------

def test_selector_returns_exactly_20_eligible():
    mod = _load("select_adaptive_pilot_qids.py")
    d = tempfile.mkdtemp()
    out = Path(d) / "scratch" / "pilot_qids.csv"
    rc = mod.main(["--plan", _plan(d), "--output", str(out), "--count", "20", "--mode", "cheap"])
    assert rc == 0
    rows = list(__import__("csv").DictReader(open(out)))
    assert len(rows) == 20
    assert all(r["recommended_layer"] != "tool_only" for r in rows)   # tool_only excluded
    assert {"qid", "route", "recommended_layer", "priority_score", "reason",
            "expected_calls"} == set(rows[0].keys())


def test_selector_caps_at_available():
    mod = _load("select_adaptive_pilot_qids.py")
    d = tempfile.mkdtemp()
    out = Path(d) / "scratch" / "pilot_qids.csv"
    mod.main(["--plan", _plan(d, n_cheap=8), "--output", str(out), "--count", "20", "--mode", "cheap"])
    rows = list(__import__("csv").DictReader(open(out)))
    assert len(rows) == 8     # only 8 eligible -> 8, not padded


def test_selector_refuses_non_scratch():
    mod = _load("select_adaptive_pilot_qids.py")
    d = tempfile.mkdtemp()
    try:
        mod.main(["--plan", _plan(d), "--output", "output/pilot.csv"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


def test_no_qid_hardcoding_in_sources():
    import re
    for name in ("select_adaptive_pilot_qids.py", "run_adaptive_pilot.py",
                 "build_pilot_decision_report.py", "build_full_adaptive_submission_candidate.py"):
        src = ((_ROOT / "scripts" / "legacy" / name if (_ROOT / "scripts" / "legacy" / name).exists() else _ROOT / "scripts" / name)).read_text()
        assert not re.search(r"test_\d{3,}", src), f"{name} hardcodes a qid"
        assert not re.search(r"\bq\d{3,}\b", src), f"{name} hardcodes a qid"


# --- Part B: pilot runner -----------------------------------------------------

def _pilot_qids(d):
    p = Path(d) / "pilot_qids.csv"
    p.write_text("qid,route,recommended_layer,priority_score,reason,expected_calls\n"
                 "q1,calculation,cheap_api,2.0,calc,3\nq2,short_knowledge,cheap_api,2.0,k,3\n")
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Q?", "choices": ["A", "B"]},
                               {"qid": "q2", "question": "Q2?", "choices": ["A", "B"]}]))
    base = Path(d) / "v10.csv"; base.write_text("qid,answer\nq1,A\nq2,B\n")
    return str(inp), str(base), str(p)


def test_pilot_runner_dry_run_no_api(monkeypatch):
    import src.selective_api_client as sac

    def _boom(*a, **k):
        raise AssertionError("API client must NOT be constructed during dry-run")
    monkeypatch.setattr(sac, "SelectiveAPIClient", _boom)
    mod = _load("run_adaptive_pilot.py")
    d = tempfile.mkdtemp(); inp, base, pq = _pilot_qids(d)
    rc = mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq,
                   "--output-dir", "scratch/_pilot_t", "--mode", "cheap", "--dry-run"])
    assert rc == 0


def test_pilot_runner_refuses_outputs_and_mutual_exclusive():
    mod = _load("run_adaptive_pilot.py")
    d = tempfile.mkdtemp(); inp, base, pq = _pilot_qids(d)
    try:
        mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq, "--output-dir", "output/x"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)
    try:
        mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq,
                  "--output-dir", "scratch/x", "--dry-run", "--execute"])
        assert False
    except SystemExit as e:
        assert "mutually exclusive" in str(e)


def test_pilot_runner_rejects_disallowed_model():
    mod = _load("run_adaptive_pilot.py")
    d = tempfile.mkdtemp(); inp, base, pq = _pilot_qids(d)
    try:
        mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq,
                  "--output-dir", "scratch/x", "--model", "gpt-4o", "--dry-run"])
        assert False
    except ValueError:
        pass


# --- Part C: decision report --------------------------------------------------

def _report_fixture(d, agree_v10=False):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Thủ đô?", "choices": ["Paris", "Lyon", "Nice"]}]))
    base = Path(d) / "v10.csv"; base.write_text("qid,answer\nq1,A\n")
    pq = Path(d) / "pilot_qids.csv"
    pq.write_text("qid,route,recommended_layer,priority_score,reason,expected_calls\n"
                  "q1,short_knowledge,cheap_api,2.0,k,3\n")
    ans = "A" if agree_v10 else "B"
    cands = Path(d) / "pilot_api_candidates.jsonl"
    recs = [{"qid": "q1", "agent": a, "answer": ans, "confidence": 0.9,
             "evidence": "Tài liệu xác nhận Lyon là trung tâm theo nguồn dẫn.",
             "rationale": "r", "risk": "low", "parse_status": "ok"}
            for a in ("route_specialist", "challenger", "option_elimination")]
    cands.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs))
    return str(inp), str(base), str(pq), str(cands)


def test_report_builds_override_decision():
    mod = _load("build_pilot_decision_report.py")
    d = tempfile.mkdtemp(); inp, base, pq, cands = _report_fixture(d, agree_v10=False)
    out = Path(d) / "scratch" / "rep"
    rc = mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq,
                   "--pilot-candidates", cands, "--output-dir", str(out)])
    assert rc == 0
    rows = list(__import__("csv").DictReader(open(out / "pilot_decisions.csv")))
    assert rows[0]["decision"] in ("override_candidate", "manual_review")
    assert (out / "pilot_decisions.md").exists()


def test_report_builds_keep_decision():
    mod = _load("build_pilot_decision_report.py")
    d = tempfile.mkdtemp(); inp, base, pq, cands = _report_fixture(d, agree_v10=True)
    out = Path(d) / "scratch" / "rep"
    mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq,
              "--pilot-candidates", cands, "--output-dir", str(out)])
    rows = list(__import__("csv").DictReader(open(out / "pilot_decisions.csv")))
    assert rows[0]["decision"] == "keep_v10"


def test_report_refuses_outputs():
    mod = _load("build_pilot_decision_report.py")
    d = tempfile.mkdtemp(); inp, base, pq, cands = _report_fixture(d)
    try:
        mod.main(["--input", inp, "--base-pred", base, "--pilot-qids", pq,
                  "--pilot-candidates", cands, "--output-dir", "output/rep"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


# --- Part D: full-run gate ----------------------------------------------------

def _full_fixture(d, name="adaptive_api_candidates.jsonl", n_samples=10, n_cov=10):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": f"q{i}", "question": "Q?", "choices": ["A", "B"]}
                               for i in range(n_samples)]))
    base = Path(d) / "v10.csv"
    base.write_text("qid,answer\n" + "\n".join(f"q{i},A" for i in range(n_samples)) + "\n")
    cands = Path(d) / name
    cands.write_text("\n".join(json.dumps({"qid": f"q{i}", "agent": "challenger", "answer": "A",
                                           "parse_status": "ok", "evidence": "x"})
                               for i in range(n_cov)))
    return str(inp), str(base), str(cands)


def test_full_builder_refuses_pilot_input():
    mod = _load("build_full_adaptive_submission_candidate.py")
    d = tempfile.mkdtemp(); inp, base, cands = _full_fixture(d, name="pilot_api_candidates.jsonl")
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", "output/cand_x.csv", "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "pilot" in str(e).lower()


def test_full_builder_refuses_partial_run():
    mod = _load("build_full_adaptive_submission_candidate.py")
    d = tempfile.mkdtemp()
    inp, base, cands = _full_fixture(d, n_samples=100, n_cov=10)   # 10% coverage
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", "output/cand_x.csv", "--i-understand-this-writes-outputs",
                  "--min-coverage", "0.8"])
        assert False
    except SystemExit as e:
        assert "coverage" in str(e).lower()


def test_full_builder_requires_outputs_path_and_ack():
    mod = _load("build_full_adaptive_submission_candidate.py")
    d = tempfile.mkdtemp(); inp, base, cands = _full_fixture(d)
    # missing ack
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", "output/cand_x.csv"])
        assert False
    except SystemExit as e:
        assert "acknowledge" in str(e).lower() or "i-understand" in str(e).lower()
    # non-outputs path
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", "scratch/cand_x.csv", "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "output/" in str(e)
    # protected pred name
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", "output/pred.csv", "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "protected" in str(e).lower()
