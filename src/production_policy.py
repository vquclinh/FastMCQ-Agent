"""Production decision policy — safe deterministic overrides over a base LLM answer.

Branch/layer separation for the hidden/private test. The base LLM answer is the
default; a deterministic rule (calculation → concept → formula bank, all surfaced via
``solve_formula_bank_sample``) overrides it ONLY when the rule is safe and uniquely
matched. Medium/high-risk detections, verifiers, and self-consistency NEVER
auto-override in production — they are log-only. No qid logic, no answer table, no
external sheet, no network.
"""

from __future__ import annotations

from src.adaptive_routing import route_to_branch
from src.formula_bank_solver import solve_formula_bank_sample
from src.question_profiler import profile_question
from src.question_router import route_question

# Branches whose answers a deterministic safe rule is allowed to set. Long-context,
# short-knowledge, law-admin and ambiguous keep the base LLM answer unless a generic
# deterministic rule (calc/concept/formula) happens to match safely — which is itself
# route-agnostic and safe. We still record the branch for diagnostics.
BRANCHES = ("calculation", "formula_bank", "concept", "long_context",
            "short_knowledge", "law_admin", "ambiguous")


def branch_of(sample: dict) -> str:
    """Coarse branch for a sample (from the existing router)."""
    return route_to_branch(route_question(profile_question(sample)).route)


def decide(sample: dict, base_answer, labels, *, enable_formula_bank=True):
    """Return (final_answer, record).

    Policy: deterministic safe rule > base LLM. If no safe rule matches, keep the
    base answer. The record documents the branch, whether a rule fired, the rule id,
    and the override reason — for the JSONL log.
    """
    branch = route_to_branch(route_question(profile_question(sample)).route)
    rec = {"branch": branch, "base_answer": base_answer, "final_answer": base_answer,
           "rule_id": None, "override_applied": False, "reason": "kept base LLM answer",
           "confidence": None}

    if not enable_formula_bank:
        return base_answer, rec

    res = solve_formula_bank_sample(sample)
    if (res is not None and res.safe_to_override and res.selected_answer in labels
            and res.selected_answer != base_answer):
        rec.update({"final_answer": res.selected_answer, "rule_id": res.rule_id,
                    "override_applied": True, "confidence": res.confidence,
                    "reason": f"safe deterministic override: {res.reason}"})
        return res.selected_answer, rec
    if res is not None and res.selected_answer == base_answer:
        rec.update({"rule_id": res.rule_id, "reason": "deterministic rule agrees with base"})
    return base_answer, rec


def apply_safe_overrides(samples, base_answers, labels_for_fn, *, enable_formula_bank=True):
    """Apply :func:`decide` across samples. Returns (final_answers, records).

    ``base_answers`` maps qid -> base label. ``labels_for_fn(n)`` -> label list.
    """
    finals, records = {}, []
    for s in samples:
        qid = s.get("qid")
        labels = labels_for_fn(len(s.get("choices", []) or []))
        base = base_answers.get(qid)
        final, rec = decide(s, base, labels, enable_formula_bank=enable_formula_bank)
        rec["qid"] = qid
        finals[qid] = final
        records.append(rec)
    return finals, records
