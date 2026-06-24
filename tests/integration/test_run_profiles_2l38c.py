"""Tests for Phase 2L.38C — run profiles + short wrapper scripts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_PUBLIC = str(_ROOT / "public-test_1780368312.json")
_V13 = str(_ROOT / "output" / "pred_v13_multilayer_candidate_api30_from_v12b.csv")
_PROFILES = json.loads((_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())
_WRAPPERS = ["run_public_replay.sh", "run_dynamic_noapi.sh", "run_public_api100.sh",
             "run_private_noapi.sh", "run_private_api200.sh", "run_public_api50.sh"]


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


# --- profile loading + application -------------------------------------------

def test_profiles_file_has_expected_profiles():
    assert set(_PROFILES) >= {"public_replay", "dynamic_noapi", "public_api100",
                              "private_noapi", "private_api200", "public_api463", "public_noapi"}


def test_apply_profile_sets_values():
    mod = _fi()
    import argparse
    ns = argparse.Namespace(profile="public_api100", mode="dynamic_full", execute_api=False,
                            enable_v12b=True, enable_v13=True, model=None, budget_usd=None,
                            v12b_max_qids=None, v12b_permutations=6, v12b_policy="conservative",
                            v13_max_qids=None, system_policy="conservative", max_overrides=None,
                            allow_public_replay=False)
    mod._apply_profile(ns, ["--profile", "public_api100"])
    assert ns.execute_api is True and ns.v12b_max_qids == 100 and ns.v13_max_qids == 100
    assert ns.model == "qwen/qwen3.5-9b-20260310" and ns.max_overrides == 50


def test_cli_flag_overrides_profile():
    mod = _fi()
    import argparse
    # argparse would have already set these from the explicit CLI flags before _apply_profile.
    ns = argparse.Namespace(profile="public_api100", mode="dynamic_full", execute_api=False,
                            enable_v12b=True, enable_v13=True, model=None, budget_usd=None,
                            v12b_max_qids=7, v12b_permutations=6, v12b_policy="conservative",
                            v13_max_qids=None, system_policy="conservative", max_overrides=None,
                            allow_public_replay=False)
    # user explicitly passed --no-api and --v12b-max-qids 7 -> profile must NOT overwrite them
    mod._apply_profile(ns, ["--profile", "public_api100", "--no-api", "--v12b-max-qids", "7"])
    assert ns.execute_api is False and ns.v12b_max_qids == 7
    assert ns.v13_max_qids == 100   # not passed on CLI -> filled from profile


def test_unknown_profile_fails_clearly():
    mod = _fi()
    import argparse
    ns = argparse.Namespace(profile="does_not_exist")
    try:
        mod._apply_profile(ns, ["--profile", "does_not_exist"])
        assert False
    except SystemExit as e:
        assert "unknown profile" in str(e)


# --- end-to-end via main (no API) --------------------------------------------

def test_public_replay_profile_reproduces_v13(tmp_path):
    out = tmp_path / "pred.csv"
    _fi().main(["--input", _PUBLIC, "--output", str(out), "--profile", "public_replay"])
    assert _md5(out) == _md5(_V13) == "cb02fef569b31e7fb544abab46c0e282"


def test_dynamic_noapi_profile_no_api(tmp_path, monkeypatch):
    import src.api.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API")))
    out = tmp_path / "pred.csv"
    rc = _fi().main(["--input", _private(tmp_path, ("z1", "z2")), "--output", str(out),
                     "--profile", "dynamic_noapi", "--work-dir", str(tmp_path / "w")])
    rows = [l.split(",")[0] for l in out.read_text().splitlines()[1:]]
    assert rc == 0 and rows == ["z1", "z2"]


def test_profile_cannot_bypass_model_policy(tmp_path):
    # public_api100 sets execute_api=True; override the model with a DISALLOWED one -> must raise
    out = tmp_path / "pred.csv"
    try:
        _fi().main(["--input", _private(tmp_path), "--output", str(out),
                    "--profile", "public_api100", "--model", "gpt-4o",
                    "--work-dir", str(tmp_path / "w")])
        assert False, "disallowed model should raise"
    except (ValueError, SystemExit) as e:
        assert "disallow" in str(e).lower() or "gpt" in str(e).lower()


def test_api_profiles_use_allowed_model():
    from src.api.model_policy import is_allowed_llm_model
    for name in ("public_api50", "public_api100", "public_api463", "private_api200"):
        assert is_allowed_llm_model(_PROFILES[name]["model"])


# --- public_api50 (2L.38D) ---------------------------------------------------

def test_public_api50_profile_values():
    p = _PROFILES["public_api50"]
    assert p["mode"] == "dynamic_full" and p["execute_api"] is True
    assert p["model"] == "qwen/qwen3.5-9b-20260310"
    assert p["v12b_max_qids"] == 50 and p["v13_max_qids"] == 50
    assert p["v12b_permutations"] == 6
    assert p["v12b_policy"] == "conservative" and p["system_policy"] == "conservative"


def test_public_api50_model_policy():
    from src.api.model_policy import is_allowed_llm_model
    assert is_allowed_llm_model(_PROFILES["public_api50"]["model"])


def test_public_api50_wrapper_exists_and_resumes():
    p = _ROOT / "scripts" / "run" / "run_public_api50.sh"
    assert p.exists()
    r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = p.read_text()
    assert "public_api50" in text and "--resume" in text


def test_public_api50_apply_profile_sets_caps():
    mod = _fi()
    import argparse
    ns = argparse.Namespace(profile="public_api50", mode="dynamic_full", execute_api=False,
                            enable_v12b=True, enable_v13=True, model=None, budget_usd=None,
                            v12b_max_qids=None, v12b_permutations=6, v12b_policy="conservative",
                            v13_max_qids=None, system_policy="conservative", max_overrides=None,
                            allow_public_replay=False)
    mod._apply_profile(ns, ["--profile", "public_api50"])
    assert ns.execute_api is True and ns.v12b_max_qids == 50 and ns.v13_max_qids == 50
    assert ns.model == "qwen/qwen3.5-9b-20260310" and ns.budget_usd == 2.50


def test_docs_mention_public_api50():
    for doc in ("README.md", "FINAL_RUN.md", "DOCKER_SUBMISSION.md"):
        assert "run_public_api50.sh" in (_ROOT / doc).read_text(), doc


def test_final_infer_works_without_profile(tmp_path):
    out = tmp_path / "pred.csv"
    rc = _fi().main(["--input", _private(tmp_path, ("q1",)), "--output", str(out), "--no-api"])
    assert rc == 0 and out.exists()


# --- wrapper scripts ---------------------------------------------------------

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
    assert "dynamic_noapi" in text["run_dynamic_noapi.sh"]
    assert "private_api200" in text["run_private_api200.sh"]


# --- hygiene -----------------------------------------------------------------

def test_no_qid_or_answer_hardcoding():
    assert not re.search(r"\btest_\d{4}\b", (_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())
    for w in _WRAPPERS:
        src = (_ROOT / "scripts" / "run" / w).read_text()
        assert not re.search(r"\btest_\d{4}\b", src), w
