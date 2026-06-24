"""Tests for the short-knowledge verifier proposal calibration (Phase 2L.15C-B).

No network, no real model. Loads the script modules via importlib to test the
critical override gate and the proposal analyzer helpers, plus source-safety checks.
Runnable with pytest, or standalone.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _load(name):
    path = next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{name}")), _ROOT / "scripts" / name)
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_RUNNER = _load("run_short_knowledge_verifier_sample.py")
_ANALYZER = _load("analyze_short_knowledge_verifier_proposals.py")

_LABELS = ["A", "B", "C", "D"]
_GOOD_PROPOSAL = {"selected_answer": "B", "should_override": True, "confidence": 0.95,
                  "reason": "B matches the definition", "evidence_type": "internal_knowledge"}


def test_gate_requires_allow_override():
    # A perfect override proposal is still NOT applied unless allow_override=True.
    assert _RUNNER._gate(_GOOD_PROPOSAL, "A", _LABELS, allow_override=False) is False
    assert _RUNNER._gate(_GOOD_PROPOSAL, "A", _LABELS, allow_override=True) is True


def test_gate_blocks_uncertain_evidence():
    p = dict(_GOOD_PROPOSAL, evidence_type="uncertain")
    assert _RUNNER._gate(p, "A", _LABELS, allow_override=True) is False


def test_gate_blocks_low_confidence():
    p = dict(_GOOD_PROPOSAL, confidence=0.85)
    assert _RUNNER._gate(p, "A", _LABELS, allow_override=True) is False


def test_gate_blocks_same_answer_or_empty_reason():
    assert _RUNNER._gate(dict(_GOOD_PROPOSAL, selected_answer="A"), "A", _LABELS,
                         allow_override=True) is False     # same as current
    assert _RUNNER._gate(dict(_GOOD_PROPOSAL, reason=""), "A", _LABELS,
                         allow_override=True) is False     # empty reason


def test_gate_blocks_should_override_false():
    assert _RUNNER._gate(dict(_GOOD_PROPOSAL, should_override=False), "A", _LABELS,
                         allow_override=True) is False


def test_runner_dry_run_default_and_lazy_client_import():
    src = (next(iter((_ROOT / "scripts" / "legacy").glob("**/run_short_knowledge_verifier_sample.py")))).read_text()
    assert "dry_run = not (args.execute and args.max_calls > 0)" in src
    # OpenRouter client imported lazily, inside the `if not dry_run` block only.
    assert src.count("from src.api.openrouter_client import OpenRouterClient") == 1
    assert "if not dry_run:" in src


def test_runner_no_qid_hardcoding_or_external_sheet():
    import re as _re
    src = (next(iter((_ROOT / "scripts" / "legacy").glob("**/run_short_knowledge_verifier_sample.py")))).read_text()
    for pat in (r'qid\s*==', r'==\s*["\']test_0'):
        assert not _re.search(pat, src)
    assert "first100_external" not in src        # never reads the answer sheet
    # risk CSV is used only for priority ordering, never to choose an answer.
    assert "risk_priority" in src and "selected_answer = risk" not in src


def test_analyzer_helpers():
    assert _ANALYZER._truthy("True") and _ANALYZER._truthy("1") and not _ANALYZER._truthy("False")
    assert _ANALYZER._conf_bucket(0.95) == ">=0.90"
    assert _ANALYZER._conf_bucket(0.8) == "0.70-0.90"
    assert _ANALYZER._conf_bucket(None) == "n/a"


def test_analyzer_handles_missing_risk_csv():
    # Build a tiny proposals CSV and run the analyzer with a nonexistent risk CSV.
    d = Path(tempfile.mkdtemp())
    csvp = d / "prop.csv"
    csvp.write_text(
        "qid,current_answer,verifier_selected,would_change_answer,verifier_confidence,evidence_type,reason\n"
        "q1,A,B,True,0.95,internal_knowledge,because B\n"
        "q2,C,C,False,0.99,option_elimination,keep\n")
    rc = _ANALYZER.main(["--proposals", str(csvp), "--risk-csv", str(d / "nope.csv")])
    assert rc == 0


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
