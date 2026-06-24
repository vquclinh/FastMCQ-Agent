"""Phase 2L.44D — BTC input/output priority + default fallback contract (no API).

Exact input priority:
  1. --input (CLI)  2. $INPUT_FILE  3. /data/private_test.csv  4. /data/public_test.csv
  5. /data/private_test.json  6. /data/public_test.json
Exact output priority:
  1. --output (CLI)  2. $OUTPUT_FILE  3. /output/pred.csv (Docker)  4. output/pred.csv (local)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _fi():
    spec = importlib.util.spec_from_file_location(
        "fi_io_prio", _ROOT / "scripts" / "tools" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _data_candidates(tmp_path):
    """tmp files standing in for the /data defaults, in the EXACT documented priority order."""
    names = ["private_test.csv", "public_test.csv", "private_test.json", "public_test.json"]
    return tuple(str(tmp_path / n) for n in names)


def _clear_env(monkeypatch):
    for k in ("INPUT_FILE", "FASTMCQ_INPUT", "OUTPUT_FILE", "FASTMCQ_OUTPUT"):
        monkeypatch.delenv(k, raising=False)


# --- INPUT priority ----------------------------------------------------------

def test_cli_input_priority_over_private_default(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    cands = _data_candidates(tmp_path)
    for c in cands:
        Path(c).write_text("qid\nq1\n")            # every /data default present
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", cands)
    monkeypatch.setenv("INPUT_FILE", "/env/should_lose.csv")
    # CLI input must win over both INPUT_FILE and /data/private_test.csv
    assert mod._resolve_input("/cli/explicit.json") == "/cli/explicit.json"


def test_input_file_env_priority_over_private_default(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    cands = _data_candidates(tmp_path)
    for c in cands:
        Path(c).write_text("qid\nq1\n")
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", cands)
    monkeypatch.setenv("INPUT_FILE", "/env/in.csv")
    assert mod._resolve_input(None) == "/env/in.csv"   # INPUT_FILE beats /data defaults


def test_empty_input_file_env_is_ignored(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    cands = _data_candidates(tmp_path)
    Path(cands[0]).write_text("qid\nq1\n")             # private_test.csv present
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", cands)
    monkeypatch.setenv("INPUT_FILE", "")               # set but blank -> ignored
    assert Path(mod._resolve_input(None)).name == "private_test.csv"


def test_private_default_used_only_without_explicit(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    cands = _data_candidates(tmp_path)
    for c in cands:
        Path(c).write_text("qid\nq1\n")
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", cands)
    # No CLI, no INPUT_FILE -> /data/private_test.csv (highest /data default)
    assert Path(mod._resolve_input(None)).name == "private_test.csv"


def test_private_default_priority_over_public(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    cands = _data_candidates(tmp_path)   # (private.csv, public.csv, private.json, public.json)
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", cands)
    # Only public present -> public_test.csv chosen (csv before json)
    Path(cands[1]).write_text("qid\nq1\n")   # public_test.csv
    Path(cands[3]).write_text("qid\nq1\n")   # public_test.json
    assert Path(mod._resolve_input(None)).name == "public_test.csv"
    # Now add private_test.csv -> it takes priority over public
    Path(cands[0]).write_text("qid\nq1\n")
    assert Path(mod._resolve_input(None)).name == "private_test.csv"


def test_csv_before_json_within_private_and_public(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    cands = _data_candidates(tmp_path)
    # Only the .json variants present -> private_test.json before public_test.json
    Path(cands[2]).write_text("[]")   # private_test.json
    Path(cands[3]).write_text("[]")   # public_test.json
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", cands)
    assert Path(mod._resolve_input(None)).name == "private_test.json"


def test_missing_input_fails_early_with_clear_message(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "_INPUT_CANDIDATES", ())   # nothing detectable
    try:
        mod._resolve_input(None)
        assert False, "expected SystemExit"
    except SystemExit as e:
        msg = str(e)
        assert "no input file found" in msg.lower()
        # lists the expected defaults...
        assert "/data/private_test.csv" in msg and "/data/public_test.csv" in msg
        assert "/data/private_test.json" in msg and "/data/public_test.json" in msg
        # ...and mentions the overrides
        assert "--input" in msg and "INPUT_FILE" in msg


# --- OUTPUT priority ---------------------------------------------------------

def test_cli_output_priority_over_output_file(monkeypatch):
    mod = _fi(); _clear_env(monkeypatch)
    monkeypatch.setenv("OUTPUT_FILE", "/env/out.csv")
    assert mod._resolve_output("cli.csv") == "cli.csv"


def test_output_file_priority_over_docker_default(monkeypatch):
    mod = _fi(); _clear_env(monkeypatch)
    monkeypatch.setenv("OUTPUT_FILE", "/env/out.csv")
    monkeypatch.setattr(mod, "_can_create", lambda p: True)   # /output creatable
    assert mod._resolve_output(None) == "/env/out.csv"        # OUTPUT_FILE beats /output/pred.csv


def test_docker_default_then_local_default(monkeypatch, tmp_path):
    mod = _fi(); _clear_env(monkeypatch)
    monkeypatch.setattr(mod, "_can_create", lambda p: True)
    assert mod._resolve_output(None) == "/output/pred.csv"    # Docker default
    monkeypatch.setattr(mod, "_can_create", lambda p: False)
    monkeypatch.chdir(tmp_path)
    assert mod._resolve_output(None) == "output/pred.csv"     # local default


def test_legacy_env_aliases_still_work(monkeypatch):
    mod = _fi(); _clear_env(monkeypatch)
    monkeypatch.setenv("FASTMCQ_INPUT", "/legacy/in.json")
    monkeypatch.setenv("FASTMCQ_OUTPUT", "/legacy/out.csv")
    assert mod._resolve_input(None) == "/legacy/in.json"
    assert mod._resolve_output(None) == "/legacy/out.csv"


# --- end-to-end: INPUT_FILE + OUTPUT_FILE honored, no API --------------------

def test_input_file_and_output_file_end_to_end_no_api(monkeypatch, tmp_path):
    import src.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API")))
    mod = _fi(); _clear_env(monkeypatch)
    inp = tmp_path / "custom_test.csv"
    inp.write_text("qid,question,A,B,C,D\nc1,2 + 2 bằng?,3,4,5,6\n")
    out = tmp_path / "custom_pred.csv"
    monkeypatch.setenv("INPUT_FILE", str(inp))
    monkeypatch.setenv("OUTPUT_FILE", str(out))
    rc = mod.main(["--no-api"])                  # no --input / --output: resolved from env
    assert rc == 0 and out.exists()
    rows = [l.split(",")[0] for l in out.read_text().splitlines()[1:]]
    assert rows == ["c1"]


# --- max-qid 'auto' default (ceil(n/8), min 1; no hardcoded 463) -------------

def test_resolve_maxq_auto_all_int():
    mod = _fi()
    assert mod._resolve_maxq("all", 100) is None
    assert mod._resolve_maxq(None, 100) is None
    assert mod._resolve_maxq("", 100) is None
    assert mod._resolve_maxq("auto", 16) == 2     # ceil(16/8)
    assert mod._resolve_maxq("auto", 17) == 3     # ceil(17/8)
    assert mod._resolve_maxq("auto", 8) == 1
    assert mod._resolve_maxq("auto", 1) == 1      # minimum 1
    assert mod._resolve_maxq("auto", 0) == 1      # guard: min 1
    assert mod._resolve_maxq("auto", None) == 1   # no count known -> min 1
    assert mod._resolve_maxq("7", 100) == 7
    assert mod._resolve_maxq(50, 100) == 50


def test_maxq_default_is_auto_not_hardcoded():
    src = (_ROOT / "scripts" / "tools" / "final_infer.py").read_text()
    assert 'default="auto"' in src           # v12b/v13 max-qids default to auto
    assert "463" not in src                  # no hardcoded size anywhere


# --- API-key profile selection + no baked secret ----------------------------

def test_entrypoint_selects_profile_by_api_key_no_secret():
    src = (_ROOT / "scripts" / "docker_entrypoint_v11.sh").read_text()
    assert "OPENROUTER_API_KEY" in src
    assert "production_full_system" in src and "production_full_system_noapi" in src
    assert "/output/pred.csv" in src and "dynamic_full" in src
    # exact /data priority documented in the entrypoint
    assert "/data/private_test.csv" in src and "/data/public_test.csv" in src
    # no secret baked into the image
    assert "sk-" not in src and "OPENROUTER_API_KEY=" not in src


def test_run_full_system_optional_input_and_key_fallback():
    src = (_ROOT / "scripts" / "run_full_system.sh").read_text()
    assert "OPENROUTER_API_KEY" in src
    assert "production_full_system_noapi" in src
    assert "${1:?" not in src                # positional input no longer mandatory
    assert "sk-" not in src and "OPENROUTER_API_KEY=" not in src


def test_no_secret_baked_in_dockerfile():
    import re
    df = (_ROOT / "Dockerfile").read_text()
    # A comment may mention the key, but it must never be baked in via ENV/ARG with a value.
    assert not re.search(r"(?im)^\s*(ENV|ARG)\s+OPENROUTER_API_KEY\s*=", df)
    assert "sk-" not in df


def test_run_full_system_resolves_input_from_env_no_api(tmp_path):
    import os
    import subprocess
    inp = tmp_path / "private_test.csv"
    inp.write_text("qid,question,A,B,C,D\nz1,2 + 2 bằng?,3,4,5,6\n")
    final = tmp_path / "final"
    env = dict(os.environ, FASTMCQ_FINAL_DIR=str(final), INPUT_FILE=str(inp))
    env.pop("OPENROUTER_API_KEY", None)      # ensure offline fallback
    # No positional input: run_full_system must let final_infer resolve it from $INPUT_FILE.
    r = subprocess.run(["bash", str(_ROOT / "scripts" / "run_full_system.sh"), "--no-api"],
                       cwd=str(_ROOT), env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (final / "pred.csv").exists()
    rows = [l.split(",")[0] for l in (final / "pred.csv").read_text().splitlines()[1:]]
    assert rows == ["z1"]
