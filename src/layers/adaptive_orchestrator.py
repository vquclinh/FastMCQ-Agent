"""Adaptive reasoning orchestrator (Phase 2L.15A) — trace-only by default.

Given a sample (and optionally the graph solver's per-sample state + the existing
answer), it analyzes route/risk, selects a branch, gathers non-binding candidates,
and emits an :class:`AdaptiveTrace`. In ``trace_only`` mode it NEVER changes the
final answer, NEVER calls an API, and ``would_override`` is always False — v6b
remains the source of truth. Later phases enable assist/active modes behind gates.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.layers.adaptive_routing import analyze as analyze_route
from src.layers.adaptive_routing import sk_verifier_eligibility
from src.layers.adaptive_types import AdaptiveTrace
from src.solvers import programmatic_solver


@dataclass
class AdaptiveConfig:
    enabled: bool = False
    mode: str = "trace_only"
    calculation_programmatic_enabled: bool = True
    calculation_allow_override: bool = False
    short_knowledge_verifier_enabled: bool = False
    sk_allow_override: bool = False
    sk_trigger_confidence_max: float = 0.95
    sk_max_verifier_calls: int = 0
    sk_require_strong_confidence: bool = True
    long_context_evidence_check_enabled: bool = True
    long_context_allow_answer_change: bool = False
    self_consistency_enabled: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> "AdaptiveConfig":
        d = d or {}
        calc = d.get("calculation_programmatic", {}) or {}
        sk = d.get("short_knowledge_verifier", {}) or {}
        lc = d.get("long_context_evidence_check", {}) or {}
        sc = d.get("self_consistency", {}) or {}
        return cls(
            enabled=bool(d.get("enabled", False)),
            mode=str(d.get("mode", "trace_only")),
            calculation_programmatic_enabled=bool(calc.get("enabled", True)),
            calculation_allow_override=bool(calc.get("allow_override", False)),
            short_knowledge_verifier_enabled=bool(sk.get("enabled", False)),
            sk_allow_override=bool(sk.get("allow_override", False)),
            sk_trigger_confidence_max=float(sk.get("trigger_confidence_max", 0.95)),
            sk_max_verifier_calls=int(sk.get("max_verifier_calls", 0)),
            sk_require_strong_confidence=bool(sk.get("require_strong_confidence", True)),
            long_context_evidence_check_enabled=bool(lc.get("enabled", True)),
            long_context_allow_answer_change=bool(lc.get("allow_answer_change", False)),
            self_consistency_enabled=bool(sc.get("enabled", False)),
        )


class AdaptiveOrchestrator:
    """Produces an AdaptiveTrace; trace-only mode is read-only w.r.t. answers."""

    def __init__(self, config: AdaptiveConfig | None = None):
        self.cfg = config or AdaptiveConfig()

    def analyze(self, sample: dict, *, existing_answer: str | None = None,
                state: dict | None = None) -> AdaptiveTrace:
        route, branch, risk_flags = analyze_route(sample, state=state)
        candidates = []

        # Calculation branch: gather a non-binding deterministic candidate.
        if branch == "calculation" and self.cfg.calculation_programmatic_enabled:
            try:
                cand = programmatic_solver.candidate_for(sample, existing_answer=existing_answer)
                candidates.append(cand.to_dict())
            except Exception as exc:  # a hook bug must never break the run
                candidates.append({"branch": "calculation", "error": type(exc).__name__})

        # Short-knowledge branch: compute verifier ELIGIBILITY only (no API call,
        # no candidate, no answer change in the orchestrator — the actual verifier
        # call lives in the explicit runner script and is gated/off by default).
        sk_eligible, sk_reasons = (False, [])
        if branch == "short_knowledge" and self.cfg.short_knowledge_verifier_enabled:
            st = dict(state or {})
            st.setdefault("final_answer", existing_answer)
            sk_eligible, sk_reasons = sk_verifier_eligibility(
                sample, route, state=st,
                trigger_confidence_max=self.cfg.sk_trigger_confidence_max)

        # Whether any candidate *would* change the answer (informational only).
        any_change = any(c.get("would_change_answer") for c in candidates)

        trace_only = self.cfg.mode == "trace_only"
        # Override is allowed ONLY outside trace-only AND when the branch permits it.
        override_allowed = (not trace_only) and (
            (branch == "calculation" and self.cfg.calculation_allow_override)
            or (branch == "long_context" and self.cfg.long_context_allow_answer_change)
        )
        would_override = bool(override_allowed and any_change)  # always False in trace_only
        final_decision = "fallback_existing_answer" if (trace_only or not would_override) \
            else "adaptive_override"

        return AdaptiveTrace(
            enabled=self.cfg.enabled, mode=self.cfg.mode, route=route,
            risk_flags=risk_flags, selected_branch=branch,
            branch_candidates=candidates, would_override=would_override,
            override_allowed=override_allowed, final_decision=final_decision,
            extra={"any_candidate_would_change": any_change,
                   "sk_verifier_eligible": sk_eligible,
                   "sk_trigger_reasons": sk_reasons},
        )
