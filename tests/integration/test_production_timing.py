"""Tests for Phase 2L.22 production timing report + Docker entrypoint metadata.

No API: the base solver is monkeypatched to a fake that returns a fixed label.
Verifies the runtime report prints, the JSONL has an `event:"summary"` record with
timing fields, prediction logic is unchanged (fake answers pass through), and the
Docker entrypoint still detects input + prints metadata.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "rpp_timing", next(iter((_ROOT / "scripts" / "legacy").glob("**/run_production_pipeline.py"))))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSolver:
    """Fixed-answer solver (no API). Used to verify timing without inference."""
    def __init__(self, answer="A"):
        self.answer = answer

    def predict_one(self, sample):
        return self.answer

    def predict_batch(self, samples):
        return [self.answer for _ in samples]


def _write_input(n=4):
    d = Path(tempfile.mkdtemp())
    rows = [{"qid": f"s{i}", "question": f"Câu hỏi {i}?", "choices": ["A", "B", "C", "D"]}
            for i in range(n)]
    p = d / "input.json"
    p.write_text(json.dumps(rows, ensure_ascii=False))
    return d, str(p)


def _run(monkeypatch, capsys, extra_args=None):
    m = _load_runner()
    monkeypatch.setattr(m, "build_solver", lambda *a, **k: _FakeSolver("A"))
    d, inp = _write_input()
    out = str(d / "pred.csv")
    log = str(d / "run.jsonl")
    args = ["--input", inp, "--output", out, "--base-solver", "openrouter_graph",
            "--log-path", log]
    if extra_args:
        args += extra_args
    rc = m.main(args)
    return rc, out, log, capsys.readouterr().out


def test_timing_report_printed(monkeypatch, capsys):
    rc, out, log, stdout = _run(monkeypatch, capsys)
    assert rc == 0
    assert "PRODUCTION RUN SUMMARY" in stdout
    for field in ("elapsed_seconds", "total_samples", "newly_predicted",
                  "samples_per_second", "avg_seconds_per_sample", "safe overrides applied"):
        assert field in stdout, f"missing timing field in report: {field}"


def test_jsonl_summary_event_with_timing(monkeypatch, capsys):
    rc, out, log, _ = _run(monkeypatch, capsys)
    lines = [json.loads(x) for x in Path(log).read_text().splitlines() if x.strip()]
    summaries = [r for r in lines if r.get("event") == "summary"]
    assert len(summaries) == 1
    s = summaries[0]
    for key in ("elapsed_seconds", "total_samples", "newly_predicted",
                "samples_per_second", "avg_seconds_per_sample", "overrides_applied"):
        assert key in s, f"missing {key} in summary record"
    assert s["total_samples"] == 4 and s["newly_predicted"] == 4


def test_prediction_logic_unchanged(monkeypatch, capsys):
    # With a fixed-answer fake solver and no formula-bank, every output == base "A".
    rc, out, log, _ = _run(monkeypatch, capsys)
    rows = [r.split(",") for r in Path(out).read_text().splitlines()[1:] if r]
    assert rows and all(r[1] == "A" for r in rows)   # timing layer did not alter answers


def test_docker_entrypoint_detection_and_metadata():
    # The entrypoint uses --detect-only (shared logic) and prints run metadata.
    src = (_ROOT / "scripts" / "docker_entrypoint.sh").read_text()
    assert "--detect-only" in src
    for token in ("detected input", "output path", "preset", "start", "end", "wall_seconds"):
        assert token in src, f"entrypoint missing metadata: {token}"
    # detection logic itself (shared with the runner)
    m = _load_runner()
    d = Path(tempfile.mkdtemp())
    (d / "private_test.csv").write_text("qid,question\n")
    assert m.detect_input_file(d).endswith("private_test.csv")


def test_no_qid_hardcoding_in_runner():
    import re as _re
    src = (next(iter((_ROOT / "scripts" / "legacy").glob("**/run_production_pipeline.py")))).read_text()
    for pat in (r'qid\s*==', r'==\s*["\']test_0', r'test_0\d{3}'):
        assert not _re.search(pat, src)
