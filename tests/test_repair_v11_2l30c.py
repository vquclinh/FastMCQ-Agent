"""Tests for Phase 2L.30C: independent v11 null-answer repair (selector + runner + repair script)."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.candidate_answer import AnswerCandidate, CandidatePool  # noqa: E402
from src.independent_answer_selector import select_independent_answer  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "") + "_t",
                                                  _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


_S = {"qid": "q1", "question": "Q?", "choices": ["Paris", "Lyon", "Nice"]}


# --- Part A: selector fail-safe ----------------------------------------------

def test_selector_uses_fallback_not_none():
    a, dec = select_independent_answer(CandidatePool(qid="q1"), _S, route="x",
                                       fallback={"answer": "C", "parse_status": "ok"})
    assert a == "C" and dec["final_answer"] == "C" and not dec["needs_direct_fallback"]


def test_selector_signals_needs_fallback_when_nothing_valid():
    # one candidate with an invalid (None) label and no fallback -> must signal, not crash
    pool = CandidatePool(qid="q1")
    pool.add(AnswerCandidate("q1", None, "api:challenger", risk_level="high"))
    a, dec = select_independent_answer(pool, _S, route="x")
    assert a is None and dec["needs_direct_fallback"] is True and dec["final_source"] == "needs_fallback"


def test_selector_prefers_valid_label_candidate_over_none():
    pool = CandidatePool(qid="q1")
    pool.add(AnswerCandidate("q1", None, "api:challenger", risk_level="high"))
    pool.add(AnswerCandidate("q1", "B", "api:option_elimination", risk_level="high", confidence=0.4))
    a, dec = select_independent_answer(pool, _S, route="x")
    assert a == "B" and not dec["needs_direct_fallback"]


# --- Part A: runner _finalize_decision repair --------------------------------

def test_finalize_repairs_via_direct_fallback():
    mod = _load("run_full_v11_independent_submission.py")
    dec = {"final_answer": None, "final_source": "needs_fallback", "note": "no valid-label candidate",
           "needs_direct_fallback": True, "fallback_used": False, "risk": "high"}
    out = mod._finalize_decision(dec, _S, direct_fallback_fn=lambda: {"answer": "B", "parse_status": "ok"})
    assert out["final_answer"] == "B" and out["final_source"] == "direct_fallback_repair"
    assert out["fallback_used"] and not out["needs_direct_fallback"]


def test_finalize_last_resort_first_label():
    mod = _load("run_full_v11_independent_submission.py")
    dec = {"final_answer": None, "final_source": "needs_fallback", "needs_direct_fallback": True}
    out = mod._finalize_decision(dec, _S, direct_fallback_fn=lambda: {"answer": None, "parse_status": "no_json"})
    assert out["final_answer"] == "A"          # first valid choice label, deterministic, never None/v10
    # 2L.30D renamed the last-resort source from direct_fallback_repair -> last_resort_valid_choice
    assert out["final_source"] == "last_resort_valid_choice"


def test_finalize_keeps_valid_decision_untouched():
    mod = _load("run_full_v11_independent_submission.py")
    called = []
    dec = {"final_answer": "B", "final_source": "formula_bank", "needs_direct_fallback": False}
    out = mod._finalize_decision(dec, _S, direct_fallback_fn=lambda: called.append(1) or {"answer": "C"})
    assert out["final_answer"] == "B" and not called   # fallback not invoked for a valid decision


# --- Part B: repair script ---------------------------------------------------

def _work(d, rows, cands=None):
    wd = Path(d) / "scratch" / "wd"; wd.mkdir(parents=True)
    with open(wd / "v11_independent_decisions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "final_answer", "final_source", "note"])
        w.writeheader(); w.writerows(rows)
    if cands:
        (wd / "v11_independent_candidates.jsonl").write_text(
            "\n".join(json.dumps(c) for c in cands))
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Q?", "choices": ["A", "B"]},
                               {"qid": "q2", "question": "Q?", "choices": ["A", "B"]}]))
    return str(inp), str(wd)


def test_repair_detects_none_label_dry_run(monkeypatch):
    import src.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in dry-run")))
    mod = _load("repair_v11_independent_run.py")
    d = tempfile.mkdtemp()
    inp, wd = _work(d, [{"qid": "q1", "final_answer": "A", "final_source": "formula_bank", "note": ""},
                        {"qid": "q2", "final_answer": "", "final_source": "none", "note": "no candidates"}])
    rc = mod.main(["--input", inp, "--work-dir", wd, "--output", f"{d}/output/r.csv",
                   "--model", "qwen/qwen3.5-9b-20260310", "--dry-run"])
    assert rc == 0
    rep = json.loads((Path(wd) / "v11_independent_repair_report.json").read_text())
    assert rep["none_labels"] == 1 and rep["broken_total"] == 1
    assert not Path(f"{d}/output/r.csv").exists()     # no outputs in dry-run


def test_repair_refuses_v10_usage_in_source():
    src = (_ROOT / "scripts" / "repair_v11_independent_run.py").read_text()
    assert "v10_base" not in src and "--base-pred" not in src and "base_pred" not in src


def test_repair_execute_requires_ack():
    mod = _load("repair_v11_independent_run.py")
    d = tempfile.mkdtemp()
    inp, wd = _work(d, [{"qid": "q1", "final_answer": "A", "final_source": "x", "note": ""},
                        {"qid": "q2", "final_answer": "A", "final_source": "x", "note": ""}])
    try:
        mod.main(["--input", inp, "--work-dir", wd, "--output", f"{d}/output/r.csv",
                  "--model", "qwen/qwen3.5-9b-20260310", "--execute"])
        assert False
    except SystemExit as e:
        assert "i-understand" in str(e).lower()


def test_repair_execute_reuses_candidate_and_validates(monkeypatch):
    import src.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("candidate reuse must not call API")))
    mod = _load("repair_v11_independent_run.py")
    d = tempfile.mkdtemp()
    # q2 is broken but has a valid candidate in the jsonl -> repaired without API
    inp, wd = _work(d,
                    [{"qid": "q1", "final_answer": "A", "final_source": "formula_bank", "note": ""},
                     {"qid": "q2", "final_answer": "", "final_source": "none", "note": "no candidates"}],
                    cands=[{"qid": "q2", "agent": "route_specialist", "answer": "B",
                            "parse_status": "ok", "confidence": 0.8, "evidence": "x"}])
    rc = mod.main(["--input", inp, "--work-dir", wd, "--output", f"{d}/output/r.csv",
                   "--model", "qwen/qwen3.5-9b-20260310", "--execute",
                   "--i-understand-this-writes-outputs"])
    assert rc == 0
    pred = {r["qid"]: r["answer"] for r in csv.DictReader(open(f"{d}/output/r.csv"))}
    assert set(pred) == {"q1", "q2"} and pred["q2"] == "B" and pred["q1"] == "A"


def test_repair_protected_output_rejected():
    mod = _load("repair_v11_independent_run.py")
    d = tempfile.mkdtemp()
    inp, wd = _work(d, [{"qid": "q1", "final_answer": "A", "final_source": "x", "note": ""}])
    try:
        mod.main(["--input", inp, "--work-dir", wd, "--output", "output/pred.csv",
                  "--model", "qwen/qwen3.5-9b-20260310", "--dry-run"])
        assert False
    except SystemExit as e:
        assert "protected" in str(e).lower()


def test_repair_disallowed_model_rejected():
    mod = _load("repair_v11_independent_run.py")
    d = tempfile.mkdtemp()
    inp, wd = _work(d, [{"qid": "q1", "final_answer": "A", "final_source": "x", "note": ""}])
    try:
        mod.main(["--input", inp, "--work-dir", wd, "--output", f"{d}/output/r.csv",
                  "--model", "claude-3-opus", "--dry-run"])
        assert False
    except ValueError:
        pass


def test_no_qid_hardcoding():
    src = (_ROOT / "scripts" / "repair_v11_independent_run.py").read_text()
    assert not re.search(r"\btest_\d{4}\b", src)
