"""Integration: --confidence-full-pipeline through predict.py main().

Proves: no-flag stays Base-only; --confidence-v12b-shadow stays observational
(official CSV unchanged); --confidence-full-pipeline CAN change the official
answer for a router-selected record via the deterministic selector while leaving
non-selected records on Base; row count/qid order are preserved; a global
full-pipeline failure still writes a Base submission; an artifact-write failure
does not suppress the submission; the three modes are pairwise mutually exclusive
and refuse before any model construction; artifacts are privacy-safe; and the
same injected backend instance serves V12B and V13 (no second model load). No
torch/GPU/network (fake predictor/backend).
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

_V12B_MARKER = "selected_label, selected_option_text, label_matches_option"


def _predict():
    spec = importlib.util.spec_from_file_location("predict_full_pipeline", _ROOT / "predict.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _text_of(prompt_or_messages):
    if isinstance(prompt_or_messages, list):
        return "".join(m.get("content", "") for m in prompt_or_messages if isinstance(m, dict))
    return str(prompt_or_messages)


def _option_lines(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 2 and s[1] == "." and s[0].isalpha():
            out.append((s[0], s[2:].strip()))
    return out


class _FakeBackend:
    """Distinguishes V12B permutation prompts from V13 prompts via V12B's own
    marker text, and (for V13) distinguishes the programmatic-solver prompt (its
    own unique marker text) from the content-first/least-to-most prompts. V12B
    always fails closed (malformed) so every full-pipeline test exercises the V13
    path deterministically. For the 4-choice arithmetic question "2 + 2 = ?"
    (choices 3/4/5/6), V13 picks the programmatic_solver layer (numeric question),
    so the fake answers with an expression evaluating to 5 -> label C, visibly
    overriding Base's "B" -- unless configured to fail."""

    def __init__(self, v12b_mode="malformed", v13_mode="ok",
                 v13_expression="2+3", v13_target_text="5"):
        self.calls = 0
        self.v12b_mode = v12b_mode
        self.v13_mode = v13_mode
        self.v13_expression = v13_expression
        self.v13_target_text = v13_target_text

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        self.calls += 1
        text = _text_of(prompt_or_messages)
        if _V12B_MARKER in text:
            if self.v12b_mode == "raise":
                raise RuntimeError("synthetic v12b failure")
            return json.dumps({"nope": True})     # malformed -> every permutation invalid
        if self.v13_mode == "raise":
            raise RuntimeError("synthetic v13 failure")
        if self.v13_mode == "malformed":
            return "not json at all"
        if self.v13_mode == "no_match":
            return json.dumps({"answer_content": "completely unrelated", "answer_type": "phrase"})
        if "calculation engine" in text:            # programmatic_solver prompt marker
            return json.dumps({"operation": "arithmetic", "expression": self.v13_expression,
                               "operands": {}, "result_hint": None, "evidence": ""})
        return json.dumps({"answer_content": self.v13_target_text, "answer_type": "term"})


class _FakePredictor:
    """q1 (2+2) gets a LOW score margin -> the single selected record (cap=ceil(2/8)=1)."""
    def __init__(self, backend, mode="ok"):
        self._backend = backend
        self.mode = mode
        self.score_calls = 0
        self.build_calls = 0

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


def _run(mod, monkeypatch, tmp_path, argv, *, predictor=None, backend=None, count_builds=False):
    backend = backend or _FakeBackend()
    pred = predictor or _FakePredictor(backend)

    def _build(args):
        pred.build_calls += 1
        return pred.load()

    monkeypatch.setattr(mod, "_build_predictor", _build if count_builds else lambda args: pred.load())
    inp = tmp_path / "in.json"; inp.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    sub = tmp_path / "submission.csv"; subt = tmp_path / "submission_time.csv"
    monkeypatch.setenv("SUBMISSION_FILE", str(sub))
    monkeypatch.setenv("SUBMISSION_TIME_FILE", str(subt))
    monkeypatch.delenv("OUTPUT_FILE", raising=False)
    rc = mod.main(["--input", str(inp), *argv])
    assert rc == 0
    return pred, sub


def _fp_argv(tmp_path, *extra):
    return ["--confidence-full-pipeline",
            "--confidence-full-pipeline-path", str(tmp_path / "fp.jsonl"),
            "--confidence-full-pipeline-summary-path", str(tmp_path / "fp.json"), *extra]


def test_no_flag_stays_base_only(tmp_path, monkeypatch):
    mod = _predict()
    _, sub = _run(mod, monkeypatch, tmp_path, [])
    assert sub.read_text().splitlines()[1].startswith("q1,B")


def test_v12b_shadow_stays_observational(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    _, sub_run = _run(mod, monkeypatch, run,
                      ["--confidence-v12b-shadow",
                       "--v12b-shadow-path", str(tmp_path / "v.jsonl"),
                       "--v12b-shadow-summary-path", str(tmp_path / "v.json")])
    assert sub_base.read_bytes() == sub_run.read_bytes()


def test_full_pipeline_overrides_selected_record_only(tmp_path, monkeypatch):
    mod = _predict()
    pred, sub = _run(mod, monkeypatch, tmp_path, _fp_argv(tmp_path))
    lines = sub.read_text().splitlines()
    assert lines[0] == "qid,answer"
    assert lines[1] == "q1,C"     # V13 resolved to "5" == choices[2] -> label C (overridden)
    assert lines[2] == "q2,A"     # not selected -> stays Base
    assert len(lines) == 3        # row count unchanged (header + 2 rows)


def test_full_pipeline_differs_from_base_only_csv(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])
    _, sub_run = _run(mod, monkeypatch, run, _fp_argv(tmp_path))
    assert sub_base.read_bytes() != sub_run.read_bytes()   # full pipeline DID change output
    assert [l.split(",")[0] for l in sub_base.read_text().splitlines()] == \
           [l.split(",")[0] for l in sub_run.read_text().splitlines()]   # qid order unchanged


def test_full_pipeline_artifacts_privacy_and_schema(tmp_path, monkeypatch):
    mod = _predict()
    _run(mod, monkeypatch, tmp_path, _fp_argv(tmp_path))
    jp = tmp_path / "fp.jsonl"; sp = tmp_path / "fp.json"
    blob = jp.read_text() + sp.read_text()
    for banned in ("question", "choices", "prompt", "Paris", "reasoning", "evidence",
                   "2 + 2", "Capital of France"):
        assert banned not in blob
    rows = [json.loads(l) for l in jp.read_text().splitlines() if l.strip()]
    assert len(rows) == 2
    by_qid = {r["qid"]: r for r in rows}
    assert by_qid["q1"]["final_source"] == "v13" and by_qid["q1"]["final_answer"] == "C"
    assert by_qid["q2"]["final_source"] == "base" and by_qid["q2"]["router_selected"] is False
    summary = json.loads(sp.read_text())
    assert summary["total_input_records"] == 2
    assert summary["total_v13_accepted"] == 1
    for line in jp.read_text().splitlines():
        if line.strip():
            json.dumps(json.loads(line), allow_nan=False)   # finite


def test_full_pipeline_global_failure_preserves_base_submission(tmp_path, monkeypatch):
    mod = _predict()
    base = tmp_path / "base"; base.mkdir()
    run = tmp_path / "run"; run.mkdir()
    _, sub_base = _run(mod, monkeypatch, base, [])

    def _boom(**kwargs):
        raise RuntimeError("synthetic full-pipeline failure")

    import src.local_model.confidence_full_pipeline as fp_mod
    monkeypatch.setattr(fp_mod, "run_full_pipeline", _boom)
    _, sub_run = _run(mod, monkeypatch, run, _fp_argv(tmp_path))
    assert sub_run.read_bytes() == sub_base.read_bytes()   # official output fell back to Base


def test_full_pipeline_artifact_write_failure_preserves_submission(tmp_path, monkeypatch):
    mod = _predict()
    bad_dir = tmp_path / "jsonl_is_a_dir"; bad_dir.mkdir()
    _, sub = _run(mod, monkeypatch, tmp_path,
                  ["--confidence-full-pipeline",
                   "--confidence-full-pipeline-path", str(bad_dir),
                   "--confidence-full-pipeline-summary-path", str(tmp_path / "fp.json")])
    lines = sub.read_text().splitlines()
    assert lines[1] == "q1,C"     # official answer still correctly computed and written
    assert len(lines) == 3


def test_legacy_plus_full_pipeline_conflict_errors_before_model_load(tmp_path, monkeypatch):
    mod = _predict()

    def _boom(*a, **k):
        raise AssertionError("model/legacy path must not be reached on a mode conflict")

    monkeypatch.setattr(mod, "_build_predictor", _boom)
    monkeypatch.setattr(mod, "_run_legacy_dynamic_full", _boom)
    inp = tmp_path / "in.json"; inp.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.main(["--input", str(inp), "--legacy-dynamic-full", "--confidence-full-pipeline"])


def test_v12b_shadow_plus_full_pipeline_conflict_errors_before_model_load(tmp_path, monkeypatch):
    mod = _predict()

    def _boom(*a, **k):
        raise AssertionError("model path must not be reached on a mode conflict")

    monkeypatch.setattr(mod, "_build_predictor", _boom)
    inp = tmp_path / "in.json"; inp.write_text(json.dumps(_SAMPLES), encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.main(["--input", str(inp), "--confidence-v12b-shadow", "--confidence-full-pipeline"])


def test_full_pipeline_never_invokes_legacy_selective(tmp_path, monkeypatch):
    mod = _predict()

    def _boom(*a, **k):
        raise AssertionError("legacy selective pipeline must not run in full-pipeline mode")

    monkeypatch.setattr(mod, "_run_legacy_dynamic_full", _boom)
    _run(mod, monkeypatch, tmp_path, _fp_argv(tmp_path))


def test_full_pipeline_uses_single_injected_backend_no_second_model_load(tmp_path, monkeypatch):
    mod = _predict()
    backend = _FakeBackend()
    pred = _FakePredictor(backend)
    _run(mod, monkeypatch, tmp_path, _fp_argv(tmp_path), predictor=pred,
         backend=backend, count_builds=True)
    assert pred.build_calls == 1                  # exactly one predictor/backend construction
    assert backend.calls > 0                       # the single backend served both V12B and V13
    assert pred.score_calls == len(_SAMPLES)        # exactly one scoring pass per record


def test_full_pipeline_scoring_and_router_run_once_when_combined_with_shadow(tmp_path, monkeypatch):
    mod = _predict()
    pred = _FakePredictor(_FakeBackend())
    _run(mod, monkeypatch, tmp_path,
         ["--confidence-shadow-router", "--shadow-router-path", str(tmp_path / "sr.jsonl"),
          "--shadow-router-summary-path", str(tmp_path / "sr.json"),
          *_fp_argv(tmp_path)],
         predictor=pred)
    assert pred.score_calls == len(_SAMPLES)
    assert (tmp_path / "sr.jsonl").exists() and (tmp_path / "fp.jsonl").exists()


def test_no_full_pipeline_files_when_flag_off(tmp_path, monkeypatch):
    mod = _predict()
    _run(mod, monkeypatch, tmp_path,
         ["--confidence-full-pipeline-path", str(tmp_path / "fp.jsonl"),
          "--confidence-full-pipeline-summary-path", str(tmp_path / "fp.json")])
    assert not (tmp_path / "fp.jsonl").exists() and not (tmp_path / "fp.json").exists()
