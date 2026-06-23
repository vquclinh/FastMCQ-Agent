"""Tests for Phase 2L.30D: independent v11 run hardening (preflight/resume/finalize/guard/audit)."""

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


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "") + "_t",
                                                  _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


_RUN = _load("run_full_v11_independent_submission.py")
_S3 = {"qid": "q1", "question": "Q?", "choices": ["Paris", "Lyon", "Nice"]}
_S2 = {"qid": "q1", "question": "Q?", "choices": ["A", "B"]}


# --- Part D: _finalize_decision ----------------------------------------------

def test_finalize_last_resort_uses_sample_labels_only():
    # fallback returns a label OUTSIDE the 2-option sample -> must NOT be used
    dec = {"final_answer": None, "needs_direct_fallback": True}
    out = _RUN._finalize_decision(dec, _S2, direct_fallback_fn=lambda: {"answer": "C", "parse_status": "ok"})
    assert out["final_answer"] in ("A", "B")               # never "C"
    assert out["final_source"] == "last_resort_valid_choice"


def test_finalize_uses_pool_valid_label_before_last_resort():
    pool = CandidatePool(qid="q1")
    pool.add(AnswerCandidate("q1", "B", "api:option_elimination", risk_level="high", confidence=0.6))
    dec = {"final_answer": None, "needs_direct_fallback": True}
    out = _RUN._finalize_decision(dec, _S2, pool=pool,
                                  direct_fallback_fn=lambda: {"answer": None, "parse_status": "no_json"})
    assert out["final_answer"] == "B" and out["final_source"] == "pool_valid_label_repair"


def test_finalize_never_returns_invalid_when_choices_exist():
    for fb in ({"answer": None}, {"answer": "Z"}, {"answer": ""}):
        out = _RUN._finalize_decision({"final_answer": None, "needs_direct_fallback": True}, _S3,
                                      direct_fallback_fn=lambda: fb)
        assert out["final_answer"] in ("A", "B", "C")


def test_finalize_raises_when_no_choices():
    try:
        _RUN._finalize_decision({"final_answer": None, "qid": "qx"}, {"qid": "qx", "choices": []})
        assert False
    except SystemExit as e:
        assert "usable choice" in str(e).lower()


# --- Part B: preflight -------------------------------------------------------

def test_preflight_catches_missing_qid():
    try:
        _RUN._preflight({"": {"choices": ["A", "B"]}})
        assert False
    except SystemExit as e:
        assert "qid" in str(e).lower()


def test_preflight_catches_no_choices():
    try:
        _RUN._preflight({"q1": {"qid": "q1", "choices": []}})
        assert False
    except SystemExit as e:
        assert "choice" in str(e).lower()


def test_preflight_ok():
    out = _RUN._preflight({"q1": _S2})
    assert out["q1"] == ["A", "B"]


# --- Part C: resume scan -----------------------------------------------------

def _write_decisions(d, rows):
    wd = Path(d) / "scratch" / "wd"; wd.mkdir(parents=True, exist_ok=True)
    with open(wd / "v11_independent_decisions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "final_answer", "final_source",
                                           "needs_direct_fallback"])
        w.writeheader(); w.writerows(rows)
    return wd


def test_resume_does_not_treat_invalid_as_completed():
    d = tempfile.mkdtemp()
    samples = {"q1": _S2, "q2": _S2, "q3": _S2}
    wd = _write_decisions(d, [
        {"qid": "q1", "final_answer": "A", "final_source": "formula_bank", "needs_direct_fallback": ""},
        {"qid": "q2", "final_answer": "", "final_source": "none", "needs_direct_fallback": ""},
        {"qid": "q3", "final_answer": "A", "final_source": "needs_fallback", "needs_direct_fallback": "True"},
    ])
    completed, summary = _RUN._scan_resume_decisions(wd, samples)
    assert set(completed) == {"q1"}            # q2 (None) and q3 (flagged) are NOT completed
    assert summary["valid"] == 1 and summary["none_or_empty"] == 1 and summary["invalid"] == 1


def test_resume_keeps_latest_valid_for_duplicate():
    d = tempfile.mkdtemp()
    samples = {"q1": _S2}
    wd = _write_decisions(d, [
        {"qid": "q1", "final_answer": "A", "final_source": "x", "needs_direct_fallback": ""},
        {"qid": "q1", "final_answer": "B", "final_source": "y", "needs_direct_fallback": ""},
    ])
    completed, summary = _RUN._scan_resume_decisions(wd, samples)
    assert completed["q1"]["final_answer"] == "B" and summary["duplicate"] == 1


# --- Part E: pre-output write guard ------------------------------------------

def test_output_guard_catches_missing_qid_and_writes_report():
    d = tempfile.mkdtemp(); outdir = Path(d) / "scratch" / "wd"
    samples = {"q1": _S2, "q2": _S2}
    decisions = [{"qid": "q1", "final_answer": "A"}]      # q2 missing
    try:
        _RUN._assert_ready_for_output(decisions, samples, outdir, full_dataset=True)
        assert False
    except SystemExit as e:
        assert "pre-output validation failed" in str(e)
    rep = json.loads((outdir / "v11_independent_pre_output_failure_report.json").read_text())
    assert rep["missing"] == ["q2"]


def test_output_guard_passes_clean():
    d = tempfile.mkdtemp(); outdir = Path(d) / "scratch" / "wd"
    samples = {"q1": _S2, "q2": _S2}
    decisions = [{"qid": "q1", "final_answer": "A"}, {"qid": "q2", "final_answer": "B"}]
    assert _RUN._assert_ready_for_output(decisions, samples, outdir, full_dataset=True)


# --- Part F: integrity audit -------------------------------------------------

def _audit_fixture(d, dec_rows, sub_rows=None):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Q", "choices": ["A", "B"]},
                               {"qid": "q2", "question": "Q", "choices": ["A", "B"]}]))
    wd = Path(d) / "scratch" / "wd"; wd.mkdir(parents=True)
    with open(wd / "v11_independent_decisions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "final_answer", "final_source", "fallback_used"])
        w.writeheader(); w.writerows(dec_rows)
    (wd / "v11_independent_candidates.jsonl").write_text(json.dumps({"qid": "q1"}) + "\n")
    sub = None
    if sub_rows is not None:
        sub = Path(d) / "outputs" / "sub.csv"; sub.parent.mkdir(parents=True)
        with open(sub, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader(); w.writerows(sub_rows)
    return str(inp), str(wd), (str(sub) if sub else None)


def test_integrity_detects_none_dup_missing():
    mod = _load("audit_v11_independent_integrity.py")
    d = tempfile.mkdtemp()
    inp, wd, _ = _audit_fixture(d, [
        {"qid": "q1", "final_answer": "", "final_source": "none", "fallback_used": "False"},
        {"qid": "q1", "final_answer": "A", "final_source": "x", "fallback_used": "True"},
    ])  # q1 None + duplicate; q2 missing
    rc = mod.main(["--input", inp, "--work-dir", wd])
    assert rc == 0
    rep = json.loads((Path(wd) / "v11_independent_integrity_audit.json").read_text())
    dec = rep["decisions"]
    assert "q1" in dec["none_or_empty"] and "q1" in dec["duplicate_qids"] and "q2" in dec["missing_qids"]
    assert rep["decisions_clean"] is False


def test_integrity_validates_good_submission_and_handles_missing():
    mod = _load("audit_v11_independent_integrity.py")
    d = tempfile.mkdtemp()
    inp, wd, sub = _audit_fixture(
        d,
        [{"qid": "q1", "final_answer": "A", "final_source": "formula_bank", "fallback_used": "False"},
         {"qid": "q2", "final_answer": "B", "final_source": "consensus", "fallback_used": "False"}],
        sub_rows=[{"qid": "q1", "answer": "A"}, {"qid": "q2", "answer": "B"}])
    rc = mod.main(["--input", inp, "--work-dir", wd, "--submission", sub])
    assert rc == 0
    rep = json.loads((Path(wd) / "v11_independent_integrity_audit.json").read_text())
    assert rep["decisions_clean"] is True and rep["submission"]["valid_submission"] is True
    # missing submission must not crash
    rc2 = mod.main(["--input", inp, "--work-dir", wd, "--submission", f"{d}/nope.csv"])
    assert rc2 == 0
    rep2 = json.loads((Path(wd) / "v11_independent_integrity_audit.json").read_text())
    assert rep2["submission"]["present"] is False


def test_no_qid_hardcoding():
    for name in ("run_full_v11_independent_submission.py", "audit_v11_independent_integrity.py"):
        src = (_ROOT / "scripts" / name).read_text()
        assert not re.search(r"\btest_\d{4}\b", src)
