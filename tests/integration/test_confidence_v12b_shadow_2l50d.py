"""Integration: Phase 3A-1 --confidence-v12b-shadow is observational.

Proves the official submission.csv is byte-identical with and without V12B shadow,
scoring runs once per record in combined modes, V12B runs only for router-selected
records via the injected backend, artifacts are privacy-safe, every failure mode
preserves the official output, the legacy+v12b conflict errors before model load, and
V13/selector/legacy are never invoked. No torch/GPU/network (fake predictor/backend).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.local_model.choice_scoring import compute_choice_scores
from src.utils.labels import labels_for

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _predict():
    spec = importlib.util.spec_from_file_location("predict_v12b", _ROOT / "predict.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class _FakeBackend:
    """Deterministic V12B backend: echoes presented option A -> valid votes; counts calls."""
    def __init__(self, mode="ok"):
        self.mode = mode
        self.calls = 0

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError("synthetic v12b generation failure")
        user = "".join(m.get("content", "") for m in prompt_or_messages if isinstance(m, dict)) \
            if isinstance(prompt_or_messages, list) else str(prompt_or_messages)
        text = "unknown"
        for line in user.splitlines():
            if line.strip()[:2] == "A.":
                text = line.strip()[2:].strip()
                break
        return json.dumps({"selected_label": "A", "selected_option_text": text,
                           "label_matches_option": True})


class _FakePredictor:
    """q1 (2+2) gets a LOW score margin -> the single selected record (cap=ceil(2/20)=1).
    Generated answer differs from scored top1 so we can prove Base is never overridden."""
    def __init__(self, backend, mode="ok"):
        self._backend = backend
        self.mode = mode
        self.score_calls = 0

    def load(self):
        return self

    def predict_one(self, item):
        return "B" if "2 + 2" in str(item.get("question", "")) else "A"

    def score_choices(self, item):
        self.score_calls += 1
        if self.mode == "score_raise":
            raise RuntimeError("synthetic scoring failure")
        labels = labels_for(len(item.get("choices") or []))
        low = "2 + 2" in str(item.get("question", ""))
        scores = {lab: (0.0 if lab == "A" else (-1.0 if low else -50.0)) for lab in labels}
        return compute_choice_scores(scores, labels)

    @property
    def backend(self):
        return self._backend


_SAMPLES = [
    {"qid": "q1", "question": "2 + 2 = ?", "choices": ["3", "4", "5", "6"]},
    {"qid": "q2", "question": "Capital of France?", "choices": ["Paris", "Rome", "Bonn"]},
]


def _run(mod, monkeypatch, tmp_path, argv, *, mode="ok", score_mode="ok", predictor=None):
    backend = _FakeBackend(mode)
    pred = predictor or _FakePredictor(backend, mode=score_mode)
    monkeypatch.setattr(mod, "_build_predictor", lambda args: pred.load())
    inp = tmp_path / "in.json"; inp.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    sub = tmp_path / "submission.csv"; subt = tmp_path / "submission_time.csv"
    monkeypatch.setenv("SUBMISSION_FILE", str(sub))
    monkeypatch.setenv("SUBMISSION_TIME_FILE", str(subt))
    monkeypatch.delenv("OUTPUT_FILE", raising=False)
    rc = mod.main(["--input", str(inp), *argv])
    assert rc == 0
    return pred, sub


def _v12b_argv(tmp_path, *extra):
    return ["--confidence-v12b-shadow",
            "--v12b-shadow-path", str(tmp_path / "v.jsonl"),
            "--v12b-shadow-summary-path", str(tmp_path / "v.json"), *extra]


def test_official_csv_byte_identical_with_and_without_v12b(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    _, sub_run = _run(mod, monkeypatch, run, _v12b_argv(tmp_path))
    assert sub_base.read_bytes() == sub_run.read_bytes()
    assert sub_run.read_text().splitlines()[1].startswith("q1,B")   # Base kept, not scored top1 'A'


def test_v12b_runs_only_for_selected_via_injected_backend(tmp_path, monkeypatch):
    mod = _predict()
    backend = _FakeBackend()
    pred = _FakePredictor(backend)
    _run(mod, monkeypatch, tmp_path, _v12b_argv(tmp_path), predictor=pred)
    jp = tmp_path / "v.jsonl"
    rows = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    assert [r["qid"] for r in rows] == ["q1"]                       # only the selected record
    assert rows[0]["source_record_ordinal"] == 0 and rows[0]["v12b_attempted"] is True
    assert pred.score_calls == len(_SAMPLES)                        # one score per record
    assert 1 <= backend.calls <= 6                                  # up to six permutations, 4 choices


def test_v12b_artifacts_schema_and_privacy(tmp_path, monkeypatch):
    mod = _predict()
    _run(mod, monkeypatch, tmp_path, _v12b_argv(tmp_path))
    jp = tmp_path / "v.jsonl"; sp = tmp_path / "v.json"
    blob = jp.read_text() + sp.read_text()
    for banned in ("question", "choices", "prompt", "selected_option_text", "Paris", "reasoning"):
        assert banned not in blob
    summary = json.loads(sp.read_text())
    assert summary["observational_only"] is True
    assert summary["total_input_records"] == 2 and summary["total_router_selected"] == 1
    assert summary["total_v12b_attempted"] == 1
    assert summary["selected_items"][0]["source_record_ordinal"] == 0


def test_scoring_runs_once_in_combined_modes(tmp_path, monkeypatch):
    mod = _predict()
    pred = _FakePredictor(_FakeBackend())
    _run(mod, monkeypatch, tmp_path,
         ["--confidence-telemetry", "--telemetry-path", str(tmp_path / "t.jsonl"),
          "--confidence-shadow-router", "--shadow-router-path", str(tmp_path / "sr.jsonl"),
          "--shadow-router-summary-path", str(tmp_path / "sr.json"),
          *_v12b_argv(tmp_path)],
         predictor=pred)
    assert pred.score_calls == len(_SAMPLES)                        # exactly one scoring pass per record
    # both artifact families present when Phase 2 + V12B are combined
    assert (tmp_path / "sr.jsonl").exists() and (tmp_path / "v.jsonl").exists()


def test_no_v12b_files_when_flag_off(tmp_path, monkeypatch):
    mod = _predict()
    # path flags present but execution flag OFF -> inert, nothing written
    _run(mod, monkeypatch, tmp_path,
         ["--v12b-shadow-path", str(tmp_path / "v.jsonl"),
          "--v12b-shadow-summary-path", str(tmp_path / "v.json")])
    assert not (tmp_path / "v.jsonl").exists() and not (tmp_path / "v.json").exists()


def test_legacy_plus_v12b_conflict_errors_before_model_load(tmp_path, monkeypatch):
    mod = _predict()

    def _boom(*a, **k):
        raise AssertionError("model/legacy path must not be reached on a mode conflict")

    monkeypatch.setattr(mod, "_build_predictor", _boom)
    monkeypatch.setattr(mod, "_run_legacy_dynamic_full", _boom)
    inp = tmp_path / "in.json"; inp.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.main(["--input", str(inp), "--legacy-dynamic-full", "--confidence-v12b-shadow"])


def test_v12b_generation_failure_preserves_official(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    _, sub_run = _run(mod, monkeypatch, run, _v12b_argv(tmp_path), mode="raise")
    assert sub_run.read_bytes() == sub_base.read_bytes()           # official intact
    rows = [json.loads(l) for l in (tmp_path / "v.jsonl").read_text().splitlines() if l.strip()]
    # the selected record was still attempted; all permutations failed generation
    assert rows[0]["v12b_attempted"] is True
    assert rows[0]["aggregate"]["generation_failure_count"] >= 1


def test_v12b_artifact_write_failure_preserves_official(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    bad_dir = tmp_path / "jsonl_is_a_dir"; bad_dir.mkdir()          # JSONL write target is a dir
    _, sub_run = _run(mod, monkeypatch, run,
                      ["--confidence-v12b-shadow", "--v12b-shadow-path", str(bad_dir),
                       "--v12b-shadow-summary-path", str(tmp_path / "v.json")])
    assert sub_run.read_bytes() == sub_base.read_bytes()           # official intact despite write failure


def test_v12b_skipped_when_choice_scoring_disabled(tmp_path, monkeypatch):
    mod = _predict()
    import src.local_model.confidence_config as cc
    monkeypatch.setattr(cc, "load_choice_scoring_config",
                        lambda *a, **k: cc.ChoiceScoringConfig(enabled=False))
    _, sub = _run(mod, monkeypatch, tmp_path, _v12b_argv(tmp_path))
    assert sub.read_text().splitlines()[1].startswith("q1,B")      # official intact
    assert not (tmp_path / "v.jsonl").exists()                     # V12B fully skipped, no file


def test_v12b_scoring_failure_fails_closed(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    # scoring raises -> no valid margins; records are still selected via scoring_invalid,
    # but the official CSV must stay byte-identical and V12B must not corrupt it.
    _, sub_run = _run(mod, monkeypatch, run, _v12b_argv(tmp_path), score_mode="score_raise")
    assert sub_run.read_bytes() == sub_base.read_bytes()


def test_v12b_never_invokes_legacy_selective(tmp_path, monkeypatch):
    mod = _predict()

    def _boom(*a, **k):
        raise AssertionError("V12B/V13/legacy selective pipeline must not run in v12b-shadow mode")

    monkeypatch.setattr(mod, "_run_legacy_dynamic_full", _boom)
    _, sub = _run(mod, monkeypatch, tmp_path, _v12b_argv(tmp_path))
    assert sub.read_text().splitlines()[1].startswith("q1,B")
