#!/usr/bin/env python3
"""Audit short_knowledge verifier candidates (no API, no answer changes).

Runs the adaptive orchestrator (short_knowledge_verifier enabled, assist mode) over
the public test using a base prediction + base log for the current answer/confidence,
and reports which short_knowledge items would be *eligible* for selective
verification. It calls NO network/LLM, changes NO answer, writes only a diagnostic
CSV, uses NO ground truth, and never reads the external 3-LLM sheet. The external
risk CSV (if given) is used only to count overlap with first-100 P0/P1 — a diagnostic
signal, not ground truth.

Usage:
    python scripts/audit_short_knowledge_verifier_candidates.py \
      --input public-test_1780368312.json \
      --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
      --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --risk-csv outputs/first100_consensus_risk_audit.csv \
      --output outputs/short_knowledge_verifier_candidates.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_orchestrator import AdaptiveConfig, AdaptiveOrchestrator  # noqa: E402


def _load_samples(path):
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def _load_pred(path):
    return {r["qid"]: r["answer"] for r in csv.DictReader(open(path))}


def _load_log(path):
    out = {}
    if not path or not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("qid"):
            out[o["qid"]] = o
    return out


def _p0p1_qids(path):
    out = set()
    if not path or not Path(path).exists():
        return out
    for r in csv.DictReader(open(path)):
        if r.get("priority") in ("P0", "P1"):
            out.add(r.get("qid"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Short-knowledge verifier candidate audit (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--trigger-confidence-max", type=float, default=0.95)
    ap.add_argument("--output", default="outputs/short_knowledge_verifier_candidates.csv")
    args = ap.parse_args(argv)

    samples = _load_samples(args.input)
    base = _load_pred(args.base_pred)
    log = _load_log(args.base_log)
    p0p1 = _p0p1_qids(args.risk_csv)

    # SK verifier enabled, but allow_override=false and max_verifier_calls=0 -> dry-run.
    orch = AdaptiveOrchestrator(AdaptiveConfig(
        enabled=True, mode="assist", short_knowledge_verifier_enabled=True,
        sk_allow_override=False, sk_trigger_confidence_max=args.trigger_confidence_max,
        sk_max_verifier_calls=0))

    sk_count = eligible = 0
    reason_ct = Counter()
    eligible_qids = []
    rows = []
    overlap_p0p1 = 0

    for s in samples:
        qid = s.get("qid")
        tr_log = log.get(qid, {})
        state = {
            "final_answer": base.get(qid),
            "confidence": tr_log.get("confidence"),
            "parsed_answer_source": tr_log.get("parsed_answer_source")
            or (tr_log.get("parsed_answer") or {}).get("source"),
            "parsed_answer_error": tr_log.get("parsed_answer_error")
            or (tr_log.get("parsed_answer") or {}).get("error"),
            "parsed_answer": tr_log.get("parsed_answer") or {},
        }
        tr = orch.analyze(s, existing_answer=base.get(qid), state=state)
        if tr.selected_branch != "short_knowledge":
            continue
        sk_count += 1
        elig = bool(tr.extra.get("sk_verifier_eligible"))
        reasons = tr.extra.get("sk_trigger_reasons", [])
        if not elig:
            continue
        eligible += 1
        for r in reasons:
            reason_ct[r] += 1
        eligible_qids.append(qid)
        in_risk = qid in p0p1
        overlap_p0p1 += int(in_risk)
        rows.append({
            "qid": qid, "route": tr.route, "base_answer": base.get(qid),
            "confidence": state["confidence"], "trigger_reasons": "|".join(reasons),
            "in_first100_p0p1": in_risk, "would_override": tr.would_override,
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "route", "base_answer", "confidence",
                                           "trigger_reasons", "in_first100_p0p1", "would_override"])
        w.writeheader(); w.writerows(rows)

    print("=" * 70)
    print("SHORT-KNOWLEDGE VERIFIER CANDIDATES (no API; no answer changes)")
    print("=" * 70)
    print(f"total samples            : {len(samples)}")
    print(f"short_knowledge count    : {sk_count}")
    print(f"verifier-eligible        : {eligible}")
    print(f"trigger reason distribution: {dict(reason_ct)}")
    if args.risk_csv and Path(args.risk_csv).exists():
        print(f"eligible ∩ first-100 P0/P1: {overlap_p0p1}")
    print(f"would_override rows (must be 0): {sum(1 for r in rows if r['would_override'])}")
    print("-" * 70)
    print(f"eligible qids ({len(eligible_qids)}): {eligible_qids[:60]}")
    print(f"candidate CSV written: {args.output}")
    print("NOTE: eligibility diagnostic only; no API call, no answer changed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
