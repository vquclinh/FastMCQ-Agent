"""Tests for Phase 2L.39D — layer-only API profile (base no-API; V12B/V13 may use API)."""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

import src.selective_api_client as sac
from src.fastmcq_system import run_fastmcq_system, FastMCQSystemConfig

_PROFILES = json.loads((_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())


class _FakeClient:
    """Counts layer API calls; never hits the network."""
    calls = 0

    def __init__(self, *a, **k):
        pass

    def chat(self, messages, **k):
        _FakeClient.calls += 1
        return ('{"selected_label": "A", "selected_option_text": "opt 0", '
                '"label_matches_option": true, "confidence": 0.9, '
                '"answer_content": "opt 0", "final_survivor_label": null}', {})

    @staticmethod
    def parse_json(content):
        try:
            return json.loads(content)
        except Exception:
            return None


def _samples(n=2):
    return [{"qid": f"z{i}", "question": "2 + 2 bằng bao nhiêu?",
             "choices": [f"opt {j}" for j in range(4)]} for i in range(n)]


# --- profile + wrapper presence ----------------------------------------------

def test_layer_profile_exists_with_expected_values():
    p = _PROFILES["public_layer_api50"]
    assert p["execute_api"] is True and p["base_execute_api"] is False
    assert p["model"] == "qwen/qwen3.5-9b-20260310"
    assert p["v12b_max_qids"] == 50 and p["v13_max_qids"] == 50 and p["enable_v13"] is True


def test_wrapper_exists_and_syntax_valid():
    p = _ROOT / "scripts" / "run" / "run_public_layer_api50.sh"
    assert p.exists()
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "public_layer_api50" in p.read_text()


# --- base_execute_api semantics ----------------------------------------------

def test_base_execute_api_false_keeps_base_deterministic(monkeypatch, tmp_path):
    # execute_api=True (layers) but base_execute_api=False -> base must NOT call the model.
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    _FakeClient.calls = 0
    out = tmp_path / "pred.csv"
    buf = io.StringIO()
    with redirect_stdout(buf):
        rep = run_fastmcq_system(_samples(2), str(out), FastMCQSystemConfig(
            execute_api=True, base_execute_api=False, enable_v12b=True, enable_v13=True,
            model="qwen/qwen3.5-9b-20260310",
            v12b_max_qids=50, v13_max_qids=50, work_dir=str(tmp_path / "w")))
    log = buf.getvalue()
    base_lines = [ln for ln in log.splitlines() if ln.startswith("[BASE]")]
    assert base_lines and all("source=api" not in ln for ln in base_lines)   # base stayed offline
    assert "base_execute_api=False layer_execute_api=True" in log
    assert rep.output_count == 2


def test_layer_api_runs_when_execute_api_true(monkeypatch, tmp_path):
    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeClient)
    _FakeClient.calls = 0
    out = tmp_path / "pred.csv"
    run_fastmcq_system(_samples(2), str(out), FastMCQSystemConfig(
        execute_api=True, base_execute_api=False, enable_v12b=True, enable_v13=True,
        model="qwen/qwen3.5-9b-20260310",
        v12b_max_qids=50, v13_max_qids=50, work_dir=str(tmp_path / "w")))
    assert _FakeClient.calls > 0   # V12B/V13 layers used the (fake) API


def test_base_api_inherits_execute_api_when_unset(monkeypatch, tmp_path):
    # base_execute_api=None -> inherits execute_api. With execute_api=False everything is offline.
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API expected")))
    out = tmp_path / "pred.csv"
    rep = run_fastmcq_system(_samples(2), str(out), FastMCQSystemConfig(
        execute_api=False, base_execute_api=None, work_dir=str(tmp_path / "w")))
    assert rep.output_count == 2


# --- arbitrary qids, no public artifact --------------------------------------

def test_arbitrary_private_qids_no_api(tmp_path):
    s = [{"qid": "weird_qid_!42", "question": "x?", "choices": ["a", "b", "c"]}]
    out = tmp_path / "pred.csv"
    rep = run_fastmcq_system(s, str(out), FastMCQSystemConfig(
        execute_api=False, base_execute_api=False, enable_v12b=True, enable_v13=True,
        work_dir=str(tmp_path / "w")))
    rows = [l.split(",")[0] for l in out.read_text().splitlines()[1:]]
    assert rows == ["weird_qid_!42"] and rep.output_count == 1


def test_no_public_artifact_required():
    # the system modules must not depend on the frozen public CSV path
    for name in ("fastmcq_system", "dynamic_base_predictor", "v12b_dynamic_layer",
                 "v13_dynamic_layer"):
        src = (_ROOT / "src" / f"{name}.py").read_text()
        assert "pred_v13_multilayer_candidate_api30_from_v12b" not in src, name


# --- hygiene -----------------------------------------------------------------

def test_no_qid_or_answer_hardcoding():
    assert not re.search(r"\btest_\d{4}\b", (_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())
    assert not re.search(r"\btest_\d{4}\b", (_ROOT / "scripts" / "run" / "run_public_layer_api50.sh").read_text())
