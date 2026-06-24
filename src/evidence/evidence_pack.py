"""Evidence pack builder (Phase 2L.27A) — no API, no answer selection.

Assembles compact evidence to *support* downstream reasoning (it never picks an
answer): option-aware snippets for long_context, retrieved knowledge cards for
short_knowledge, and formula/tool hints for calculation. Deterministic, lexical,
dependency-free. No qid logic, no answer table, no network.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from src.solvers.formula_bank_solver import detect_formula_hints, solve_formula_bank_sample
from src.evidence.knowledge_cards import retrieve_cards
from src.evidence.option_evidence import build_option_aware_evidence_pack
from src.evidence.rag_lite import retrieve_cards_per_option


@dataclass
class EvidencePack:
    kind: str
    matched: bool
    text: str = ""
    per_option: dict = field(default_factory=dict)
    cards: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def build_long_context_evidence_pack(sample, max_snippets: int = 5) -> EvidencePack:
    pk = build_option_aware_evidence_pack(sample, per_option_top_k=1,
                                          max_chars=600 * max_snippets)
    if not pk.matched:
        return EvidencePack("long_context", False, diagnostics=pk.diagnostics)
    return EvidencePack("long_context", True, text=pk.pack_text,
                        per_option=pk.evidence_selected_by_option,
                        diagnostics={"pack_size": pk.evidence_pack_size,
                                     "top_option_scores": pk.top_option_evidence_scores})


def build_short_knowledge_evidence_pack(sample, cards=None, max_cards: int = 5) -> EvidencePack:
    q = sample.get("question", "")
    hits = retrieve_cards(q, top_k=max_cards)
    per_opt = retrieve_cards_per_option(q, sample.get("choices", []) or [], top_k=1)
    card_list = [{"id": c.id, "statement": c.statement, "formula": c.formula_or_rule,
                  "score": round(s, 3)} for c, s in hits]
    return EvidencePack("short_knowledge", bool(card_list),
                        cards=card_list,
                        per_option={lbl: [c.id for c, _ in v] for lbl, v in per_opt.items()},
                        diagnostics={"n_cards": len(card_list)})


def build_calculation_evidence_pack(sample) -> EvidencePack:
    fb = solve_formula_bank_sample(sample)
    hints = detect_formula_hints(sample)
    text = ""
    if fb is not None and fb.safe_to_override:
        text = f"deterministic: {fb.rule_id} -> {fb.selected_answer} ({fb.reason})"
    return EvidencePack("calculation", bool(fb is not None or hints),
                        text=text, hints=[h["hint"] for h in hints],
                        diagnostics={"has_safe_tool": bool(fb is not None and fb.safe_to_override),
                                     "n_hints": len(hints)})


def build_evidence_pack(sample, route: str):
    """Dispatch to the route-appropriate evidence pack builder."""
    if route == "long_context":
        return build_long_context_evidence_pack(sample)
    if route == "calculation":
        return build_calculation_evidence_pack(sample)
    return build_short_knowledge_evidence_pack(sample)
