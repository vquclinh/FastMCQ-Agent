"""Per-choice uncertainty scoring for local MCQ inference (Phase 1 — observational).

This module owns the PURE math of turning per-label conditional log-probabilities
into an uncertainty summary (top-1/top-2, log-probability margin, probability
margin, normalized entropy). It imports no torch/transformers and never loads a
model, so it is fully unit-testable with deterministic fake logits.

The model forward that produces the raw per-label log-probabilities lives in
``LocalQwenBackend.score_mcq_choices`` (torch, lazy). Phase 1 is telemetry only:
nothing here changes any answer, route, or official output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ChoiceScoreResult:
    """Uncertainty summary over the allowed labels of one MCQ item.

    ``scores_by_label`` are raw (summed conditional) log-probabilities; higher is
    more likely. ``probabilities_by_label`` is the softmax over ONLY the allowed
    labels. All numeric fields are None when ``valid`` is False.
    """

    allowed_labels: list[str] = field(default_factory=list)
    scores_by_label: dict[str, float] = field(default_factory=dict)
    probabilities_by_label: dict[str, float] = field(default_factory=dict)
    top1_label: str | None = None
    top2_label: str | None = None
    top1_score: float | None = None
    top2_score: float | None = None
    logit_margin: float | None = None
    probability_margin: float | None = None
    normalized_entropy: float | None = None
    scoring_method: str = "sequence_logprob"
    valid: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        """Numeric/categorical diagnostics only (no question text, no reasoning)."""
        return {
            "allowed_labels": list(self.allowed_labels),
            "scores_by_label": {k: _round(v) for k, v in self.scores_by_label.items()},
            "probabilities_by_label": {k: _round(v) for k, v in self.probabilities_by_label.items()},
            "top1_label": self.top1_label,
            "top2_label": self.top2_label,
            "top1_score": _round(self.top1_score),
            "top2_score": _round(self.top2_score),
            "logit_margin": _round(self.logit_margin),
            "probability_margin": _round(self.probability_margin),
            "normalized_entropy": _round(self.normalized_entropy),
            "scoring_method": self.scoring_method,
            "valid": self.valid,
            "error": self.error,
        }


def _round(x, n: int = 6):
    if x is None or not _finite(x):
        return None
    return round(float(x), n)


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _log_softmax(scores: list[float]) -> list[float]:
    """Numerically stable log-softmax."""
    m = max(scores)
    logZ = m + math.log(sum(math.exp(s - m) for s in scores))
    return [s - logZ for s in scores]


def compute_choice_scores(scores_by_label, labels, *,
                          scoring_method: str = "sequence_logprob",
                          error: str | None = None) -> ChoiceScoreResult:
    """Turn raw per-label log-probabilities into a ChoiceScoreResult (pure).

    ``labels`` is the ordered list of allowed labels for the item (A..). Ties are
    broken deterministically by that order. Missing/NaN/inf scores or fewer than
    one label yield an explicit invalid result (never a fabricated label).
    """
    allowed = [str(lab).strip().upper() for lab in (labels or []) if str(lab).strip()]
    if error is not None:
        return ChoiceScoreResult(allowed_labels=allowed, scoring_method=scoring_method,
                                 valid=False, error=error)
    if not allowed:
        return ChoiceScoreResult(allowed_labels=allowed, scoring_method=scoring_method,
                                 valid=False, error="no_allowed_labels")

    raw = {}
    for lab in allowed:
        if lab not in (scores_by_label or {}):
            return ChoiceScoreResult(allowed_labels=allowed, scoring_method=scoring_method,
                                     valid=False, error=f"missing_score:{lab}")
        val = scores_by_label[lab]
        if not _finite(val):
            return ChoiceScoreResult(allowed_labels=allowed, scoring_method=scoring_method,
                                     valid=False, error=f"nonfinite_score:{lab}")
        raw[lab] = float(val)

    ordered = list(raw.items())                       # preserves allowed-label order
    log_probs = _log_softmax([v for _, v in ordered])
    probs = [math.exp(lp) for lp in log_probs]
    prob_by_label = {lab: p for (lab, _), p in zip(ordered, probs)}

    # Rank by score desc, ties broken by allowed-label order (stable sort on -score).
    ranked = sorted(range(len(ordered)), key=lambda i: (-ordered[i][1], i))
    top1_i = ranked[0]
    top1_label, top1_score = ordered[top1_i]
    if len(ordered) >= 2:
        top2_i = ranked[1]
        top2_label, top2_score = ordered[top2_i]
        logit_margin = top1_score - top2_score
        probability_margin = prob_by_label[top1_label] - prob_by_label[top2_label]
    else:
        top2_label, top2_score = None, None
        logit_margin = None
        probability_margin = None

    n = len(ordered)
    if n <= 1:
        normalized_entropy = 0.0
    else:
        ent = -sum(p * math.log(p) for p in probs if p > 0.0)
        normalized_entropy = ent / math.log(n)

    return ChoiceScoreResult(
        allowed_labels=allowed,
        scores_by_label=raw,
        probabilities_by_label=prob_by_label,
        top1_label=top1_label, top2_label=top2_label,
        top1_score=top1_score, top2_score=top2_score,
        logit_margin=logit_margin, probability_margin=probability_margin,
        normalized_entropy=normalized_entropy,
        scoring_method=scoring_method, valid=True, error=None)
