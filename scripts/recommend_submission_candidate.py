#!/usr/bin/env python3
"""Recommend a submission candidate from the disagreement review (no API, no truth).

Reads ``candidate_disagreement_review.csv`` and ranks candidates by SAFETY of their
changes vs the baseline: prefer few low-risk deterministic changes; penalize
unexplained model-rerun drift. Uses optional known leaderboard scores only as context
(never the external 3-LLM sheet, never hidden truth). Writes a Markdown recommendation
+ a terminal summary. Decides no correctness.

Usage: see Phase 2L.23 Part F.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Recommend a submission candidate (no API)")
    ap.add_argument("--review", required=True)
    ap.add_argument("--known-score", action="append", default=[], help="name=score (repeatable)")
    ap.add_argument("--baseline-name", default="v8_clean")
    ap.add_argument("--output", default="output/submission_candidate_recommendation.md")
    args = ap.parse_args(argv)

    known = {}
    for kv in args.known_score:
        if "=" in kv:
            k, v = kv.split("=", 1)
            known[k.strip()] = v.strip()

    rows = list(csv.DictReader(open(args.review)))
    per = defaultdict(lambda: {"total": 0, "low": 0, "medium": 0, "high": 0,
                               "deterministic": 0, "drift": 0})
    for r in rows:
        src = r["candidate_source"]
        d = per[src]
        d["total"] += 1
        d[r["risk_level"]] = d.get(r["risk_level"], 0) + 1
        if r["matches_safe_deterministic_rule"].strip().lower() == "true" \
                or r["change_type"] == "deterministic_rule":
            d["deterministic"] += 1
        if r["change_type"] == "production_model_drift":
            d["drift"] += 1

    # Safety score: reward deterministic-backed low-risk changes; penalize drift + risk.
    def safety(d):
        return d["deterministic"] * 1.0 - d["drift"] * 1.0 - d["high"] * 2.0 - d["medium"] * 0.5

    ranked = sorted(per.items(), key=lambda kv: safety(kv[1]), reverse=True)

    # Build recommendation text.
    lines = ["# Submission Candidate Recommendation", "",
             "> Diagnostic only — no ground truth, no external 3-LLM sheet. Ranks by the "
             "**safety** of changes vs the baseline (deterministic & low-risk preferred; "
             "unexplained model-rerun drift penalized).", "",
             f"Baseline (`{args.baseline_name}`): the current submission "
             f"(known score {known.get(args.baseline_name, '?')}). A candidate is only worth "
             "switching to if its changes are safe/explained.", "",
             "## Candidates", ""]
    for src, d in per.items():
        lines.append(f"### `{src}`")
        lines.append(f"- changes vs baseline: **{d['total']}** "
                     f"(low {d['low']}, medium {d['medium']}, high {d['high']})")
        lines.append(f"- deterministic-backed: **{d['deterministic']}**; model-drift: **{d['drift']}**")
        lines.append("")

    # Decision policy.
    fb = next((s for s in per if "formula_bank" in s.lower() or "_v9" in s.lower()), None)
    prod = next((s for s in per if "production" in s.lower()), None)
    if fb and per[fb]["drift"] == 0 and per[fb]["high"] == 0 \
            and (not prod or per[prod]["drift"] >= 3):
        rec = (f"**Submit `{fb}`** as the upgrade candidate: its change(s) are all "
               f"deterministic & low-risk ({per[fb]['deterministic']} backed by a safe rule, "
               f"0 drift), strictly safer than re-running the model. Keep "
               f"`{args.baseline_name}` as the conservative fallback. **Avoid the "
               f"production rerun** — it has {per[prod]['drift'] if prod else 0} unexplained "
               "model-drift changes that cannot be verified offline.")
        choice = fb
    elif not per:
        rec = f"No disagreements found — submit the baseline `{args.baseline_name}`."
        choice = args.baseline_name
    else:
        rec = (f"Keep the baseline `{args.baseline_name}` unless a candidate's changes are "
               "all low-risk/deterministic. Review medium/high-risk rows manually.")
        choice = args.baseline_name
    lines += ["## Recommendation", "", rec, "",
              "With only 2 submissions left, prefer the smallest safe, explained change set.",
              ""]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("\n".join(lines))

    print("=" * 64)
    print("SUBMISSION CANDIDATE RECOMMENDATION (diagnostic; no ground truth)")
    print("=" * 64)
    for src, d in ranked:
        print(f"  {src}: total={d['total']} low={d['low']} med={d['medium']} "
              f"high={d['high']} det={d['deterministic']} drift={d['drift']} "
              f"safety={safety(d):.1f}")
    print("-" * 64)
    print(f"RECOMMENDED: {choice}")
    print(f"recommendation md: {args.output}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
