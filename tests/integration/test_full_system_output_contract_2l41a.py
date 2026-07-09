"""Tests for the local full-system wrapper shape and output quality helper."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.tools.output_quality_report import compute_quality_report  # noqa: E402

_WRAPPER = _ROOT / "scripts" / "run_full_system.sh"
_PROFILES = json.loads((_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())


def test_run_full_system_exists_and_valid():
    assert _WRAPPER.exists()
    r = subprocess.run(["bash", "-n", str(_WRAPPER)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = _WRAPPER.read_text()
    assert "local_selective_auto" in text
    assert "FASTMCQ_FINAL_DIR" in text
    assert "scripts/final_infer.py" in text


def test_local_selective_profile_is_full_system_not_public_replay():
    p = _PROFILES["local_selective_auto"]
    assert p["mode"] == "dynamic_full" and p["enable_v12b"] and p["enable_v13"]
    assert "public_replay" not in json.dumps(p)
    assert "public_replay" not in _WRAPPER.read_text()


def test_local_profiles_no_public_qids_or_seed():
    blob = json.dumps(_PROFILES["local_selective_auto"]) + json.dumps(_PROFILES["private_local200"])
    assert "public-test" not in blob and "pred_v13" not in blob and "1780368312" not in blob


def test_quality_report_detects_duplicate_answers(tmp_path):
    pred = tmp_path / "pred.csv"
    pred.write_text("qid,answer\nq1,A\nq2,A\nq3,A\n")
    report = compute_quality_report(pred)
    assert report["total"] == 3
    assert report["top_ratio"] == 1.0
    assert report["degenerate"] is True


def test_no_qid_hardcoding_in_wrapper_or_profiles():
    assert not re.search(r"\btest_\d{4}\b", _WRAPPER.read_text())
    assert not re.search(r"\btest_\d{4}\b", json.dumps(_PROFILES))
