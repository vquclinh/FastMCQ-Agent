#!/usr/bin/env python3
"""Analyze short_knowledge verifier PROPOSALS (read-only; no API; no patching).

Summarizes a proposal CSV/JSONL produced by
``run_short_knowledge_verifier_sample.py --execute`` (proposal-only, no override):
how many propose changing vs keeping, confidence/evidence_type distributions, and —
if the first-100 risk CSV is given — whether proposals move toward/away from the
external 3-LLM majority. The external majority is a RISK SIGNAL, **NOT ground
truth**; "toward/away" is diagnostic only. Reads no answer sheet directly and patches
nothing.

Usage:
    python scripts/analyze_short_knowledge_verifier_proposals.py \
      --proposals output/short_knowledge_verifier_proposals_25.csv \
      --risk-csv output/first100_consensus_risk_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def _load_proposals(path):
    p = Path(path)
    rows = []
    if p.suffix == ".jsonl":
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    else:
        rows = list(csv.DictReader(open(path)))
    return rows


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def _conf_bucket(c):
    try:
        c = float(c)
    except (TypeError, ValueError):
        return "n/a"
    if c >= 0.90:
        return ">=0.90"
    if c >= 0.70:
        return "0.70-0.90"
    return "<0.70"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Analyze SK verifier proposals (read-only)")
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--risk-csv", default=None)
    args = ap.parse_args(argv)

    rows = _load_proposals(args.proposals)
    # external majority from the risk CSV (diagnostic only; NOT ground truth).
    ext_majority = {}
    if args.risk_csv and Path(args.risk_csv).exists():
        for r in csv.DictReader(open(args.risk_csv)):
            mc = r.get("external_majority_count")
            try:
                mc = int(mc)
            except (TypeError, ValueError):
                mc = 0
            if r.get("external_majority") and mc >= 2:
                ext_majority[r.get("qid")] = (r["external_majority"], r.get("priority"))

    total = len(rows)
    propose_change = propose_keep = 0
    conf_ct = Counter()
    ev_ct = Counter()
    toward = away = unchanged_vs_maj = 0
    changes = []

    for r in rows:
        cur = (r.get("current_answer") or "").strip().upper()
        sel = (r.get("verifier_selected") or "").strip().upper()
        wc = _truthy(r.get("would_change_answer"))
        if wc:
            propose_change += 1
        else:
            propose_keep += 1
        conf_ct[_conf_bucket(r.get("verifier_confidence"))] += 1
        ev_ct[(r.get("evidence_type") or "n/a")] += 1

        qid = r.get("qid")
        if qid in ext_majority and sel:
            maj, _pri = ext_majority[qid]
            if wc and sel == maj:
                toward += 1
            elif wc and cur == maj and sel != maj:
                away += 1
            elif not wc:
                unchanged_vs_maj += 1
        if wc:
            changes.append((qid, cur, sel, r.get("verifier_confidence"),
                            r.get("evidence_type"), (r.get("reason") or "")[:80]))

    print("=" * 72)
    print("SHORT-KNOWLEDGE VERIFIER PROPOSAL ANALYSIS (external majority = NOT truth)")
    print("=" * 72)
    print(f"proposals file        : {args.proposals}")
    print(f"total verifier calls  : {total}")
    print(f"propose CHANGE answer : {propose_change}")
    print(f"propose KEEP answer   : {propose_keep}")
    print(f"verifier confidence   : {dict(conf_ct)}")
    print(f"evidence_type dist    : {dict(ev_ct)}")
    if ext_majority:
        print("-" * 72)
        print("vs first-100 external 3-LLM majority (DIAGNOSTIC ONLY, not ground truth):")
        print(f"  proposals toward majority : {toward}")
        print(f"  proposals away from major.: {away}")
        print(f"  kept (no change)          : {unchanged_vs_maj}")
    print("-" * 72)
    print(f"proposed changes ({len(changes)}):")
    for qid, cur, sel, conf, ev, reason in changes:
        print(f"  {qid}: {cur} -> {sel}  conf={conf} evidence={ev}  reason={reason}")
    print("-" * 72)
    print("WARNING: external 3-LLM majority is a RISK SIGNAL, not ground truth. A move")
    print("'away' is not necessarily wrong, and 'toward' is not necessarily correct.")
    print("No prediction was patched by this analysis.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
