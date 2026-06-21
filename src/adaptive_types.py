"""Dataclasses for the adaptive reasoning orchestrator (Phase 2L.15A).

These are pure data holders — no I/O, no network, no qid logic. The orchestrator
is **trace-only** by default: it analyzes route/risk and records diagnostics but
never changes a final answer. See ``src/adaptive_orchestrator.py``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Canonical branch + mode names.
BRANCHES = ("calculation", "long_context", "short_knowledge", "law_admin", "ambiguous")
MODES = ("trace_only", "assist", "active")   # only trace_only is wired in 2L.15A


@dataclass
class FormulaCard:
    """Metadata describing a deterministic formula family (executor may be a stub)."""

    formula_id: str
    domain: str
    trigger_keywords: tuple
    required_variables: tuple
    do_not_use_when: tuple = ()
    target_intents: tuple = ()           # e.g. ("gamma",) vs ("momentum",) — disambiguation
    output_type: str = "numeric"         # numeric | multiple_of | interval | pair | combined | symbolic
    option_match_policy: str = "nearest_margin"
    executor: str = ""                   # name of the try_* executor (string ref)
    implemented: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BranchCandidate:
    """A non-binding candidate produced by a branch (never auto-applied in trace_only)."""

    branch: str
    method: str | None = None
    answer: str | None = None            # a label, or None
    confidence: float = 0.0
    would_change_answer: bool = False    # differs from the existing v6b answer
    source: str = ""                     # e.g. "programmatic_solver"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AdaptiveTrace:
    """The ``adaptive`` object attached to a sample's trace when enabled."""

    enabled: bool
    mode: str
    route: str
    risk_flags: list = field(default_factory=list)
    selected_branch: str = ""
    branch_candidates: list = field(default_factory=list)   # list[dict]
    would_override: bool = False         # MUST be False in trace_only mode
    override_allowed: bool = False
    final_decision: str = "fallback_existing_answer"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # branch_candidates may already be dicts; normalize.
        d["branch_candidates"] = [
            c.to_dict() if isinstance(c, BranchCandidate) else c
            for c in self.branch_candidates
        ]
        return d
