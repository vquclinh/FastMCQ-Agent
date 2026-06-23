"""V13 multi-layer reasoning as a dynamic architecture layer (Phase 2L.37A).

Integrates the three V13 methods — programmatic solver, content-first normalizer, least-to-most
constraint table — into the real dynamic system over ARBITRARY inputs. Target assignment is
feature-based (no qid hardcoding). API is called only under explicit ``execute_api``; otherwise
each layer is reported ``skipped_no_api`` EXCEPT the programmatic solver, whose deterministic
arithmetic path may run without API when the question is a simple computable expression.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.labels import is_valid_label, labels_for
from src import programmatic_solver_layer as PS
from src import content_first_answerer as CF
from src import least_to_most_constraint_solver as LTM

_MULTI_COND_HINTS = ("đúng", "sai", "phát biểu", "chọn câu", "không đúng", "ngoại trừ",
                     "statement", "which of the following", "true", "false", "except")
_CONTENT_HINTS = ("tục ngữ", "thành ngữ", "nghĩa", "định nghĩa", "là gì", "thuật ngữ",
                  "khái niệm", "đồng nghĩa", "proverb", "definition", "term", "meaning")
_WEAK_TOKENS = ("fallback", "weak", "single_source", "dynamic_api", "api:")
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
    """No-API deterministic arithmetic path: if the question is a simple computable expression
    and a single option matches, return (label, option_text, value); else None."""
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


def _interpret_api(layer, sample, parsed):
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


def _prompt(layer, sample, route):
    if layer == "programmatic_solver":
        return PS.build_programmatic_prompt(sample, PS.classify_programmatic_domain(sample))
    if layer == "content_first":
        return CF.build_content_first_prompt(sample, route)
    return LTM.build_ltm_constraint_prompt(sample, route)


def run_v13_layer(samples, base_predictions, targets, *, model=None, execute_api=False,
                  budget_usd=None, work_dir="scratch/v13_dynamic", resume=False):
    by_qid = {s["qid"]: s for s in samples}
    client = None
    if execute_api:
        from src.model_policy import assert_allowed_llm_model
        assert_allowed_llm_model(model)
        from src.selective_api_client import SelectiveAPIClient
        client = SelectiveAPIClient(model=model)

    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    results, raw = [], []
    for t in targets:
        s = by_qid.get(t.qid)
        if not s:
            continue
        for layer in t.target_layers:
            if not execute_api:
                # Deterministic-only path: programmatic arithmetic may run offline.
                if layer == "programmatic_solver":
                    det = _deterministic_programmatic(s)
                    if det and det[0] != t.current_answer and is_valid_label(det[0], s):
                        results.append(V13LayerResult(
                            t.qid, layer, det[0], det[1], True, 1.0,
                            "deterministic_arithmetic", f"value={det[2]}",
                            {"mode": "deterministic_no_api"}))
                        continue
                    if det:
                        results.append(V13LayerResult(
                            t.qid, layer, det[0], det[1], False, 1.0,
                            "deterministic_matches_current", f"value={det[2]}",
                            {"mode": "deterministic_no_api"}))
                        continue
                results.append(V13LayerResult(t.qid, layer, None, None, False, None,
                                              "skipped_no_api", "", {"mode": "no_api"}))
                continue
            # API path.
            content, _u = client.chat(_prompt(layer, s, t.route))
            parsed = client.parse_json(content) or {}
            lab, text, evid, valid, reason = _interpret_api(layer, s, parsed)
            accept = bool(valid and lab and lab != t.current_answer and is_valid_label(lab, s))
            results.append(V13LayerResult(
                t.qid, layer, lab, text, accept, parsed.get("confidence"),
                reason or "ok", str(evid or "")[:200], {"mode": "api"}))
            raw.append({"qid": t.qid, "layer": layer, "proposed": lab, "accept": accept})
    if raw:
        (work / "v13_dynamic_records.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in raw), encoding="utf-8")
    return results
