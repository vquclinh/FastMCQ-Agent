"""Unit tests for Phase 1 per-choice scoring math, backend scoring, and config.

Deterministic fake logits/tokenizer only — no torch, weights, GPU, or network.
Observational: nothing here changes any answer or official output.
"""

from __future__ import annotations

import math

import pytest

from src.local_model.choice_scoring import ChoiceScoreResult, compute_choice_scores
from src.local_model.local_qwen_backend import LocalQwenBackend
from src.local_model.confidence_config import (
    ChoiceScoringConfig,
    load_choice_scoring_config,
)

ABCD = list("ABCD")
ABC = list("ABC")
AJ = list("ABCDEFGHIJ")


# --- pure scoring math ------------------------------------------------------
def test_four_choice_ranking_and_margins():
    r = compute_choice_scores({"A": -2.0, "B": -0.1, "C": -3.0, "D": -4.0}, ABCD)
    assert r.valid and r.top1_label == "B" and r.top2_label == "A"
    assert math.isclose(r.logit_margin, 1.9)
    assert math.isclose(sum(r.probabilities_by_label.values()), 1.0, abs_tol=1e-9)
    assert r.probability_margin > 0


def test_three_choice_scoring():
    r = compute_choice_scores({"A": -0.2, "B": -1.0, "C": -2.0}, ABC)
    assert r.valid and r.top1_label == "A" and r.top2_label == "B"
    assert set(r.probabilities_by_label) == {"A", "B", "C"}


def test_ten_choice_scoring():
    r = compute_choice_scores({c: -float(i) for i, c in enumerate(AJ)}, AJ)
    assert r.valid and r.top1_label == "A" and r.top2_label == "B"
    assert len(r.scores_by_label) == 10


def test_tie_is_deterministic_by_label_order():
    r = compute_choice_scores({"A": -1.0, "B": -1.0, "C": -5.0}, ABC)
    assert r.top1_label == "A" and r.top2_label == "B"
    assert r.logit_margin == 0.0 and abs(r.probability_margin) < 1e-12


def test_uniform_entropy_is_one_and_peaked_near_zero():
    uni = compute_choice_scores({k: 0.0 for k in ABCD}, ABCD)
    assert math.isclose(uni.normalized_entropy, 1.0, abs_tol=1e-9)
    peaked = compute_choice_scores({"A": 50.0, "B": -50.0, "C": -50.0, "D": -50.0}, ABCD)
    assert peaked.normalized_entropy < 1e-6


@pytest.mark.parametrize("scores,labels,why", [
    ({"A": -1.0}, ABCD, "missing"),
    ({"A": float("nan"), "B": -1.0, "C": -1.0, "D": -1.0}, ABCD, "nan"),
    ({"A": float("inf"), "B": -1.0, "C": -1.0, "D": -1.0}, ABCD, "inf"),
    ({}, [], "empty"),
])
def test_invalid_scores_return_invalid_result(scores, labels, why):
    r = compute_choice_scores(scores, labels)
    assert r.valid is False and r.top1_label is None and r.error


def test_single_label_entropy_zero_and_no_top2():
    r = compute_choice_scores({"A": -0.5}, ["A"])
    assert r.valid and r.top1_label == "A" and r.top2_label is None
    assert r.logit_margin is None and r.normalized_entropy == 0.0


def test_as_dict_is_json_safe_and_numeric_only():
    d = compute_choice_scores({"A": -2.0, "B": -0.1, "C": -3.0, "D": -4.0}, ABCD).as_dict()
    assert set(d) >= {"top1_label", "top2_label", "logit_margin", "probability_margin",
                      "normalized_entropy", "scoring_method", "valid", "error"}
    assert "question" not in d and "text" not in d
    import json
    json.loads(json.dumps(d))   # serializable


# --- backend scoring with fake tokenizer + fake logprob fn ------------------
class _FakeTok:
    """Prefix-consistent tokenizer: encode(a+b) == encode(a)+encode(b)."""
    def encode(self, text):
        return [ord(c) for c in text]


def _backend():
    b = LocalQwenBackend("/tmp/fake", device="cpu")
    b._model = object()        # bypass load()
    b._tokenizer = _FakeTok()
    return b


_SCORES = {"A": -2.0, "B": -0.1, "C": -3.0, "D": -4.0}
_ITEM = {"qid": "q1", "question": "Who?", "choices": ["w", "x", "y", "z"]}


def _fake_lp(prompt_ids, cont_ids):
    return [_SCORES[chr(cont_ids[-1])]]


def test_backend_multi_token_path():
    r = _backend().score_mcq_choices(_ITEM, logprob_fn=_fake_lp)   # prefix ' ' -> [space,label]
    assert r.scoring_method == "sequence_logprob"
    assert r.valid and r.top1_label == "B" and r.top2_label == "A"


def test_backend_single_token_path_equivalent():
    generic = _backend().score_mcq_choices(_ITEM, logprob_fn=_fake_lp)
    single = _backend().score_mcq_choices(_ITEM, canonical_prefix="", logprob_fn=_fake_lp)
    assert single.scoring_method == "single_token"
    assert generic.top1_label == single.top1_label == "B"
    assert generic.scores_by_label == single.scores_by_label   # equivalence


def test_backend_ten_choice():
    item = {"qid": "q", "question": "?", "choices": [f"o{i}" for i in range(10)]}
    scores = {c: -float(i) for i, c in enumerate(AJ)}
    r = _backend().score_mcq_choices(item, canonical_prefix="",
                                     logprob_fn=lambda p, c: [scores[chr(c[-1])]])
    assert r.valid and r.top1_label == "A" and len(r.scores_by_label) == 10


def test_backend_fails_closed_on_scorer_error():
    def boom(p, c):
        raise RuntimeError("synthetic")
    r = _backend().score_mcq_choices(_ITEM, logprob_fn=boom)
    assert r.valid is False and "RuntimeError" in r.error


def test_backend_no_choices_is_invalid():
    r = _backend().score_mcq_choices({"qid": "q", "question": "?", "choices": []},
                                     logprob_fn=_fake_lp)
    assert r.valid is False and r.error == "no_choices"


def test_generated_vs_scored_agreement_signal():
    r = _backend().score_mcq_choices(_ITEM, logprob_fn=_fake_lp)
    assert (r.top1_label == "B") is True            # generated 'B' would agree
    assert (r.top1_label == "A") is False           # generated 'A' would disagree


# --- config loader ----------------------------------------------------------
def test_config_defaults_when_source_none_and_no_file(monkeypatch):
    import src.local_model.confidence_config as cc
    monkeypatch.setattr(cc, "_DEFAULT_CONFIG_PATH", "does/not/exist.yaml")
    cfg = cc.load_choice_scoring_config()
    assert isinstance(cfg, ChoiceScoringConfig) and cfg.enabled and cfg.normalization == "softmax"


def test_config_from_repo_file_loads():
    cfg = load_choice_scoring_config("configs/confidence_selective.yaml")
    assert cfg.enabled is True and cfg.batch_size >= 1 and cfg.normalization == "softmax"


def test_config_from_dict_and_validation():
    cfg = load_choice_scoring_config({"choice_scoring": {"batch_size": 4, "enabled": False}})
    assert cfg.batch_size == 4 and cfg.enabled is False
    with pytest.raises(ValueError):
        load_choice_scoring_config({"choice_scoring": {"normalization": "argmax"}})
    with pytest.raises(ValueError):
        load_choice_scoring_config({"choice_scoring": {"batch_size": 0}})
    with pytest.raises(ValueError):
        load_choice_scoring_config({"choice_scoring": {"canonical_answer_prefix": 5}})


def test_config_missing_explicit_path_raises():
    with pytest.raises(FileNotFoundError):
        load_choice_scoring_config("configs/definitely_missing.yaml")
