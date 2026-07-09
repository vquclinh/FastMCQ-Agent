"""V13 multi-layer reasoning as a dynamic architecture layer.

Integrates the three V13 methods — programmatic solver, content-first normalizer, least-to-most
constraint table — into the real dynamic system over ARBITRARY inputs. Target assignment is
feature-based (no qid hardcoding). Model-backed layers use the shared local Qwen backend.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.utils.labels import is_valid_label, labels_for
from src.layers import programmatic_solver_layer as PS
from src.layers import content_first_answerer as CF
from src.layers import least_to_most_constraint_solver as LTM
from src.local_model.local_qwen_backend import get_local_qwen_backend, parse_json_object

def _log(msg):
    print(msg, flush=True)


_MULTI_COND_HINTS = ("đúng", "sai", "phát biểu", "chọn câu", "không đúng", "ngoại trừ",
                     "statement", "which of the following", "true", "false", "except")
_CONTENT_HINTS = ("tục ngữ", "thành ngữ", "nghĩa", "định nghĩa", "là gì", "thuật ngữ",
                  "khái niệm", "đồng nghĩa", "proverb", "definition", "term", "meaning")
_WEAK_TOKENS = ("fallback", "weak", "single_source", "dynamic_local_qwen")
# Simple binary arithmetic, e.g. "2 + 2", "10 * 5", "12 / 4" (x/× treated as multiply).
_ARITH = re.compile(r"(-?\d+(?:\.\d+)?)\s*([+\-*x×/])\s*(-?\d+(?:\.\d+)?)")


@dataclass
class V13Target:
    qid: str
    target_layers: list
    priority_score: float
    reason: str
    current_answer: str
    option_count: int
    route: str
    risk_reason: str


@dataclass
class V13LayerResult:
    qid: str
    layer: str
    proposed_answer: str | None
    proposed_option_text: str | None
    accept: bool
    confidence: float | None
    reason: str
    evidence: str = ""
    metadata: dict = field(default_factory=dict)


def _is_weak(bp):
    return (any(t in (bp.source or "") for t in _WEAK_TOKENS)
            or any(t in (bp.risk_reason or "") for t in ("fallback", "weak"))
            or bp.confidence is None
            or (isinstance(bp.confidence, (int, float)) and bp.confidence < 0.66))


def _options_numeric(sample):
    return any(PS.extract_numeric_values(c) for c in (sample.get("choices") or []))


def select_v13_targets(samples, base_predictions, *, max_qids=None):
    by_qid = {s["qid"]: s for s in samples}
    targets = []
    for bp in base_predictions:
        s = by_qid.get(bp.qid)
        if not s:
            continue
        q = s.get("question") or ""
        ql = q.lower()
        choices = s.get("choices") or []
        n = len(choices)
        layers, reasons, score = [], [], 0.0

        domain = PS.classify_programmatic_domain(s)
        if domain in ("arithmetic", "economics", "geometry", "binary") or \
                (bp.route or "") == "calculation" or (PS.extract_numeric_values(q) and _options_numeric(s)):
            layers.append("programmatic_solver"); reasons.append(f"numeric:{domain}")
        if any(h in ql for h in _CONTENT_HINTS) or \
                (bp.route or "") in ("short_knowledge", "long_context", "ambiguous", "law_admin"):
            layers.append("content_first"); reasons.append("content_indicator")
        if any(h in ql for h in _MULTI_COND_HINTS) or (bp.route or "") in ("law_admin", "long_context"):
            layers.append("least_to_most"); reasons.append("multi_condition")

        if _is_weak(bp):
            score += 4.0; reasons.append("weak_or_low_conf_base")
        if n >= 5:
            score += 2.0; reasons.append(f"option_count:{n}")
        if len(q) > 600:
            score += 1.0; reasons.append("long_question")

        if not layers:
            layers = ["content_first"]; reasons.append("default_content_first")
        # de-dup layers preserving order
        seen, uniq = set(), []
        for L in layers:
            if L not in seen:
                seen.add(L); uniq.append(L)
        targets.append(V13Target(
            qid=bp.qid, target_layers=uniq, priority_score=round(score + len(uniq), 3),
            reason=";".join(reasons), current_answer=bp.answer, option_count=n,
            route=bp.route or "", risk_reason=bp.risk_reason or ""))
    targets.sort(key=lambda t: (-t.priority_score, t.qid))
    return targets[:max_qids] if max_qids else targets


def _deterministic_programmatic(sample):
    """If a simple computable expression maps to one option, return (label, option_text, value)."""
    q = str(sample.get("question") or "")
    m = _ARITH.search(q)
    if not m:
        return None
    a, op, b = m.group(1), m.group(2), m.group(3)
    op = {"x": "*", "×": "*"}.get(op, op)
    spec = PS.parse_calculation_spec({"operation": "arithmetic", "expression": f"{a}{op}{b}"})
    res = PS.match_result_to_options(PS.safe_execute_calculation(spec), sample)
    if res.ok and res.mapped_label:
        choices = sample.get("choices") or []
        labels = labels_for(len(choices))
        text = choices[labels.index(res.mapped_label)] if res.mapped_label in labels else None
        return res.mapped_label, text, res.value
    return None


def _interpret_model_json(layer, sample, parsed):
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    if layer == "programmatic_solver":
        spec = PS.parse_calculation_spec(parsed)
        res = PS.match_result_to_options(PS.safe_execute_calculation(spec), sample)
        lab = res.mapped_label
        return lab, (choices[labels.index(lab)] if lab in labels else None), \
            parsed.get("result_hint"), bool(res.ok and lab), res.failure_reason
    if layer == "content_first":
        ca = CF.parse_content_answer(parsed)
        m = CF.match_content_to_options(ca, sample)
        lab = m.mapped_label
        return lab, (choices[labels.index(lab)] if lab in labels else None), \
            ca.evidence, bool(m.ok and lab), m.failure_reason
    if layer == "least_to_most":
        dec = LTM.parse_constraint_table(parsed)
        out = LTM.select_answer_from_constraint_table(dec, sample)
        lab = out.get("proposed_label")
        return lab, (choices[labels.index(lab)] if lab in labels else None), \
            f"survivors={out.get('survivors')}", bool(out.get("ok")), out.get("rejection_reason")
    return None, None, None, False, "unknown_layer"


def _generic_verifier_prompt(sample):
    """Safe fallback prompt for unknown layer names (never empty)."""
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    opts = "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, choices))
    return ("Answer the multiple-choice question. Return a SINGLE JSON object only: "
            '{"selected_label": "<one option letter>", "selected_option_text": "<verbatim>", '
            '"confidence": 0..1}.\n\nQuestion:\n'
            f"{sample.get('question','')}\n\nOptions:\n{opts}\n\nJSON:")


def _prompt(layer, sample, route):
    """Return the raw prompt text for a layer (may be empty if the builder produced nothing)."""
    if layer == "programmatic_solver":
        return PS.build_programmatic_prompt(sample, PS.classify_programmatic_domain(sample))
    if layer == "content_first":
        return CF.build_content_first_prompt(sample, route)
    if layer == "least_to_most":
        return LTM.build_ltm_constraint_prompt(sample, route)
    return _generic_verifier_prompt(sample)   # unknown layer -> safe generic prompt


def build_messages(layer, sample, route):
    """Return (messages_list, prompt_len) or (None, 0) if the prompt is empty/invalid.
    Never returns an empty/whitespace prompt to the model backend."""
    text = (_prompt(layer, sample, route) or "").strip()
    if not text:
        return None, 0
    return [{"role": "user", "content": text}], len(text)


def _result_to_record(r: "V13LayerResult") -> dict:
    return {"qid": r.qid, "layer": r.layer, "proposed_answer": r.proposed_answer,
            "proposed_option_text": r.proposed_option_text, "accept": r.accept,
            "confidence": r.confidence, "reason": r.reason, "evidence": r.evidence,
            "metadata": r.metadata}


def _record_to_result(rec: dict) -> "V13LayerResult":
    return V13LayerResult(
        qid=rec.get("qid"), layer=rec.get("layer"), proposed_answer=rec.get("proposed_answer"),
        proposed_option_text=rec.get("proposed_option_text"), accept=bool(rec.get("accept")),
        confidence=rec.get("confidence"), reason=rec.get("reason") or "",
        evidence=rec.get("evidence") or "", metadata=rec.get("metadata") or {})


def _load_completed(path):
    """Load completed V13 records keyed by (qid, layer). Tolerates partial/corrupt last line."""
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
                continue   # skip a partial/corrupt trailing line
            key = (rec.get("qid"), rec.get("layer"))
            if key[0] and key[1]:
                done[key] = rec
    return done


def run_v13_layer(samples, base_predictions, targets, *, model_path=None, local_backend=None,
                  max_new_tokens=768, work_dir="scratch/v13_dynamic", resume=False):
    by_qid = {s["qid"]: s for s in samples}
    backend = local_backend or get_local_qwen_backend(
        model_path, default_max_new_tokens=max_new_tokens)

    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    rec_path = work / "v13_dynamic_records.jsonl"

    # Resume: load completed (qid, layer) units; reopen the JSONL in append mode.
    completed = _load_completed(rec_path) if resume else {}
    if resume and completed:
        _log(f"[V13] resume loaded={len(completed)} skipped={len(completed)}")
    fh = open(rec_path, "a" if (resume and completed) else "w", encoding="utf-8")

    def _emit(result):
        fh.write(json.dumps(_result_to_record(result), ensure_ascii=False) + "\n")
        fh.flush()

    total = sum(len(t.target_layers) for t in targets)
    results, idx = [], 0
    try:
        for t in targets:
            s = by_qid.get(t.qid)
            if not s:
                continue
            for layer in t.target_layers:
                idx += 1
                key = (t.qid, layer)
                if key in completed:                 # resume: reuse, do not re-call/duplicate
                    results.append(_record_to_result(completed[key]))
                    continue

                if layer == "programmatic_solver":
                    det = _deterministic_programmatic(s)
                    if det and det[0] != t.current_answer and is_valid_label(det[0], s):
                        r = V13LayerResult(t.qid, layer, det[0], det[1], True, 1.0,
                                           "deterministic_arithmetic", f"value={det[2]}",
                                           {"mode": "deterministic"})
                        results.append(r); _emit(r); continue
                    if det:
                        r = V13LayerResult(t.qid, layer, det[0], det[1], False, 1.0,
                                           "deterministic_matches_current", f"value={det[2]}",
                                           {"mode": "deterministic"})
                        results.append(r); _emit(r); continue
                    r = V13LayerResult(t.qid, layer, None, None, False, None,
                                       "no_deterministic_programmatic_match", "",
                                       {"mode": "deterministic"})
                    results.append(r); _emit(r); continue

                # Local model path: build + validate the prompt BEFORE generation.
                messages, plen = build_messages(layer, s, t.route)
                if messages is None:
                    _log(f"[V13] skip qid={t.qid} layer={layer} reason=empty_prompt")
                    r = V13LayerResult(t.qid, layer, None, None, False, None,
                                       "skipped_empty_prompt", "", {"mode": "local_qwen"})
                    results.append(r); _emit(r); continue
                try:
                    _log(f"[V13] {idx}/{total} qid={t.qid} layer={layer} prompt_len={plen}")
                    content = backend.generate_text(messages, max_new_tokens=max_new_tokens)
                    parsed = parse_json_object(content) or {}
                    lab, text, evid, valid, reason = _interpret_model_json(layer, s, parsed)
                    accept = bool(valid and lab and lab != t.current_answer and is_valid_label(lab, s))
                    r = V13LayerResult(t.qid, layer, lab, text, accept, parsed.get("confidence"),
                                       reason or "ok", str(evid or "")[:200], {"mode": "local_qwen"})
                except Exception as exc:
                    r = V13LayerResult(t.qid, layer, None, None, False, None,
                                       f"local_error:{type(exc).__name__}", "",
                                       {"mode": "local_qwen"})
                results.append(r); _emit(r)
    finally:
        fh.close()
    _log(f"[V13] done records={len(results)} path={rec_path}")
    return results
