"""Tests for the Phase 2L.16 adaptive branch calibration suite.

No network, no real model. Loads script modules via importlib; runs no-API audits
into a temp dir; unit-tests evidence sufficiency and the shared override gate.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.adaptive_proposal_common import override_gate  # noqa: E402
from src.evidence_sufficiency import compute_evidence_sufficiency  # noqa: E402

_INPUT = str(_ROOT / "public-test_1780368312.json")
_PRED = str(_ROOT / "output" / "pred_v7_programmatic_assist_from_v6b.csv")
_LOG = str(_ROOT / "output" / "run_v6b_qwen_rerank_calc_verifier_fast.jsonl")
_HAVE_DATA = Path(_INPUT).exists() and Path(_PRED).exists() and Path(_LOG).exists()


def _load(name):
    path = _ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tmp(name):
    return str(Path(tempfile.mkdtemp()) / name)


# --- evidence sufficiency -----------------------------------------------------

def test_evidence_sufficiency_statuses():
    q = "Thủ đô của Ai Cập nằm bên bờ sông nào? Sông nào chảy qua thủ đô Ai Cập?"
    choices = ["Sông Nile", "Sông Amazon", "Sông Mê Kông", "Sông Hằng"]
    # Realistically long evidence (> 200 chars) so the length floor doesn't trip.
    strong = ("Thủ đô Cairo của Ai Cập nằm bên bờ sông Nile. Sông Nile là con sông dài "
              "nhất châu Phi và chảy qua Ai Cập. Cairo là thủ đô và thành phố lớn nhất "
              "của Ai Cập, nằm dọc theo bờ sông Nile gần đồng bằng châu thổ. ") * 2
    es = compute_evidence_sufficiency(q, choices, "A", strong)
    assert es.status in ("sufficient", "weak") and es.has_evidence
    # insufficient: tiny evidence
    es2 = compute_evidence_sufficiency(q, choices, "A", "ngắn")
    assert es2.status == "insufficient" and es2.recommendation == "needs evidence expansion"
    # unknown: no evidence
    es3 = compute_evidence_sufficiency(q, choices, "A", "")
    assert es3.status == "unknown" and es3.has_evidence is False


def test_evidence_sufficiency_never_returns_answer():
    es = compute_evidence_sufficiency("q?", ["A", "B"], "A", "some evidence text " * 20)
    d = es.to_dict()
    assert "answer" not in d and "selected_answer" not in d   # diagnostic only


# --- shared override gate -----------------------------------------------------

_GOOD = {"selected_answer": "B", "should_override": True, "confidence": 0.95,
         "reason": "B fits", "evidence_type": "legal_admin_knowledge"}


def test_override_gate_requires_allow_override():
    assert override_gate(_GOOD, "A", ["A", "B", "C"], allow_override=False) is False
    assert override_gate(_GOOD, "A", ["A", "B", "C"], allow_override=True) is True


def test_override_gate_blocks_uncertain_and_low_conf_and_same():
    assert not override_gate(dict(_GOOD, evidence_type="uncertain"), "A", ["A", "B"], allow_override=True)
    assert not override_gate(dict(_GOOD, confidence=0.5), "A", ["A", "B"], allow_override=True)
    assert not override_gate(dict(_GOOD, selected_answer="A"), "A", ["A", "B"], allow_override=True)
    assert not override_gate(dict(_GOOD, reason=""), "A", ["A", "B"], allow_override=True)


# --- candidate audits: no API, write a CSV, return 0 --------------------------

def test_law_admin_candidate_audit_no_api():
    if not _HAVE_DATA:
        return
    mod = _load("audit_law_admin_verifier_candidates.py")
    out = _tmp("la.csv")
    rc = mod.main(["--input", _INPUT, "--base-pred", _PRED, "--base-log", _LOG, "--output", out])
    assert rc == 0 and Path(out).exists()


def test_ambiguous_candidate_audit_no_api():
    if not _HAVE_DATA:
        return
    mod = _load("audit_ambiguous_adjudicator_candidates.py")
    out = _tmp("amb.csv")
    rc = mod.main(["--input", _INPUT, "--base-pred", _PRED, "--base-log", _LOG, "--output", out])
    assert rc == 0 and Path(out).exists()


def test_self_consistency_candidate_audit_no_api():
    if not _HAVE_DATA:
        return
    mod = _load("audit_self_consistency_candidates.py")
    out = _tmp("sc.csv")
    rc = mod.main(["--input", _INPUT, "--base-pred", _PRED, "--base-log", _LOG, "--output", out])
    assert rc == 0 and Path(out).exists()


# --- runners: dry-run default, no API -----------------------------------------

def test_law_admin_runner_dry_run_no_api():
    if not _HAVE_DATA:
        return
    mod = _load("run_law_admin_verifier_sample.py")
    rc = mod.main(["--input", _INPUT, "--base-pred", _PRED, "--base-log", _LOG,
                   "--max-calls", "7",
                   "--output-jsonl", _tmp("la.jsonl"), "--output-csv", _tmp("la2.csv")])
    assert rc == 0   # dry-run default -> no API, no exception


def test_self_consistency_runner_dry_run_no_api():
    if not _HAVE_DATA:
        return
    cand_mod = _load("audit_self_consistency_candidates.py")
    cand = _tmp("sc_cand.csv")
    cand_mod.main(["--input", _INPUT, "--base-pred", _PRED, "--base-log", _LOG, "--output", cand])
    run_mod = _load("run_selective_self_consistency_sample.py")
    rc = run_mod.main(["--input", _INPUT, "--candidates", cand, "--base-pred", _PRED,
                       "--max-calls", "5",
                       "--output-jsonl", _tmp("sc.jsonl"), "--output-csv", _tmp("sc2.csv")])
    assert rc == 0


# --- unified analyzer: graceful with missing files ----------------------------

def test_unified_analyzer_handles_missing_files():
    mod = _load("analyze_adaptive_branch_proposals.py")
    rc = mod.main(["--sk-proposals", "/nope/a.csv", "--risk-csv", "/nope/r.csv"])
    assert rc == 0


# --- source safety ------------------------------------------------------------

def test_branch_source_safety():
    import re as _re
    scripts = ["audit_law_admin_verifier_candidates.py", "run_law_admin_verifier_sample.py",
               "audit_ambiguous_adjudicator_candidates.py", "run_ambiguous_adjudicator_sample.py",
               "audit_self_consistency_candidates.py", "run_selective_self_consistency_sample.py",
               "analyze_adaptive_branch_proposals.py", "audit_long_context_evidence_sufficiency.py"]
    for name in scripts:
        src = (_ROOT / "scripts" / name).read_text()
        assert ".env" not in src and "OPENROUTER_API_KEY" not in src, name
        assert "first100_external" not in src, name        # never reads the answer sheet
        for pat in (r'qid\s*==', r'==\s*["\']test_0'):
            assert not _re.search(pat, src), f"qid hardcoding in {name}"
        # OpenRouter client (if used) must be imported lazily under the execute path.
        if "OpenRouterClient" in src:
            assert "if not dry_run:" in src, name
    # source modules too
    for name in ("evidence_sufficiency.py", "adaptive_proposal_common.py"):
        src = (_ROOT / "src" / name).read_text()
        for bad in ("import requests", "import urllib", "import socket", "eval(", "exec("):
            assert bad not in src, f"{bad} in {name}"


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
