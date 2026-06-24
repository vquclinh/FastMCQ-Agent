#!/usr/bin/env python3
"""Audit ambiguous-route adjudicator candidates (no API, no answer changes).

Usage:
    python scripts/audit_ambiguous_adjudicator_candidates.py \
      --input public-test_1780368312.json \
      --base-pred output/pred_v7_programmatic_assist_from_v6b.csv \
      --base-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --risk-csv output/first100_consensus_risk_audit.csv \
      --output output/ambiguous_adjudicator_candidates.csv
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import (load_log, load_pred, load_risk_priority,  # noqa: E402
                                          load_samples, write_csv)
from src.question_profiler import profile_question  # noqa: E402
from src.question_router import route_question  # noqa: E402

_FIELDS = ["qid", "route", "base_answer", "original_confidence", "priority",
           "trigger_reasons", "eligible"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ambiguous adjudicator candidate audit (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--output", default="output/ambiguous_adjudicator_candidates.csv")
    args = ap.parse_args(argv)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.base_log)
    risk = load_risk_priority(args.risk_csv)

    total = eligible = overlap = 0
    answer_dist = Counter()
    reason_ct = Counter()
    rows = []
    for s in samples:
        qid = s.get("qid")
        if route_question(profile_question(s)).route != "ambiguous":
            continue
        total += 1
        current = base.get(qid)
        is_elig = bool(current)
        reasons = ["needs_adjudication", "duplicate_or_unclear_choices"] if is_elig else []
        if is_elig:
            eligible += 1
            answer_dist[current] += 1
            for r in reasons:
                reason_ct[r] += 1
            overlap += int(qid in risk)
        rows.append({"qid": qid, "route": "ambiguous", "base_answer": current,
                     "original_confidence": log.get(qid, {}).get("confidence"),
                     "priority": risk.get(qid), "trigger_reasons": "|".join(reasons),
                     "eligible": is_elig})

    write_csv(args.output, rows, _FIELDS)
    print("=" * 64)
    print("AMBIGUOUS ADJUDICATOR CANDIDATES (no API; no answer changes)")
    print("=" * 64)
    print(f"ambiguous samples : {total}")
    print(f"eligible          : {eligible}")
    print(f"trigger reasons   : {dict(reason_ct)}")
    print(f"current answer dist: {dict(answer_dist)}")
    if args.risk_csv and Path(args.risk_csv).exists():
        print(f"eligible ∩ first-100 P0/P1: {overlap}")
    print(f"candidate CSV: {args.output}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
