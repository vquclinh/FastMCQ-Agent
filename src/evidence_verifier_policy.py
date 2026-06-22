"""Strict evidence-grounded override policy (Phase 2L.23).

Defines when a FUTURE automatic override of the base LLM answer is permitted. The bar
is high and evidence-grounded: an override is allowed ONLY for a deterministic
calculation proof with a unique option, a knowledge answer backed by a retrieved card
with high confidence + clear option mapping, or a conceptual answer with explicit
option elimination + support. Everything weak (internal-knowledge-only, self-
consistency-only, vague rationale, unsupported law/admin, medium/high-risk formula
hint) is REJECTED. Pure policy — no network, no qid logic, no answer table.
"""

from __future__ import annotations

from dataclasses import dataclass

# Evidence-type tiers.
ACCEPTABLE_KINDS = ("deterministic_calculation", "retrieved_card", "option_elimination")
REJECTED_KINDS = ("internal_knowledge", "self_consistency", "vague", "law_admin_unsupported",
                  "formula_hint")
_HIGH_CONF = 0.90


@dataclass
class OverrideDecision:
    allow: bool
    reason: str
    evidence_kind: str = ""

    def to_dict(self) -> dict:
        return {"allow": self.allow, "reason": self.reason, "evidence_kind": self.evidence_kind}


def evaluate_override(proposal: dict) -> OverrideDecision:
    """Decide whether a proposed override is allowed under the strict policy.

    ``proposal`` keys (all optional unless noted):
      evidence_kind, unique_option (bool), selected_answer, current_answer, confidence,
      card_support (bool), elimination_support (bool), risk_level, reason.
    """
    kind = proposal.get("evidence_kind")
    sel = proposal.get("selected_answer")
    cur = proposal.get("current_answer")
    try:
        conf = float(proposal.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(proposal.get("reason") or "").strip()

    if not sel:
        return OverrideDecision(False, "no selected answer", kind or "")
    if sel == cur:
        return OverrideDecision(False, "selected equals current (no change)", kind or "")
    if kind in REJECTED_KINDS:
        return OverrideDecision(False, f"rejected evidence kind: {kind}", kind or "")
    if proposal.get("risk_level") in ("medium", "high"):
        return OverrideDecision(False, "medium/high-risk detection is hint-only", kind or "")

    # (1) deterministic calculation proof + unique option.
    if kind == "deterministic_calculation" and proposal.get("unique_option"):
        return OverrideDecision(True, "deterministic calculation with unique option", kind)
    # (2) retrieved knowledge card + high confidence + option mapping.
    if kind == "retrieved_card" and proposal.get("card_support") and conf >= _HIGH_CONF \
            and proposal.get("unique_option"):
        return OverrideDecision(True, "retrieved card support + high confidence + mapping", kind)
    # (3) conceptual: explicit option elimination + support.
    if kind == "option_elimination" and proposal.get("elimination_support") and reason:
        return OverrideDecision(True, "explicit option elimination with support", kind)

    return OverrideDecision(False, "insufficient evidence for override", kind or "")
