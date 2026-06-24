"""Dynamic base predictor (Phase 2L.36B).

Produces one valid label for EVERY input sample using the repo's deterministic solvers — works
for ARBITRARY qids (public, private, unseen) and never references a public frozen CSV or any
qid-specific answer artifact.

No-API mode: route + deterministic formula/concept/calculation bank (``solve_formula_bank_sample``);
unresolved questions get a conservative fallback to a valid label, marked weak/high-risk.
Execute-API mode: unresolved questions may additionally be sent to the allowed model (guarded by
``assert_allowed_llm_model``) for a single-label answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.labels import labels_for, is_valid_label
from src.solvers.formula_bank_solver import solve_formula_bank_sample

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


def _api_answer(sample, labels, client):
    """One guarded model call returning a valid label, or None on any problem."""
    opts = "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, sample.get("choices") or []))
    messages = [
        {"role": "system", "content":
            "Answer the multiple-choice question. Respond with a SINGLE JSON object only: "
            '{"answer": "<one option letter>"}. No prose.'},
        {"role": "user", "content": f"Question:\n{sample.get('question','')}\n\nOptions:\n{opts}\n\nJSON:"},
    ]
    try:
        content, _usage = client.chat(messages)
        parsed = client.parse_json(content) or {}
        ans = str(parsed.get("answer") or "").strip().upper()[:1]
        return ans if ans in labels else None
    except Exception:
        return None


def predict_base_answers(samples, *, model=None, execute_api=False, budget_usd=None,
                         work_dir=None, resume=False):
    client = None
    if execute_api:
        from src.api.model_policy import assert_allowed_llm_model
        assert_allowed_llm_model(model)
        from src.api.selective_api_client import SelectiveAPIClient
        client = SelectiveAPIClient(model=model)

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
            elif execute_api and client is not None and (_a := _api_answer(s, labels, client)):
                pred = BasePrediction(qid, _a, "dynamic_api", 0.6, route,
                                      "single_source_model", {"model": model})
            else:
                # Conservative fallback — valid label, explicitly weak/high-risk.
                pred = BasePrediction(qid, _fallback_label(labels), "dynamic_fallback", None, route,
                                      "no_deterministic_solver;weak"
                                      + (";no_api" if not execute_api else ";api_unparsed"), {})
        preds.append(pred)
        cat = ("formula_bank" if pred.source.startswith("formula_bank")
               else "api" if pred.source == "dynamic_api" else "fallback")
        _log(f"[BASE] {i}/{n} qid={qid} source={cat}")
    return preds


def base_prediction_is_valid(pred: BasePrediction, sample: dict) -> bool:
    choices = sample.get("choices") or []
    if not choices:
        return pred.answer in _GLOBAL_LABELS
    return is_valid_label(pred.answer, sample)
