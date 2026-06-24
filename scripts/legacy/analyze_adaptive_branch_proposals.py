#!/usr/bin/env python3
"""Unified analyzer across adaptive branch proposal/audit artifacts (read-only).

Combines whatever proposal/audit CSVs exist (short_knowledge / law_admin / ambiguous
/ self-consistency proposals, long-context sufficiency, first-100 risk) and reports a
consolidated view: proposed changes per branch, confidence/evidence distributions,
overlap with first-100 P0/P1, toward/away vs the diagnostic external majority (with a
NOT-ground-truth warning), and which proposals would pass the override gate. Handles
missing files gracefully and patches NOTHING.

Usage: see Phase 2L.16 Part I command.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import override_gate  # noqa: E402


def _rows(path):
    if path and Path(path).exists():
        return list(csv.DictReader(open(path)))
    return None


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def _conf(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Unified adaptive branch proposal analyzer (read-only)")
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--long-context-audit", default=None)
    ap.add_argument("--sk-candidates", default=None)
    ap.add_argument("--sk-proposals", default=None)
    ap.add_argument("--law-admin-candidates", default=None)
    ap.add_argument("--law-admin-proposals", default=None)
    ap.add_argument("--ambiguous-candidates", default=None)
    ap.add_argument("--ambiguous-proposals", default=None)
    ap.add_argument("--self-consistency-candidates", default=None)
    ap.add_argument("--self-consistency-proposals", default=None)
    args = ap.parse_args(argv)

    # external majority (diagnostic only) from risk CSV
    ext = {}
    rrows = _rows(args.risk_csv)
    if rrows:
        for r in rrows:
            try:
                mc = int(r.get("external_majority_count") or 0)
            except ValueError:
                mc = 0
            if r.get("external_majority") and mc >= 2:
                ext[r.get("qid")] = (r["external_majority"], r.get("priority"))

    proposal_files = {
        "short_knowledge": args.sk_proposals,
        "law_admin": args.law_admin_proposals,
        "ambiguous": args.ambiguous_proposals,
        "self_consistency": args.self_consistency_proposals,
    }
    audit_files = {
        "risk_csv": args.risk_csv, "long_context_audit": args.long_context_audit,
        "sk_candidates": args.sk_candidates, "law_admin_candidates": args.law_admin_candidates,
        "ambiguous_candidates": args.ambiguous_candidates,
        "self_consistency_candidates": args.self_consistency_candidates,
    }

    print("=" * 72)
    print("UNIFIED ADAPTIVE BRANCH PROPOSAL ANALYSIS (read-only; patches NOTHING)")
    print("=" * 72)
    print("audit/candidate files found:")
    for name, p in audit_files.items():
        print(f"  {name:28s}: {'FOUND ' + p if p and Path(p).exists() else 'missing'}")
    print("-" * 72)

    total_changes = 0
    gate_pass = gate_reject = 0
    toward = away = 0
    branch_changes = Counter()
    conf_ct = Counter()
    ev_ct = Counter()
    any_proposals = False

    for branch, path in proposal_files.items():
        rows = _rows(path)
        if rows is None:
            print(f"[{branch}] proposals: missing")
            continue
        any_proposals = True
        ch = 0
        for r in rows:
            cur = (r.get("current_answer") or "").strip().upper()
            sel = (r.get("verifier_selected") or r.get("majority_answer") or "").strip().upper()
            wc = _truthy(r.get("would_change_answer"))
            if wc:
                ch += 1
                total_changes += 1
                branch_changes[branch] += 1
            conf_ct[_conf_bucket(r.get("verifier_confidence"))] += 1
            ev_ct[r.get("evidence_type") or "n/a"] += 1
            # would this proposal pass the shared gate (allow_override hypothetically on)?
            labels = [chr(ord("A") + i) for i in range(11)]
            proposal = {"selected_answer": sel, "should_override": _truthy(r.get("should_override")),
                        "confidence": _conf(r.get("verifier_confidence")),
                        "reason": r.get("reason"), "evidence_type": r.get("evidence_type")}
            if wc:
                if override_gate(proposal, cur, labels, allow_override=True):
                    gate_pass += 1
                else:
                    gate_reject += 1
            qid = r.get("qid")
            if wc and qid in ext and sel:
                maj, _pri = ext[qid]
                if sel == maj:
                    toward += 1
                elif cur == maj:
                    away += 1
        print(f"[{branch}] proposals: {len(rows)} rows, {ch} propose change")

    print("-" * 72)
    print(f"total proposed changes across branches: {total_changes}")
    print(f"  by branch: {dict(branch_changes)}")
    print(f"verifier confidence buckets: {dict(conf_ct)}")
    print(f"evidence_type distribution : {dict(ev_ct)}")
    print(f"proposals passing override gate : {gate_pass}")
    print(f"proposals rejected by gate      : {gate_reject}")
    if ext:
        print(f"changes toward external majority: {toward}  | away: {away}  "
              f"(external majority is a RISK SIGNAL, NOT ground truth)")
    print("-" * 72)
    if not any_proposals:
        rec = "no v8 yet — no proposal artifacts present; run proposal batches first"
    elif total_changes == 0:
        rec = "no v8 yet — no branch proposes a change"
    elif gate_pass > 0:
        rec = f"v8 safe candidate POSSIBLE for {gate_pass} gate-passing change(s) — needs manual review"
    else:
        rec = "needs manual review — proposals exist but none pass the override gate"
    print(f"RECOMMENDATION: {rec}")
    print("No prediction was patched by this analysis.")
    print("=" * 72)
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
