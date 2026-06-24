"""Tests for the Phase 2L.27A accuracy-engine expansion (no API, no outputs writes)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.adaptive_accuracy_planner import (build_adaptive_plan, estimate_calls_for_plan,
                                           recommend_layers_for_question,
                                           score_question_difficulty)
from src.candidate_answer import AnswerCandidate
from src.evidence_pack import (build_calculation_evidence_pack,
                               build_short_knowledge_evidence_pack)
from src.option_grounding import (map_claim_to_option, verify_answer_label_matches_reasoning)
from src.tool_solvers import cs_solver, finance_econ_solver, geometry_solver, probability_solver


# --- option grounding ---------------------------------------------------------

_OPTS = ["q_X = 4, q_Y = 4", "q_X = 5, q_Y = 5", "q_X = 6, q_Y = 6"]


def test_map_claim_numeric_and_ambiguous():
    assert map_claim_to_option(6.0, _OPTS) == "C"
    assert map_claim_to_option(4.5, _OPTS) is None        # ambiguous/no match
    assert map_claim_to_option("Paris thủ đô", ["Paris là thủ đô", "Lyon"]) == "A"


def test_verify_label_matches_reasoning():
    s = {"qid": "x", "question": "?", "choices": _OPTS}
    good = AnswerCandidate("x", "C", "api", evidence_text="q = (20-2)/3 = 6")
    bad = AnswerCandidate("x", "A", "api", evidence_text="q = (20-2)/3 = 6")
    assert verify_answer_label_matches_reasoning(good, s) is True
    assert verify_answer_label_matches_reasoning(bad, s) is False


# --- evidence pack ------------------------------------------------------------

def test_calculation_evidence_pack_no_answer():
    s = {"qid": "c", "question": "Tính định thức ma trận [[3,8],[4,6]].",
         "choices": ["-14", "14", "50"]}
    pk = build_calculation_evidence_pack(s)
    d = pk.to_dict()
    assert "answer" not in d and pk.kind == "calculation"


def test_short_knowledge_evidence_pack():
    s = {"qid": "k", "question": "Trong phân trang, địa chỉ luận lý có dạng nào?",
         "choices": ["page+offset", "frame", "size"]}
    pk = build_short_knowledge_evidence_pack(s)
    assert pk.kind == "short_knowledge" and any(c["id"] == "paging_logical_address" for c in pk.cards)


# --- new domain solvers: positive + decline ----------------------------------

def test_probability_independent():
    r = probability_solver.solve({"qid": "p", "question":
        "Hai biến cố độc lập xác suất 0,5 và 0,4. Xác suất cả hai cùng xảy ra?",
        "choices": ["0.2", "0.9", "0.1"]})
    assert r and r.answer == "A" and r.rule_id == "independent_and"


def test_probability_declines():
    assert probability_solver.solve({"qid": "p", "question": "Xác suất là gì?",
                                     "choices": ["a", "b"]}) is None


def test_geometry_rectangle_and_decline():
    r = geometry_solver.solve({"qid": "g", "question": "Hình chữ nhật dài 6 rộng 4. Diện tích?",
                               "choices": ["24", "20", "10"]})
    assert r and r.answer == "A"
    assert geometry_solver.solve({"qid": "g", "question": "Hình chữ nhật là gì?",
                                  "choices": ["a", "b"]}) is None


def test_cs_hex_and_subnet():
    assert cs_solver.solve({"qid": "c", "question": "Chuyển thập phân 255 sang thập lục phân.",
                            "choices": ["FF", "EE", "F0"]}).answer == "A"
    assert cs_solver.solve({"qid": "c", "question": "Mạng con IPv4 /24 có bao nhiêu host khả dụng?",
                            "choices": ["254", "256", "510"]}).answer == "A"


def test_finance_monopoly_and_decline():
    r = finance_econ_solver.solve({"qid": "f", "question":
        "Hãng độc quyền có cầu P=20-Q, MC=4. Sản lượng tối ưu?", "choices": ["6", "8", "10"]})
    assert r and r.answer == "B"      # q*=(20-4)/2=8 -> option B
    # duopoly wording must NOT use the monopoly rule
    assert finance_econ_solver.solve({"qid": "f", "question":
        "Định nghĩa độc quyền là gì?", "choices": ["a", "b"]}) is None


# --- adaptive planner ---------------------------------------------------------

def test_planner_tool_only_for_deterministic():
    s = {"qid": "c", "question": "Tính định thức ma trận [[3,8],[4,6]].",
         "choices": ["-14", "14", "50"]}
    assert recommend_layers_for_question(s) == "tool_only"
    assert score_question_difficulty(s) == 0.0


def test_planner_recommends_api_for_hard_calc():
    s = {"qid": "h", "question": "Một bài toán giải tích phức tạp cần suy luận?",
         "choices": ["A", "B", "C", "D"]}
    layer = recommend_layers_for_question(s, {"route": "calculation", "confidence": 0.4})
    assert layer in ("cheap_api", "rich_api")


def test_build_adaptive_plan_and_estimate():
    samples = [{"qid": "c", "question": "Tính định thức ma trận [[2,0],[0,2]].", "choices": ["0", "4"]},
               {"qid": "k", "question": "Câu hỏi khó cần API?", "choices": ["A", "B"]}]
    rows, selected = build_adaptive_plan(samples, max_qids=10)
    assert len(rows) == 2
    assert estimate_calls_for_plan(rows) >= 0
    assert all(r["est_calls"] > 0 for r in selected)   # only API-needing qids selected


# --- scripts: scratch-only + source safety ------------------------------------

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), (_ROOT / "scripts" / "legacy" / name if (_ROOT / "scripts" / "legacy" / name).exists() else _ROOT / "scripts" / name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scripts_refuse_outputs_dir():
    for name, args in (("build_overall_accuracy_plan.py",
                        ["--input", "x", "--base-pred", "y", "--output-dir", "output/z"]),
                       ("audit_selective_runner_behavior.py",
                        ["--api-candidates", "x", "--output-dir", "output/z"])):
        mod = _load(name)
        try:
            mod.main(args)
            assert False, f"{name} should refuse output/"
        except SystemExit as e:
            assert "scratch/" in str(e)


def test_no_qid_hardcoding_in_new_sources():
    import re as _re
    for rel in ("src/option_grounding.py", "src/evidence_pack.py",
                "src/adaptive_accuracy_planner.py", "src/tool_solvers/probability_solver.py",
                "src/tool_solvers/geometry_solver.py",
                "scripts/legacy/build_overall_accuracy_plan.py",
                "scripts/legacy/audit_selective_runner_behavior.py"):
        src = (_ROOT / rel).read_text()
        for pat in (r'qid\s*==', r'==\s*["\']test_0', r'test_0\d{3}'):
            assert not _re.search(pat, src), f"{pat} in {rel}"
        assert "first100_external" not in src
