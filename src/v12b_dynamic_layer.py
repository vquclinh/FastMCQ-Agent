"""Official V12B option-permutation debiaser as a dynamic architecture layer (Phase 2L.36B).

Wraps ``src.mcq_permutation_debiaser`` so the V12B debiaser runs over ARBITRARY inputs (not the
public frozen CSV). Target selection is purely feature-based (no qid hardcoding). The layer only
calls the model under explicit ``execute_api=True``; otherwise it reports the selected targets as
skipped (``skipped_no_api``) and applies nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.labels import labels_for
from src.mcq_permutation_debiaser import (
    build_option_permutations, map_permuted_answer_to_original,
    summarize_permutation_votes, select_permutation_override)

_MULTI_COND_HINTS = ("đúng", "sai", "phát biểu", "chọn câu", "không đúng", "ngoại trừ",
                     "statement", "which of the following", "true", "false", "except")
_WEAK_SOURCE_TOKENS = ("fallback", "weak", "single_source", "api:", "dynamic_api")


@dataclass
class V12BTarget:
    qid: str
    priority_score: float
    reason: str
    current_answer: str
    option_count: int
    route: str
    risk_reason: str


@dataclass
class V12BLayerResult:
    qid: str
    proposed_answer: str | None
    accept: bool
    reason: str
    vote_counts: dict = field(default_factory=dict)
    valid_votes: int = 0
    records_path: str | None = None
    metadata: dict = field(default_factory=dict)


def _multi_condition(question):
    q = (question or "").lower()
    return any(h in q for h in _MULTI_COND_HINTS)


def select_v12b_targets(samples, base_predictions, *, max_qids=None):
    """Feature-based target ranking — NO qid hardcoding."""
    by_qid = {s["qid"]: s for s in samples}
    targets = []
    for bp in base_predictions:
        s = by_qid.get(bp.qid)
        if not s:
            continue
        choices = s.get("choices") or []
        n = len(choices)
        q = s.get("question") or ""
        risk = bp.risk_reason or ""
        reasons, score = [], 0.0

        if any(tok in (bp.source or "") for tok in _WEAK_SOURCE_TOKENS) or \
                any(tok in risk for tok in ("fallback", "weak")):
            score += 4.0; reasons.append("weak_or_fallback_source")
        if bp.confidence is None or (isinstance(bp.confidence, (int, float)) and bp.confidence < 0.66):
            score += 2.0; reasons.append("low_confidence")
        if n >= 5:
            score += 2.0; reasons.append(f"option_count:{n}")
        if n > 8:
            score += 1.0; reasons.append("labels_beyond_H")
        if _multi_condition(q):
            score += 1.5; reasons.append("multi_condition")
        if len(q) > 600:
            score += 1.0; reasons.append("long_question")
        if (bp.route or "") in ("long_context", "law_admin", "ambiguous"):
            score += 1.0; reasons.append(f"route:{bp.route}")

        if score <= 0:
            continue
        targets.append(V12BTarget(
            qid=bp.qid, priority_score=round(score, 3),
            reason=";".join(reasons), current_answer=bp.answer,
            option_count=n, route=bp.route or "", risk_reason=risk))
    targets.sort(key=lambda t: (-t.priority_score, t.qid))
    return targets[:max_qids] if max_qids else targets


def _prompt(perm, question):
    opts = "\n".join(f"{pc['label']}. {pc['text']}" for pc in perm.permuted_choices)
    sys_msg = (
        "You are an independent MCQ solver. Answer FROM SCRATCH using only the options shown. "
        "Respond with a SINGLE JSON object ONLY. Required keys: "
        '"selected_label", "selected_option_text" (verbatim), "confidence" (0..1), '
        '"reason_type", "label_matches_option" (true/false), "evidence". '
        "If unsure set selected_label to null.")
    return [{"role": "system", "content": sys_msg},
            {"role": "user", "content": f"Question:\n{question}\n\nOptions:\n{opts}\n\nReturn JSON now."}]


def run_v12b_layer(samples, base_predictions, targets, *, model=None, execute_api=False,
                   budget_usd=None, permutations=6, policy="conservative",
                   work_dir="scratch/v12b_dynamic", resume=False):
    by_qid = {s["qid"]: s for s in samples}
    cur = {bp.qid: bp.answer for bp in base_predictions}

    if not execute_api:
        # Do NOT pretend to run — report each target as skipped, apply nothing.
        return [V12BLayerResult(qid=t.qid, proposed_answer=None, accept=False,
                                reason="skipped_no_api", vote_counts={}, valid_votes=0,
                                records_path=None,
                                metadata={"priority_score": t.priority_score}) for t in targets]

    from src.model_policy import assert_allowed_llm_model
    assert_allowed_llm_model(model)
    from src.selective_api_client import SelectiveAPIClient
    client = SelectiveAPIClient(model=model)

    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    rec_path = work / "v12b_dynamic_records.jsonl"
    results, all_records = [], []
    for t in targets:
        s = by_qid.get(t.qid)
        if not s or len(s.get("choices") or []) < 2:
            results.append(V12BLayerResult(t.qid, None, False, "no_choices", {}, 0, None, {}))
            continue
        records = []
        for perm in build_option_permutations(s, n=permutations):
            content, _u = client.chat(_prompt(perm, s.get("question", "")))
            parsed = client.parse_json(content) or {}
            res = map_permuted_answer_to_original(
                s, perm, parsed.get("selected_label"), parsed.get("selected_option_text"),
                parsed.get("label_matches_option"))
            rec = {"original_qid": t.qid, "permutation_id": perm.permutation_id,
                   "mapped_original_label": res.mapped_original_label,
                   "parse_status": "ok" if parsed else "parse_error",
                   "label_option_match": res.label_option_match, "valid": res.valid,
                   "confidence": parsed.get("confidence")}
            records.append(rec); all_records.append(rec)
        summ = summarize_permutation_votes(t.qid, cur.get(t.qid, ""), records)
        dec = select_permutation_override(summ, policy=policy)
        results.append(V12BLayerResult(
            qid=t.qid, proposed_answer=dec.proposed_answer, accept=dec.accept,
            reason=dec.reason, vote_counts=summ.vote_counts, valid_votes=summ.valid_records,
            records_path=str(rec_path), metadata={"priority_score": t.priority_score}))
    with rec_path.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return results
