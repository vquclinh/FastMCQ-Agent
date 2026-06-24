"""Unified dynamic override selector for V12B + V13 (Phase 2L.37A).

Combines the official V12B debiaser results and the V13 multi-layer results into a single
conservative override decision per qid, on top of the dynamic base predictions. Uses no public
answers and no ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.labels import is_valid_label

_WEAK_TOKENS = ("fallback", "weak", "single_source", "dynamic_api", "api:")
_STRONG_CONF = 0.6


@dataclass
class SystemOverrideDecision:
    qid: str
    accept: bool
    proposed_answer: str | None
    source_layers: list
    reason: str
    confidence: float | None = None
    metadata: dict = field(default_factory=dict)


def _is_weak(bp):
    return (any(t in (bp.source or "") for t in _WEAK_TOKENS)
            or any(t in (bp.risk_reason or "") for t in ("fallback", "weak"))
            or bp.confidence is None
            or (isinstance(bp.confidence, (int, float)) and bp.confidence < 0.66))


def select_system_overrides(samples, base_predictions, v12b_results, v13_results,
                            *, policy="conservative", max_overrides=None):
    by_qid = {s["qid"]: s for s in samples}
    base_by = {bp.qid: bp for bp in base_predictions}
    v12b_by = {r.qid: r for r in (v12b_results or [])}
    v13_by = {}
    for r in (v13_results or []):
        v13_by.setdefault(r.qid, {})[r.layer] = r

    decisions = []
    for s in samples:
        qid = s["qid"]
        bp = base_by.get(qid)
        current = bp.answer if bp else None
        weak = _is_weak(bp) if bp else True

        v12b = v12b_by.get(qid)
        v12b_label = (v12b.proposed_answer if (v12b and v12b.accept and v12b.proposed_answer
                      and v12b.proposed_answer != current) else None)

        layers = v13_by.get(qid, {})
        def _lab(name):
            r = layers.get(name)
            return (r.proposed_answer if (r and r.accept and r.proposed_answer
                    and r.proposed_answer != current) else None)
        prog = _lab("programmatic_solver")
        content = _lab("content_first")
        ltm = _lab("least_to_most")
        content_conf = (layers.get("content_first").confidence
                        if layers.get("content_first") else None)

        def _valid(lbl):
            return bool(lbl) and is_valid_label(lbl, s)

        accept, proposed, srcs, reason, conf = False, None, [], "no_override", None

        # 1) V12B conservative result (already passed V12B policy).
        if _valid(v12b_label):
            accept, proposed, srcs, reason = True, v12b_label, ["v12b"], "v12b_conservative"
        # 2) Programmatic unique deterministic match.
        elif _valid(prog):
            accept, proposed, srcs, reason = True, prog, ["programmatic_solver"], "programmatic_unique"
        # 3) Cross-layer agreement.
        elif _valid(content) and content == ltm:
            accept, proposed, srcs, reason = True, content, ["content_first", "least_to_most"], "content+ltm_agree"
        elif _valid(content) and content == v12b_label:
            accept, proposed, srcs, reason = True, content, ["content_first", "v12b"], "content+v12b_agree"
        elif _valid(content) and content == prog:
            accept, proposed, srcs, reason = True, content, ["programmatic_solver", "content_first"], "programmatic+content_agree"
        # 4) Content-first alone — strong confidence AND (weak current OR another layer present).
        elif _valid(content) and (content_conf or 0) >= _STRONG_CONF and (weak or ltm or prog):
            accept, proposed, srcs, reason, conf = True, content, ["content_first"], "content_first_strong", content_conf
        # 5) Least-to-most alone — single survivor AND (weak current OR another layer).
        elif _valid(ltm) and (weak or content or prog):
            accept, proposed, srcs, reason = True, ltm, ["least_to_most"], "ltm_eliminates_current"

        decisions.append(SystemOverrideDecision(
            qid=qid, accept=accept, proposed_answer=proposed if accept else None,
            source_layers=srcs, reason=reason, confidence=conf,
            metadata={"current": current, "weak_current": weak}))

    accepted = [d for d in decisions if d.accept]
    if max_overrides is not None and len(accepted) > max_overrides:
        # keep the strongest: v12b/programmatic/cross-layer before single-source
        rank = {"v12b_conservative": 0, "programmatic_unique": 1, "content+ltm_agree": 2,
                "content+v12b_agree": 2, "programmatic+content_agree": 2,
                "content_first_strong": 3, "ltm_eliminates_current": 3}
        accepted.sort(key=lambda d: (rank.get(d.reason, 9), d.qid))
        keep = {d.qid for d in accepted[:max_overrides]}
        for d in decisions:
            if d.accept and d.qid not in keep:
                d.accept = False
                d.proposed_answer = None
                d.reason = "dropped_max_overrides"
    return decisions
