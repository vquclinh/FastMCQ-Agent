#!/usr/bin/env python3
"""Submission variant audit (Phase 2L.29A; read-only, no API, no ground truth).

Compares any number of submission candidate CSVs against the v10 base: per-candidate
changed count + label distribution, route distribution of changed qids (if a plan is
given), a pairwise overlap/disagreement matrix, qids changed by multiple candidates, and
qids where candidates disagree with each other. Writes CSV + MD under scratch/ only.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_pred, load_samples  # noqa: E402


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit submission variants vs v10 (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="output/pred_v10_full_production_user_run.csv")
    ap.add_argument("--candidates", nargs="+", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--output-dir", default="scratch/submission_variant_audit")
    args = ap.parse_args(argv)
    _guard_scratch(args.output_dir)
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    plan = {r["qid"]: r for r in csv.DictReader(open(args.plan))} if args.plan and Path(args.plan).exists() else {}

    cands = {}
    for c in args.candidates:
        if Path(c).exists():
            cands[Path(c).name] = load_pred(c)

    # Per-candidate stats.
    rows = []
    changed_sets = {}
    for name, pred in cands.items():
        changed = {q for q in samples if pred.get(q) and pred.get(q) != base.get(q)}
        changed_sets[name] = changed
        label_dist = Counter(pred.get(q) for q in samples)
        route_dist = Counter((plan.get(q) or {}).get("route", "?") for q in changed) if plan else {}
        rows.append({"candidate": name, "changed_vs_v10": len(changed),
                     "label_distribution": dict(label_dist),
                     "route_distribution_of_changes": dict(route_dist)})

    # qids changed by multiple candidates; qids where candidates disagree with each other.
    all_changed = Counter()
    for s in changed_sets.values():
        all_changed.update(s)
    changed_by_multiple = sorted(q for q, n in all_changed.items() if n >= 2)
    disagree = []
    for q in sorted(all_changed):
        answers = {name: cands[name].get(q) for name in cands}
        non_base = {a for a in answers.values() if a and a != base.get(q)}
        if len(non_base) >= 2:                       # candidates propose different changes
            disagree.append(q)

    # Pairwise overlap + disagreement.
    pair_rows = []
    for a, b in combinations(cands, 2):
        both_changed = changed_sets[a] & changed_sets[b]
        agree = sum(1 for q in both_changed if cands[a].get(q) == cands[b].get(q))
        disagree_n = sum(1 for q in samples if cands[a].get(q) != cands[b].get(q))
        pair_rows.append({"pair": f"{a} vs {b}", "both_changed_vs_v10": len(both_changed),
                          "agree_on_change": agree, "total_disagreements": disagree_n})

    with open(outdir / "variant_comparison.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["candidate", "changed_vs_v10", "label_distribution",
                                           "route_distribution_of_changes"])
        w.writeheader(); w.writerows(rows)

    md = ["# Submission Variant Comparison (read-only; no ground truth)", "",
          f"base v10: `{Path(args.base_pred).name}`   candidates: {list(cands)}", "",
          "## Per-candidate", "",
          "| candidate | changed vs v10 | route dist of changes |", "|---|---|---|"]
    for r in rows:
        md.append(f"| {r['candidate']} | {r['changed_vs_v10']} | {r['route_distribution_of_changes']} |")
    md += ["", "## Pairwise overlap / disagreement", "",
           "| pair | both changed | agree-on-change | total disagreements |", "|---|---|---|---|"]
    for p in pair_rows:
        md.append(f"| {p['pair']} | {p['both_changed_vs_v10']} | {p['agree_on_change']} | "
                  f"{p['total_disagreements']} |")
    md += ["", f"## qids changed by ≥2 candidates: **{len(changed_by_multiple)}**", "",
           ", ".join(changed_by_multiple[:60]) or "(none)",
           "", f"## qids where candidates disagree with each other: **{len(disagree)}**", "",
           ", ".join(disagree[:60]) or "(none)"]
    (outdir / "variant_comparison.md").write_text("\n".join(md))

    print("=" * 64)
    print("SUBMISSION VARIANT AUDIT (no API, no ground truth)")
    print("=" * 64)
    for r in rows:
        print(f"  {r['candidate']}: changed_vs_v10={r['changed_vs_v10']}")
    print(f"changed_by_>=2={len(changed_by_multiple)}  candidates_disagree={len(disagree)}")
    print(f"-> {outdir}/variant_comparison.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
