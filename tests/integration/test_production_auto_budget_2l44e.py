"""Phase 2L.44E — production full-system default layer budget = auto (ceil(input_count/8)).

The production profiles must default the V12B/V13 caps to 'auto' (not 'all'); explicit int / 'all'
overrides still work; logs render auto(<cap>/<N>). No API.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_PROFILES = json.loads((_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())


def _fi():
    spec = importlib.util.spec_from_file_location(
        "fi_auto", _ROOT / "scripts" / "tools" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


# --- production profiles default to auto -------------------------------------

def test_production_profiles_default_to_auto():
    for name in ("production_full_system", "production_full_system_noapi"):
        p = _PROFILES[name]
        assert p["v12b_max_qids"] == "auto", name
        assert p["v13_max_qids"] == "auto", name


def test_production_profiles_not_all():
    for name in ("production_full_system", "production_full_system_noapi"):
        p = _PROFILES[name]
        assert p["v12b_max_qids"] != "all" and p["v13_max_qids"] != "all", name


# --- auto formula: ceil(N/8), min 1 (no hardcoded sizes) ---------------------

def test_auto_formula_examples():
    mod = _fi()
    assert mod._resolve_maxq("auto", 3) == 1        # 3 -> 1
    assert mod._resolve_maxq("auto", 463) == 58     # 463 -> 58
    assert mod._resolve_maxq("auto", 2000) == 250   # 2000 -> 250
    assert mod._resolve_maxq("auto", 1) == 1        # min 1
    assert mod._resolve_maxq("auto", 8) == 1
    assert mod._resolve_maxq("auto", 9) == 2


def test_explicit_int_and_all_override():
    mod = _fi()
    assert mod._resolve_maxq(50, 463) == 50         # explicit int wins
    assert mod._resolve_maxq("50", 463) == 50
    assert mod._resolve_maxq("all", 463) is None    # 'all' = every input qid
    assert mod._resolve_maxq(None, 463) is None


# --- log rendering: auto(<cap>/<N>) ------------------------------------------

def test_fmt_cap_renders_auto_all_int():
    from src.system.fastmcq_system import _fmt_cap
    assert _fmt_cap(1, "auto", 3) == "auto(1/3)"
    assert _fmt_cap(250, "auto", 2000) == "auto(250/2000)"
    assert _fmt_cap(58, "auto", 463) == "auto(58/463)"
    assert _fmt_cap(None, "all", 463) == "all(463)"
    assert _fmt_cap(None, None, 463) == "all(463)"
    assert _fmt_cap(50, "50", 463) == "50"


# --- end-to-end: default full-system run uses auto (no API) ------------------

def _write_input(tmp_path, n):
    samples = [{"qid": f"q{i}", "question": "2 + 2 bằng?", "choices": ["3", "4", "5", "6"]}
               for i in range(n)]
    p = tmp_path / "in.json"; p.write_text(json.dumps(samples, ensure_ascii=False))
    return p


def test_run_full_system_default_uses_auto_no_api(tmp_path):
    inp = _write_input(tmp_path, 3)
    final = tmp_path / "final"
    env = dict(os.environ, FASTMCQ_FINAL_DIR=str(final))
    env.pop("OPENROUTER_API_KEY", None)
    r = subprocess.run(["bash", str(_ROOT / "scripts" / "run_full_system.sh"),
                        str(inp), "--no-api"],
                       cwd=str(_ROOT), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    # default (production_full_system_noapi) caps must resolve to auto(1/3) for N=3
    assert "v12b_max_qids=auto(1/3)" in r.stdout
    assert "v13_max_qids=auto(1/3)" in r.stdout
    assert (final / "pred.csv").exists()


def test_explicit_cap_overrides_auto_no_api(tmp_path):
    inp = _write_input(tmp_path, 20)
    final = tmp_path / "final"
    env = dict(os.environ, FASTMCQ_FINAL_DIR=str(final))
    env.pop("OPENROUTER_API_KEY", None)
    r = subprocess.run(["bash", str(_ROOT / "scripts" / "run_full_system.sh"),
                        str(inp), "--no-api", "--v12b-max-qids", "5", "--v13-max-qids", "5"],
                       cwd=str(_ROOT), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "v12b_max_qids=5" in r.stdout and "v13_max_qids=5" in r.stdout
    assert "auto(" not in r.stdout


def test_explicit_all_overrides_auto_no_api(tmp_path):
    inp = _write_input(tmp_path, 10)
    final = tmp_path / "final"
    env = dict(os.environ, FASTMCQ_FINAL_DIR=str(final))
    env.pop("OPENROUTER_API_KEY", None)
    r = subprocess.run(["bash", str(_ROOT / "scripts" / "run_full_system.sh"),
                        str(inp), "--no-api", "--v12b-max-qids", "all", "--v13-max-qids", "all"],
                       cwd=str(_ROOT), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "v12b_max_qids=all(10)" in r.stdout and "v13_max_qids=all(10)" in r.stdout


# --- no hardcoded 463 in production code/config ------------------------------

def test_no_hardcoded_463_in_production():
    files = [
        "scripts/tools/final_infer.py",
        "src/system/fastmcq_system.py",
        "configs/production/default.json",
        "scripts/run_full_system.sh",
        "scripts/docker_entrypoint_v11.sh",
    ]
    for f in files:
        assert "463" not in (_ROOT / f).read_text(), f
    # run_profiles.json: only the cosmetic profile NAME 'public_api463' may contain 463 —
    # never as a cap value.
    prof = (_ROOT / "configs" / "profiles" / "run_profiles.json").read_text()
    assert "463" not in prof.replace("public_api463", ""), "463 used as a value, not just a name"
