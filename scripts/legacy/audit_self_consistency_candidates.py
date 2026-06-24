#!/usr/bin/env python3
"""Audit selective self-consistency / best-of-N candidates (no API, no changes).

Aggregates signals from the per-branch audits to pick which samples would most
benefit from a future self-consistency / best-of-N pass. No network, no ground
truth, no qid decisions, no prediction written.

Candidate rules (any one triggers):
  short_knowledge verifier-recommended; ambiguous route; law_admin with
  source_grounding_recommended; long_context weak/insufficient evidence;
  low confidence; parse review needed; deterministic calc disagreement with current.

Usage: see Phase 2L.16 Part I command.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import (load_log, load_pred, load_risk_priority,  # noqa: E402
                                          load_samples, write_csv)
from src.labels import labels_for  # noqa: E402
from src.programmatic_solver import candidate_for  # noqa: E402
from src.question_profiler import profile_question  # noqa: E402
from src.question_router import route_question  # noqa: E402

_FIELDS = ["qid", "route", "base_answer", "original_confidence", "priority",
           "trigger_reasons"]
_LOW_CONF = 0.7


def _csv_set(path, pred):
    """Load a candidate/audit CSV -> {qid: row} (empty if missing)."""
    out = {}
    if path and Path(path).exists():
        for r in csv.DictReader(open(path)):
            out[r.get("qid")] = r
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="self-consistency candidate audit (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--long-context-audit", default=None)
    ap.add_argument("--sk-candidates", default=None)
    ap.add_argument("--law-admin-candidates", default=None)
    ap.add_argument("--ambiguous-candidates", default=None)
    ap.add_argument("--output", default="output/self_consistency_candidates.csv")
    args = ap.parse_args(argv)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.base_log)
    risk = load_risk_priority(args.risk_csv)
    lc = _csv_set(args.long_context_audit, base)
    sk = _csv_set(args.sk_candidates, base)
    la = _csv_set(args.law_admin_candidates, base)
    amb = _csv_set(args.ambiguous_candidates, base)

    rows = []
    route_ct = Counter()
    reason_ct = Counter()
    for s in samples:
        qid = s.get("qid")
        route = route_question(profile_question(s)).route
        tr = log.get(qid, {})
        conf = tr.get("confidence")
        current = base.get(qid)
        reasons = []

        if qid in sk:                                   # SK verifier eligible
            reasons.append("short_knowledge_verifier_recommended")
        if route == "ambiguous":
            reasons.append("ambiguous_route")
        if qid in la:                                   # law_admin candidate
            reasons.append("law_admin_source_grounding")
        lcr = lc.get(qid)
        if lcr and lcr.get("status") in ("weak", "insufficient"):
            reasons.append(f"long_context_{lcr['status']}_evidence")
        if isinstance(conf, (int, float)) and conf < _LOW_CONF:
            reasons.append("low_confidence")
        pa = tr.get("parsed_answer") or {}
        if pa.get("needs_review") or pa.get("error") == "no_json" \
                or (tr.get("parsed_answer_source") == "partial_answer_key"):
            reasons.append("parse_review_needed")
        if route == "calculation" and current:          # deterministic disagreement
            try:
                cand = candidate_for(s, existing_answer=current)
                if cand.would_change_answer:
                    reasons.append("calc_deterministic_disagreement")
            except Exception:
                pass

        if reasons:
            route_ct[route] += 1
            for r in reasons:
                reason_ct[r] += 1
            rows.append({"qid": qid, "route": route, "base_answer": current,
                         "original_confidence": conf, "priority": risk.get(qid),
                         "trigger_reasons": "|".join(reasons)})

    write_csv(args.output, rows, _FIELDS)
    rec_max_calls = min(40, len(rows))
    print("=" * 70)
    print("SELF-CONSISTENCY CANDIDATES (no API; no answer changes)")
    print("=" * 70)
    print(f"total candidates       : {len(rows)}")
    print(f"route distribution     : {dict(route_ct)}")
    print(f"trigger reason dist     : {dict(reason_ct)}")
    print(f"recommended max-calls (controlled run): {rec_max_calls}")
    print(f"candidate CSV: {args.output}")
    print("NOTE: candidate selection only; no API; no answer changed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
