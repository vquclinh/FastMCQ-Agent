"""Tests for Phase 2L.30D: independent v11 integrity-audit hardening."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "") + "_t",
                                                  next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{name}")), _ROOT / "scripts" / name))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


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
        sub = Path(d) / "output" / "sub.csv"; sub.parent.mkdir(parents=True)
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
    for name in ("audit_v11_independent_integrity.py",):
        src = (next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{name}")), _ROOT / "scripts" / name)).read_text()
        assert not re.search(r"\btest_\d{4}\b", src)
