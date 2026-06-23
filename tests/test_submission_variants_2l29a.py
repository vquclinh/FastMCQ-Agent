"""Tests for Phase 2L.29A: submission variant builder, ensemble merger, variant audit."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _dataset(d, n=2):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": f"q{i}", "question": "Thủ đô?", "choices": ["Paris", "Lyon", "Nice"]}
                               for i in range(1, n + 1)]))
    base = Path(d) / "v10.csv"
    base.write_text("qid,answer\n" + "\n".join(f"q{i},A" for i in range(1, n + 1)) + "\n")
    return str(inp), str(base)


def _consensus_candidates(d, name="adaptive_api_candidates.jsonl"):
    """3 independent agents agree on B (non-v10) with valid evidence -> consensus override."""
    p = Path(d) / name
    recs = []
    for i in (1, 2):
        for ag in ("route_specialist", "challenger", "option_elimination"):
            recs.append({"qid": f"q{i}", "agent": ag, "answer": "B", "parse_status": "ok",
                         "confidence": 0.9, "risk": "medium",
                         "evidence": "Tài liệu xác nhận Lyon là đáp án đúng theo nguồn dẫn."})
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs))
    return str(p)


# --- Part A: variant builder guards ------------------------------------------

def test_variant_refuses_pilot_input():
    mod = _load("build_submission_variant.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d)
    cands = _consensus_candidates(d, name="pilot_api_candidates.jsonl")
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", f"{d}/outputs/v11.csv", "--review-dir", f"{d}/scratch/r",
                  "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "pilot" in str(e).lower()


def test_variant_refuses_protected_name_and_path_and_ack():
    mod = _load("build_submission_variant.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d); cands = _consensus_candidates(d)
    # missing ack
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", f"{d}/outputs/v11.csv", "--review-dir", f"{d}/scratch/r"])
        assert False
    except SystemExit as e:
        assert "i-understand" in str(e).lower() or "acknowledge" in str(e).lower()
    # non-outputs path
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", f"{d}/scratch/v11.csv", "--review-dir", f"{d}/scratch/r",
                  "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "outputs/" in str(e)
    # protected name
    try:
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", "outputs/pred.csv", "--review-dir", f"{d}/scratch/r",
                  "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "protected" in str(e).lower()


def test_variant_conservative_le_aggressive():
    mod = _load("build_submission_variant.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d); cands = _consensus_candidates(d)

    def _run(policy):
        out = f"{d}/outputs/{policy}.csv"
        mod.main(["--input", inp, "--base-pred", base, "--api-candidates", cands,
                  "--output", out, "--review-dir", f"{d}/scratch/{policy}",
                  "--policy", policy, "--min-coverage", "0.5", "--max-total-overrides", "100",
                  "--i-understand-this-writes-outputs"])
        diff = list(__import__("csv").DictReader(open(f"{d}/scratch/{policy}/variant_diff.csv")))
        return len(diff)
    cons, aggr = _run("conservative"), _run("aggressive")
    assert cons <= aggr               # consensus medium-risk overrides only survive aggressive/balanced
    assert cons == 0 and aggr >= 1


# --- Part B: ensemble --------------------------------------------------------

def _cand_csv(d, name, mapping):
    p = Path(d) / name
    p.write_text("qid,answer\n" + "\n".join(f"{q},{a}" for q, a in mapping.items()) + "\n")
    return str(p)


def test_ensemble_at_least_two():
    mod = _load("build_submission_ensemble.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d, n=2)
    c1 = _cand_csv(d, "c1.csv", {"q1": "B", "q2": "C"})
    c2 = _cand_csv(d, "c2.csv", {"q1": "B", "q2": "A"})
    c3 = _cand_csv(d, "c3.csv", {"q1": "A", "q2": "A"})
    out = f"{d}/outputs/ens.csv"
    rc = mod.main(["--input", inp, "--base-pred", base, "--candidates", c1, c2, c3,
                   "--output", out, "--review-dir", f"{d}/scratch/ens",
                   "--strategy", "at_least_two", "--i-understand-this-writes-outputs"])
    assert rc == 0
    pred = {r["qid"]: r["answer"] for r in __import__("csv").DictReader(open(out))}
    assert pred["q1"] == "B"          # 2 candidates agree on B -> override
    assert pred["q2"] == "A"          # only 1 non-v10 -> keep v10


def test_ensemble_validates_rowcount_and_labels():
    mod = _load("build_submission_ensemble.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d, n=2)
    short = _cand_csv(d, "short.csv", {"q1": "B"})          # missing q2
    try:
        mod.main(["--input", inp, "--base-pred", base, "--candidates", short,
                  "--output", f"{d}/outputs/e.csv", "--review-dir", f"{d}/scratch/e",
                  "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "row-count" in str(e).lower() or "qid set" in str(e).lower()
    bad = _cand_csv(d, "bad.csv", {"q1": "Z", "q2": "A"})   # invalid label
    try:
        mod.main(["--input", inp, "--base-pred", base, "--candidates", bad,
                  "--output", f"{d}/outputs/e.csv", "--review-dir", f"{d}/scratch/e",
                  "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "invalid label" in str(e).lower()


# --- Part C: audit -----------------------------------------------------------

def test_audit_variant_comparison():
    mod = _load("audit_submission_variants.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d, n=3)
    c1 = _cand_csv(d, "c1.csv", {"q1": "B", "q2": "A", "q3": "A"})
    c2 = _cand_csv(d, "c2.csv", {"q1": "B", "q2": "C", "q3": "A"})
    out = Path(d) / "scratch" / "audit"
    rc = mod.main(["--input", inp, "--base-pred", base, "--candidates", c1, c2,
                   "--output-dir", str(out)])
    assert rc == 0
    rows = {r["candidate"]: r for r in __import__("csv").DictReader(open(out / "variant_comparison.csv"))}
    assert rows["c1.csv"]["changed_vs_v10"] == "1"   # only q1
    assert rows["c2.csv"]["changed_vs_v10"] == "2"   # q1 + q2
    assert (out / "variant_comparison.md").exists()


def test_audit_refuses_outputs():
    mod = _load("audit_submission_variants.py")
    d = tempfile.mkdtemp(); inp, base = _dataset(d)
    c1 = _cand_csv(d, "c1.csv", {"q1": "B", "q2": "A"})
    try:
        mod.main(["--input", inp, "--base-pred", base, "--candidates", c1, "--output-dir", "outputs/a"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


# --- no qid hardcoding --------------------------------------------------------

def test_no_qid_hardcoding():
    for name in ("build_submission_variant.py", "build_submission_ensemble.py",
                 "audit_submission_variants.py", "print_submission_runbook.py"):
        src = (_ROOT / "scripts" / name).read_text()
        # qids look like test_0001 (4 digits); the dataset filename test_1780368312 is fine.
        assert not re.search(r"\btest_\d{4}\b", src), f"{name} hardcodes a qid"


def test_runbook_executes_nothing():
    mod = _load("print_submission_runbook.py")
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert mod.main([]) == 0
    out = buf.getvalue()
    assert "RUNBOOK" in out and "build_submission_variant.py" in out and "ensemble" in out.lower()
