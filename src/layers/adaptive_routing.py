"""Route → branch mapping and per-branch risk-flag analysis (trace-only signals).

Reuses the existing router/profiler. Produces non-binding risk flags used for
diagnostics and (in later phases) selective verification. No answers change here.
No qid is read for any decision.
"""

from __future__ import annotations

from src.layers.question_profiler import profile_question
from src.layers.question_router import route_question

# route -> adaptive branch (1:1 today; kept explicit for future divergence).
_ROUTE_TO_BRANCH = {
    "calculation": "calculation",
    "long_context": "long_context",
    "short_knowledge": "short_knowledge",
    "law_admin": "law_admin",
    "ambiguous": "ambiguous",
}

_ADMIN_POLICY_HINTS = ("luật", "nghị định", "thông tư", "điều ", "khoản ", "chính sách",
                       "quy định", "bộ luật", "hiến pháp", "nguyên tắc", "theo quy")
_LOW_CONF_DEFAULT = 0.6


def route_to_branch(route: str) -> str:
    return _ROUTE_TO_BRANCH.get(route, "short_knowledge")


def analyze_risk(sample: dict, route: str, *, state: dict | None = None) -> list:
    """Return a list of non-binding risk-flag strings for the sample's branch.

    ``state`` (optional) is the graph solver's per-sample dict — when present we use
    its confidence / parse fields; otherwise only question-text signals are used.
    """
    low = str(sample.get("question", "") or "").lower()
    state = state or {}
    flags: list[str] = []
    branch = route_to_branch(route)

    conf = state.get("confidence")
    parse_src = state.get("parsed_answer_source") or (state.get("parsed_answer") or {}).get("source")
    parse_err = state.get("parsed_answer_error") or (state.get("parsed_answer") or {}).get("error")
    needs_review = (state.get("parsed_answer") or {}).get("needs_review")

    is_admin_policy = any(h in low for h in _ADMIN_POLICY_HINTS)

    if branch in ("short_knowledge", "law_admin"):
        if isinstance(conf, (int, float)) and conf < _LOW_CONF_DEFAULT:
            flags.append("low_confidence")
        if is_admin_policy:
            flags.append("domain_admin_or_policy")
        if needs_review or parse_err == "no_json" or parse_src == "partial_answer_key":
            flags.append("answer_has_uncertain_reasoning")
        if branch == "law_admin":
            flags.append("source_grounding_recommended")
        if flags:
            flags.append("verifier_recommended")

    elif branch == "ambiguous":
        flags.append("needs_adjudication")
        flags.append("adjudication_reason:duplicate_or_unclear_choices")

    elif branch == "long_context":
        # Placeholders for Phase 2L.15D (evidence sufficiency); no answer effect now.
        flags.append("evidence_check_pending")

    elif branch == "calculation":
        if state.get("calculation_safe_to_override"):
            flags.append("deterministic_candidate_available")
        elif state.get("calculation_matched"):
            flags.append("deterministic_candidate_unsafe")

    return flags


def sk_verifier_eligibility(sample: dict, route: str, *, state: dict | None = None,
                            trigger_confidence_max: float = 0.95):
    """Return (eligible: bool, trigger_reasons: list) for the short_knowledge verifier.

    Eligible ONLY when route == short_knowledge, the current answer is valid, and at
    least one trigger fires: confidence <= ``trigger_confidence_max``,
    domain_admin_or_policy, or answer_has_uncertain_reasoning. ``verifier_recommended``
    is added when any trigger fires. No API call, no answer change.
    """
    if route_to_branch(route) != "short_knowledge":
        return False, []
    state = state or {}
    low = str(sample.get("question", "") or "").lower()
    answer = state.get("final_answer")
    if not answer:                              # no valid current answer -> skip
        return False, []

    reasons = []
    conf = state.get("confidence")
    if isinstance(conf, (int, float)) and conf <= trigger_confidence_max:
        reasons.append("confidence_below_max")
    if any(h in low for h in _ADMIN_POLICY_HINTS):
        reasons.append("domain_admin_or_policy")
    parse_src = state.get("parsed_answer_source") or (state.get("parsed_answer") or {}).get("source")
    parse_err = state.get("parsed_answer_error") or (state.get("parsed_answer") or {}).get("error")
    needs_review = (state.get("parsed_answer") or {}).get("needs_review")
    if needs_review or parse_err == "no_json" or parse_src == "partial_answer_key":
        reasons.append("answer_has_uncertain_reasoning")
    if reasons:
        reasons.append("verifier_recommended")
    return (len(reasons) > 0), reasons


def analyze(sample: dict, *, state: dict | None = None):
    """Return (route, branch, risk_flags)."""
    route = route_question(profile_question(sample)).route
    branch = route_to_branch(route)
    flags = analyze_risk(sample, route, state=state)
    return route, branch, flags
