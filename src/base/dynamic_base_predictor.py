"""Dynamic base predictor.

Produces one valid label for every input sample using deterministic solvers first and the shared
local Qwen backend for unresolved questions. It works for arbitrary qids and never references a
public frozen CSV or qid-specific answer artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.labels import labels_for, is_valid_label
from src.solvers.formula_bank_solver import solve_formula_bank_sample
from src.local_model.local_qwen_backend import get_local_qwen_backend

try:
    from src.layers.question_router import route_question
except Exception:  # pragma: no cover - router optional
    route_question = None

def _log(msg):
    print(msg, flush=True)


# Global label space used only when a sample carries no choices (qid-only CSV).
_GLOBAL_LABELS = list("ABCDEFGHIJK")


@dataclass
class BasePrediction:
    qid: str
    answer: str
    source: str
    confidence: float | None
    route: str
    risk_reason: str
    metadata: dict = field(default_factory=dict)


def _route(sample) -> str:
    if route_question is None:
        return ""
    try:
        return route_question(sample).route or ""
    except Exception:
        return ""


def _fallback_label(labels):
    return labels[0] if labels else "A"


def _local_answer(sample, labels, backend, *, max_new_tokens):
    """One local model call returning a valid label, or None on any problem."""
    try:
        ans = backend.predict_mcq(sample, max_new_tokens=max_new_tokens)
        ans = str(ans or "").strip().upper()[:1]
        return ans if ans in labels else None
    except Exception:
        return None


def predict_base_answers(samples, *, model_path=None, local_backend=None, max_new_tokens=64,
                         work_dir=None, resume=False):
    backend = local_backend or get_local_qwen_backend(model_path, default_max_new_tokens=max_new_tokens)
    preds = []
    n = len(samples)
    for i, s in enumerate(samples, start=1):
        qid = s.get("qid")
        choices = s.get("choices") or []
        labels = labels_for(len(choices)) if choices else []
        route = _route(s)

        if not choices:
            pred = BasePrediction(qid, _fallback_label(_GLOBAL_LABELS),
                                  "dynamic_fallback_nochoices", None, route, "no_choices;weak", {})
        else:
            fb = solve_formula_bank_sample(s)
            if fb is not None and fb.selected_answer in labels:
                pred = BasePrediction(qid, fb.selected_answer, f"formula_bank:{fb.rule_id}",
                                      float(fb.confidence), route, "deterministic_match",
                                      {"matched_option_text": fb.matched_option_text})
            elif (_a := _local_answer(s, labels, backend, max_new_tokens=max_new_tokens)):
                pred = BasePrediction(qid, _a, "dynamic_local_qwen", 0.6, route,
                                      "single_source_local_model", {"model_path": model_path})
            else:
                # Conservative fallback: valid label, explicitly weak/high-risk.
                pred = BasePrediction(qid, _fallback_label(labels), "dynamic_fallback", None, route,
                                      "local_model_unparsed;weak", {})
        preds.append(pred)
        cat = ("formula_bank" if pred.source.startswith("formula_bank")
               else "local_qwen" if pred.source == "dynamic_local_qwen" else "fallback")
        _log(f"[BASE] {i}/{n} qid={qid} source={cat}")
    return preds


def base_prediction_is_valid(pred: BasePrediction, sample: dict) -> bool:
    choices = sample.get("choices") or []
    if not choices:
        return pred.answer in _GLOBAL_LABELS
    return is_valid_label(pred.answer, sample)
