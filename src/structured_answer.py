"""Structured-output schema + robust parser for the OpenRouter graph solver.

The model is asked to return strict JSON with these fields:
  * ``answer``      — the chosen label (must be one of the available labels)
  * ``confidence``  — float in [0, 1]
  * ``evidence``    — short supporting evidence (string or list[str])
  * ``reason_type`` — e.g. "lookup", "calculation", "reading", "elimination"
  * ``needs_review``— bool

Parsing is defensive: it accepts strict JSON, JSON inside ```fences```, or a
JSON object embedded in surrounding text, and it validates the label against the
sample's actual labels. On failure it falls back to the existing single-label
parser, and finally to a structured failure the caller can default to ``A``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from .output_parser import parse_answer_label

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
REASON_TYPES = ("lookup", "reading", "calculation", "elimination", "other")


@dataclass
class StructuredAnswer:
    answer: str | None
    confidence: float = 0.0
    evidence: object = ""
    reason_type: str = "other"
    needs_review: bool = False
    ok: bool = False              # True iff answer is a valid label
    source: str = "json"          # json | json_in_fence | embedded | label_fallback | none
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _clamp_conf(value) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))


def _extract_json(text: str):
    """Return a dict parsed from strict JSON / fenced JSON / embedded object."""
    text = (text or "").strip()
    if not text:
        return None, "empty"
    # 1) strict
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, "json"
    except json.JSONDecodeError:
        pass
    # 2) fenced ```json { ... } ```
    m = _FENCE_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj, "json_in_fence"
        except json.JSONDecodeError:
            pass
    # 3) first {...} block anywhere
    m = _OBJ_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj, "embedded"
        except json.JSONDecodeError:
            pass
    return None, "unparseable"


def _normalize_label(raw, valid_labels: list[str]) -> str | None:
    """Map a raw answer value to a valid label, or None."""
    if raw is None:
        return None
    valid = {l.upper(): l for l in valid_labels}
    s = str(raw).strip()
    # Direct single-letter label.
    if s.upper() in valid:
        return valid[s.upper()]
    # e.g. "A." / "(A)" / "Answer: B" — reuse the robust single-label parser.
    return parse_answer_label(s, valid_labels)


def parse_structured_answer(text: str, valid_labels: list[str]) -> StructuredAnswer:
    """Parse model output into a validated :class:`StructuredAnswer`."""
    obj, source = _extract_json(text)

    if obj is not None:
        label = _normalize_label(obj.get("answer"), valid_labels)
        if label is not None:
            reason = str(obj.get("reason_type", "other")).strip().lower() or "other"
            return StructuredAnswer(
                answer=label,
                confidence=_clamp_conf(obj.get("confidence", 0.0)),
                evidence=obj.get("evidence", ""),
                reason_type=reason if reason in REASON_TYPES else "other",
                needs_review=bool(obj.get("needs_review", False)),
                ok=True, source=source, error=None,
            )
        # JSON parsed but answer label invalid/missing → try whole-text fallback.
        fallback = parse_answer_label(text, valid_labels)
        if fallback is not None:
            return StructuredAnswer(answer=fallback, confidence=0.0, evidence="",
                                    reason_type="other", needs_review=True,
                                    ok=True, source="label_fallback",
                                    error="json_answer_invalid")
        return StructuredAnswer(answer=None, ok=False, source=source,
                                needs_review=True, error="json_answer_invalid")

    # No JSON at all → last-ditch single-label parse over the raw text.
    fallback = parse_answer_label(text, valid_labels)
    if fallback is not None:
        return StructuredAnswer(answer=fallback, confidence=0.0, evidence="",
                                reason_type="other", needs_review=True,
                                ok=True, source="label_fallback",
                                error="no_json")
    return StructuredAnswer(answer=None, ok=False, source="none",
                            needs_review=True, error="unparseable")


# JSON schema usable as an OpenRouter response_format (json_schema) hint.
def response_format_schema() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "mcq_answer",
            "strict": False,
            "schema": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                    "reason_type": {"type": "string"},
                    "needs_review": {"type": "boolean"},
                },
                "required": ["answer"],
            },
        },
    }
