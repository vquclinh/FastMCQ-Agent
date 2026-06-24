#!/usr/bin/env python3
"""Audit law_admin verifier candidates (no API, no answer changes).

Flags law_admin samples eligible for stricter source-grounded verification. No
network, no ground truth, no qid-based decisions, no prediction written. The risk
CSV (optional) is used only to count first-100 P0/P1 overlap.

Usage:
    python scripts/audit_law_admin_verifier_candidates.py \
      --input public-test_1780368312.json \
      --base-pred output/pred_v7_programmatic_assist_from_v6b.csv \
      --base-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --risk-csv output/first100_consensus_risk_audit.csv \
      --output output/law_admin_verifier_candidates.csv
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


def law_admin_triggers(confidence, trigger_confidence_max=0.95):
    """law_admin items always warrant source grounding; add low-confidence flag."""
    reasons = ["source_grounding_recommended"]
    if isinstance(confidence, (int, float)) and confidence <= trigger_confidence_max:
        reasons.append("low_confidence")
    reasons.append("verifier_recommended")
    return reasons


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="law_admin verifier candidate audit (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--trigger-confidence-max", type=float, default=0.95)
    ap.add_argument("--output", default="output/law_admin_verifier_candidates.csv")
    args = ap.parse_args(argv)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.base_log)
    risk = load_risk_priority(args.risk_csv)

    total = eligible = overlap = 0
    reason_ct = Counter()
    rows = []
    for s in samples:
        qid = s.get("qid")
        if route_question(profile_question(s)).route != "law_admin":
            continue
        total += 1
        current = base.get(qid)
        conf = log.get(qid, {}).get("confidence")
        is_elig = bool(current)            # valid current answer required
        reasons = law_admin_triggers(conf, args.trigger_confidence_max) if is_elig else []
        if is_elig:
            eligible += 1
            for r in reasons:
                reason_ct[r] += 1
            overlap += int(qid in risk)
        rows.append({"qid": qid, "route": "law_admin", "base_answer": current,
                     "original_confidence": conf, "priority": risk.get(qid),
                     "trigger_reasons": "|".join(reasons), "eligible": is_elig})

    write_csv(args.output, rows, _FIELDS)
    print("=" * 64)
    print("LAW_ADMIN VERIFIER CANDIDATES (no API; no answer changes)")
    print("=" * 64)
    print(f"law_admin samples : {total}")
    print(f"eligible          : {eligible}")
    print(f"trigger reasons   : {dict(reason_ct)}")
    if args.risk_csv and Path(args.risk_csv).exists():
        print(f"eligible ∩ first-100 P0/P1: {overlap}")
    print(f"candidate CSV: {args.output}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
