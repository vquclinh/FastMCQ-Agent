"""Local selective pipeline tests with fake backends; no real model is loaded."""

from __future__ import annotations

import json
from pathlib import Path

from src.base.dynamic_base_predictor import predict_base_answers
from src.layers.v12b_dynamic_layer import run_v12b_layer, select_v12b_targets
from src.layers.v13_dynamic_layer import build_messages, run_v13_layer, select_v13_targets
from src.system.fastmcq_system import FastMCQSystemConfig, run_fastmcq_system


class FakeLocalBackend:
    def __init__(self, *, fail_once: bool = False):
        self.load_count = 0
        self.predict_calls = 0
        self.generate_calls = 0
        self.fail_once = fail_once

    def load(self):
        self.load_count += 1
        return self

    def predict_mcq(self, item, *, max_new_tokens=None):
        self.predict_calls += 1
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("synthetic failure")
        q = str(item.get("question", ""))
        return "B" if "2 + 2" in q else "A"

    def generate_text(self, messages, *, max_new_tokens=None, temperature=0.0):
        self.generate_calls += 1
        text = "\n".join(m.get("content", "") for m in messages) if isinstance(messages, list) else str(messages)
        if "selected_label" in text:
            return json.dumps({
                "selected_label": "A",
                "selected_option_text": "opt 0",
                "label_matches_option": True,
                "confidence": 0.9,
            })
        if "ANSWER CONTENT" in text:
            return json.dumps({
                "answer_content": "opt 1",
                "answer_type": "term",
                "numeric_value": None,
                "evidence": "fake",
                "confidence": 0.8,
            })
        if "atomic constraints" in text:
            return json.dumps({
                "constraints": ["fake"],
                "option_evaluations": [
                    {"label": "A", "passes_constraints": [False], "eliminated": True},
                    {"label": "B", "passes_constraints": [True], "eliminated": False},
                ],
                "final_survivor_label": "B",
                "confidence": 0.8,
                "contradiction_check": True,
            })
        return json.dumps({"answer": "B", "confidence": 0.7})


def _samples(n=2, choices=4):
    return [{"qid": f"qq{i}", "question": "2 + 2 bằng bao nhiêu?",
             "choices": [f"opt {j}" for j in range(choices)]} for i in range(n)]


def test_build_messages_valid_and_empty():
    s = _samples(1)[0]
    msgs, n = build_messages("content_first", s, "short_knowledge")
    assert isinstance(msgs, list) and msgs and n > 0
    msgs2, n2 = build_messages("totally_unknown_layer", s, "x")
    assert msgs2 and n2 > 0


def test_base_uses_formula_then_local_then_fallback():
    samples = [
        {"qid": "formula", "question": "2 + 2 bằng bao nhiêu?", "choices": ["3", "4", "5", "6"]},
        {"qid": "local", "question": "Chọn khái niệm đúng.", "choices": ["x", "y", "z", "w"]},
    ]
    backend = FakeLocalBackend()
    preds = predict_base_answers(samples, local_backend=backend)
    assert len(preds) == 2
    assert all(p.answer for p in preds)
    assert any(p.source.startswith("formula_bank") or p.source == "dynamic_local_qwen" for p in preds)

    failing = FakeLocalBackend(fail_once=True)
    pred = predict_base_answers([samples[1]], local_backend=failing)[0]
    assert pred.source == "dynamic_fallback"
    assert pred.answer == "A"


def test_v12b_writes_incremental_jsonl_and_resume(tmp_path):
    backend = FakeLocalBackend()
    s = _samples(1)
    base = predict_base_answers(s, local_backend=backend)
    targets = select_v12b_targets(s, base, max_qids=None)
    wd = str(tmp_path / "w")
    run_v12b_layer(s, base, targets, local_backend=backend, permutations=6,
                   policy="conservative", work_dir=wd, resume=False)
    recs = (Path(wd) / "v12b_dynamic_records.jsonl").read_text().splitlines()
    assert recs and all(json.loads(l).get("original_qid") for l in recs)
    first_calls = backend.generate_calls

    run_v12b_layer(s, base, targets, local_backend=backend, permutations=6,
                   policy="conservative", work_dir=wd, resume=True)
    recs2 = (Path(wd) / "v12b_dynamic_records.jsonl").read_text().splitlines()
    assert len(recs2) == len(recs)
    assert backend.generate_calls == first_calls


def test_v13_writes_incremental_jsonl_and_one_layer_failure_isolated(tmp_path):
    class PartlyFailing(FakeLocalBackend):
        def generate_text(self, messages, *, max_new_tokens=None, temperature=0.0):
            text = "\n".join(m.get("content", "") for m in messages)
            if "ANSWER CONTENT" in text:
                raise RuntimeError("content failed")
            return super().generate_text(messages, max_new_tokens=max_new_tokens, temperature=temperature)

    backend = PartlyFailing()
    s = [{"qid": "m", "question": "Chọn phát biểu đúng về CSDL.",
          "choices": ["opt 0", "opt 1", "opt 2", "opt 3", "opt 4"]}]
    base = predict_base_answers(s, local_backend=backend)
    targets = select_v13_targets(s, base, max_qids=None)
    res = run_v13_layer(s, base, targets, local_backend=backend, work_dir=str(tmp_path / "w"))
    assert any(r.reason.startswith("local_error") for r in res)
    assert any(r.layer == "least_to_most" and r.proposed_answer == "B" for r in res)
    recs = (tmp_path / "w" / "v13_dynamic_records.jsonl").read_text().splitlines()
    assert recs and all(json.loads(l).get("qid") for l in recs)


def test_full_system_uses_one_shared_backend_instance(tmp_path):
    backend = FakeLocalBackend()
    samples = _samples(3)
    out = tmp_path / "pred.csv"
    report = run_fastmcq_system(samples, str(out), FastMCQSystemConfig(
        local_backend=backend, v12b_max_qids=1, v13_max_qids=1, work_dir=str(tmp_path / "w")))
    assert report.status == "PASS"
    assert report.output_count == len(samples)
    assert backend.predict_calls >= 1
    assert backend.generate_calls >= 1
