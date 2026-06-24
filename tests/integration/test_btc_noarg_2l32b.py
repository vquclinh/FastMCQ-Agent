"""Tests for Phase 2L.32B: BTC no-argument default I/O + timing for final_infer.py."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_INPUT = str(_ROOT / "public-test_1780368312.json")
# Current production best (promoted in 2L.36A): V12B option-permutation debiaser (78.83).
_BEST = str(_ROOT / "output" / "pred_v12b_permutation_candidate_api30.csv")


def _fi():
    spec = importlib.util.spec_from_file_location("fi_noarg", _ROOT / "scripts" / "tools" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _qid_csv(path):
    data = json.loads(Path(_INPUT).read_text())
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["qid"])
        for r in data:
            w.writerow([r["qid"]])


# --- no-arg run --------------------------------------------------------------

def test_runs_with_no_input_no_output(monkeypatch):
    # No-arg default is now dynamic_full: it must run and emit valid predictions for exactly
    # the detected input's qids (NOT a public-frozen replay).
    mod = _fi()
    d = tempfile.mkdtemp()
    Path(d, "public-test_1780368312.json").write_text(Path(_INPUT).read_text())
    monkeypatch.chdir(d)
    rc = mod.main([])                       # no --input, no --output
    assert rc == 0
    out = Path(d) / "pred.csv"
    assert out.exists()
    n_input = len(json.loads(Path(_INPUT).read_text()))
    assert len(out.read_text().splitlines()) - 1 == n_input   # one row per input qid


def test_no_arg_csv_input_autodetected(monkeypatch):
    mod = _fi()
    d = tempfile.mkdtemp()
    _qid_csv(Path(d) / "doc_public_test.csv")
    monkeypatch.chdir(d)
    rc = mod.main([])
    out = Path(d) / "pred.csv"
    n_input = len(json.loads(Path(_INPUT).read_text()))
    assert rc == 0 and out.exists() and len(out.read_text().splitlines()) - 1 == n_input


def test_no_arg_default_is_dynamic_full(monkeypatch):
    mod = _fi()
    d = tempfile.mkdtemp()
    Path(d, "public-test_1780368312.json").write_text(Path(_INPUT).read_text())
    monkeypatch.chdir(d)
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main([])
    assert "resolved mode: dynamic_full" in buf.getvalue()


def test_no_arg_makes_no_api_call(monkeypatch):
    import src.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in frozen_csv")))
    mod = _fi()
    d = tempfile.mkdtemp()
    Path(d, "public-test_1780368312.json").write_text(Path(_INPUT).read_text())
    monkeypatch.chdir(d)
    assert mod.main([]) == 0


def test_elapsed_and_status_printed_no_arg(monkeypatch):
    mod = _fi()
    d = tempfile.mkdtemp()
    Path(d, "public-test_1780368312.json").write_text(Path(_INPUT).read_text())
    monkeypatch.chdir(d)
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main([])
    txt = buf.getvalue()
    assert "FINAL INFER COMPLETE" in txt and "elapsed_seconds:" in txt and "status: PASS" in txt


def test_no_detectable_input_prints_timing_and_clear_error(monkeypatch):
    mod = _fi()
    d = tempfile.mkdtemp()                  # empty dir, no input, no /data lone file
    monkeypatch.chdir(d)
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", ())   # neutralize repo-relative fallbacks
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            mod.main([])
        assert False
    except SystemExit as e:
        assert "no input" in str(e).lower()
    out = buf.getvalue()
    assert "elapsed_seconds:" in out and "status: FAIL" in out


# --- input/output resolution units ------------------------------------------

def test_input_autodetect_prefers_private_test(monkeypatch):
    # BTC priority (2L.42A): private_test.csv is auto-detected before public/doc variants.
    mod = _fi()
    d = tempfile.mkdtemp()
    _qid_csv(Path(d) / "doc_public_test.csv")
    _qid_csv(Path(d) / "public_test.csv")
    _qid_csv(Path(d) / "private_test.csv")
    monkeypatch.chdir(d)
    assert Path(mod._resolve_input(None)).name == "private_test.csv"


def test_input_explicit_and_env(monkeypatch):
    mod = _fi()
    assert mod._resolve_input("x.json") == "x.json"             # explicit wins
    monkeypatch.setenv("FASTMCQ_INPUT", "envfile.json")
    assert mod._resolve_input(None) == "envfile.json"


def test_output_defaults(monkeypatch):
    mod = _fi()
    monkeypatch.delenv("FASTMCQ_OUTPUT", raising=False)
    assert mod._resolve_output("o.csv") == "o.csv"              # explicit
    monkeypatch.setenv("FASTMCQ_OUTPUT", "envout.csv")
    assert mod._resolve_output(None) == "envout.csv"           # env
    monkeypatch.delenv("FASTMCQ_OUTPUT", raising=False)
    monkeypatch.setattr(mod, "_can_create", lambda p: True)    # pretend /output is creatable
    assert mod._resolve_output(None) == "/output/pred.csv"
    monkeypatch.setattr(mod, "_can_create", lambda p: False)   # not creatable -> local
    d = tempfile.mkdtemp(); monkeypatch.chdir(d)
    assert mod._resolve_output(None) == "pred.csv"


# --- CSV / global-label validation ------------------------------------------

def test_global_label_validation_when_no_choices():
    mod = _fi()
    d = tempfile.mkdtemp()
    ds = Path(d) / "ds.json"
    ds.write_text(json.dumps([{"qid": "q1"}, {"qid": "q2"}]))   # no choices
    good = Path(d) / "good.csv"
    good.write_text("qid,answer\nq1,A\nq2,K\n")                 # A..K accepted globally
    assert mod._validate(str(good), str(ds)) == 2
    bad = Path(d) / "bad.csv"
    bad.write_text("qid,answer\nq1,A\nq2,Z\n")                  # Z is out of A..K
    try:
        mod._validate(str(bad), str(ds))
        assert False
    except SystemExit as e:
        assert "invalid label" in str(e).lower()


# --- protection still holds --------------------------------------------------

def test_frozen_best_and_v10_still_protected():
    mod = _fi()
    for name in ("output/pred_v11_independent_rerun1.csv",
                 "output/pred_v10_full_production_user_run.csv"):
        try:
            mod.main(["--input", _INPUT, "--output", name])
            assert False, name
        except SystemExit as e:
            assert "protected" in str(e).lower()


# --- docs + hygiene ----------------------------------------------------------

def test_docs_contain_btc_noarg_docker_command():
    text = (_ROOT / "DOCKER_SUBMISSION.md").read_text() + (_ROOT / "FINAL_RUN.md").read_text()
    assert 'docker run --rm' in text and '-v "$PWD/data:/data"' in text
    assert 'fastmcq-final' in text


def test_no_qid_hardcoding():
    src = (_ROOT / "scripts" / "tools" / "final_infer.py").read_text()
    assert not re.search(r"\btest_\d{4}\b", src)
