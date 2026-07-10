"""Unit tests for Phase 1 per-choice scoring (corrected: one-forward bare-label
next-token logits), plus config wiring.

Deterministic fake tokenizer/logits only — no torch, weights, GPU, or network.
Observational: nothing here changes any answer or official output.
"""

from __future__ import annotations

import math

import pytest

from src.local_model.choice_scoring import ChoiceScoreResult, compute_choice_scores
from src.local_model.local_qwen_backend import LocalQwenBackend, build_mcq_prompt, _encode_ids
from src.local_model.confidence_config import (
    ChoiceScoringConfig,
    SCORING_METHOD,
    load_choice_scoring_config,
)

ABCD = list("ABCD")
ABC = list("ABC")
AJ = list("ABCDEFGHIJ")


# --- pure scoring math (score-agnostic; production feeds raw logits) --------
def test_four_choice_ranking_and_margins():
    r = compute_choice_scores({"A": 25.75, "B": 53.5, "C": 28.875, "D": 30.0}, ABCD)
    assert r.valid and r.top1_label == "B" and r.top2_label == "D"
    assert math.isclose(r.logit_margin, 23.5)                 # raw top1-top2 logit diff
    assert math.isclose(sum(r.probabilities_by_label.values()), 1.0, abs_tol=1e-9)
    assert r.probability_margin > 0


def test_three_choice_scoring():
    r = compute_choice_scores({"A": 2.0, "B": 1.0, "C": 0.0}, ABC)
    assert r.valid and r.top1_label == "A" and r.top2_label == "B"
    assert set(r.probabilities_by_label) == {"A", "B", "C"}


def test_ten_choice_scoring():
    r = compute_choice_scores({c: -float(i) for i, c in enumerate(AJ)}, AJ)
    assert r.valid and r.top1_label == "A" and r.top2_label == "B"
    assert len(r.scores_by_label) == 10


def test_tie_is_deterministic_by_label_order():
    r = compute_choice_scores({"A": 1.0, "B": 1.0, "C": -5.0}, ABC)
    assert r.top1_label == "A" and r.top2_label == "B"
    assert r.logit_margin == 0.0 and abs(r.probability_margin) < 1e-12


def test_uniform_entropy_is_one_and_peaked_near_zero():
    uni = compute_choice_scores({k: 0.0 for k in ABCD}, ABCD)
    assert math.isclose(uni.normalized_entropy, 1.0, abs_tol=1e-9)
    peaked = compute_choice_scores({"A": 50.0, "B": -50.0, "C": -50.0, "D": -50.0}, ABCD)
    assert peaked.normalized_entropy < 1e-6


@pytest.mark.parametrize("scores,labels", [
    ({"A": -1.0}, ABCD),
    ({"A": float("nan"), "B": -1.0, "C": -1.0, "D": -1.0}, ABCD),
    ({"A": float("inf"), "B": -1.0, "C": -1.0, "D": -1.0}, ABCD),
    ({}, []),
])
def test_invalid_scores_return_invalid_result(scores, labels):
    r = compute_choice_scores(scores, labels)
    assert r.valid is False and r.top1_label is None and r.error


def test_single_label_entropy_zero_and_no_top2():
    r = compute_choice_scores({"A": -0.5}, ["A"])
    assert r.valid and r.top1_label == "A" and r.top2_label is None
    assert r.logit_margin is None and r.normalized_entropy == 0.0


def test_as_dict_is_json_safe_and_numeric_only():
    d = compute_choice_scores({"A": 2.0, "B": 5.0, "C": 3.0, "D": 4.0}, ABCD).as_dict()
    assert set(d) >= {"top1_label", "top2_label", "logit_margin", "probability_margin",
                      "normalized_entropy", "scoring_method", "valid", "error"}
    assert "question" not in d and "text" not in d
    import json
    json.loads(json.dumps(d))


# --- backend scoring: one-forward, bare-label next-token logits -------------
class _Tok:
    """Fake tokenizer with DISTINCT bare vs space-prefixed label ids, so tests can
    prove the scorer reads the BARE ids. Bare 'A'..='J' -> ord(); ' A' -> 300+ord()."""
    def encode(self, text, add_special_tokens=True):
        out, i = [], 0
        while i < len(text):
            c = text[i]
            if c == " " and i + 1 < len(text) and text[i + 1] in "ABCDEFGHIJ":
                out.append(300 + ord(text[i + 1])); i += 2
            else:
                out.append(ord(c)); i += 1
        return out


def _backend(tok=None):
    b = LocalQwenBackend("/tmp/fake", device="cpu")
    b._model = object()
    b._tokenizer = tok or _Tok()
    return b


_ITEM = {"qid": "q1", "question": "What is 2 + 2?", "choices": ["3", "4", "5", "6"]}
_LOGITS = {ord("A"): 25.75, ord("B"): 53.5, ord("C"): 28.875, ord("D"): 30.0}


def _logits_fn(prompt_ids, token_ids):
    return [_LOGITS[t] for t in token_ids]


def test_backend_uses_bare_label_token_ids_not_space_prefixed():
    seen = {}
    def fn(prompt_ids, token_ids):
        seen["ids"] = list(token_ids)
        return [_LOGITS[t] for t in token_ids]
    r = _backend().score_mcq_choices(_ITEM, logits_fn=fn)
    assert r.valid and r.scoring_method == "next_token_logits_one_forward"
    assert seen["ids"] == [ord("A"), ord("B"), ord("C"), ord("D")]   # bare (65..68), not 365..


@pytest.mark.parametrize("nchoices", [3, 4, 10])
def test_backend_exactly_one_forward_per_item(nchoices):
    item = {"qid": "q", "question": "?", "choices": [f"o{i}" for i in range(nchoices)]}
    calls = {"n": 0}
    def fn(prompt_ids, token_ids):
        calls["n"] += 1
        return [float(-i) for i in range(len(token_ids))]
    r = _backend().score_mcq_choices(item, logits_fn=fn)
    assert r.valid and calls["n"] == 1                       # ONE forward, regardless of #labels


def test_backend_top1_top2_and_raw_logit_margin():
    r = _backend().score_mcq_choices(_ITEM, logits_fn=_logits_fn)
    assert r.top1_label == "B" and r.top2_label == "D"
    assert math.isclose(r.logit_margin, 53.5 - 30.0)         # raw top1-top2 logit diff
    assert r.scores_by_label["B"] == 53.5                    # raw logit stored


def test_backend_softmax_over_valid_labels_and_prob_margin_entropy():
    r = _backend().score_mcq_choices(_ITEM, logits_fn=_logits_fn)
    assert math.isclose(sum(r.probabilities_by_label.values()), 1.0, abs_tol=1e-9)
    assert r.probability_margin == r.probabilities_by_label["B"] - r.probabilities_by_label["D"]
    assert 0.0 <= r.normalized_entropy <= 1.0


def test_backend_agrees_with_greedy_argmax_first_token():
    # Greedy generation picks the argmax next token = the bare label with the highest logit.
    argmax_label = max("ABCD", key=lambda lab: _LOGITS[ord(lab)])
    r = _backend().score_mcq_choices(_ITEM, logits_fn=_logits_fn)
    assert r.top1_label == argmax_label == "B"


def test_backend_prompt_prefix_equals_generation_render():
    b = _backend()
    prefix = b._generation_prefix(_ITEM)
    assert prefix == b._render_prompt([{"role": "user", "content": build_mcq_prompt(_ITEM)[0]}])
    captured = {}
    def fn(prompt_ids, token_ids):
        captured["ids"] = list(prompt_ids)
        return [_LOGITS[t] for t in token_ids]
    b.score_mcq_choices(_ITEM, logits_fn=fn)
    assert captured["ids"] == _encode_ids(b._tokenizer, prefix)   # same tokens generation would see


# --- fail-closed cases ------------------------------------------------------
def test_multi_token_label_fails_closed():
    class TokMulti(_Tok):
        def encode(self, text, add_special_tokens=True):
            if text == "B":
                return [ord("B"), 999]
            return super().encode(text, add_special_tokens)
    r = _backend(TokMulti()).score_mcq_choices(_ITEM, logits_fn=_logits_fn)
    assert r.valid is False and r.error == "label_not_single_token:B"


def test_duplicate_label_token_ids_fail_closed():
    class TokDup(_Tok):
        def encode(self, text, add_special_tokens=True):
            if text in ("A", "B", "C", "D"):
                return [777]
            return super().encode(text, add_special_tokens)
    r = _backend(TokDup()).score_mcq_choices(_ITEM, logits_fn=_logits_fn)
    assert r.valid is False and r.error == "duplicate_label_token_ids"


def test_nonfinite_logits_fail_closed():
    r = _backend().score_mcq_choices(_ITEM, logits_fn=lambda p, t: [float("nan")] * len(t))
    assert r.valid is False and r.error


def test_forward_exception_fails_closed():
    def boom(p, t):
        raise RuntimeError("synthetic")
    r = _backend().score_mcq_choices(_ITEM, logits_fn=boom)
    assert r.valid is False and "RuntimeError" in r.error


def test_invalid_logit_shape_fails_closed():
    r = _backend().score_mcq_choices(_ITEM, logits_fn=lambda p, t: [1.0])   # wrong length
    assert r.valid is False and r.error == "logits_shape_invalid"


def test_single_and_zero_choice_fail_closed():
    b = _backend()
    assert b.score_mcq_choices({"qid": "q", "question": "?", "choices": ["x"]},
                               logits_fn=_logits_fn).error == "need_at_least_two_labels"
    assert b.score_mcq_choices({"qid": "q", "question": "?", "choices": []},
                               logits_fn=_logits_fn).error == "no_choices"


# --- config loader ----------------------------------------------------------
def test_config_defaults_when_source_none_and_no_file(monkeypatch):
    import src.local_model.confidence_config as cc
    monkeypatch.setattr(cc, "_DEFAULT_CONFIG_PATH", "does/not/exist.yaml")
    cfg = cc.load_choice_scoring_config()
    assert isinstance(cfg, ChoiceScoringConfig) and cfg.enabled and cfg.normalization == "softmax"


def test_config_from_repo_file_loads():
    cfg = load_choice_scoring_config("configs/confidence_selective.yaml")
    assert cfg.enabled is True and cfg.batch_size >= 1 and cfg.normalization == "softmax"


def test_config_scoring_method_is_next_token_and_prefix_ignored():
    cfg = load_choice_scoring_config({"choice_scoring": {"batch_size": 4, "enabled": False}})
    assert cfg.batch_size == 4 and cfg.enabled is False
    assert cfg.scoring_method == SCORING_METHOD == "next_token_logits_one_forward"
    # a deprecated canonical_answer_prefix in an old config is accepted and ignored (no error)
    cfg2 = load_choice_scoring_config({"choice_scoring": {"canonical_answer_prefix": " "}})
    assert not hasattr(cfg2, "canonical_answer_prefix")


def test_config_validation_errors():
    with pytest.raises(ValueError):
        load_choice_scoring_config({"choice_scoring": {"normalization": "argmax"}})
    with pytest.raises(ValueError):
        load_choice_scoring_config({"choice_scoring": {"batch_size": 0}})


def test_config_missing_explicit_path_raises():
    with pytest.raises(FileNotFoundError):
        load_choice_scoring_config("configs/definitely_missing.yaml")
