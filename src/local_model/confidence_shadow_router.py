"""Phase 2 confidence-aware SHADOW router (observational only).

Given the corrected Phase 1 per-choice scoring result for each item, this module
computes deterministic uncertainty/risk metadata and decides which qids WOULD be
selected for follow-up reasoning under a provisional threshold + budget cap. It
NEVER runs V12B/V13, NEVER calls the selector, and NEVER changes a generated answer
or official output. It imports no torch/transformers and consumes no ground truth.

Policy: threshold filtering + maximum budget cap.
  * budget cap = max_targets_override, else ceil(N / budget_divisor);
  * only items meeting an uncertainty/risk condition are candidates;
  * candidates are ranked deterministically (explicit failures first, then lower
    raw-logit margin, then higher entropy, then stable input order);
  * only the highest-risk candidates up to the cap are marked selected;
  * the cap is a maximum — the router never backfills with non-candidates.

The provisional margin threshold is SHADOW-ONLY and is NOT a final production value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Candidate reasons.
REASON_SCORING_INVALID = "scoring_invalid"
REASON_PARSER_FAILURE = "parser_failure"
REASON_FORMULA_DISAGREEMENT = "formula_model_disagreement"
REASON_HIGH_ENTROPY = "high_normalized_entropy"
REASON_LOW_MARGIN = "low_logit_margin"

# Explicit failure/disagreement reasons rank above ordinary numerical uncertainty.
_EXPLICIT_REASONS = (REASON_SCORING_INVALID, REASON_PARSER_FAILURE, REASON_FORMULA_DISAGREEMENT)


@dataclass(frozen=True)
class ShadowRouterConfig:
    enabled: bool = False
    provisional_margin_threshold: float = 10.0     # SHADOW-ONLY; not a final threshold
    entropy_threshold: float | None = None         # None -> entropy does not affect selection
    budget_divisor: int = 20
    max_targets_override: int | None = None
    include_scoring_invalid: bool = True
    include_parser_failure: bool = True
    include_formula_disagreement: bool = True
    analysis_margin_thresholds: tuple[float, ...] = (5.0, 7.5, 10.0, 12.5, 15.0, 20.0)


@dataclass
class ShadowRoutingInput:
    qid: str
    input_index: int
    generated_answer: str | None = None
    scoring_valid: bool = False
    scoring_error: str | None = None
    top1: str | None = None
    top2: str | None = None
    logit_margin: float | None = None
    probability_margin: float | None = None
    normalized_entropy: float | None = None
    scoring_method: str | None = None
    # Optional supplemental risk metadata — used ONLY when genuinely provided.
    parser_failure: bool | None = None
    formula_disagreement: bool | None = None
    formula_source: str | None = None


@dataclass
class ShadowRoutingDecision:
    qid: str
    input_index: int
    candidate: bool
    selected: bool
    selected_rank: int | None
    candidate_reasons: list[str]
    generated_answer: str | None
    top1: str | None
    top2: str | None
    logit_margin: float | None
    probability_margin: float | None
    normalized_entropy: float | None
    scoring_valid: bool
    scoring_error: str | None
    risk_tier: int                 # 0 = explicit failure/disagreement, 1 = numerical only
    risk_margin: float | None      # the margin used for ranking (None when invalid)
    provisional_threshold: float
    budget_cap: int
    scoring_method: str | None

    def as_dict(self) -> dict:
        return {
            "qid": self.qid, "input_index": self.input_index,
            "candidate": self.candidate, "selected": self.selected,
            "selected_rank": self.selected_rank,
            "candidate_reasons": list(self.candidate_reasons),
            "generated_answer": self.generated_answer,
            "top1": self.top1, "top2": self.top2,
            "logit_margin": _num(self.logit_margin),
            "probability_margin": _num(self.probability_margin),
            "normalized_entropy": _num(self.normalized_entropy),
            "scoring_valid": self.scoring_valid, "scoring_error": self.scoring_error,
            "risk_tier": self.risk_tier, "risk_margin": _num(self.risk_margin),
            "provisional_threshold": _num(self.provisional_threshold),
            "budget_cap": self.budget_cap, "scoring_method": self.scoring_method,
        }


@dataclass
class ShadowRoutingSummary:
    n_input: int
    budget_cap: int
    provisional_threshold: float
    candidate_count: int
    selected_count: int                              # counts selected RECORDS, not unique qids
    selected_qids: list[str]                         # risk-rank order; MAY contain duplicate qids
    selected_items: list = field(default_factory=list)   # per-record: {qid, input_index, selected_rank}
    reason_counts: dict = field(default_factory=dict)
    scoring_method: str | None = None
    threshold_sweeps: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "n_input": self.n_input, "budget_cap": self.budget_cap,
            "provisional_threshold": _num(self.provisional_threshold),
            "candidate_count": self.candidate_count, "selected_count": self.selected_count,
            "selected_qids": list(self.selected_qids),
            "selected_items": [dict(it) for it in self.selected_items],
            "reason_counts": dict(self.reason_counts),
            "scoring_method": self.scoring_method,
            "threshold_sweeps": list(self.threshold_sweeps),
            "note": ("shadow-only; provisional threshold is NOT final; no follow-up reasoning ran. "
                     "selected_qids is risk-rank order and may contain duplicate qids; use "
                     "selected_items / selected_input_indexes to trace records uniquely"),
        }


def _num(x):
    """Keep NaN/Infinity out of JSON; pass through finite floats / None."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return xf if math.isfinite(xf) else None


def _budget_cap(n: int, config: ShadowRouterConfig) -> int:
    if config.max_targets_override is not None:
        return max(0, int(config.max_targets_override))
    if n <= 0:
        return 0
    divisor = config.budget_divisor if config.budget_divisor and config.budget_divisor > 0 else 20
    return max(0, math.ceil(n / divisor))


def _reasons_for(inp: ShadowRoutingInput, config: ShadowRouterConfig, margin_threshold: float):
    """Deterministic candidate reasons for one input at a given margin threshold."""
    reasons = []
    if inp.scoring_valid is False and config.include_scoring_invalid:
        reasons.append(REASON_SCORING_INVALID)
    if inp.parser_failure is True and config.include_parser_failure:
        reasons.append(REASON_PARSER_FAILURE)
    if inp.formula_disagreement is True and config.include_formula_disagreement:
        reasons.append(REASON_FORMULA_DISAGREEMENT)
    if (config.entropy_threshold is not None and inp.normalized_entropy is not None
            and inp.normalized_entropy > config.entropy_threshold):
        reasons.append(REASON_HIGH_ENTROPY)
    if inp.logit_margin is not None and inp.logit_margin <= margin_threshold:
        reasons.append(REASON_LOW_MARGIN)
    return reasons


def _rank_key(ordinal: int, inp: ShadowRoutingInput, reasons):
    """Lower key = higher risk (selected first). Explicit failures first, then lower
    raw-logit margin, then higher entropy, then stable caller input_index, then the
    private enumeration ordinal as the final deterministic tie-break. Missing margin/
    entropy are normalized to +inf / 0.0 so ``None`` is never compared with a number."""
    tier = 0 if any(r in _EXPLICIT_REASONS for r in reasons) else 1
    margin = inp.logit_margin if inp.logit_margin is not None else math.inf
    entropy = inp.normalized_entropy if inp.normalized_entropy is not None else 0.0
    idx = inp.input_index if isinstance(inp.input_index, int) else ordinal
    return (tier, margin, -entropy, idx, ordinal)


def _select(inputs, config: ShadowRouterConfig, margin_threshold: float, cap: int):
    """Return (candidates, selected) as lists of (ordinal, input, reasons) for a given
    margin threshold. The ``ordinal`` is the private per-record enumeration index — it
    is unique even when both ``qid`` and ``input_index`` are duplicated."""
    candidates = []
    for ordinal, inp in enumerate(inputs):
        reasons = _reasons_for(inp, config, margin_threshold)
        if reasons:
            candidates.append((ordinal, inp, reasons))
    candidates.sort(key=lambda t: _rank_key(t[0], t[1], t[2]))
    return candidates, candidates[:cap]


def run_shadow_router(inputs, config: ShadowRouterConfig):
    """Compute shadow decisions + summary. Pure and deterministic; no ground truth,
    no model, no answer change. Correct for duplicate qids AND duplicate input indexes
    because every record is associated by its private enumeration ordinal, never by qid.
    Returns (decisions, summary)."""
    inputs = list(inputs)
    n = len(inputs)
    cap = _budget_cap(n, config)
    thr = float(config.provisional_margin_threshold)

    candidates, selected = _select(inputs, config, thr, cap)
    reasons_by_ord = {ordinal: reasons for ordinal, _inp, reasons in candidates}
    rank_by_ord = {ordinal: i + 1 for i, (ordinal, _inp, _r) in enumerate(selected)}

    decisions = []
    reason_counts: dict[str, int] = {}
    for ordinal, inp in enumerate(inputs):                # stable input order
        reasons = reasons_by_ord.get(ordinal, [])         # this record's own reasons
        for r in reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
        selected_rank = rank_by_ord.get(ordinal)          # this record's own rank (or None)
        tier = 0 if any(r in _EXPLICIT_REASONS for r in reasons) else 1
        decisions.append(ShadowRoutingDecision(
            qid=inp.qid, input_index=inp.input_index,
            candidate=bool(reasons), selected=selected_rank is not None,
            selected_rank=selected_rank, candidate_reasons=list(reasons),
            generated_answer=inp.generated_answer, top1=inp.top1, top2=inp.top2,
            logit_margin=inp.logit_margin, probability_margin=inp.probability_margin,
            normalized_entropy=inp.normalized_entropy,
            scoring_valid=inp.scoring_valid, scoring_error=inp.scoring_error,
            risk_tier=tier, risk_margin=inp.logit_margin,
            provisional_threshold=thr, budget_cap=cap,
            scoring_method=inp.scoring_method))

    selected_qids = [inp.qid for _ord, inp, _r in selected]           # risk-rank order; may dup
    selected_items = [{"qid": inp.qid, "input_index": inp.input_index, "selected_rank": i + 1}
                      for i, (_ord, inp, _r) in enumerate(selected)]

    # Diagnostic threshold sweeps — observational only; never change primary decisions.
    sweeps = []
    for t in config.analysis_margin_thresholds:
        _cands_t, sel_t = _select(inputs, config, float(t), cap)
        sel_margins = sorted(m for _o, i, _r in sel_t
                             for m in (i.logit_margin,) if m is not None and math.isfinite(m))
        sweeps.append({
            "margin_threshold": _num(t),
            "candidates_before_cap": len(_cands_t),
            "selected_after_cap": len(sel_t),
            "selected_qids": [i.qid for _o, i, _r in sel_t],
            "selected_input_indexes": [i.input_index for _o, i, _r in sel_t],
            "selected_margin_min": sel_margins[0] if sel_margins else None,
            "selected_margin_median": (sel_margins[len(sel_margins) // 2]
                                       if sel_margins else None),
            "selected_margin_max": sel_margins[-1] if sel_margins else None,
        })

    scoring_method = next((inp.scoring_method for inp in inputs if inp.scoring_method), None)
    summary = ShadowRoutingSummary(
        n_input=n, budget_cap=cap, provisional_threshold=thr,
        candidate_count=len(candidates), selected_count=len(selected),
        selected_qids=selected_qids, selected_items=selected_items,
        reason_counts=reason_counts, scoring_method=scoring_method, threshold_sweeps=sweeps)
    return decisions, summary
