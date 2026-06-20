"""Selective second-pass MCQ verifier + option elimination.

Given the question/evidence actually used, the choices, and the original answer,
the verifier asks the model to briefly assess each option and decide whether the
original answer is supported or another option is clearly better. It runs **only
on hard/uncertain cases** (see :func:`should_run_verifier`) and is **off by
default**, so existing behavior is unchanged unless explicitly enabled.

Robustness/safety: structured JSON only (no hidden chain-of-thought is requested
or logged), reasons are short and evidence-focused, the verified answer is always
validated against the available labels, and on any uncertainty/failure the
original answer is kept. No qid logic, no answer tables, no `eval`/`exec`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .labels import labels_for
from .openrouter_prompts import format_choices
# Reuse the robust JSON extraction + helpers from the answer parser.
from .structured_answer import _clamp_conf, _extract_json, _normalize_label

_STATUSES = ("supported", "contradicted", "irrelevant", "uncertain")
_MAX_REASON = 160


@dataclass
class OptionAssessment:
    label: str
    status: str
    confidence: float
    brief_reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationResult:
    verified_answer: str | None
    should_override: bool
    confidence: float
    method: str                       # parse source: json | embedded | none
    assessments: list
    original_answer: str | None
    disagreement: bool
    rationale: str
    error: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["assessments"] = [a.to_dict() for a in self.assessments]
        return d


# --- prompt ------------------------------------------------------------------

_SYSTEM = (
    "Bạn là người kiểm tra đáp án trắc nghiệm cẩn thận. Nhiệm vụ: đánh giá ngắn gọn "
    "từng lựa chọn dựa trên câu hỏi/đoạn thông tin đã cho, xác định đáp án ban đầu có "
    "được hỗ trợ hay không, và CHỈ đổi đáp án nếu một lựa chọn khác rõ ràng đúng hơn.\n"
    "Chỉ in ra MỘT đối tượng JSON hợp lệ, KHÔNG markdown, KHÔNG suy luận dài, theo schema:\n"
    '{{"original_answer_supported": <true|false>, "best_answer": "<NHÃN>", '
    '"should_override": <true|false>, "confidence": <0..1>, '
    '"option_assessments": [{{"label":"A","status":"supported|contradicted|irrelevant|uncertain",'
    '"confidence":<0..1>,"reason":"<ngắn gọn>"}}], "rationale":"<ngắn gọn>"}}\n'
    '"best_answer" PHẢI là đúng một trong các nhãn: {labels}. Mỗi "reason" tối đa ~120 ký tự, '
    "chỉ nêu bằng chứng, không giải thích dài. Nếu không chắc, đặt should_override=false."
)


def build_verifier_messages(route: str, question_text: str, choices: list,
                            original_answer: str | None, *, calc_meta: dict | None = None,
                            evidence_diag: dict | None = None) -> list:
    """Build chat messages for the verifier (JSON-only output)."""
    labels = labels_for(len(choices or []))
    hints = []
    if calc_meta and calc_meta.get("method") and calc_meta.get("method") != "none":
        hints.append(f"Gợi ý công thức (tham khảo, có thể sai): {calc_meta.get('method')}.")
    if evidence_diag and evidence_diag.get("method") == "evidence_reranker":
        hints.append("Bằng chứng đã được chọn lọc từ đoạn văn; có thể chưa đầy đủ.")
    hint_text = ("\n" + " ".join(hints)) if hints else ""
    user = (
        f"Câu hỏi / đoạn thông tin:\n{question_text}\n\n"
        f"Các lựa chọn:\n{format_choices(choices or [])}\n\n"
        f"Đáp án ban đầu: {original_answer}{hint_text}\n\n"
        f"Hãy đánh giá từng lựa chọn trong [{', '.join(labels)}] và trả về JSON theo schema."
    )
    return [{"role": "system", "content": _SYSTEM.format(labels=", ".join(labels))},
            {"role": "user", "content": user}]


def verifier_response_format_schema() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "mcq_verification", "strict": False,
            "schema": {
                "type": "object",
                "properties": {
                    "original_answer_supported": {"type": "boolean"},
                    "best_answer": {"type": "string", "maxLength": 4},
                    "should_override": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "option_assessments": {
                        "type": "array",
                        "items": {"type": "object", "properties": {
                            "label": {"type": "string", "maxLength": 4},
                            "status": {"type": "string"},
                            "confidence": {"type": "number"},
                            "reason": {"type": "string", "maxLength": 160},
                        }},
                    },
                    "rationale": {"type": "string", "maxLength": 200},
                },
                "required": ["best_answer", "should_override"],
            },
        },
    }


# --- parser ------------------------------------------------------------------

def parse_verification(text: str, valid_labels: list, original_answer: str | None) -> VerificationResult:
    """Parse verifier output into a validated :class:`VerificationResult`.

    The returned ``should_override`` is the model's intent AND a valid, different
    label; the caller still applies the confidence threshold before overriding.
    """
    obj, source = _extract_json(text)
    if obj is None:
        return VerificationResult(None, False, 0.0, "none", [], original_answer,
                                  False, "", error="unparseable")

    best = _normalize_label(obj.get("best_answer"), valid_labels)
    conf = _clamp_conf(obj.get("confidence", 0.0))
    want_override = bool(obj.get("should_override", False))

    assessments = []
    raw = obj.get("option_assessments") or []
    if isinstance(raw, list):
        for item in raw[: len(valid_labels)]:
            if not isinstance(item, dict):
                continue
            lbl = _normalize_label(item.get("label"), valid_labels)
            if lbl is None:
                continue
            status = str(item.get("status", "uncertain")).strip().lower()
            assessments.append(OptionAssessment(
                label=lbl,
                status=status if status in _STATUSES else "uncertain",
                confidence=_clamp_conf(item.get("confidence", 0.0)),
                brief_reason=str(item.get("reason", "")).strip()[:_MAX_REASON]))

    disagreement = best is not None and original_answer is not None and best != original_answer
    # Only call it an override if a valid, different label is proposed.
    should_override = bool(want_override and best is not None and disagreement)
    return VerificationResult(
        verified_answer=best, should_override=should_override, confidence=conf,
        method=source, assessments=assessments, original_answer=original_answer,
        disagreement=disagreement,
        rationale=str(obj.get("rationale", "")).strip()[:200], error=None)


# --- selective trigger -------------------------------------------------------

def should_run_verifier(state: dict, config) -> tuple:
    """Decide whether the verifier should run for this sample. (bool, reason)."""
    if not getattr(config, "mcq_verifier_enabled", False):
        return False, "disabled"
    # Never touch a deterministic calculation override.
    if str(state.get("strategy") or "").startswith("calculation_override"):
        return False, "calc_override"
    if not state.get("final_answer"):
        return False, "no_valid_answer"   # let normal repair handle it first
    route = state.get("route")
    if route not in getattr(config, "mcq_verifier_apply_routes", ()):
        return False, "route_not_in_scope"

    reasons = []
    parsed = state.get("parsed_answer") or {}
    conf = state.get("confidence") or 0.0
    if config.mcq_verifier_trigger_on_partial_parse and parsed.get("source") == "partial_answer_key":
        reasons.append("partial_parse")
    if conf < config.mcq_verifier_trigger_below_confidence:
        reasons.append("low_confidence")
    if config.mcq_verifier_trigger_on_repair and state.get("repair_used"):
        reasons.append("repair")
    if (config.mcq_verifier_trigger_on_reranked_long_context and route == "long_context"
            and state.get("evidence_reranker_enabled") and not state.get("evidence_fallback_used")):
        reasons.append("reranked_long_context")
    if reasons:
        return True, "+".join(reasons)
    return False, "no_trigger"
