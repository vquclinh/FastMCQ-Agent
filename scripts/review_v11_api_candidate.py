#!/usr/bin/env python3
"""Review + safety gate for the v11 API-ranked proposals (Phase 2L.26A; no API).

Summarizes the proposed overrides and emits a safety recommendation:
submit_candidate / manual_review_required / reject_candidate. Policy: reject if changes
are dominated by model-only / judge-only signals without evidence; consider only when
changes are few and supported by multiple agents / proof / evidence. No qid hardcoding.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Review v11 API candidate (no API)")
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--output-dir", default="scratch/selective_multicandidate_2l26")
    args = ap.parse_args(argv)

    outdir = Path(args.output_dir)
    rows = list(csv.DictReader(open(args.proposals))) if Path(args.proposals).exists() else []

    total = len(rows)
    low = sum(1 for r in rows if r.get("risk_level") == "low")
    manual = sum(1 for r in rows if _truthy(r.get("requires_manual_review")))
    high = sum(1 for r in rows if r.get("risk_level") == "high")
    deterministic = sum(1 for r in rows if r.get("selected_source", "").startswith(
        ("formula_bank", "concept", "tool:")))
    consensus = sum(1 for r in rows if r.get("selected_source") == "multi_agent_consensus")
    by_source = Counter(r.get("selected_source") for r in rows)
    by_route_changes = [(r["qid"], r["v10_answer"], r["selected_answer"],
                         r["selected_source"], r["risk_level"], r.get("reason", "")) for r in rows]

    # Safety recommendation.
    if total == 0:
        rec = "reject_candidate"
        why = "no proposed overrides — keep v10."
    elif deterministic == total and high == 0:
        rec = "submit_candidate"
        why = "all changes are deterministic-proof backed and low-risk."
    elif consensus > 0 and deterministic + consensus == total and total <= 15:
        rec = "manual_review_required"
        why = "changes include multi-agent consensus (evidence-backed) — review before submit."
    else:
        rec = "reject_candidate"
        why = "changes are model/judge-only or too numerous without deterministic proof."

    md = ["# v11 API Candidate Review", "",
          f"Proposed overrides: **{total}** (low {low}, manual-review {manual}, high {high})",
          f"deterministic-backed: {deterministic}; multi-agent consensus: {consensus}", "",
          f"## Source breakdown\n", *[f"- `{s}`: {n}" for s, n in by_source.most_common()], "",
          "## Changed qids", ""]
    for qid, a, b, src, risk, reason in by_route_changes:
        md.append(f"- **{qid}** {a}→{b} ({src}, {risk}): {reason}")
    md += ["", f"## Safety recommendation: **{rec}**", "", why,
           "", "_Diagnostic only; no ground truth; not promoted to pred.csv._"]
    if "scratch/" in str(outdir).replace("\\", "/"):
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "v11_api_candidate_review.md").write_text("\n".join(md))

    print("=" * 64)
    print("V11 API CANDIDATE REVIEW (no API)")
    print("=" * 64)
    print(f"proposed overrides: {total} | low {low} | manual {manual} | high {high}")
    print(f"deterministic: {deterministic} | consensus: {consensus} | by_source: {dict(by_source)}")
    print(f"RECOMMENDATION: {rec} — {why}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
