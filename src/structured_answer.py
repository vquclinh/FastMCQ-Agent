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
# Explicit answer-key recovery: matches `"answer": "C"`, `'answer': C`, `answer: C`
# — the labelled field, NOT a random standalone letter. Used only when full JSON
# parsing fails (e.g. the trailing evidence truncated the object).
_ANSWER_KEY_RE = re.compile(r"""['"]?answer['"]?\s*:\s*['"]?\s*([A-Za-z])\b""", re.IGNORECASE)
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


def _recover_answer_key(text: str, valid_labels: list[str]) -> str | None:
    """Recover an explicit ``"answer": "X"`` label from partial/broken JSON.

    Only matches the *labelled* answer field (not a random standalone letter or a
    letter inside evidence), and validates it against ``valid_labels``.
    """
    valid = {l.upper(): l for l in valid_labels}
    m = _ANSWER_KEY_RE.search(text or "")
    if m:
        cand = m.group(1).upper()
        if cand in valid:
            return valid[cand]
    return None


def parse_structured_answer(text: str, valid_labels: list[str]) -> StructuredAnswer:
    """Parse model output into a validated :class:`StructuredAnswer`.

    Order (success quality decreasing):
      1-3. full JSON (strict / fenced / embedded) with a valid ``answer``
      4.   explicit answer-key recovery from partial JSON (degraded; needs_review)
      5.   failure (ok=False) — caller falls back to the safe default label.

    We deliberately do NOT recover from the first standalone letter in free text
    or from letters inside evidence — that is unreliable and not counted a success.
    """
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

    # 4) Explicit answer-key recovery (partial JSON / truncated evidence).
    recovered = _recover_answer_key(text, valid_labels)
    if recovered is not None:
        return StructuredAnswer(
            answer=recovered, confidence=0.0, evidence="",
            reason_type="other", needs_review=True, ok=True,
            source="partial_answer_key",
            error=("json_answer_invalid" if obj is not None else "no_json"),
        )

    # 5) No reliable answer → failure; the graph falls back to the safe default.
    return StructuredAnswer(answer=None, ok=False,
                            source=(source if obj is not None else "none"),
                            needs_review=True,
                            error=("json_answer_invalid" if obj is not None else "unparseable"))


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
                    # answer first + short; evidence capped so verbose derivations
                    # cannot truncate the JSON (Phase 2K.2 correctness fix).
                    "answer": {"type": "string", "maxLength": 4},
                    "confidence": {"type": "number"},
                    "reason_type": {"type": "string"},
                    "needs_review": {"type": "boolean"},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 120},
                        "maxItems": 2,
                    },
                },
                "required": ["answer"],
            },
        },
    }
