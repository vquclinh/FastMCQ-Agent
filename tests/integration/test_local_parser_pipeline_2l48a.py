"""Integration: BTC single-pass and dynamic Base use the hardened answer parser
and reach the existing deterministic caller-level fallback on parse failure.

No torch, no weights, no network: a ScriptedBackend subclasses the real
LocalQwenBackend and only overrides generate_text, so the REAL predict_mcq +
REAL parse_mcq_label run. AUDIT 65.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from src.local_model.local_qwen_backend import LocalQwenBackend
from src.local_model.qwen_mcq_predictor import QwenMCQPredictor
from src.base.dynamic_base_predictor import predict_base_answers

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


class ScriptedBackend(LocalQwenBackend):
    """Real backend with a scripted generate_text (no model load)."""

    def __init__(self, reply):
        super().__init__("/tmp/fake-model", device="cpu")
        self._reply = reply
        self._model = object()      # bypass load()
        self._tokenizer = object()

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        return self._reply


_Q4 = {"qid": "q1", "question": "Who invented the telephone?",
       "choices": ["Edison", "Bell", "Tesla", "Marconi"]}
_Q10 = {"qid": "q2", "question": "Pick the term.",
        "choices": [f"opt{i}" for i in range(10)]}


# --- backend predict_mcq exercises the hardened parser ----------------------
def test_predict_mcq_prose_answer_is_B_not_A():
    assert ScriptedBackend("The answer is clearly option B.").predict_mcq(_Q4) == "B"


def test_predict_mcq_grace_hopper_is_none():
    assert ScriptedBackend("Grace Hopper").predict_mcq(_Q4) is None


def test_predict_mcq_json_supported():
    assert ScriptedBackend('{"answer":"C"}').predict_mcq(_Q4) == "C"


def test_predict_mcq_ten_choice_and_out_of_range():
    assert ScriptedBackend("Đáp án: J").predict_mcq(_Q10) == "J"
    assert ScriptedBackend("Đáp án: K").predict_mcq(_Q10) is None   # K not allowed


# --- (1) BTC single-pass path uses the hardened parser ----------------------
def test_btc_single_pass_uses_hardened_parser():
    p = QwenMCQPredictor("/tmp/fake")
    p._backend = ScriptedBackend("The answer is clearly option B.")
    assert p.predict_one(_Q4) == "B"


def test_btc_single_pass_grace_hopper_reaches_caller_fallback():
    p = QwenMCQPredictor("/tmp/fake")
    p._backend = ScriptedBackend("Grace Hopper")
    assert p.predict_one(_Q4) is None                    # parser fails (not G/A)
    # predict.py coerces None to the deterministic first-label fallback.
    spec = importlib.util.spec_from_file_location("predict_btc", _ROOT / "predict.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod._coerce_label(None, _Q4) == "A"


# --- (2) dynamic Base path uses the hardened parser -------------------------
def test_dynamic_base_prose_answer_is_B():
    backend = ScriptedBackend("The answer is clearly option B.")
    preds = predict_base_answers([_Q4], local_backend=backend)
    assert preds[0].answer == "B"
    assert preds[0].source == "dynamic_local_qwen"


def test_dynamic_base_grace_hopper_reaches_fallback():
    backend = ScriptedBackend("Grace Hopper")
    preds = predict_base_answers([_Q4], local_backend=backend)
    assert preds[0].source == "dynamic_fallback"          # parser failed -> caller fallback
    assert preds[0].answer == "A"                          # first valid label, not 'G'


def test_dynamic_base_out_of_range_reaches_fallback():
    backend = ScriptedBackend("Đáp án: K")                # K invalid for a 4-choice item
    preds = predict_base_answers([_Q4], local_backend=backend)
    assert preds[0].source == "dynamic_fallback"
    assert preds[0].answer == "A"
