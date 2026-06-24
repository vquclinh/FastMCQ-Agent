"""Candidate answer/evidence consistency guard (Phase 2L.26B).

API/model agents sometimes return a label that contradicts their own evidence (e.g.
evidence derives q=6 but the selected option is q=4). This module detects placeholder
evidence and numeric answer/evidence mismatches so the ranker can reject or downgrade
such candidates. Pure functions — no network, no qid logic, no answer table.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
# Strong final numeric claim: the number after the LAST '=' (or 'q = N').
_EQ_NUM_RE = re.compile(r"=\s*\(?\s*([-+]?\d+(?:[.,]\d+)?)\s*\)?")

_PLACEHOLDER_EXACT = {"", "r", "x", "n/a", "na", "none", "tbd", "...", "-", "evidence",
                      "some evidence", "no evidence", "bằng chứng", "không có",
                      "rationale", "reason", "lý do"}
_DETERMINISTIC_PREFIXES = ("tool:", "formula_bank", "concept", "calc:")


@dataclass
class ConsistencyRecord:
    ok: bool
    severity: str            # "ok" | "placeholder" | "numeric_mismatch"
    reason: str
    detected_claims: list = field(default_factory=list)
    option_values: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _to_float(tok):
    try:
        return float(str(tok).replace(",", "."))
    except (TypeError, ValueError):
        return None


def detect_placeholder_evidence(text: str) -> bool:
    """True if the evidence/rationale is empty, a placeholder token, or too vague."""
    t = str(text or "").strip().lower()
    if t in _PLACEHOLDER_EXACT:
        return True
    if len(t) < 5:                      # too short to be real evidence
        return True
    # all-whitespace / single repeated char
    if len(set(t.replace(" ", ""))) <= 1:
        return True
    return False


def extract_numeric_claims(text: str) -> list:
    """All numeric values mentioned in the text (comma-decimal aware)."""
    return [v for v in (_to_float(m.group(0)) for m in _NUM_RE.finditer(str(text or "")))
            if v is not None]


def strong_claim(text: str):
    """The strongest final numeric claim: the value after the LAST '=', else None."""
    matches = _EQ_NUM_RE.findall(str(text or ""))
    return _to_float(matches[-1]) if matches else None


def extract_option_numeric_values(choice_text: str) -> list:
    return extract_numeric_claims(choice_text)


def _is_deterministic(candidate) -> bool:
    src = getattr(candidate, "source", "") or ""
    return any(src.startswith(p) for p in _DETERMINISTIC_PREFIXES)


def candidate_matches_option(candidate, sample) -> bool:
    """If the candidate states a strong numeric result, the selected option must contain it."""
    labels = [chr(ord("A") + i) for i in range(len(sample.get("choices", []) or []))]
    ans = getattr(candidate, "answer", None)
    if ans not in labels:
        return False
    text = " ".join(str(x or "") for x in (getattr(candidate, "proof_text", ""),
                                           getattr(candidate, "evidence_text", ""),
                                           getattr(candidate, "rationale", "")))
    claim = strong_claim(text)
    if claim is None:
        return True                     # no numeric claim to contradict
    opt_text = sample["choices"][labels.index(ans)]
    opt_vals = extract_option_numeric_values(opt_text)
    if not opt_vals:
        return True                     # non-numeric option; nothing to check
    tol = 1e-6 + 1e-3 * abs(claim)
    return any(abs(claim - v) <= tol for v in opt_vals)


def validate_candidate_consistency(candidate, sample) -> ConsistencyRecord:
    """Return a ConsistencyRecord. Deterministic-tool candidates are trusted."""
    deterministic = _is_deterministic(candidate)
    text = " ".join(str(x or "") for x in (getattr(candidate, "proof_text", ""),
                                           getattr(candidate, "evidence_text", ""),
                                           getattr(candidate, "rationale", "")))
    claims = extract_numeric_claims(text)
    labels = [chr(ord("A") + i) for i in range(len(sample.get("choices", []) or []))]
    ans = getattr(candidate, "answer", None)
    opt_vals = extract_option_numeric_values(
        sample["choices"][labels.index(ans)]) if ans in labels else []

    # Numeric mismatch is decisive regardless of source.
    if not candidate_matches_option(candidate, sample):
        return ConsistencyRecord(False, "numeric_mismatch",
                                 "evidence's numeric result is absent from the selected option",
                                 claims, opt_vals)
    # Deterministic tool candidates carry a real proof -> trusted.
    if deterministic:
        return ConsistencyRecord(True, "ok", "deterministic tool candidate", claims, opt_vals)
    # Non-deterministic candidates need real (non-placeholder) evidence or rationale.
    ev_ok = not detect_placeholder_evidence(getattr(candidate, "evidence_text", ""))
    rat_ok = not detect_placeholder_evidence(getattr(candidate, "rationale", ""))
    if not (ev_ok or rat_ok):
        return ConsistencyRecord(False, "placeholder",
                                 "placeholder/empty evidence cannot support an override",
                                 claims, opt_vals)
    return ConsistencyRecord(True, "ok", "consistent", claims, opt_vals)


def is_candidate_consistent(candidate, sample) -> bool:
    """Combined gate: numeric/placeholder guard AND option-grounding label check.

    Used by the ranker. Lazy-imports ``option_grounding`` to avoid an import cycle.
    """
    if not validate_candidate_consistency(candidate, sample).ok:
        return False
    try:
        from src.evidence.option_grounding import verify_answer_label_matches_reasoning
        return verify_answer_label_matches_reasoning(candidate, sample)
    except Exception:   # pragma: no cover - grounding must never crash the ranker
        return True
