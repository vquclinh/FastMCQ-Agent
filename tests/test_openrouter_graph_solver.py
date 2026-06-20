"""Tests for the OpenRouter graph solver using a fake client (no live API).

Runnable with pytest, or standalone:
``python tests/test_openrouter_graph_solver.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.openrouter_client import ChatResult  # noqa: E402
from src.openrouter_graph_solver import OpenRouterConfig, OpenRouterGraphSolver  # noqa: E402
from src.solver_factory import SOLVER_NAMES, build_solver  # noqa: E402

ABCD = ["w", "x", "y", "z"]


class FakeClient:
    """Returns scripted contents in sequence (repeats the last when exhausted)."""

    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0
        self.model = "qwen/qwen3.5-9b"

    def chat(self, messages, *, response_format=None, temperature=None, max_tokens=None):
        c = self.contents[min(self.calls, len(self.contents) - 1)]
        self.calls += 1
        return ChatResult(content=c, model=self.model, response_id="fake")


class CaptureLogger:
    def __init__(self):
        self.events = []

    def record_event(self, rec):
        self.events.append(rec)


def _sample(question="Thủ đô của Pháp là gì?", choices=ABCD, qid="q1"):
    return {"qid": qid, "question": question, "choices": choices}


def test_valid_answer_accepted():
    client = FakeClient(['{"answer": "B", "confidence": 0.95}'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    assert solver.predict_one(_sample()) == "B"
    assert client.calls == 1  # no repair needed


def test_invalid_then_repair():
    client = FakeClient(['{"answer": "Z"}',                 # invalid label
                         '{"answer": "C", "confidence": 0.9}'])  # repair
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(enable_repair=True), client=client)
    assert solver.predict_one(_sample()) == "C"
    assert client.calls == 2


def test_final_answer_always_valid():
    client = FakeClient(["totally not json", "still not json"])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    out = solver.predict_one(_sample())
    assert out in ["A", "B", "C", "D"]  # valid label sized to 4 choices
    assert out == "A"  # safe fallback


def test_self_consistency_off_by_default():
    client = FakeClient(['{"answer": "B", "confidence": 0.95}'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    solver.predict_one(_sample())
    # high confidence + default config => no extra sampling calls
    assert client.calls == 1


def test_self_consistency_gated_on_low_confidence():
    # First answer is low-confidence -> triggers gated self-consistency vote.
    client = FakeClient([
        '{"answer": "A", "confidence": 0.1}',  # primary (low conf, valid)
        '{"answer": "D"}', '{"answer": "D"}', '{"answer": "B"}',  # 3 SC votes
    ])
    cfg = OpenRouterConfig(enable_self_consistency=True, self_consistency_k=3,
                           low_confidence_threshold=0.5)
    solver = OpenRouterGraphSolver(config=cfg, client=client)
    assert solver.predict_one(_sample()) == "D"  # majority vote
    assert client.calls == 4


def test_dynamic_labels_ten_choices():
    client = FakeClient(['{"answer": "J"}'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    sample = _sample(question="Một bài toán?", choices=[f"opt{i}" for i in range(10)])
    assert solver.predict_one(sample) == "J"


def test_logging_excludes_sample_and_has_trace():
    client = FakeClient(['{"answer": "B", "confidence": 0.9}'])
    logger = CaptureLogger()
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client, logger=logger)
    solver.predict_one(_sample())
    assert len(logger.events) == 1
    rec = logger.events[0]
    assert "_sample" not in rec            # raw sample never logged
    assert rec["solver"] == "openrouter_graph"
    for key in ("qid", "route", "final_answer", "confidence", "repair_used",
                "self_consistency_used", "elapsed_sec", "raw_response"):
        assert key in rec, f"missing trace field {key}"
    assert rec["final_answer"] == "B"


def test_speed_normal_path_one_call():
    # A valid first answer must cost exactly ONE API call (speed policy).
    client = FakeClient(['{"answer": "B", "confidence": 0.95}'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    solver.predict_one(_sample())
    assert client.calls == 1


def test_speed_needs_review_does_not_force_repair_by_default():
    # Model self-flags needs_review but the label is valid -> still ONE call,
    # because repair_only_on_invalid is the default.
    client = FakeClient(['{"answer": "B", "confidence": 0.4, "needs_review": true}'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client)
    assert solver.predict_one(_sample()) == "B"
    assert client.calls == 1


def test_speed_repair_path_at_most_two_calls():
    client = FakeClient(['not json', '{"answer": "C"}'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(enable_repair=True), client=client)
    solver.predict_one(_sample())
    assert client.calls <= 2
    assert client.calls == 2  # one answer + one repair


def test_speed_repair_capped_by_budget():
    # Even if both responses are invalid, repair fires at most once (cap = 2).
    client = FakeClient(['nope', 'still nope', 'and again'])
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(enable_repair=True), client=client)
    out = solver.predict_one(_sample())
    assert client.calls == 2          # answer + single repair, no more
    assert out == "A"                 # safe fallback


def test_thorough_mode_repairs_flagged_answer():
    # With repair_only_on_invalid=False, a needs_review valid answer DOES repair.
    client = FakeClient(['{"answer": "B", "needs_review": true}', '{"answer": "C"}'])
    cfg = OpenRouterConfig(repair_only_on_invalid=False, enable_repair=True)
    solver = OpenRouterGraphSolver(config=cfg, client=client)
    solver.predict_one(_sample())
    assert client.calls == 2


def test_api_calls_logged():
    client = FakeClient(['{"answer": "B"}'])
    logger = CaptureLogger()
    solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client, logger=logger)
    solver.predict_one(_sample())
    assert logger.events[0]["api_calls"] == 1


def test_no_api_key_in_logs():
    # Even with a key in env, the logged trace must not contain it.
    os.environ["OPENROUTER_API_KEY"] = "sk-or-SECRETVALUE123"
    try:
        client = FakeClient(['{"answer": "B"}'])
        logger = CaptureLogger()
        solver = OpenRouterGraphSolver(config=OpenRouterConfig(), client=client, logger=logger)
        solver.predict_one(_sample())
        blob = repr(logger.events[0])
        assert "sk-or-SECRETVALUE123" not in blob
        assert "SECRET" not in blob
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_factory_registers_openrouter_graph():
    assert "openrouter_graph" in SOLVER_NAMES


def test_factory_without_key_raises():
    # Hermetic "no key": force api_key_available False (a real .env may exist).
    import src.openrouter_client as oc
    saved = os.environ.pop("OPENROUTER_API_KEY", None)
    orig = oc.api_key_available
    oc.api_key_available = lambda: False
    try:
        raised = False
        try:
            build_solver("openrouter_graph")
        except ValueError as exc:
            raised = True
            assert "OPENROUTER_API_KEY" in str(exc)
        assert raised
    finally:
        oc.api_key_available = orig
        if saved is not None:
            os.environ["OPENROUTER_API_KEY"] = saved


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
