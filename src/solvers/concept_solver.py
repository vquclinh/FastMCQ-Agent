"""Generalized deterministic *concept* rules (no qid logic, no answer tables).

Closed-form qualitative reasoners for well-defined CS/economics concepts where the
correct option is determined by the concept itself, not by arithmetic. Like
``calculation_solver``, every rule keys off generic wording + the option texts and
overrides ONLY when exactly one option uniquely matches the concept. There is no
``qid`` logic, no public-test answer table, and no external sheet usage — only string
matching and fixed concept rules. **Prefer no answer over a risky answer.**
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


@dataclass
class ConceptResult:
    answer: str | None
    matched: bool
    safe_to_override: bool
    rule_id: str
    reason: str
    matched_option_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _no_match() -> ConceptResult:
    return ConceptResult(None, False, False, "none", "", "")


def _num_after(pattern: str, text: str):
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    mn = _NUM_RE.search(m.group(1))
    return float(mn.group(0).replace(",", ".")) if mn else None


def _has(text: str, kws) -> bool:
    return any(k in text for k in kws)


# --- Rule 1: paging logical-address structure --------------------------------

def try_paging_logical_address(q: str, choices, labels) -> ConceptResult:
    """Logical address in paging = page number + offset/displacement (not frame/size).

    Fires only on a paging + logical-address *structure* question, and only when
    exactly one option contains page + offset/displacement while excluding the
    frame-number and page-size distractors.
    """
    low = q.lower()
    paging = _has(low, ("phân trang", "phân hoạch trang", "paging", "phân đoạn trang"))
    logical = _has(low, ("địa chỉ luận lý", "địa chỉ logic", "địa chỉ lô-gic",
                         "logical address"))
    if not (paging and logical):
        return _no_match()

    page_kw = ("page", "trang", "(p)")
    offset_kw = ("độ dời", "độ dịch", "offset", "displacement", "(d)")
    frame_kw = ("frame", "khung")
    size_kw = ("kích thước", "size", "(s)")

    hits = []
    for i, c in enumerate(choices):
        cl = str(c).lower()
        if _has(cl, page_kw) and _has(cl, offset_kw) and not _has(cl, frame_kw) \
                and not _has(cl, size_kw):
            hits.append((labels[i], str(c)))
    if len(hits) == 1:
        lbl, text = hits[0]
        return ConceptResult(lbl, True, True, "paging_logical_address",
                             "logical address = page number + page offset/displacement", text)
    return _no_match()


# --- Rule 2: marginal cost vs average variable cost --------------------------

def try_mc_vs_avc(q: str, choices, labels) -> ConceptResult:
    """If output rises by one unit: MC>AVC ⇒ AVC↑; MC<AVC ⇒ AVC↓; MC=AVC ⇒ unchanged."""
    low = q.lower()
    has_avc = _has(low, ("chi phí biến đổi trung bình", "average variable cost", "avc"))
    has_mc = _has(low, ("chi phí biên", "marginal cost", " mc"))
    if not (has_avc and has_mc):
        return _no_match()
    # The asked quantity must be the AVC change.
    if not _has(low, ("chi phí biến đổi trung bình", "average variable cost", "avc")):
        return _no_match()

    avc = (_num_after(r"chi phí biến đổi trung bình[^0-9]{0,20}?(\d[\d.,]*)", q)
           or _num_after(r"average variable cost[^0-9]{0,20}?(\d[\d.,]*)", q)
           or _num_after(r"\bavc\b[^0-9]{0,20}?(\d[\d.,]*)", q))
    mc = (_num_after(r"chi phí biên[^0-9]{0,20}?(\d[\d.,]*)", q)
          or _num_after(r"marginal cost[^0-9]{0,20}?(\d[\d.,]*)", q)
          or _num_after(r"\bmc\b[^0-9]{0,20}?(\d[\d.,]*)", q))
    if avc is None or mc is None:
        return _no_match()

    if mc > avc:
        direction, want, avoid = "increase", ("tăng", "increase", "rise"), ("giảm", "decrease")
    elif mc < avc:
        direction, want, avoid = "decrease", ("giảm", "decrease", "fall"), ("tăng", "increase")
    else:
        direction, want, avoid = "unchanged", ("không thay đổi", "không đổi", "unchanged",
                                               "không thay đôi", "constant"), ()

    hits = []
    for i, c in enumerate(choices):
        cl = str(c).lower()
        # "không thay đổi"/"không thể xác định" must not count as increase/decrease.
        if direction in ("increase", "decrease") and _has(cl, ("không", "unable", "cannot")):
            continue
        if _has(cl, want) and not _has(cl, avoid):
            hits.append((labels[i], str(c)))
    if len(hits) == 1:
        lbl, text = hits[0]
        return ConceptResult(lbl, True, True, "mc_vs_avc",
                             f"MC={mc:g} {'>' if mc > avc else '<' if mc < avc else '='} "
                             f"AVC={avc:g} ⇒ AVC {direction}", text)
    return _no_match()


_RULES = (
    try_paging_logical_address,
    try_mc_vs_avc,
)


def solve_concept_sample(sample: dict, labels: list) -> ConceptResult:
    """Try each generalized concept rule; return the first safe, unique match.

    Never returns a label outside ``labels``. No qid is used. On any ambiguity a
    rule declines (``matched=False``) and the caller keeps the existing answer.
    """
    q = str(sample.get("question", "") or "")
    choices = sample.get("choices", []) or []
    if not labels or not choices:
        return _no_match()
    for rule in _RULES:
        try:
            res = rule(q, choices, labels)
        except Exception:
            res = _no_match()
        if res.matched and res.answer in labels:
            return res
    return _no_match()
