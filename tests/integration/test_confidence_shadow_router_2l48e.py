"""Integration: Phase 2 shadow router is observational.

Proves official submission.csv is byte-identical with/without the shadow router,
scoring runs exactly once per qid when telemetry + shadow are both on, the shadow
artifacts have the right schema and no question text, no answer is overridden, and
V12B/V13/selector/legacy are never invoked. No torch/GPU/network.
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
    spec = importlib.util.spec_from_file_location("predict_shadow", _ROOT / "predict.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class _FakePredictor:
    """Deterministic. score_choices counts calls; top1='A' always (differs from the
    generated 'B' on q1 so we can prove the official answer is never overridden)."""
    def __init__(self, mode="ok"):
        self.mode = mode
        self.score_calls = 0

    def load(self):
        return self

    def predict_one(self, item):
        return "B" if "2 + 2" in str(item.get("question", "")) else "A"

    def score_choices(self, item):
        self.score_calls += 1
        if self.mode == "raise":
            raise RuntimeError("synthetic scoring failure")
        labels = labels_for(len(item.get("choices") or []))
        # q1 gets a LOW margin (shadow candidate); others high. top1='A'.
        low = "2 + 2" in str(item.get("question", ""))
        scores = {lab: (0.0 if lab == "A" else (-1.0 if low else -50.0)) for lab in labels}
        return compute_choice_scores(scores, labels)


_SAMPLES = [
    {"qid": "q1", "question": "2 + 2 = ?", "choices": ["3", "4", "5", "6"]},
    {"qid": "q2", "question": "Capital of France?", "choices": ["Paris", "Rome", "Bonn"]},
]


def _run(mod, monkeypatch, tmp_path, argv, mode="ok", predictor=None):
    pred = predictor or _FakePredictor(mode)
    monkeypatch.setattr(mod, "_build_predictor", lambda args: pred.load())
    inp = tmp_path / "in.json"; inp.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    sub = tmp_path / "submission.csv"; subt = tmp_path / "submission_time.csv"
    monkeypatch.setenv("SUBMISSION_FILE", str(sub))
    monkeypatch.setenv("SUBMISSION_TIME_FILE", str(subt))
    monkeypatch.delenv("OUTPUT_FILE", raising=False)
    rc = mod.main(["--input", str(inp), *argv])
    assert rc == 0
    return pred, sub


def test_official_csv_identical_with_and_without_shadow(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    sh = tmp_path / "sh"; sh.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    _, sub_sh = _run(mod, monkeypatch, sh, [
        "--confidence-shadow-router",
        "--shadow-router-path", str(tmp_path / "sr.jsonl"),
        "--shadow-router-summary-path", str(tmp_path / "sr.json")])
    assert sub_base.read_bytes() == sub_sh.read_bytes()
    # official answer is the GENERATED one (q1 -> B), never the scored top1 ('A')
    assert sub_sh.read_text().splitlines()[1].startswith("q1,B")


def test_shadow_artifacts_schema_and_no_text(tmp_path, monkeypatch):
    mod = _predict()
    jp = tmp_path / "sr.jsonl"; sp = tmp_path / "sr.json"
    _run(mod, monkeypatch, tmp_path, ["--confidence-shadow-router",
                                      "--shadow-router-path", str(jp),
                                      "--shadow-router-summary-path", str(sp)])
    decs = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    assert [d["qid"] for d in decs] == ["q1", "q2"]           # one per qid, input order
    for d in decs:
        assert {"candidate", "selected", "selected_rank", "candidate_reasons",
                "logit_margin", "risk_tier", "budget_cap", "scoring_method"} <= set(d)
        for banned in ("question", "choices", "prompt", "text"):
            assert banned not in d
        json.dumps(d, allow_nan=False)                        # JSON-safe
    summary = json.loads(sp.read_text())
    assert summary["n_input"] == 2 and summary["budget_cap"] == 1   # ceil(2/20)=1
    assert "question" not in json.dumps(summary)
    # q1 (low margin) is the candidate/selected; q2 not
    q1 = next(d for d in decs if d["qid"] == "q1")
    assert q1["candidate"] is True and q1["selected"] is True


def test_scoring_runs_once_per_qid_in_combined_mode(tmp_path, monkeypatch):
    mod = _predict()
    pred = _FakePredictor()
    _run(mod, monkeypatch, tmp_path,
         ["--confidence-telemetry", "--telemetry-path", str(tmp_path / "t.jsonl"),
          "--confidence-shadow-router", "--shadow-router-path", str(tmp_path / "sr.jsonl"),
          "--shadow-router-summary-path", str(tmp_path / "sr.json")],
         predictor=pred)
    assert pred.score_calls == len(_SAMPLES)   # exactly one scoring call per qid, not two


def test_shadow_never_invokes_legacy_selective(tmp_path, monkeypatch):
    mod = _predict()

    def _boom(*a, **k):
        raise AssertionError("V12B/V13/legacy selective pipeline must not run in shadow mode")

    monkeypatch.setattr(mod, "_run_legacy_dynamic_full", _boom)
    _, sub = _run(mod, monkeypatch, tmp_path,
                  ["--confidence-shadow-router", "--shadow-router-path", str(tmp_path / "sr.jsonl"),
                   "--shadow-router-summary-path", str(tmp_path / "sr.json")])
    assert sub.read_text().splitlines()[1].startswith("q1,B")


def test_shadow_output_failure_does_not_break_official(tmp_path, monkeypatch):
    mod = _predict()
    # point the shadow JSONL at a directory path -> write fails, official output must still be fine
    bad_dir = tmp_path / "adir"; bad_dir.mkdir()
    _, sub = _run(mod, monkeypatch, tmp_path,
                  ["--confidence-shadow-router", "--shadow-router-path", str(bad_dir),
                   "--shadow-router-summary-path", str(tmp_path / "sr.json")])
    lines = sub.read_text().splitlines()
    assert lines[0] == "qid,answer" and lines[1].startswith("q1,B") and len(lines) == 3


def test_scoring_failure_marks_invalid_but_official_ok(tmp_path, monkeypatch):
    mod = _predict()
    jp = tmp_path / "sr.jsonl"
    _, sub = _run(mod, monkeypatch, tmp_path,
                  ["--confidence-shadow-router", "--shadow-router-path", str(jp),
                   "--shadow-router-summary-path", str(tmp_path / "sr.json")], mode="raise")
    assert sub.read_text().splitlines()[1].startswith("q1,B")   # official output intact
    decs = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    assert all(d["scoring_valid"] is False for d in decs)


def test_no_shadow_files_when_flag_off(tmp_path, monkeypatch):
    mod = _predict()
    jp = tmp_path / "sr.jsonl"; sp = tmp_path / "sr.json"
    _run(mod, monkeypatch, tmp_path, ["--shadow-router-path", str(jp),
                                      "--shadow-router-summary-path", str(sp)])
    assert not jp.exists() and not sp.exists()


def test_shadow_skipped_when_choice_scoring_disabled(tmp_path, monkeypatch):
    mod = _predict()
    import src.local_model.confidence_config as cc
    monkeypatch.setattr(cc, "load_choice_scoring_config",
                        lambda *a, **k: cc.ChoiceScoringConfig(enabled=False))
    jp = tmp_path / "sr.jsonl"
    _, sub = _run(mod, monkeypatch, tmp_path,
                  ["--confidence-shadow-router", "--shadow-router-path", str(jp),
                   "--shadow-router-summary-path", str(tmp_path / "sr.json")])
    assert sub.read_text().splitlines()[1].startswith("q1,B")   # official output intact
    assert not jp.exists()                                      # shadow skipped, no file


def test_malformed_shadow_config_fails_closed_end_to_end(tmp_path, monkeypatch):
    """AUDIT 73 F3: a malformed shadow_router config must disable shadow (fail closed),
    never select qids with an unintended default, and never affect official output."""
    mod = _predict()
    import src.local_model.confidence_config as cc
    # valid choice_scoring (so scoring is enabled) + malformed shadow_router (budget_divisor 0)
    cfg = tmp_path / "confidence_selective.yaml"
    cfg.write_text("choice_scoring:\n  enabled: true\n"
                   "shadow_router:\n  enabled: true\n  budget_divisor: 0\n", encoding="utf-8")
    monkeypatch.setattr(cc, "_DEFAULT_CONFIG_PATH", str(cfg))
    jp = tmp_path / "sr.jsonl"; sp = tmp_path / "sr.json"

    base = tmp_path / "base"; base.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])              # deterministic no-shadow baseline
    run = tmp_path / "run"; run.mkdir()
    _, sub_run = _run(mod, monkeypatch, run, ["--confidence-shadow-router",
                                              "--shadow-router-path", str(jp),
                                              "--shadow-router-summary-path", str(sp)])
    assert sub_run.read_bytes() == sub_base.read_bytes()        # official CSV byte-identical
    lines = sub_run.read_text().splitlines()
    assert lines[0] == "qid,answer" and len(lines) == 3         # no qid dropped, order unchanged
    assert not jp.exists() and not sp.exists()                  # shadow fully disabled (fail closed)


def test_summary_write_failure_preserves_official_output(tmp_path, monkeypatch):
    """AUDIT 73 F4: summary write fails independently AFTER the JSONL write; official
    output must remain complete and correct, with only a warning."""
    mod = _predict()
    jp = tmp_path / "sr.jsonl"
    summary_dir = tmp_path / "summary_is_a_dir"; summary_dir.mkdir()   # writing here fails
    base = tmp_path / "base"; base.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    run = tmp_path / "run"; run.mkdir()
    _, sub_run = _run(mod, monkeypatch, run, ["--confidence-shadow-router",
                                              "--shadow-router-path", str(jp),
                                              "--shadow-router-summary-path", str(summary_dir)])
    # the JSONL write succeeded (we genuinely reached the summary-write step, which then failed)
    assert jp.exists() and len(jp.read_text().splitlines()) == len(_SAMPLES)
    # official output complete, correct, byte-identical to the no-shadow baseline
    assert sub_run.read_bytes() == sub_base.read_bytes()
    assert sub_run.read_text().splitlines()[1].startswith("q1,B")
