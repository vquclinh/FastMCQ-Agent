"""Deterministic routing from a :class:`QuestionProfile` to a strategy route.

No LLM call: routing is transparent heuristics over the cheap profile signals.
The route informs the adaptive solver's strategy and budget tier but is not
trusted blindly — the confidence verifier can still trigger a fallback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .question_profiler import QuestionProfile, profile_question

ROUTES = (
    "short_knowledge", "long_context", "calculation",
    "law_admin", "safety_ethics", "ambiguous", "unknown",
)

# Budget tiers (see docs/ARCHITECTURE.md §8).
TIER_CHEAP = 0
TIER_MODERATE = 1
TIER_EXPENSIVE = 2

_PRIMARY = "option_score_label_plus_choice"


@dataclass
class RouteDecision:
    route: str
    reason: str
    signals: dict
    recommended_budget_tier: int
    primary_strategy: str
    fallback_strategy: str

    def to_dict(self) -> dict:
        return asdict(self)


def route_question(sample_or_profile, *, allow_tier2_ambiguous: bool = False) -> RouteDecision:
    """Assign a route. Accepts a raw sample dict or a precomputed profile."""
    profile = (sample_or_profile if isinstance(sample_or_profile, QuestionProfile)
               else profile_question(sample_or_profile))

    signals = {
        "difficulty": profile.estimated_difficulty,
        "num_choices": profile.num_choices,
        "question_length": profile.question_length,
        "has_long_context_marker": profile.has_long_context_marker,
        "is_calculation": profile.raw_signals.get("is_calculation", False),
        "legal_keyword_count": profile.legal_keyword_count,
        "safety_keyword_count": profile.safety_keyword_count,
        "ethics_keyword_count": profile.ethics_keyword_count,
        "duplicate_choice_groups": profile.duplicate_choice_groups,
    }

    is_calc = profile.raw_signals.get("is_calculation", False)
    long_ctx = profile.has_long_context_marker or profile.question_length > 1500
    legal = profile.legal_keyword_count
    safety_ethics = profile.safety_keyword_count + profile.ethics_keyword_count

    # 1) Duplicate choices => genuinely ambiguous (hard to score cleanly).
    if profile.duplicate_choice_groups:
        return _decision("ambiguous",
                         "duplicate choice content detected", signals,
                         allow_tier2_ambiguous)

    # 2) Long context dominates budgeting, so it wins next.
    if long_ctx:
        return _decision("long_context",
                         "long-context markers or long question", signals,
                         allow_tier2_ambiguous)

    # 3) Calculation.
    if is_calc:
        return _decision("calculation",
                         "math/numeric signals present", signals,
                         allow_tier2_ambiguous)

    # 4) Law / admin — require a clear legal signal and no stronger one above.
    if legal >= 2:
        return _decision("law_admin",
                         f"legal/admin keywords ({legal})", signals,
                         allow_tier2_ambiguous)

    # 5) Safety / ethics.
    if safety_ethics >= 2:
        return _decision("safety_ethics",
                         f"safety/ethics keywords ({safety_ethics})", signals,
                         allow_tier2_ambiguous)

    # 6) Short knowledge: short, no strong signal.
    if profile.question_length <= 400:
        return _decision("short_knowledge",
                         "short question, no strong domain signal", signals,
                         allow_tier2_ambiguous)

    # 7) Fallback.
    return _decision("unknown", "no decisive signal", signals, allow_tier2_ambiguous)


# Per-route budget tier + recommended fallback.
_ROUTE_TIER = {
    "short_knowledge": TIER_CHEAP,
    "long_context": TIER_MODERATE,
    "calculation": TIER_MODERATE,
    "law_admin": TIER_MODERATE,
    "safety_ethics": TIER_MODERATE,
    "ambiguous": TIER_EXPENSIVE,   # only if config allows; else clamped below
    "unknown": TIER_CHEAP,
}
_ROUTE_FALLBACK = {
    "short_knowledge": "option_score_label_only",
    "long_context": "direct_generation",
    "calculation": "direct_generation",
    "law_admin": "option_score_label_only",
    "safety_ethics": "direct_generation",
    "ambiguous": "option_score_label_only",
    "unknown": "direct_generation",
}


def _decision(route: str, reason: str, signals: dict,
              allow_tier2_ambiguous: bool) -> RouteDecision:
    tier = _ROUTE_TIER[route]
    if route == "ambiguous" and not allow_tier2_ambiguous:
        tier = TIER_MODERATE  # clamp: don't spend Tier 2 unless explicitly enabled
    return RouteDecision(
        route=route,
        reason=reason,
        signals=signals,
        recommended_budget_tier=tier,
        primary_strategy=_PRIMARY,
        fallback_strategy=_ROUTE_FALLBACK[route],
    )
