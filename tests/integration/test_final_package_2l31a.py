"""Tests for Phase 2L.31A: freeze v11 independent + final_infer + production audit."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_INPUT = str(_ROOT / "public-test_1780368312.json")
# Current production best (promoted in 2L.36A): V12B option-permutation debiaser (78.83).
# Current production best (promoted in 2L.38A): V13 multi-layer dynamic system (79.7).
_BEST = "output/pred_v13_multilayer_candidate_api30_from_v12b.csv"
_V10 = "output/pred_v10_full_production_user_run.csv"


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "") + "_t",
                                                  (_ROOT / "scripts" / "legacy" / name if (_ROOT / "scripts" / "legacy" / name).exists() else _ROOT / "scripts" / name))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


# --- manifest ----------------------------------------------------------------

def test_manifest_freezes_v13_as_default():
    m = json.loads((_ROOT / "experiments" / "best_candidate_manifest.json").read_text())
    assert m["production_default"] == "v13_multilayer_dynamic_system"
    assert m["recommended_final_csv"] == _BEST
    assert m["current_best"]["public_score"] == 79.7
    assert m["current_best"]["md5"] == _md5(_ROOT / _BEST)        # manifest md5 matches the file
    assert m["previous_best_v12b"]["architecture"] == "v12b_option_permutation_debiaser"
    # current best beats the previous V12B best (79.7 > 78.83)
    assert m["current_best"]["public_score"] > m["previous_best_v12b"]["public_score"]


# --- final_infer frozen_csv --------------------------------------------------

def test_frozen_csv_md5_identical_and_valid():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp(); out = f"{d}/scratch/pred_final_smoke.csv"
    rc = mod.main(["--input", _INPUT, "--output", out, "--mode", "frozen_csv"])
    assert rc == 0
    assert _md5(out) == _md5(_ROOT / _BEST)              # exact reproducible copy


def test_frozen_csv_explicit_source():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp(); out = f"{d}/out.csv"
    rc = mod.main(["--input", _INPUT, "--output", out, "--mode", "frozen_csv",
                   "--source-csv", _BEST])
    assert rc == 0 and _md5(out) == _md5(_ROOT / _BEST)


def test_dry_run_writes_nothing():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp(); out = f"{d}/out.csv"
    rc = mod.main(["--input", _INPUT, "--output", out, "--mode", "frozen_csv", "--dry-run"])
    assert rc == 0 and not Path(out).exists()


# --- output protection (Part D) ----------------------------------------------

def test_refuses_protected_output_names():
    mod = _load("final_infer.py")
    # frozen best / v10 / v8 are still refused; pred.csv is NOT protected (final export).
    for name in (_BEST, _V10, "output/pred_v8_clean_generalized_from_v7.csv"):
        try:
            mod.main(["--input", _INPUT, "--output", name, "--mode", "frozen_csv"])
            assert False, name
        except SystemExit as e:
            assert "protected" in str(e).lower()


def test_pred_csv_allowed_without_flag():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp(); out = f"{d}/pred.csv"         # basename pred.csv, no --allow-pred-csv
    # public_replay reproduces the frozen best exactly; pred.csv basename needs no special flag.
    rc = mod.main(["--input", _INPUT, "--output", out, "--mode", "public_replay"])
    assert rc == 0 and Path(out).exists() and _md5(out) == _md5(_ROOT / _BEST)


# --- v11_independent / v10 modes ---------------------------------------------

def test_v11_independent_requires_execute_and_budget():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp(); out = f"{d}/out.csv"
    try:
        mod.main(["--input", _INPUT, "--output", out, "--mode", "v11_independent"])
        assert False
    except SystemExit as e:
        assert "execute" in str(e).lower()
    try:
        mod.main(["--input", _INPUT, "--output", out, "--mode", "v11_independent", "--execute"])
        assert False
    except SystemExit as e:
        assert "budget" in str(e).lower()


def test_v10_mode_is_fallback_copy():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp(); out = f"{d}/out.csv"
    rc = mod.main(["--input", _INPUT, "--output", out, "--mode", "v10"])
    assert rc == 0 and _md5(out) == _md5(_ROOT / _V10)   # explicit fallback copy


def test_validation_catches_bad_source():
    mod = _load("final_infer.py")
    d = tempfile.mkdtemp()
    bad = f"{d}/bad.csv"
    with open(bad, "w", newline="") as fh:               # only 2 rows -> missing qids
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader()
        w.writerow({"qid": "test_0001", "answer": "A"})
    try:
        mod.main(["--input", _INPUT, "--output", f"{d}/out.csv", "--mode", "frozen_csv",
                  "--source-csv", bad])
        assert False
    except SystemExit as e:
        assert "missing" in str(e).lower() or "row count" in str(e).lower()


# --- production candidate audit (Part F) -------------------------------------

def test_production_audit_recommends_freeze():
    mod = _load("audit_production_candidate.py")
    d = tempfile.mkdtemp()
    rc = mod.main(["--input", _INPUT, "--candidate", _BEST, "--baseline", _V10,
                   "--output-dir", f"{d}/scratch/audit"])
    assert rc == 0
    rep = json.loads(Path(f"{d}/scratch/audit/production_candidate_audit.json").read_text())
    assert rep["recommendation"] == "freeze_as_default"
    assert rep["beats_v10"] and rep["qid_set_valid"] and rep["md5_matches_manifest"]


def test_production_audit_do_not_freeze_on_md5_mismatch():
    mod = _load("audit_production_candidate.py")
    d = tempfile.mkdtemp()
    # using the v10 CSV as the "candidate" -> md5 won't match the manifest current_best
    rc = mod.main(["--input", _INPUT, "--candidate", _V10, "--baseline", _V10,
                   "--output-dir", f"{d}/scratch/audit"])
    rep = json.loads(Path(f"{d}/scratch/audit/production_candidate_audit.json").read_text())
    assert rep["recommendation"] == "do_not_freeze" and not rep["md5_matches_manifest"]


def test_production_audit_refuses_non_scratch():
    mod = _load("audit_production_candidate.py")
    try:
        mod.main(["--input", _INPUT, "--candidate", _BEST, "--output-dir", "output/x"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


# --- docker / hygiene --------------------------------------------------------

def test_dockerignore_excludes_secrets_and_scratch():
    di = (_ROOT / ".dockerignore").read_text()
    for pat in (".env", "scratch/", ".git/", "*.log"):
        assert pat in di


def test_docker_default_not_v10():
    # default entrypoint runs the dynamic system, not the v10 production pipeline
    dockerfile = (_ROOT / "Dockerfile").read_text()
    assert "docker_entrypoint_v11.sh" in dockerfile
    entry = (_ROOT / "scripts" / "docker_entrypoint_v11.sh").read_text()
    assert "dynamic_full" in entry and "run_production_pipeline.py --input" not in entry


def test_no_qid_hardcoding():
    for name in ("final_infer.py", "audit_production_candidate.py"):
        src = ((_ROOT / "scripts" / "legacy" / name if (_ROOT / "scripts" / "legacy" / name).exists() else _ROOT / "scripts" / name)).read_text()
        assert not re.search(r"\btest_\d{4}\b", src)
