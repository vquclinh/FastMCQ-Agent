"""V12B option-permutation debiaser as a dynamic architecture layer.

Runs over arbitrary inputs with feature-based target selection and the shared local Qwen backend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.utils.labels import labels_for
from src.layers.mcq_permutation_debiaser import (
    build_option_permutations, map_permuted_answer_to_original,
    summarize_permutation_votes, select_permutation_override)
from src.local_model.local_qwen_backend import get_local_qwen_backend, parse_json_object


def _log(msg):
    print(msg, flush=True)


def _load_completed_v12b(path):
    """Load completed V12B records keyed by (qid, permutation_id) for resume. Tolerates a
    partial/corrupt trailing line."""
    done = {}
    if not Path(path).exists():
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            key = (rec.get("original_qid"), rec.get("permutation_id"))
            if key[0] and key[1]:
                done[key] = rec
    return done


_MULTI_COND_HINTS = ("đúng", "sai", "phát biểu", "chọn câu", "không đúng", "ngoại trừ",
                     "statement", "which of the following", "true", "false", "except")
_WEAK_SOURCE_TOKENS = ("fallback", "weak", "single_source", "dynamic_local_qwen")


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


def run_v12b_layer(samples, base_predictions, targets, *, model_path=None, local_backend=None,
                   max_new_tokens=384, permutations=6, policy="conservative",
                   work_dir="scratch/v12b_dynamic", resume=False):
    by_qid = {s["qid"]: s for s in samples}
    cur = {bp.qid: bp.answer for bp in base_predictions}
    backend = local_backend or get_local_qwen_backend(
        model_path, default_max_new_tokens=max_new_tokens)

    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    rec_path = work / "v12b_dynamic_records.jsonl"

    # Resume: load completed (qid, permutation_id) units; reopen JSONL in append mode.
    completed = _load_completed_v12b(rec_path) if resume else {}
    if resume and completed:
        _log(f"[V12B] resume loaded={len(completed)} skipped={len(completed)}")
    fh = open(rec_path, "a" if (resume and completed) else "w", encoding="utf-8")

    def _emit(rec):
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()

    n_recs = 0
    results = []
    try:
        for t in targets:
            s = by_qid.get(t.qid)
            if not s or len(s.get("choices") or []) < 2:
                results.append(V12BLayerResult(t.qid, None, False, "no_choices", {}, 0, None, {}))
                continue
            perms = build_option_permutations(s, n=permutations)
            records = []
            for j, perm in enumerate(perms, start=1):
                key = (t.qid, perm.permutation_id)
                if key in completed:                 # resume: reuse, do not re-call/duplicate
                    records.append(completed[key])
                    continue
                _log(f"[V12B] qid={t.qid} permutation={j}/{len(perms)}")
                try:
                    content = backend.generate_text(
                        _prompt(perm, s.get("question", "")),
                        max_new_tokens=max_new_tokens)
                    parsed = parse_json_object(content) or {}
                    res = map_permuted_answer_to_original(
                        s, perm, parsed.get("selected_label"), parsed.get("selected_option_text"),
                        parsed.get("label_matches_option"))
                    rec = {"original_qid": t.qid, "permutation_id": perm.permutation_id,
                           "mapped_original_label": res.mapped_original_label,
                           "parse_status": "ok" if parsed else "parse_error",
                           "label_option_match": res.label_option_match, "valid": res.valid,
                           "failure_reason": res.failure_reason,
                           "confidence": parsed.get("confidence")}
                except Exception as exc:
                    rec = {"original_qid": t.qid, "permutation_id": perm.permutation_id,
                           "mapped_original_label": None, "parse_status": "local_error",
                           "label_option_match": False, "valid": False,
                           "failure_reason": type(exc).__name__, "confidence": None}
                records.append(rec); _emit(rec); n_recs += 1
            summ = summarize_permutation_votes(t.qid, cur.get(t.qid, ""), records)
            dec = select_permutation_override(summ, policy=policy)
            results.append(V12BLayerResult(
                qid=t.qid, proposed_answer=dec.proposed_answer, accept=dec.accept,
                reason=dec.reason, vote_counts=summ.vote_counts, valid_votes=summ.valid_records,
                records_path=str(rec_path), metadata={"priority_score": t.priority_score}))
    finally:
        fh.close()
    _log(f"[V12B] done records={n_recs} path={rec_path}")
    return results
