"""Direct production inference path (Phase 2L.21) — route prompts + hints + repair.

Ties together the route-aware prompts (``production_prompts``), option-aware evidence
(``option_evidence``), formula hints (``formula_bank_solver.detect_formula_hints``),
and a single JSON-repair retry. The base call goes through an injected ``client`` with
a ``.chat(messages, ...) -> result.content`` interface — so this is fully testable
with a fake client and makes NO network call by itself. No qid logic, no answer table.

This is an injectable direct-prompt helper for local/fake clients.
"""

from __future__ import annotations

from src.layers.adaptive_routing import route_to_branch
from src.solvers.formula_bank_solver import detect_formula_hints
from src.utils.labels import labels_for
from src.evidence.option_evidence import build_option_aware_evidence_pack
from src.system.production_prompts import answer_needs_repair, build_production_prompt, build_repair_prompt
from src.layers.question_profiler import profile_question
from src.layers.question_router import route_question
from src.utils.structured_answer import parse_structured_answer

_FALLBACK = "A"


def _parse(content, labels):
    try:
        sa = parse_structured_answer(content or "", labels)
        return (sa.answer if sa.answer in labels else None), sa.to_dict().get("source", "")
    except Exception:
        return None, "parse_error"


def predict_one_direct(client, sample, *, json_repair_retry=True, route_prompts=True,
                       option_evidence=True, use_hints=True, temperature=0.0,
                       max_tokens=512):
    """Return (answer, record). One base call + at most one repair retry. No multi-sampling."""
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    route = route_question(profile_question(sample)).route if route_prompts else "default"
    branch = route_to_branch(route)
    question = str(sample.get("question", "") or "")

    evidence = None
    ev_log = {}
    if option_evidence and branch == "long_context":
        pack = build_option_aware_evidence_pack(sample)
        if pack.matched:
            evidence = pack.pack_text
            ev_log = {"evidence_pack_size": pack.evidence_pack_size,
                      "evidence_selected_by_option": pack.evidence_selected_by_option,
                      "top_option_evidence_scores": pack.top_option_evidence_scores}

    hints = []
    if use_hints:
        hints = [h["hint"] for h in detect_formula_hints(sample) if not h["safe_to_override"]]

    messages = build_production_prompt(route, question, choices,
                                       evidence=evidence, hints=hints or None)
    res = client.chat(messages, response_format={"type": "json_object"},
                      temperature=temperature, max_tokens=max_tokens)
    answer, source = _parse(getattr(res, "content", ""), labels)

    retry_count = 0
    repair_status = "not_needed"
    if json_repair_retry and answer_needs_repair(answer, choices):
        retry_count = 1
        rmsg = build_repair_prompt(question, choices)
        rres = client.chat(rmsg, response_format={"type": "json_object"},
                           temperature=0.0, max_tokens=64)
        ranswer, _ = _parse(getattr(rres, "content", ""), labels)
        if ranswer in labels:
            answer, repair_status = ranswer, "repaired"
        else:
            repair_status = "repair_failed"

    final = answer if answer in labels else _FALLBACK
    rec = {"qid": sample.get("qid"), "route": route, "branch": branch,
           "answer": final, "parse_source": source, "retry_count": retry_count,
           "repair_status": repair_status, "hints_attached": len(hints),
           "solver": "production_direct", **ev_log}
    return final, rec
