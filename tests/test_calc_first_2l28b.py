"""Tests for Phase 2L.28B: calc-first planner, calc agent+parser, new solvers, analyzer."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src import api_candidate_agents as A  # noqa: E402
from src import calculation_first_planner as P  # noqa: E402
from src.formula_bank_solver import (labels_for, try_percent_change,  # noqa: E402
                                     try_simple_linear_equation)


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


# --- Part B: calc-first planner ----------------------------------------------

def test_subtype_detection():
    assert P.detect_calculation_subtype({"question": "Tính xác suất kỳ vọng", "choices": []}) == "probability"
    assert P.detect_calculation_subtype({"question": "diện tích tam giác", "choices": []}) == "geometry"
    assert P.detect_calculation_subtype({"question": "lãi suất lợi nhuận doanh thu", "choices": []}) == "finance_econ"
    assert P.detect_calculation_subtype({"question": "đổi hex sang nhị phân", "choices": []}) == "cs_numeric"
    assert P.detect_calculation_subtype({"question": "giải phương trình bậc hai", "choices": []}) == "algebra"
    assert P.detect_calculation_subtype({"question": "Một câu hỏi mơ hồ", "choices": []}) == "unknown"


def test_strategy_tool_only_when_solver_hits():
    s = {"question": "Giá 200 tăng 10%. Giá mới?", "choices": ["180", "220", "210", "200"]}
    st = P.recommend_calculation_strategy(s)
    assert st["strategy"] == "tool_only" and st["tool_answer"] == "B"


def test_strategy_tool_then_llm_and_compact():
    s_known = {"question": "Tính kỳ vọng E[Y]", "choices": ["k", "2k", "3k"]}
    assert P.recommend_calculation_strategy(s_known)["strategy"] == "tool_then_llm"
    s_unknown = {"question": "Một câu hỏi không rõ loại", "choices": ["A", "B"]}
    assert P.recommend_calculation_strategy(s_unknown)["strategy"] == "compact_llm"


def test_tool_context_shape():
    s = {"question": "Giá 200 tăng 10%?", "choices": ["180", "220"]}
    ctx = P.build_calculation_tool_context(s)
    assert set(ctx) >= {"subtype", "strategy", "formula_hints", "option_numeric_map",
                        "parsed_numbers", "tool_answer", "decline_reason"}
    assert ctx["option_numeric_map"] == {"A": [180.0], "B": [220.0]}
    assert "BỐI CẢNH TÍNH TOÁN" in P.format_tool_context_for_prompt(ctx)


# --- Part C: calculation_solver agent + parser -------------------------------

_S = {"question": "Giá 200 tăng 10%?", "choices": ["180", "220", "210", "200"]}


def test_calc_agent_builder_compact():
    msgs = A.build_calculation_solver(_S, "[CTX]")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert "JSON" in msgs[0]["content"]


def test_calc_parser_ok():
    r = A.parse_calculation_candidate(
        '{"final_answer":"B","final_numeric_value":220,"chosen_option_text":"220",'
        '"calculation_steps":["200*1.1=220"],"evidence":"200*1.1=220","confidence":0.9,"risk":"low"}', _S)
    assert r["parse_status"] == "ok" and r["answer"] == "B"


def test_calc_parser_numeric_mismatch():
    r = A.parse_calculation_candidate(
        '{"final_answer":"A","final_numeric_value":220,"chosen_option_text":"180",'
        '"calculation_steps":["x"],"evidence":"compute 220","risk":"low"}', _S)
    assert r["parse_status"] == "numeric_mismatch"


def test_calc_parser_missing_steps():
    r = A.parse_calculation_candidate(
        '{"final_answer":"B","final_numeric_value":220,"calculation_steps":[],'
        '"evidence":"200*1.1=220","risk":"low"}', _S)
    assert r["parse_status"] == "missing_steps"


def test_calc_parser_placeholder():
    r = A.parse_calculation_candidate(
        '{"final_answer":"B","final_numeric_value":220,"calculation_steps":["s"],'
        '"evidence":"","risk":"low"}', _S)
    assert r["parse_status"] == "placeholder_evidence"


def test_calc_parser_high_risk_passes_without_steps():
    r = A.parse_calculation_candidate(
        '{"final_answer":"B","final_numeric_value":220,"calculation_steps":[],'
        '"evidence":"","risk":"high"}', _S)
    assert r["parse_status"] == "ok"   # self-declared high risk is allowed (won't override)


# --- Part E: new deterministic solvers ---------------------------------------

def test_percent_change_positive():
    L = labels_for(4)
    assert try_percent_change("Giá 200 tăng 10%?", ["180", "220", "210", "200"], L).selected_answer == "B"
    assert try_percent_change("Giá 500 giảm 20%?", ["400", "450", "300", "350"], L).selected_answer == "A"


def test_percent_change_declines():
    L = labels_for(4)
    assert try_percent_change("Hai số 200 và 300, tăng 10%?", ["180", "220", "210", "200"], L) is None
    assert try_percent_change("Tính tổng hai số.", ["1", "2", "3", "4"], L) is None  # no percent


def test_simple_linear_positive_and_decline():
    L = labels_for(4)
    assert try_simple_linear_equation("Giải 2x + 3 = 11.", ["2", "3", "4", "5"], L).selected_answer == "C"
    assert try_simple_linear_equation("Không có phương trình ở đây.", ["1", "2", "3", "4"], L) is None


# --- Part D: route-aware runner ----------------------------------------------

def test_runner_route_aware_agents():
    mod = _load("run_adaptive_selective_api.py")
    assert mod._agents_temps_for("cheap_api", "calculation") == (["calculation_solver"], [0.0])
    assert mod._agents_temps_for("cheap_api", "short_knowledge") == (["challenger", "option_elimination"], [0.0])
    assert "calculation_solver" in mod._agents_temps_for("rich_api", "calculation")[0]


def test_runner_calc_upper_bound_includes_fallback():
    mod = _load("run_adaptive_selective_api.py")
    d = tempfile.mkdtemp()
    plan = Path(d) / "plan.csv"
    plan.write_text("qid,route,recommended_layer,priority_score\n"
                    "q1,calculation,cheap_api,2.0\nq2,calculation,cheap_api,2.0\n")
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Q?", "choices": ["A", "B"]},
                               {"qid": "q2", "question": "Q?", "choices": ["A", "B"]}]))
    base = Path(d) / "v10.csv"; base.write_text("qid,answer\nq1,A\nq2,A\n")
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main(["--input", str(inp), "--base-pred", str(base), "--plan", str(plan),
                  "--output-dir", "scratch/_calc_t", "--mode", "cheap", "--max-qids", "10"])
    # 2 qids * (1 calc agent + 1 fallback + 1 judge) = 6
    assert "upper-bound calls: 6" in buf.getvalue()


# --- Part A: failure analyzer -------------------------------------------------

def test_analyzer_classifies_and_refuses_outputs():
    mod = _load("analyze_pilot_failures.py")
    d = tempfile.mkdtemp()
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Q?", "choices": ["A", "B"]}]))
    base = Path(d) / "v10.csv"; base.write_text("qid,answer\nq1,A\n")
    pq = Path(d) / "pq.csv"
    pq.write_text("qid,route,recommended_layer\nq1,calculation,cheap_api\n")
    cands = Path(d) / "c.jsonl"
    cands.write_text("\n".join(json.dumps(r) for r in [
        {"qid": "q1", "agent": "challenger", "answer": None, "parse_status": "no_json", "total_tokens": 1200},
        {"qid": "q1", "agent": "option_elimination", "answer": "A", "parse_status": "numeric_mismatch",
         "evidence": "", "total_tokens": 500}]))
    out = Path(d) / "scratch" / "fa"
    rc = mod.main(["--input", str(inp), "--base-pred", str(base), "--pilot-qids", str(pq),
                   "--pilot-candidates", str(cands), "--output-dir", str(out)])
    assert rc == 0
    rows = list(__import__("csv").DictReader(open(out / "pilot_failure_analysis.csv")))
    assert rows[0]["primary_failure"] == "truncation"   # no_json @1200 tokens dominates
    assert (out / "pilot_failure_analysis.md").exists()
    try:
        mod.main(["--input", str(inp), "--base-pred", str(base), "--pilot-qids", str(pq),
                  "--pilot-candidates", str(cands), "--output-dir", "output/fa"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)
