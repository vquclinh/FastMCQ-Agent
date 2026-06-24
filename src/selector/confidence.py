"""Confidence assessment for the adaptive agent.

Turns an option-scoring result (top-2 margin) plus structural signals into an
accept/fallback decision. Thresholds are **configurable** and deliberately
**not claimed optimal** — they start conservative and are tuned against the
leaderboard (there is no local ground truth).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Conservative defaults; override via config (hf.adaptive.* / CLI).
DEFAULT_THRESHOLDS = {
    "high_margin": 0.30,    # >= this average-logprob gap => accept
    "medium_margin": 0.10,  # >= this => accept unless config wants a check
    "low_margin": 0.0,      # below medium => low confidence
}


@dataclass
class ConfidenceDecision:
    level: str           # "high" | "medium" | "low" | "unknown"
    margin: float | None
    thresholds: dict
    should_accept: bool
    should_fallback: bool
    reason: str
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def assess_confidence(*, margin: float | None, has_valid_label: bool = True,
                      duplicate_choice_groups=None, thresholds: dict | None = None,
                      allow_fallback: bool = True,
                      accept_medium: bool = True) -> ConfidenceDecision:
    """Decide accept vs fallback from the scoring margin and structural signals.

    ``margin`` is best minus second-best average log-prob (``None`` if unavailable).
    ``accept_medium`` controls whether a *medium* margin is accepted outright or
    flagged for one lightweight fallback (when the budget allows).
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    duplicate_choice_groups = duplicate_choice_groups or []
    signals = {
        "has_valid_label": has_valid_label,
        "duplicate_choice_groups": duplicate_choice_groups,
    }

    # No usable label => lowest confidence, fallback if allowed.
    if not has_valid_label:
        return ConfidenceDecision(
            level="low", margin=margin, thresholds=th,
            should_accept=False, should_fallback=allow_fallback,
            reason="missing_or_invalid_label", signals=signals,
        )

    # No margin available (e.g. generation path or scoring error).
    if margin is None:
        return ConfidenceDecision(
            level="unknown", margin=None, thresholds=th,
            should_accept=not allow_fallback,  # accept only if we cannot fall back
            should_fallback=allow_fallback,
            reason="no_margin_available", signals=signals,
        )

    # Duplicate choices reduce confidence: never treat as high.
    has_duplicates = bool(duplicate_choice_groups)

    if margin >= th["high_margin"] and not has_duplicates:
        return ConfidenceDecision(
            level="high", margin=margin, thresholds=th,
            should_accept=True, should_fallback=False,
            reason="margin>=high_margin", signals=signals,
        )

    if margin >= th["medium_margin"]:
        accept = accept_medium and not has_duplicates
        reason = "margin>=medium_margin"
        if has_duplicates:
            reason += " but duplicate choices -> verify"
        elif not accept_medium:
            reason += " but accept_medium disabled -> verify"
        return ConfidenceDecision(
            level="medium", margin=margin, thresholds=th,
            should_accept=accept, should_fallback=(not accept) and allow_fallback,
            reason=reason, signals=signals,
        )

    # Low margin.
    return ConfidenceDecision(
        level="low", margin=margin, thresholds=th,
        should_accept=not allow_fallback, should_fallback=allow_fallback,
        reason="margin<medium_margin", signals=signals,
    )
