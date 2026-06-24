#!/usr/bin/env python3
"""Dry-run generalization-readiness scanner (no API, no patching, diagnostic only).

Runs the deterministic formula/concept bank over an input set (public test, used ONLY
as a diagnostic — never as ground truth) and reports: how many questions each branch
sees, how many bank rules would fire as SAFE overrides, top detected families, and a
coverage-gap signal (calculation-route questions with no safe deterministic rule). No
base LLM answer is needed, no network is contacted, and NO prediction is written.

Usage:
    python scripts/audit_hidden_generalization_readiness.py \
      --input public-test_1780368312.json \
      --output output/hidden_generalization_readiness_audit.csv
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import load_samples, write_csv  # noqa: E402
from src.formula_bank_solver import solve_formula_bank_sample  # noqa: E402
from src.production_policy import branch_of  # noqa: E402

_FIELDS = ["qid", "branch", "fireable_safe_rule", "rule_id", "reason"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Hidden-test generalization readiness (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", default="output/hidden_generalization_readiness_audit.csv")
    args = ap.parse_args(argv)

    samples = load_samples(args.input)
    branch_ct = Counter()
    rule_ct = Counter()
    fireable_by_branch = Counter()
    calc_no_rule = 0
    rows = []

    for s in samples:
        branch = branch_of(s)
        branch_ct[branch] += 1
        res = solve_formula_bank_sample(s)     # deterministic only; no API
        fireable = res is not None and res.safe_to_override
        if fireable:
            rule_ct[res.rule_id] += 1
            fireable_by_branch[branch] += 1
        elif branch == "calculation":
            calc_no_rule += 1
        rows.append({"qid": s.get("qid"), "branch": branch,
                     "fireable_safe_rule": fireable,
                     "rule_id": res.rule_id if res else None,
                     "reason": (res.reason if res else "")[:80]})

    write_csv(args.output, rows, _FIELDS)

    print("=" * 70)
    print("HIDDEN-TEST GENERALIZATION READINESS (no API; diagnostic only)")
    print("=" * 70)
    print(f"total questions          : {len(samples)}")
    print(f"branch distribution      : {dict(branch_ct)}")
    print(f"fireable safe rules total: {sum(fireable_by_branch.values())}")
    print(f"fireable by branch       : {dict(fireable_by_branch)}")
    print("-" * 70)
    print("top detected formula/concept families (safe-fireable):")
    for rid, n in rule_ct.most_common(25):
        print(f"  {str(rid):34s} {n}")
    print("-" * 70)
    print(f"calculation-route questions with NO safe rule (coverage gap signal): {calc_no_rule}")
    print(f"audit CSV written: {args.output}")
    print("NOTE: a 'fireable' rule would override the base LLM ONLY if it differs from "
          "the base answer; this scan needs no base answer and patches nothing.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
