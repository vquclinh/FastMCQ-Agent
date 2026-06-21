#!/usr/bin/env python3
"""Audit long_context evidence sufficiency (no API, no answer changes).

Scores each long_context sample's reranked/compressed evidence (from the v6b log)
with the deterministic lexical heuristic in ``src/evidence_sufficiency.py`` and
reports the sufficiency distribution + recommendations. No network, no ground truth,
no qid-based decisions, no prediction written.

Usage:
    python scripts/audit_long_context_evidence_sufficiency.py \
      --input public-test_1780368312.json \
      --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --risk-csv outputs/first100_consensus_risk_audit.csv \
      --output outputs/long_context_evidence_sufficiency_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_log, load_risk_priority, load_samples, write_csv  # noqa: E402
from src.evidence_sufficiency import compute_evidence_sufficiency  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.question_profiler import profile_question  # noqa: E402
from src.question_router import route_question  # noqa: E402

_FIELDS = ["qid", "route", "current_answer", "status", "recommendation",
           "question_coverage", "current_answer_support", "best_other_support",
           "multiple_equally_supported", "evidence_chars", "has_evidence",
           "in_first100_p0p1"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Long-context evidence sufficiency audit (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-log", required=True)
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--output", default="outputs/long_context_evidence_sufficiency_audit.csv")
    args = ap.parse_args(argv)

    samples = load_samples(args.input)
    log = load_log(args.base_log)
    risk = load_risk_priority(args.risk_csv)

    status_ct = Counter()
    rec_ct = Counter()
    weak_insufficient = []
    overlap = 0
    rows = []

    for s in samples:
        qid = s.get("qid")
        route = route_question(profile_question(s)).route
        if route != "long_context":
            continue
        tr = log.get(qid, {})
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        current = tr.get("final_answer")
        evidence = tr.get("compressed_question") or s.get("question", "")
        es = compute_evidence_sufficiency(s.get("question", ""), choices, current,
                                          evidence, labels=labels)
        status_ct[es.status] += 1
        rec_ct[es.recommendation] += 1
        in_risk = qid in risk
        if es.status in ("weak", "insufficient"):
            weak_insufficient.append(qid)
            overlap += int(in_risk)
        rows.append({
            "qid": qid, "route": route, "current_answer": current,
            "status": es.status, "recommendation": es.recommendation,
            "question_coverage": es.question_coverage,
            "current_answer_support": es.current_answer_support,
            "best_other_support": es.best_other_support,
            "multiple_equally_supported": es.multiple_equally_supported,
            "evidence_chars": es.evidence_chars, "has_evidence": es.has_evidence,
            "in_first100_p0p1": in_risk,
        })

    write_csv(args.output, rows, _FIELDS)

    print("=" * 70)
    print("LONG-CONTEXT EVIDENCE SUFFICIENCY (no API; no answer changes)")
    print("=" * 70)
    print(f"long_context samples     : {len(rows)}")
    print(f"sufficiency distribution : {dict(status_ct)}")
    print(f"recommendation distribution: {dict(rec_ct)}")
    print(f"weak/insufficient qids   : {len(weak_insufficient)}")
    if args.risk_csv and Path(args.risk_csv).exists():
        print(f"weak/insufficient ∩ first-100 P0/P1: {overlap}")
    print(f"  sample weak/insufficient: {weak_insufficient[:30]}")
    print(f"audit CSV written: {args.output}")
    print("NOTE: lexical heuristic only; no answer changed; the LLM still decides.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
