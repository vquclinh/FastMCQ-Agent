"""Tests for the Phase 2L.25 answer-factory architecture (no API, no ground truth)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate, CandidatePool  # noqa: E402
from src.rag_lite import retrieve_cards_for_question, retrieve_cards_per_option  # noqa: E402
from src.tool_solvers import (cs_solver, finance_econ_solver, physics_solver,  # noqa: E402
                              safe_math_solver, stats_solver)

_DET = {"qid": "d", "question": "Tính định thức của ma trận [[3, 8], [4, 6]].",
        "choices": ["-14", "14", "50", "-50"]}
_KNOW = {"qid": "k", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon", "Nice", "Huế"]}


# --- candidate model ----------------------------------------------------------

def test_pool_dedup_and_votes():
    p = CandidatePool(qid="x")
    p.add(AnswerCandidate("x", "A", "v10_base", confidence=0.5))
    p.add(AnswerCandidate("x", "A", "v10_base", confidence=0.9))   # dup (source,answer)
    p.add(AnswerCandidate("x", "B", "tool:physics", confidence=0.97))
    p.add(AnswerCandidate("x", None, "tool:cs"))                    # ignored (no answer)
    p.deduplicate()
    assert len(p.candidates) == 2
    assert p.answer_votes() == {"A": 1, "B": 1}
    assert p.best_by_source("v10_base").confidence == 0.9
    assert set(p.sources()) == {"v10_base", "tool:physics"}


# --- tool solvers: positive + decline ----------------------------------------

def test_tool_solvers_positive():
    assert safe_math_solver.solve({"qid": "1", "question": "Tính giá trị của 2 + 3 * 4 là bao nhiêu?",
                                   "choices": ["10", "14", "20"]}).answer == "B"
    assert stats_solver.solve({"qid": "2", "question": "Cho dãy số: 2, 4, 6, 8. Số trung bình cộng?",
                               "choices": ["4", "5", "6"]}).answer == "B"
    assert finance_econ_solver.solve({"qid": "3", "question": "Lợi nhuận 200 trên vốn đầu tư 1000. ROI?",
                                      "choices": ["10%", "20%", "30%"]}).answer == "B"
    assert cs_solver.solve({"qid": "4", "question": "Chuyển số thập phân 10 sang nhị phân.",
                            "choices": ["1010", "1100", "1001"]}).answer == "A"
    assert physics_solver.solve(
        {"qid": "5", "question": "Một vật có khối lượng 2 kg chuyển động với vận tốc 3 m/s. "
                                 "Động năng là bao nhiêu?",
         "choices": ["6 J", "9 J", "18 J"]}).answer == "B"


def test_tool_solvers_decline():
    for tool in (safe_math_solver, stats_solver, finance_econ_solver, cs_solver, physics_solver):
        assert tool.solve(_KNOW) is None


def test_safe_math_rejects_dates_and_word_problems():
    # date inside long-context prose -> must NOT compute "24/1"
    s1 = {"qid": "a", "question": "Đoạn thông tin: Tuyết rơi ngày 24/1/2016. Phát biểu nào đúng?",
          "choices": ["x", "Tuyết 24/1/2016", "y"]}
    assert safe_math_solver.solve(s1) is None
    # polynomial word problem -> must NOT compute "2 + 3"
    s2 = {"qid": "b", "question": "Một hạt có vị trí x(t)=t^3 - 3t^2 + 3t + 1. Vận tốc nhỏ nhất tại t?",
          "choices": ["1 giây", "2 giây", "5 giây"]}
    assert safe_math_solver.solve(s2) is None


# --- RAG-lite -----------------------------------------------------------------

def test_rag_lite_retrieval():
    hits = retrieve_cards_for_question("Trong phân trang, địa chỉ luận lý có dạng nào?", top_k=3)
    assert hits and hits[0][0].id == "paging_logical_address"
    per = retrieve_cards_per_option("Định luật Ohm V=IR", ["3 A", "không liên quan"], top_k=1)
    assert set(per.keys()) == {"A", "B"}


# --- answer factory -----------------------------------------------------------

def test_factory_builds_candidates_no_api():
    pool = build_candidate_pool(_DET, "B", {"route": "calculation", "confidence": 0.6})
    assert "v10_base" in pool.sources() and "formula_bank" in pool.sources()


def test_factory_stubs_return_none():
    from src import answer_factory as af
    assert af.direct_route_prompt_agent_stub(_DET) is None
    assert af.self_consistency_agent_stub(_DET) is None
    assert af.pairwise_judge_agent_stub(_DET) is None


# --- ranker -------------------------------------------------------------------

def test_ranker_overrides_with_deterministic_proof():
    pool = build_candidate_pool(_DET, "B", {"route": "calculation", "confidence": 0.6})
    ans, rec = select_answer(pool, _DET, "B")
    assert ans == "A" and rec["decision"] == "override"


def test_ranker_keeps_base_when_alternative_weak():
    pool = build_candidate_pool(_KNOW, "A", {"route": "short_knowledge", "confidence": 0.9})
    ans, rec = select_answer(pool, _KNOW, "A")
    assert ans == "A" and rec["decision"] == "keep_base"


def test_ranker_keeps_base_when_candidate_contradicts_proof():
    # base already matches the deterministic proof; a (hypothetical) drift must not win.
    pool = build_candidate_pool(_DET, "A", {"route": "calculation", "confidence": 0.6})
    pool.add(AnswerCandidate("d", "C", "v10_base", confidence=0.4))   # noise, same source
    ans, rec = select_answer(pool, _DET, "A")
    assert ans == "A" and rec["decision"] == "keep_base"


# --- scripts: scratch-only + deterministic + source safety --------------------

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), (_ROOT / "scripts" / "legacy" / name if (_ROOT / "scripts" / "legacy" / name).exists() else _ROOT / "scripts" / name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_v11_generator_refuses_non_scratch_output():
    mod = _load("build_v11_answer_factory_proposals.py")
    try:
        mod.main(["--input", "x", "--output-dir", "output/foo"])
        assert False, "should refuse non-scratch output dir"
    except SystemExit as e:
        assert "scratch/" in str(e)


def test_selective_planner_refuses_non_scratch_output():
    mod = _load("plan_selective_multicandidate_api.py")
    try:
        mod.main(["--input", "x", "--output-dir", "output/foo"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


def test_no_qid_hardcoding_in_new_sources():
    import re as _re
    for rel in ("src/candidate_answer.py", "src/answer_factory.py", "src/answer_ranker.py",
                "src/rag_lite.py", "src/tool_solvers/safe_math_solver.py",
                "scripts/legacy/build_v11_answer_factory_proposals.py",
                "scripts/legacy/plan_selective_multicandidate_api.py"):
        src = (_ROOT / rel).read_text()
        for pat in (r'qid\s*==', r'==\s*["\']test_0', r'test_0\d{3}'):
            assert not _re.search(pat, src), f"{pat} in {rel}"
        assert "first100_external" not in src


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
