#!/usr/bin/env python3
"""Phase 2L.34A — V12 delta candidate review tool (OFFLINE, no ground truth).

Compares a v12 delta candidate CSV against the frozen v11 winner and reports what changed and
why — purely descriptive. It never asserts an answer is *correct* (no ground truth, no answer
table); it only summarizes the proposed changes and their evidence provenance for human review.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.utils.data_io import load_dataset, read_predictions  # noqa: E402
from src.utils.labels import is_valid_label  # noqa: E402


def _read_plan(path):
    rows = {}
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["qid"]] = r
    return rows


def _load_candidates(path):
    out = defaultdict(list)
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("qid"):
                    out[rec["qid"]].append(rec)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit a V12 delta candidate vs v11 (offline)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--candidates", default=None, help="verifier candidates jsonl (for evidence)")
    ap.add_argument("--output-dir", default="scratch/v12_delta_verifier/audit")
    args = ap.parse_args(argv)

    samples = load_dataset(args.input)
    by_qid = {s["qid"]: s for s in samples}
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    cand = {r["qid"]: r["answer"] for r in read_predictions(args.candidate)}
    plan = _read_plan(args.plan)
    evidence = _load_candidates(args.candidates)

    # Validation of the candidate CSV.
    valid = (set(cand) == set(by_qid)
             and all(is_valid_label(a, by_qid[q]) for q, a in cand.items()))

    changed = [q for q in current if current.get(q) != cand.get(q)]
    by_route = Counter(plan.get(q, {}).get("route", "?") for q in changed)
    by_source = Counter(plan.get(q, {}).get("current_source", "?") for q in changed)

    # Provenance of each change: which agent types supported the new label.
    fallback_n = determ_n = api_n = highrisk_n = 0
    detail = []
    for q in changed:
        new = cand[q]
        supporters = sorted({c.get("agent") for c in evidence.get(q, [])
                             if c.get("selected_label") == new
                             and (c.get("parse_status") or "") == "ok"})
        is_determ = any(a in ("deterministic_solver", "calculation_solver", "formula_bank")
                        for a in supporters)
        is_api = any(a in ("route_specialist", "challenger", "calculation_solver",
                           "option_elimination", "pairwise_judge") for a in supporters)
        determ_n += int(is_determ)
        api_n += int(is_api and not is_determ)
        risk_reason = plan.get(q, {}).get("risk_reason", "")
        if "risk:high" in risk_reason:
            highrisk_n += 1
        if "fallback_source" in risk_reason:
            fallback_n += 1
        detail.append({
            "qid": q, "v11": current[q], "v12": new,
            "route": plan.get(q, {}).get("route", ""),
            "source": plan.get(q, {}).get("current_source", ""),
            "support": "|".join(supporters),
            "evidence": "; ".join(str(c.get("evidence") or "")[:80]
                                  for c in evidence.get(q, [])
                                  if c.get("selected_label") == new)[:240],
        })

    label_dist_v11 = Counter(current.values())
    label_dist_v12 = Counter(cand.values())

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    report = {
        "total_qids": len(samples),
        "changed_vs_v11": len(changed),
        "changed_by_route": dict(by_route),
        "changed_by_source": dict(by_source),
        "deterministic_supported": determ_n,
        "api_supported_only": api_n,
        "fallback_origin_changes": fallback_n,
        "high_risk_overrides": highrisk_n,
        "label_dist_v11": dict(label_dist_v11),
        "label_dist_v12": dict(label_dist_v12),
        "validation": "PASS" if valid else "FAIL",
    }
    (out / "v12_delta_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "v12_delta_changes_top50.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "v11", "v12", "route", "source", "support", "evidence"])
        w.writeheader(); w.writerows(detail[:50])

    print("=" * 60)
    print("V12 DELTA CANDIDATE AUDIT (offline, no ground truth)")
    for k, v in report.items():
        print(f"{k:24}: {v}")
    print(f"top-50 changes -> {out/'v12_delta_changes_top50.csv'}")
    print("=" * 60)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
