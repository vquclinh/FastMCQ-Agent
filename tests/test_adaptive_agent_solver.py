"""Tests for AdaptiveAgentSolver orchestration (no torch / no real model).

We bypass ``__init__`` (which would load a model) and inject fake scoring /
generation components, so the routing/confidence/fallback logic is tested in
isolation. Also checks the factory wiring and the gated-method guard.

Runnable with pytest, or standalone: ``python tests/test_adaptive_agent_solver.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_agent_solver import AdaptiveAgentSolver, AdaptiveConfig  # noqa: E402
from src.baseline_solver import AlwaysASolver  # noqa: E402
from src.solver_factory import SOLVER_NAMES, build_solver  # noqa: E402

FOUR = ["w", "x", "y", "z"]


class FakeScorer:
    """Returns a scripted result per score_mode."""

    def __init__(self, by_mode):
        self.by_mode = by_mode
        self.calls = []

    def score_sample(self, sample, score_mode=None):
        self.calls.append(score_mode)
        return self.by_mode[score_mode]


class FakeGen:
    def __init__(self, label):
        self.label = label
        self.calls = 0

    def predict_one(self, sample):
        self.calls += 1
        return self.label


class CaptureLogger:
    def __init__(self):
        self.events = []

    def record_event(self, rec):
        self.events.append(rec)


def _agent(cfg, scorer, gen=None, logger=None):
    a = object.__new__(AdaptiveAgentSolver)
    a.cfg = cfg
    a.scorer = scorer
    a.generate_fallback = gen
    a.logger = logger
    return a


def _result(best, margin, second=None, error=None):
    return {"label": best, "best_label": best, "second_label": second,
            "margin": margin, "score_mode": "x", "labels": FOUR,
            "scores": {}, "error": error}


def _sample(question="Thủ đô của Pháp là gì?", choices=FOUR):
    return {"qid": "q1", "question": question, "choices": choices}


def test_high_confidence_accept_no_fallback():
    scorer = FakeScorer({"label_plus_choice": _result("B", 0.5, "A")})
    agent = _agent(AdaptiveConfig(), scorer)
    assert agent.predict_one(_sample()) == "B"
    assert scorer.calls == ["label_plus_choice"]  # no fallback scoring


def test_low_margin_triggers_alternate_score_fallback():
    scorer = FakeScorer({
        "label_plus_choice": _result("A", 0.01, "B"),  # low margin
        "label_only": _result("C", 0.9, "A"),          # confident alternate
    })
    cfg = AdaptiveConfig(alternate_score_modes=["label_only"], max_fallbacks_per_sample=1)
    agent = _agent(cfg, scorer)
    assert agent.predict_one(_sample()) == "C"
    assert "label_only" in scorer.calls


def test_scoring_error_falls_back_to_generation():
    scorer = FakeScorer({"label_plus_choice": _result(None, None, error="boom")})
    cfg = AdaptiveConfig(alternate_score_modes=[], enable_generation_fallback=True,
                         max_fallbacks_per_sample=1)
    gen = FakeGen("D")
    agent = _agent(cfg, scorer, gen=gen)
    assert agent.predict_one(_sample()) == "D"
    assert gen.calls == 1


def test_final_answer_always_valid_label():
    scorer = FakeScorer({"label_plus_choice": _result(None, None, error="boom")})
    cfg = AdaptiveConfig(alternate_score_modes=[], enable_generation_fallback=True,
                         max_fallbacks_per_sample=1)
    gen = FakeGen("Z")  # invalid for a 4-choice question
    agent = _agent(cfg, scorer, gen=gen)
    assert agent.predict_one(_sample()) == "A"  # postprocess safety net


def test_logging_emits_required_fields():
    scorer = FakeScorer({"label_plus_choice": _result("B", 0.5, "A")})
    logger = CaptureLogger()
    agent = _agent(AdaptiveConfig(), scorer, logger=logger)
    agent.predict_one(_sample())
    assert len(logger.events) == 1
    rec = logger.events[0]
    for key in ("qid", "solver", "route", "profile_features", "num_choices",
                "question_length", "budget_tier", "strategy", "score_mode",
                "best_label", "second_label", "margin", "confidence_level",
                "fallback_used", "fallback_reason", "compressed_context_used",
                "compressed_context_stats", "duplicate_choice_groups",
                "elapsed_sec", "final_answer"):
        assert key in rec, f"missing log field {key}"
    assert rec["solver"] == "adaptive_agent"
    assert rec["final_answer"] == "B"


def test_gated_method_raises_not_implemented():
    # The gate runs before any model load, so no torch is needed.
    for flag in ("enable_self_consistency", "enable_pal_lite", "enable_debate",
                 "enable_tot_lite"):
        raised = False
        try:
            AdaptiveAgentSolver("/fake/model", config=AdaptiveConfig(**{flag: True}))
        except NotImplementedError:
            raised = True
        except Exception as exc:  # must be NotImplementedError, not a load error
            raised = False
            assert False, f"{flag}: expected NotImplementedError, got {type(exc).__name__}"
        assert raised, f"{flag} should raise NotImplementedError"


def test_factory_recognizes_adaptive_agent():
    assert "adaptive_agent" in SOLVER_NAMES
    raised = False
    try:
        build_solver("adaptive_agent", model_path=None)
    except ValueError as exc:
        raised = True
        assert "model-path" in str(exc) or "model_path" in str(exc)
    assert raised, "adaptive_agent without model_path should raise ValueError"


def test_default_solver_is_always_a():
    assert isinstance(build_solver("always_a"), AlwaysASolver)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
