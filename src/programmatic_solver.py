"""Programmatic (deterministic) calculation hooks for the adaptive orchestrator.

This is the architectural seam between the orchestrator and the deterministic
calculation engine. For Phase 2L.15A it is a thin, side-effect-free wrapper around
``src/calculation_solver.solve_calculation_sample`` that produces a NON-BINDING
``BranchCandidate`` — it never applies an override. Phase 2L.15B will expand the
extract → execute → match → gate hooks (Formula Registry binding, Formula-RAG).

No qid logic, no external answer sheet, no network.
"""

from __future__ import annotations

from src.adaptive_types import BranchCandidate
from src.calculation_solver import solve_calculation_sample
from src.formula_registry import eligible_formula_ids
from src.labels import labels_for


def candidate_for(sample: dict, *, existing_answer: str | None = None,
                  min_confidence: float = 0.95) -> BranchCandidate:
    """Return a non-binding deterministic candidate for a calculation question.

    Reports the matched family, its answer/confidence, whether it *would* differ
    from the existing answer, and the metadata-eligible formula ids. Does NOT change
    any answer; the orchestrator decides (and in trace-only mode never applies it).
    """
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    eligible = eligible_formula_ids(sample.get("question", ""))
    res = solve_calculation_sample(sample, labels, min_confidence=min_confidence)
    if not (res.matched and res.answer in labels):
        return BranchCandidate(branch="calculation", method=None, answer=None,
                               confidence=0.0, would_change_answer=False,
                               source="programmatic_solver",
                               note=f"no_match; eligible_cards={eligible}")
    would_change = bool(res.safe_to_override and existing_answer is not None
                        and res.answer != existing_answer)
    return BranchCandidate(branch="calculation", method=res.method, answer=res.answer,
                           confidence=res.confidence, would_change_answer=would_change,
                           source="programmatic_solver",
                           note=f"family={res.formula_family}; safe={res.safe_to_override}; "
                                f"eligible_cards={eligible}")
