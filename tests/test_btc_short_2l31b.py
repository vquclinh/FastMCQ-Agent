"""Tests for Phase 2L.31B: BTC short command polish + default timing output."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_INPUT = str(_ROOT / "public-test_1780368312.json")
# Current production best (promoted in 2L.36A): V12B option-permutation debiaser (78.83).
# Current production best (promoted in 2L.38A): V13 multi-layer dynamic system (79.7).
_BEST = "outputs/pred_v13_multilayer_candidate_api30_from_v12b.csv"


def _final_infer():
    spec = importlib.util.spec_from_file_location("fi_btc", _ROOT / "scripts" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _run_short(out):
    """The exact BTC short command: only --input and --output."""
    mod = _final_infer()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--input", _INPUT, "--output", out])
    return rc, buf.getvalue()


def test_short_command_works_no_mode_no_flag():
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    rc, _ = _run_short(out)
    assert rc == 0 and Path(out).exists()


def _run_mode(out, mode):
    mod = _final_infer()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--input", _INPUT, "--output", out, "--mode", mode])
    return rc, buf.getvalue()


def test_default_mode_is_dynamic_full():
    # The short command (no --mode) now resolves to the real dynamic system, not a frozen replay.
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    rc, txt = _run_short(out)
    assert "resolved mode: dynamic_full" in txt


def test_public_replay_source_is_frozen_best():
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    rc, txt = _run_mode(out, "public_replay")
    assert f"source: {_BEST}" in txt


def test_public_replay_md5_matches_winning_csv():
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    _run_mode(out, "public_replay")
    assert _md5(out) == _md5(_ROOT / _BEST)


def test_elapsed_and_status_printed_by_default():
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    rc, txt = _run_short(out)
    assert "elapsed_seconds:" in txt and "status: PASS" in txt
    assert "FINAL INFER COMPLETE" in txt


def test_pred_csv_basename_allowed():
    mod = _final_infer()
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    assert mod.main(["--input", _INPUT, "--output", out]) == 0


def test_frozen_best_and_v10_still_protected():
    mod = _final_infer()
    for name in ("outputs/pred_v11_independent_rerun1.csv",
                 "outputs/pred_v10_full_production_user_run.csv",
                 "outputs/pred_v8_clean_generalized_from_v7.csv"):
        try:
            mod.main(["--input", _INPUT, "--output", name])
            assert False, name
        except SystemExit as e:
            assert "protected" in str(e).lower()


def test_v10_is_not_default():
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    rc, txt = _run_short(out)
    assert "v10" not in txt.lower().split("source:")[1].split("\n")[0]  # source line is not v10
    assert _md5(out) != _md5(_ROOT / "outputs/pred_v10_full_production_user_run.csv")


def test_short_command_makes_no_api_call(monkeypatch):
    import src.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in frozen_csv")))
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    rc, _ = _run_short(out)
    assert rc == 0


def test_failure_prints_elapsed(monkeypatch):
    mod = _final_infer()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            mod.main(["--input", _INPUT, "--output", "outputs/pred_v11_independent_rerun1.csv"])
    except SystemExit:
        pass
    out = buf.getvalue()
    assert "elapsed_seconds:" in out and "status: FAIL" in out


def test_allow_pred_csv_flag_harmless_backward_compat():
    mod = _final_infer()
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"
    # flag still accepted, behaves identically (no longer required)
    assert mod.main(["--input", _INPUT, "--output", out, "--allow-pred-csv"]) == 0


def test_docs_contain_dynamic_and_replay_commands():
    fr = (_ROOT / "FINAL_RUN.md").read_text()
    # the default dynamic command and the public_replay reproduction command are both documented
    assert "scripts/final_infer.py --input" in fr
    assert "--mode public_replay" in fr
    assert "dynamic_full" in fr


def test_no_qid_hardcoding():
    src = (_ROOT / "scripts" / "final_infer.py").read_text()
    assert not re.search(r"\btest_\d{4}\b", src)
