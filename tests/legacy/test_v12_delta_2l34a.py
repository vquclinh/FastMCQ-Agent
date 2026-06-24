"""Tests for Phase 2L.34A — V12 delta-safe verifier experiment."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_INPUT = str(_ROOT / "public-test_1780368312.json")
_V11 = str(_ROOT / "output" / "pred_v11_independent_rerun1.csv")


def _load(script):
    spec = importlib.util.spec_from_file_location(
        f"v12_{script}", _ROOT / "scripts" / f"{script}.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


# --- Part A: plan ranks weak/fallback qids -----------------------------------

def test_plan_ranks_fallback_and_weak_qids_first():
    plan = _load("build_v12_delta_plan")
    samples = [
        {"qid": "q1", "question": "x", "choices": ["a", "b", "c", "d"]},
        {"qid": "q2", "question": "y", "choices": ["a", "b", "c", "d", "e", "f"]},
        {"qid": "q3", "question": "z", "choices": ["a", "b"]},
    ]
    current = {"q1": "A", "q2": "B", "q3": "C"}
    decisions = {
        "q1": {"final_source": "direct_fallback", "route": "long_context", "risk": "high"},
        "q2": {"final_source": "consensus", "route": "calculation", "risk": "medium"},
        "q3": {"final_source": "formula_bank", "route": "calculation", "risk": "low"},
    }
    out = plan.build_plan(samples, current, decisions=decisions)
    # q1 (fallback+high+long_context) must outrank q3 (deterministic, low risk).
    order = [r["qid"] for r in out]
    assert order.index("q1") < order.index("q3")
    q1 = next(r for r in out if r["qid"] == "q1")
    assert "fallback_source:direct_fallback" in q1["risk_reason"]
    assert q1["opportunity_score"] > 0


def test_plan_no_qid_hardcoding():
    src = (_ROOT / "scripts" / "build_v12_delta_plan.py").read_text()
    assert not re.search(r"\btest_\d{4}\b", src)


# --- Part B: verifier dry-run makes no API call ------------------------------

def test_verifier_dry_run_no_api(monkeypatch):
    # Any attempt to construct the API client must fail the test.
    import src.api.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in dry-run")))
    runner = _load("run_v12_delta_verifier")
    d = tempfile.mkdtemp()
    samples_by_qid = {"q1": {"qid": "q1", "question": "x", "choices": ["a", "b", "c", "d"]}}
    plan_rows = [{"qid": "q1", "suggested_agents": "route_specialist|option_grounding|challenger"}]
    summary = runner.run(samples_by_qid, plan_rows, {"q1": "A"}, work_dir=d,
                         model="qwen/qwen3.5-9b-20260310", max_qids=10, budget_usd=0.5,
                         execute=False, dry_run=True, resume=False)
    assert summary["mode"] == "dry_run"
    assert summary["model_calls_made"] == 0
    # model agents recorded as dry_run, offline agent recorded as ok
    recs = [json.loads(l) for l in Path(summary["out"]).read_text().splitlines()]
    assert any(r["parse_status"] == "dry_run" and r["needs_api"] for r in recs)
    assert any(r["agent"] == "option_grounding" and not r["needs_api"] for r in recs)


def test_verifier_prompt_forces_json_label_and_option_text():
    runner = _load("run_v12_delta_verifier")
    sample = {"qid": "q1", "question": "2+2?", "choices": ["3", "4", "5", "6"]}
    msgs = runner.build_verifier_prompt(sample, "calculation_solver", "A")
    sys_txt = msgs[0]["content"]
    assert "JSON" in sys_txt and "selected_label" in sys_txt
    assert "selected_option_text" in sys_txt and "label_matches_option" in sys_txt
    assert "equation" in sys_txt  # calculation agent must request the equation


# --- Part C: conservative selector gates -------------------------------------

def _sample(n=4):
    return {"qid": "q1", "question": "q", "choices": [f"opt{i}" for i in range(n)]}


def test_selector_rejects_weak_model_only_single_source():
    sel = _load("build_v12_delta_candidate")
    cands = [{"qid": "q1", "agent": "route_specialist", "selected_label": "B",
              "label_matches_option": True, "parse_status": "ok"}]
    new, dec = sel.decide_override("q1", "A", cands, _sample(), policy="conservative")
    assert new is None and dec["verdict"] == "reject"


def test_selector_accepts_two_independent_sources():
    sel = _load("build_v12_delta_candidate")
    cands = [
        {"qid": "q1", "agent": "route_specialist", "selected_label": "B",
         "label_matches_option": True, "parse_status": "ok"},
        {"qid": "q1", "agent": "challenger", "selected_label": "B",
         "label_matches_option": True, "parse_status": "ok"},
    ]
    new, dec = sel.decide_override("q1", "A", cands, _sample(), policy="conservative")
    assert new == "B" and dec["verdict"] == "accept"


def test_selector_accepts_deterministic_low_risk_proof():
    sel = _load("build_v12_delta_candidate")
    cands = [
        {"qid": "q1", "agent": "deterministic_solver", "selected_label": "C",
         "label_matches_option": True, "parse_status": "ok"},
        {"qid": "q1", "agent": "numeric_consistency", "selected_label": "C",
         "label_matches_option": True, "parse_status": "ok"},
    ]
    new, dec = sel.decide_override("q1", "A", cands, _sample(), policy="conservative")
    assert new == "C" and dec["verdict"] == "accept"


def test_selector_rejects_numeric_label_mismatch():
    sel = _load("build_v12_delta_candidate")
    cands = [
        {"qid": "q1", "agent": "deterministic_solver", "selected_label": "B",
         "label_matches_option": False, "parse_status": "ok"},
        {"qid": "q1", "agent": "challenger", "selected_label": "B",
         "label_matches_option": True, "parse_status": "ok"},
    ]
    new, dec = sel.decide_override("q1", "A", cands, _sample(), policy="conservative")
    assert new is None and dec["verdict"] == "reject" and "mismatch" in dec["reason"]


def test_selector_validates_and_writes_candidate(tmp_path):
    sel = _load("build_v12_delta_candidate")
    # Empty candidates => candidate must equal v11 exactly (zero overrides), still valid.
    cand_jsonl = tmp_path / "cands.jsonl"; cand_jsonl.write_text("")
    out = tmp_path / "pred_v12_delta_candidate.csv"
    rc = sel.main(["--input", _INPUT, "--current", _V11,
                   "--candidates", str(cand_jsonl), "--output", str(out),
                   "--review-dir", str(tmp_path / "review")])
    assert rc == 0 and out.exists()
    assert _md5(out) == _md5(_V11)   # no change with no evidence


def test_selector_refuses_protected_outputs():
    sel = _load("build_v12_delta_candidate")
    for prot in ("output/pred_v11_independent_rerun1.csv", "output/pred.csv",
                 "output/pred_v10_full_production_user_run.csv"):
        try:
            sel.main(["--input", _INPUT, "--current", _V11, "--candidates",
                      str(_ROOT / "nonexistent.jsonl"), "--output", prot])
            assert False, prot
        except SystemExit as e:
            assert "protected" in str(e).lower()


# --- safety invariants -------------------------------------------------------

def test_frozen_v11_not_overwritten_md5_stable():
    # Sanity: the frozen winner md5 is the known value and unchanged by importing these tools.
    assert _md5(_V11) == "69f4e7c990e8c612e7bee53084d13b4d"


def test_production_default_is_v12b_frozen():
    fi = _load("final_infer")
    cfg = json.loads((_ROOT / "configs" / "production_v12b_permutation_7883.json").read_text())
    assert cfg["default_mode"] == "frozen_csv"
    assert cfg["current_best_csv"].endswith("pred_v12b_permutation_candidate_api30.csv")


def test_no_qid_hardcoding_across_v12_scripts():
    for name in ("build_v12_delta_plan", "run_v12_delta_verifier",
                 "build_v12_delta_candidate", "audit_v12_delta_candidate"):
        src = (_ROOT / "scripts" / f"{name}.py").read_text()
        assert not re.search(r"\btest_\d{4}\b", src), name
