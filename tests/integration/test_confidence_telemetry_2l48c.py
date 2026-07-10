"""Integration: Phase 1 --confidence-telemetry is observational.

Proves the official submission.csv is byte-identical with and without telemetry,
the diagnostics JSONL has the required schema, telemetry fails closed, and no
JSONL is written in the default (no-flag) path. No torch/GPU/network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from src.local_model.choice_scoring import compute_choice_scores
from src.utils.labels import labels_for

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _predict():
    spec = importlib.util.spec_from_file_location("predict_btc_tel", _ROOT / "predict.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class _FakePredictor:
    """Deterministic: answer from predict_one; score_choices returns fake logits."""
    def __init__(self, mode="ok"):
        self.mode = mode

    def load(self):
        return self

    def predict_one(self, item):
        return "B" if "2 + 2" in str(item.get("question", "")) else "A"

    def score_choices(self, item):
        if self.mode == "raise":
            raise RuntimeError("synthetic scoring failure")
        labels = labels_for(len(item.get("choices") or []))
        scores = {lab: -float(i) for i, lab in enumerate(labels)}   # top1 = 'A'
        return compute_choice_scores(scores, labels, scoring_method="single_token")


_SAMPLES = [
    {"qid": "q1", "question": "2 + 2 = ?", "choices": ["3", "4", "5", "6"]},
    {"qid": "q2", "question": "Capital of France?", "choices": ["Paris", "Rome", "Bonn"]},
]


def _write_input(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    return str(p)


def _run(mod, monkeypatch, tmp_path, argv, mode="ok"):
    monkeypatch.setattr(mod, "_build_predictor", lambda args: _FakePredictor(mode).load())
    sub = tmp_path / "submission.csv"
    subt = tmp_path / "submission_time.csv"
    monkeypatch.setenv("SUBMISSION_FILE", str(sub))
    monkeypatch.setenv("SUBMISSION_TIME_FILE", str(subt))
    monkeypatch.delenv("OUTPUT_FILE", raising=False)
    rc = mod.main(["--input", _write_input(tmp_path), *argv])
    assert rc == 0
    return sub, subt


def test_official_csv_identical_with_and_without_telemetry(tmp_path, monkeypatch):
    mod = _predict()
    base_dir = tmp_path / "base"; base_dir.mkdir()
    tel_dir = tmp_path / "tel"; tel_dir.mkdir()
    tpath = tmp_path / "telemetry.jsonl"

    sub_base, _ = _run(mod, monkeypatch, base_dir, [])
    sub_tel, _ = _run(mod, monkeypatch, tel_dir,
                      ["--confidence-telemetry", "--telemetry-path", str(tpath)])

    assert sub_base.read_bytes() == sub_tel.read_bytes()      # answers byte-identical
    assert sub_tel.read_text().splitlines()[0] == "qid,answer"


def test_telemetry_jsonl_schema_and_agreement(tmp_path, monkeypatch):
    mod = _predict()
    tpath = tmp_path / "telemetry.jsonl"
    _run(mod, monkeypatch, tmp_path, ["--confidence-telemetry", "--telemetry-path", str(tpath)])

    recs = [json.loads(l) for l in tpath.read_text().splitlines() if l.strip()]
    assert len(recs) == len(_SAMPLES)
    required = {"qid", "generated_answer", "scored_top1", "scored_top2", "scores_by_label",
                "probabilities_by_label", "logit_margin", "probability_margin",
                "normalized_entropy", "generated_vs_scored_agree", "scoring_method",
                "scoring_valid", "scoring_error", "elapsed_sec"}
    for r in recs:
        assert required <= set(r)
        assert r["scoring_valid"] is True
        assert "question" not in r                            # no private text
    by_qid = {r["qid"]: r for r in recs}
    # q1: generated 'B' vs scored top1 'A' -> disagree; q2: generated 'A' == top1 'A' -> agree
    assert by_qid["q1"]["generated_answer"] == "B"
    assert by_qid["q1"]["generated_vs_scored_agree"] is False
    assert by_qid["q2"]["generated_vs_scored_agree"] is True


def test_telemetry_fails_closed_without_breaking_submission(tmp_path, monkeypatch):
    mod = _predict()
    tpath = tmp_path / "telemetry.jsonl"
    sub, _ = _run(mod, monkeypatch, tmp_path,
                  ["--confidence-telemetry", "--telemetry-path", str(tpath)], mode="raise")
    # official answers still written correctly
    lines = sub.read_text().splitlines()
    assert lines[0] == "qid,answer" and lines[1].startswith("q1,B") and lines[2].startswith("q2,A")
    recs = [json.loads(l) for l in tpath.read_text().splitlines() if l.strip()]
    assert all(r["scoring_valid"] is False and r["scoring_error"] for r in recs)


def test_no_telemetry_file_in_default_path(tmp_path, monkeypatch):
    mod = _predict()
    tpath = tmp_path / "telemetry.jsonl"
    _run(mod, monkeypatch, tmp_path, ["--telemetry-path", str(tpath)])   # flag OFF
    assert not tpath.exists()
