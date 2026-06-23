"""Tests for Phase 2L.30B: independent full v11 runner + selector (no v10 base)."""

from __future__ import annotations

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


def _load():
    spec = importlib.util.spec_from_file_location(
        "rv11", _ROOT / "scripts" / "run_full_v11_independent_submission.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


_S = {"qid": "q1", "question": "Thủ đô Pháp?", "choices": ["Paris", "Lyon", "Nice"]}


def _fixture(d, n=2):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": f"q{i}", "question": "Q?", "choices": ["A", "B"]}
                               for i in range(1, n + 1)]))
    return str(inp)


def _args(d, inp, **over):
    a = {"--input": inp, "--work-dir": f"{d}/scratch/wd",
         "--output": f"{d}/outputs/v11.csv", "--mode": "cheap",
         "--model": "qwen/qwen3.5-9b-20260310"}
    a.update(over)
    out = []
    for k, v in a.items():
        out += [k] if v is None else [k, str(v)]
    return out


# --- structural: no v10 base -------------------------------------------------

def test_runner_has_no_base_pred_arg():
    src = (_ROOT / "scripts" / "run_full_v11_independent_submission.py").read_text()
    # no --base-pred CLI argument is defined (docstrings may mention it to explain its absence)
    assert "add_argument(\"--base-pred\"" not in src
    # generation must not add a v10_base candidate
    assert "v10_base" not in src


def test_runner_rejects_base_pred_flag():
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    try:
        mod.main(_args(d, inp, **{"--base-pred": "outputs/pred_v10_full_production_user_run.csv"})
                 + ["--dry-run"])
        assert False
    except SystemExit:
        pass            # argparse rejects the unknown flag


def test_dry_run_does_not_read_v10(monkeypatch):
    """Dry-run without --compare-pred must never load any prediction file."""
    import src.adaptive_proposal_common as apc
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    monkeypatch.setattr(mod, "load_pred",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("v11 dry-run read a pred file")))
    assert mod.main(_args(d, inp) + ["--dry-run"]) == 0


def test_compare_pred_is_report_only_not_needed_to_run(monkeypatch):
    """A nonexistent --compare-pred must not break the dry-run (proves it's not used for answers)."""
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    rc = mod.main(_args(d, inp, **{"--compare-pred": f"{d}/does_not_exist.csv"}) + ["--dry-run"])
    assert rc == 0


# --- guards ------------------------------------------------------------------

def test_dry_run_no_api_no_outputs(monkeypatch):
    import src.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in dry-run")))
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    rc = mod.main(_args(d, inp) + ["--dry-run"])
    assert rc == 0 and not Path(f"{d}/outputs/v11.csv").exists()


def test_execute_requires_ack():
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    try:
        mod.main(_args(d, inp) + ["--execute"])
        assert False
    except SystemExit as e:
        assert "i-understand" in str(e).lower()


def test_protected_output_rejected():
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    for name in ("outputs/pred.csv", "outputs/pred_v10_full_production_user_run.csv"):
        try:
            mod.main(_args(d, inp, **{"--output": name}) + ["--dry-run"])
            assert False
        except SystemExit as e:
            assert "protected" in str(e).lower()


def test_disallowed_model_rejected():
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    try:
        mod.main(_args(d, inp, **{"--model": "gpt-4o"}) + ["--dry-run"])
        assert False
    except ValueError:
        pass


def test_output_must_be_under_outputs():
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    try:
        mod.main(_args(d, inp, **{"--output": f"{d}/scratch/x.csv"}) + ["--dry-run"])
        assert False
    except SystemExit as e:
        assert "outputs/" in str(e)


def test_work_dir_must_be_under_scratch():
    mod = _load(); d = tempfile.mkdtemp(); inp = _fixture(d)
    try:
        mod.main(_args(d, inp, **{"--work-dir": f"{d}/outputs/wd"}) + ["--dry-run"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


# --- output validation -------------------------------------------------------

def test_validation_catches_bad_label_and_missing_qid():
    mod = _load()
    samples = {"q1": {"choices": ["A", "B"]}, "q2": {"choices": ["A", "B"]}}
    bad = [{"qid": "q1", "final_answer": "Z"}, {"qid": "q2", "final_answer": "A"}]
    try:
        mod._validate_decisions(bad, samples, full_dataset=True)
        assert False
    except SystemExit as e:
        assert "invalid label" in str(e).lower()
    missing = [{"qid": "q1", "final_answer": "A"}]      # q2 absent
    try:
        mod._validate_decisions(missing, samples, full_dataset=True)
        assert False
    except SystemExit as e:
        assert "qid set" in str(e).lower() or "row-count" in str(e).lower()


# --- selector: fallback is not v10 -------------------------------------------

def test_fallback_answer_not_from_v10():
    """With no tool/evidence candidates, the selector uses the direct fallback only."""
    pool = CandidatePool(qid="q1")
    a, dec = select_independent_answer(pool, _S, route="short_knowledge",
                                       fallback={"answer": "C", "parse_status": "ok"})
    assert a == "C" and dec["final_source"] == "direct_fallback" and dec["fallback_used"]


def test_selector_module_has_no_v10():
    src = (_ROOT / "src" / "independent_answer_selector.py").read_text()
    # the selector must not consume a v10 base answer/source (docstring may name v10 to explain)
    assert "v10_base" not in src and "_BASE_SOURCE" not in src and "base_answer" not in src


def test_selector_unique_deterministic():
    pool = CandidatePool(qid="q1")
    pool.add(AnswerCandidate("q1", "B", "formula_bank", risk_level="low", proof_text="200*1.1=220"))
    a, dec = select_independent_answer(pool, _S, route="calculation")
    assert a == "B" and dec["final_source"] == "formula_bank" and dec["risk"] == "low"


def test_no_qid_hardcoding():
    for name in ("run_full_v11_independent_submission.py",):
        src = (_ROOT / "scripts" / name).read_text()
        assert not re.search(r"\btest_\d{4}\b", src)
    assert not re.search(r"\btest_\d{4}\b", (_ROOT / "src" / "independent_answer_selector.py").read_text())
