"""Least-to-most constraint-table solver (Phase 2L.35A) — V13 shadow stack.

For multi-condition MCQs ("chọn phát biểu đúng/sai", law/admin, pedagogy, psychology,
proverbs, multi-condition CS/DB), the model decomposes the question into atomic constraints and
evaluates every option against each constraint. The module accepts an answer ONLY when exactly
one option survives all constraints and the contradiction check passes.

Pure and deterministic — no API calls, no client construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.labels import is_valid_label, labels_for


@dataclass
class Constraint:
    text: str
    index: int


@dataclass
class OptionConstraintEvaluation:
    label: str
    passes_constraints: list      # list[bool]
    eliminated: bool
    elimination_reason: str = ""


@dataclass
class ConstraintTableDecision:
    constraints: list             # list[Constraint]
    option_evaluations: list      # list[OptionConstraintEvaluation]
    final_survivor_label: str | None
    confidence: float | None
    contradiction_check: bool
    parse_status: str = "ok"


def build_ltm_constraint_prompt(sample: dict, route: str) -> str:
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    opts = "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, choices))
    return (
        "Decompose the question into atomic constraints, then test EACH option against EACH "
        "constraint. Return a SINGLE JSON object with keys: "
        '"constraints" (list of atomic condition strings), '
        '"option_evaluations" (list of {"label", "passes_constraints":[bool,...], '
        '"eliminated":bool, "elimination_reason"}), '
        '"final_survivor_label" (the single surviving option or null), '
        '"confidence" (0..1), "contradiction_check" (true if exactly one option is consistent). '
        f"Route hint: {route}.\n\nQuestion:\n{sample.get('question','')}\n\n"
        f"Options:\n{opts}\n\nReturn JSON now."
    )


def parse_constraint_table(model_json: dict) -> ConstraintTableDecision:
    if not isinstance(model_json, dict):
        return ConstraintTableDecision([], [], None, None, False, "parse_error")
    cons = []
    for i, c in enumerate(model_json.get("constraints") or []):
        cons.append(Constraint(text=str(c), index=i))
    evals = []
    for ev in model_json.get("option_evaluations") or []:
        if not isinstance(ev, dict):
            continue
        passes = ev.get("passes_constraints") or []
        passes = [bool(x) for x in passes] if isinstance(passes, list) else []
        evals.append(OptionConstraintEvaluation(
            label=str(ev.get("label") or "").strip().upper()[:1] or None,
            passes_constraints=passes,
            eliminated=bool(ev.get("eliminated", False)),
            elimination_reason=str(ev.get("elimination_reason") or "")))
    surv = model_json.get("final_survivor_label")
    surv = str(surv).strip().upper()[:1] if surv else None
    return ConstraintTableDecision(
        constraints=cons, option_evaluations=evals, final_survivor_label=surv,
        confidence=model_json.get("confidence"),
        contradiction_check=bool(model_json.get("contradiction_check", False)),
        parse_status="ok")


def _survivors(decision: ConstraintTableDecision):
    out = []
    for ev in decision.option_evaluations:
        if ev.label and not ev.eliminated and (not ev.passes_constraints or all(ev.passes_constraints)):
            out.append(ev.label)
    return out


def validate_constraint_table(decision: ConstraintTableDecision, sample: dict):
    """(valid, reason). Requires parse ok, constraints present, a contradiction check that
    holds, and EXACTLY ONE surviving option that is a valid label for the sample."""
    if decision.parse_status != "ok":
        return False, "parse_error"
    if not decision.constraints:
        return False, "no_constraints"
    if not decision.option_evaluations:
        return False, "no_option_evaluations"
    survivors = _survivors(decision)
    if len(survivors) == 0:
        return False, "no_survivor"
    if len(survivors) > 1:
        return False, "multiple_survivors"
    if not decision.contradiction_check:
        return False, "contradiction_check_failed"
    surv = survivors[0]
    if decision.final_survivor_label and decision.final_survivor_label != surv:
        return False, "survivor_label_inconsistent"
    if not is_valid_label(surv, sample):
        return False, "invalid_label_for_sample"
    return True, "ok"


def select_answer_from_constraint_table(decision: ConstraintTableDecision, sample: dict) -> dict:
    valid, reason = validate_constraint_table(decision, sample)
    if not valid:
        return {"ok": False, "proposed_label": None, "rejection_reason": reason,
                "survivors": _survivors(decision)}
    surv = _survivors(decision)[0]
    return {"ok": True, "proposed_label": surv, "rejection_reason": "",
            "confidence": decision.confidence, "survivors": [surv]}
