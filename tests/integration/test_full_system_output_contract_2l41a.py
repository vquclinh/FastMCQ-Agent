"""Tests for Phase 2L.41A — official full-system command + output/pred.csv contract.

Integration-focused (no per-layer workflows). No real API: the wrapper runs with --no-api and
the final artifact dir is redirected via FASTMCQ_FINAL_DIR so the repo's output/ is never touched.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.tools.output_quality_report import compute_quality_report  # noqa: E402
_WRAPPER = _ROOT / "scripts" / "run_full_system.sh"
_PROFILES = json.loads((_ROOT / "configs" / "profiles" / "run_profiles.json").read_text())


def _write_input(tmp_path, samples):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(samples, ensure_ascii=False))
    return p


def _run_wrapper(input_path, final_dir, *extra):
    env = dict(os.environ, FASTMCQ_FINAL_DIR=str(final_dir))
    return subprocess.run(["bash", str(_WRAPPER), str(input_path), "--no-api", *extra],
                          cwd=str(_ROOT), env=env, capture_output=True, text=True)


_SAMPLES = [{"qid": f"priv_{i}", "question": "2 + 2 bằng bao nhiêu?" if i == 0 else "Chọn câu đúng.",
             "choices": ["3", "4", "5", "6"] if i == 0 else ["a", "b", "c", "d"]} for i in range(4)]


# --- wrapper presence / shape ------------------------------------------------

def test_run_full_system_exists_and_valid():
    assert _WRAPPER.exists()
    r = subprocess.run(["bash", "-n", str(_WRAPPER)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    text = _WRAPPER.read_text()
    assert "production_full_system" in text          # official profile
    assert "FASTMCQ_FINAL_DIR" in text               # final dir is overridable (default output/)
    assert "scripts/final_infer.py" in text          # delegates to the full system entrypoint


def test_production_profile_is_full_system_not_public_replay():
    p = _PROFILES["production_full_system"]
    assert p["mode"] == "dynamic_full" and p["enable_v12b"] and p["enable_v13"]
    assert "public_replay" not in json.dumps(p)
    # wrapper must not default to public_replay
    assert "public_replay" not in _WRAPPER.read_text()


def test_production_profile_no_public_qids_or_seed():
    blob = json.dumps(_PROFILES["production_full_system"]) + json.dumps(
        _PROFILES["production_full_system_noapi"])
    assert "public-test" not in blob and "pred_v13" not in blob and "1780368312" not in blob


# --- end-to-end contract (no API) --------------------------------------------

def test_successful_run_promotes_to_final_pred_csv(tmp_path):
    final = tmp_path / "final"
    r = _run_wrapper(_write_input(tmp_path, _SAMPLES), final)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (final / "pred.csv").exists()
    assert "status  : PASS" in r.stdout


def test_output_qids_match_input_exactly(tmp_path):
    final = tmp_path / "final"
    _run_wrapper(_write_input(tmp_path, _SAMPLES), final)
    rows = [l.split(",")[0] for l in (final / "pred.csv").read_text().splitlines()[1:]]
    assert rows == [s["qid"] for s in _SAMPLES]


def test_timestamped_run_dir_and_quality_report_created(tmp_path):
    final = tmp_path / "final"
    r = _run_wrapper(_write_input(tmp_path, _SAMPLES), final)
    # parse run dir from stdout
    m = re.search(r"run_out : (\S+/full_system_\d+_\d+/pred\.csv)", r.stdout)
    assert m, r.stdout
    run_dir = Path(m.group(1)).parent
    assert (run_dir / "quality_report.json").exists()
    assert (run_dir / "run.log").exists()
    rep = json.loads((run_dir / "quality_report.json").read_text())
    assert rep["total"] == len(_SAMPLES)


def test_failed_run_does_not_overwrite_existing_final(tmp_path):
    final = tmp_path / "final"; final.mkdir()
    sentinel = "qid,answer\nSENTINEL,Z\n"
    (final / "pred.csv").write_text(sentinel)
    # non-existent input -> final_infer fails -> wrapper must NOT promote
    r = _run_wrapper(tmp_path / "does_not_exist.json", final)
    assert r.returncode != 0
    assert (final / "pred.csv").read_text() == sentinel   # untouched


def test_fail_on_quality_guard_blocks_promotion(tmp_path):
    # 3 single-choice-ish samples that all fall back to 'A' -> 100% degenerate
    samples = [{"qid": f"d{i}", "question": "?", "choices": ["a", "b", "c", "d"]} for i in range(3)]
    final = tmp_path / "final"
    r = _run_wrapper(_write_input(tmp_path, samples), final, "--fail-on-quality-guard")
    assert "WARNING: degenerate" in r.stdout
    assert not (final / "pred.csv").exists()        # guard blocked promotion
    assert "NOT promoted" in r.stdout


# --- quality report unit ------------------------------------------------------

def test_quality_report_flags_degenerate(tmp_path):
    p = tmp_path / "deg.csv"
    p.write_text("qid,answer\n" + "".join(f"q{i},A\n" for i in range(10)))
    rep = compute_quality_report(str(p))
    assert rep["degenerate"] is True and rep["top_label"] == "A" and rep["top_ratio"] == 1.0


def test_quality_report_balanced_not_degenerate(tmp_path):
    p = tmp_path / "bal.csv"
    p.write_text("qid,answer\nq1,A\nq2,B\nq3,C\nq4,D\n")
    rep = compute_quality_report(str(p))
    assert rep["degenerate"] is False


# --- Docker + hygiene ---------------------------------------------------------

def test_docker_writes_output_pred_csv():
    entry = (_ROOT / "scripts" / "docker_entrypoint_v11.sh").read_text()
    assert "/output/pred.csv" in entry
    assert "/output/pred.csv" in (_ROOT / "DOCKER_SUBMISSION.md").read_text()


def test_no_qid_or_answer_hardcoding():
    for f in ("scripts/run_full_system.sh", "scripts/output_quality_report.py",
              "configs/profiles/run_profiles.json"):
        assert not re.search(r"\btest_\d{4}\b", (_ROOT / f).read_text()), f
