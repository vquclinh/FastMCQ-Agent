"""Tests for local run profiles and wrapper scripts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_PUBLIC = str(_ROOT / "public-test_1780368312.json")
_V13 = str(_ROOT / "output" / "pred_v13_multilayer_candidate_api30_from_v12b.csv")
_PROFILES = json.loads((_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())
_WRAPPERS = ["run_public_replay.sh", "run_local_auto.sh", "run_public_local100.sh",
             "run_private_local.sh", "run_private_local200.sh", "run_public_local50.sh"]


def _fi():
    spec = importlib.util.spec_from_file_location("fi_prof", _ROOT / "scripts" / "tools" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _private(tmp_path, qids=("a1",)):
    s = [{"qid": q, "question": "2 + 2 bằng bao nhiêu?", "choices": ["3", "4", "5", "6"]} for q in qids]
    p = tmp_path / "p.json"; p.write_text(json.dumps(s, ensure_ascii=False))
    return str(p)


def _ns(profile):
    return argparse.Namespace(
        profile=profile, mode="dynamic_full", enable_v12b=True, enable_v13=True,
        model_path=None, device="auto", max_new_tokens=64, layer_max_new_tokens=768,
        v12b_max_qids=None, v12b_permutations=6, v12b_policy="conservative",
        v13_max_qids=None, system_policy="conservative", max_overrides=None,
        allow_public_replay=False,
    )


def test_profiles_file_has_expected_profiles():
    assert set(_PROFILES) >= {"public_replay", "local_selective_auto",
                              "public_local50", "public_local100", "private_local200"}


def test_apply_profile_sets_values():
    mod = _fi()
    ns = _ns("public_local100")
    mod._apply_profile(ns, ["--profile", "public_local100"])
    assert ns.v12b_max_qids == 100 and ns.v13_max_qids == 100
    assert ns.max_overrides == 50


def test_cli_flag_overrides_profile():
    mod = _fi()
    ns = _ns("public_local100")
    ns.v12b_max_qids = 7
    mod._apply_profile(ns, ["--profile", "public_local100", "--v12b-max-qids", "7"])
    assert ns.v12b_max_qids == 7
    assert ns.v13_max_qids == 100


def test_unknown_profile_fails_clearly():
    mod = _fi()
    ns = argparse.Namespace(profile="does_not_exist")
    try:
        mod._apply_profile(ns, ["--profile", "does_not_exist"])
        assert False
    except SystemExit as e:
        assert "unknown profile" in str(e)


def test_public_replay_profile_reproduces_v13(tmp_path):
    out = tmp_path / "pred.csv"
    _fi().main(["--input", _PUBLIC, "--output", str(out), "--profile", "public_replay"])
    assert _md5(out) == _md5(_V13) == "cb02fef569b31e7fb544abab46c0e282"


def test_local_profile_dry_run(tmp_path):
    out = tmp_path / "pred.csv"
    rc = _fi().main(["--input", _private(tmp_path, ("z1", "z2")), "--output", str(out),
                     "--profile", "local_selective_auto", "--dry-run"])
    assert rc == 0


def test_public_local50_profile_values():
    p = _PROFILES["public_local50"]
    assert p["mode"] == "dynamic_full"
    assert p["v12b_max_qids"] == 50 and p["v13_max_qids"] == 50
    assert p["v12b_permutations"] == 6
    assert p["v12b_policy"] == "conservative" and p["system_policy"] == "conservative"


def test_public_local50_wrapper_exists_and_resumes():
    p = _ROOT / "scripts" / "run" / "run_public_local50.sh"
    assert p.exists()
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = p.read_text()
    assert "public_local50" in text and "--resume" in text


def test_final_infer_works_without_profile_dry_run(tmp_path):
    out = tmp_path / "pred.csv"
    rc = _fi().main(["--input", _private(tmp_path, ("q1",)), "--output", str(out), "--dry-run"])
    assert rc == 0


def test_wrappers_exist_and_syntax_valid():
    for w in _WRAPPERS:
        p = _ROOT / "scripts" / "run" / w
        assert p.exists(), w
        r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"{w}: {r.stderr}"
        assert "--profile" in p.read_text()


def test_wrappers_reference_profiles():
    text = {w: (_ROOT / "scripts" / "run" / w).read_text() for w in _WRAPPERS}
    assert "public_replay" in text["run_public_replay.sh"]
    assert "local_selective_auto" in text["run_local_auto.sh"]
    assert "private_local200" in text["run_private_local200.sh"]


def test_no_qid_or_answer_hardcoding():
    assert not re.search(r"\btest_\d{4}\b", (_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())
    for w in _WRAPPERS:
        src = (_ROOT / "scripts" / "run" / w).read_text()
        assert not re.search(r"\btest_\d{4}\b", src), w
