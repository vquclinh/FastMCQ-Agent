"""Adaptive accuracy / budget planner (Phase 2L.27A) — offline, no API.

Scores question difficulty and recommends the cheapest layer that is likely to help:
``tool_only`` (a safe deterministic tool already answers), ``evidence_pack``,
``cheap_api``, ``rich_api``, or ``manual_review``. Produces plans only — it never calls
an API or selects an answer. No qid logic, no answer table.
"""

from __future__ import annotations

from src.layers.adaptive_routing import route_to_branch
from src.solvers.formula_bank_solver import solve_formula_bank_sample
from src.layers.question_profiler import profile_question
from src.layers.question_router import route_question
from src.evidence.rag_lite import best_card

# Approximate API call counts per recommended layer (for budget estimation).
_LAYER_CALLS = {"tool_only": 0, "evidence_pack": 0, "cheap_api": 2, "rich_api": 5,
                "manual_review": 0}
_LOW_CONF = 0.7


def score_question_difficulty(sample, v10_record=None, factory_record=None) -> float:
    """0 (easy / deterministically solved) .. ~5 (hard, needs rich API)."""
    rec = v10_record or {}
    route = rec.get("route") or route_to_branch(route_question(profile_question(sample)).route)
    score = 0.0
    has_tool = solve_formula_bank_sample(sample) is not None
    if has_tool:
        return 0.0                                  # deterministic tool answers it
    conf = rec.get("confidence")
    if isinstance(conf, (int, float)) and conf < _LOW_CONF:
        score += 2.0
    if route == "calculation":
        score += 2.0                                # calc without a tool proof is risky
    if route == "long_context":
        chars = rec.get("evidence_selected_chars")
        score += 1.0 if (isinstance(chars, int) and chars < 800) else 0.5
    if route == "ambiguous":
        score += 1.5
    if route == "law_admin":
        score += 1.0
    if route == "short_knowledge" and best_card(sample.get("question", "")) is None:
        score += 1.0
    if rec.get("parsed_answer_source") == "partial_answer_key" or rec.get("parsed_answer_error") == "no_json":
        score += 1.5
    return round(score, 2)


def recommend_layers_for_question(sample, v10_record=None):
    rec = v10_record or {}
    route = rec.get("route") or route_to_branch(route_question(profile_question(sample)).route)
    if solve_formula_bank_sample(sample) is not None:
        return "tool_only"
    diff = score_question_difficulty(sample, rec)
    if route == "long_context":
        return "evidence_pack" if diff < 2 else "rich_api"
    if route == "short_knowledge":
        return "cheap_api" if best_card(sample.get("question", "")) is None else "evidence_pack"
    if route == "calculation":
        # Calculation is tool-first: a unique-option solver already returned tool_only
        # above; otherwise use a compact calc agent (cheap) unless the question is hard.
        from src.solvers.calculation_first_planner import recommend_calculation_strategy
        if recommend_calculation_strategy(sample)["strategy"] == "tool_only":
            return "tool_only"
        return "rich_api" if diff >= 3 else "cheap_api"
    if route in ("ambiguous", "law_admin"):
        return "cheap_api"
    return "cheap_api" if diff >= 2 else "evidence_pack"


def estimate_calls_for_plan(plan) -> int:
    return sum(_LAYER_CALLS.get(p.get("layer"), 0) for p in plan)


def build_adaptive_plan(samples, max_qids=120, budget_mode="balanced", v10_log=None):
    """Return a list of plan dicts (qid, route, layer, difficulty, est_calls), capped."""
    v10_log = v10_log or {}
    rows = []
    for s in samples:
        qid = s.get("qid")
        rec = v10_log.get(qid, {})
        route = rec.get("route") or route_to_branch(route_question(profile_question(s)).route)
        layer = recommend_layers_for_question(s, rec)
        diff = score_question_difficulty(s, rec)
        rows.append({"qid": qid, "route": route, "layer": layer,
                     "difficulty": diff, "est_calls": _LAYER_CALLS.get(layer, 0)})
    # Prioritize hardest non-tool questions; tool_only/evidence_pack need no API budget.
    needs_api = [r for r in rows if r["est_calls"] > 0]
    needs_api.sort(key=lambda r: (r["difficulty"], r["qid"]), reverse=True)
    if budget_mode == "cheap":
        needs_api = [r for r in needs_api if r["layer"] == "cheap_api"]
    selected = needs_api[: max(0, max_qids)]
    return rows, selected
