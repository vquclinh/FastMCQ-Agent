#!/usr/bin/env python3
"""Phase 2L.34B — V12B permutation candidate review tool (OFFLINE, no ground truth).

Describes what the permutation candidate changed vs frozen v11 and the vote evidence behind
each change. Purely descriptive — no correctness claim, no answer table.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.data_io import load_dataset, read_predictions  # noqa: E402
from src.labels import is_valid_label  # noqa: E402


def _read_plan(path):
    out = {}
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["qid"]] = r
    return out


def _load_records(path):
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
                qid = rec.get("original_qid") or rec.get("qid")
                if qid:
                    out[qid].append(rec)
    return out


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit a V12B permutation candidate vs v11")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--permutation-records", default=None)
    ap.add_argument("--output-dir", default="scratch/v12b_option_permutation/audit")
    args = ap.parse_args(argv)

    samples = load_dataset(args.input)
    by_qid = {s["qid"]: s for s in samples}
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    cand = {r["qid"]: r["answer"] for r in read_predictions(args.candidate)}
    plan = _read_plan(args.plan)
    records = _load_records(args.permutation_records)

    valid = (set(cand) == set(by_qid)
             and all(is_valid_label(a, by_qid[q]) for q, a in cand.items()))
    changed = [q for q in current if current.get(q) != cand.get(q)]

    by_optcount = Counter(plan.get(q, {}).get("option_count", "?") for q in changed)
    by_source = Counter(plan.get(q, {}).get("current_source", "?") for q in changed)
    by_risk = Counter((plan.get(q, {}).get("risk_reason", "") or "none").split(";")[0]
                      for q in changed)

    detail = []
    for q in changed:
        recs = [r for r in records.get(q, []) if r.get("valid")]
        votes = Counter(r.get("mapped_original_label") for r in recs)
        detail.append({
            "qid": q, "v11": current[q], "v12b": cand[q],
            "option_count": plan.get(q, {}).get("option_count", ""),
            "current_source": plan.get(q, {}).get("current_source", ""),
            "valid_votes": len(recs),
            "vote_table": json.dumps(dict(votes), ensure_ascii=False),
            "margin": (votes.get(cand[q], 0) - votes.get(current[q], 0)),
        })
    detail.sort(key=lambda d: -d["margin"])

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    report = {
        "total_qids": len(samples),
        "changed_vs_v11": len(changed),
        "changed_by_option_count": dict(by_optcount),
        "changed_by_current_source": dict(by_source),
        "changed_by_risk_reason": dict(by_risk),
        "label_dist_v11": dict(Counter(current.values())),
        "label_dist_v12b": dict(Counter(cand.values())),
        "candidate_md5": _md5(args.candidate),
        "v11_md5": _md5(args.current),
        "identical_to_v11": _md5(args.candidate) == _md5(args.current),
        "validation": "PASS" if valid else "FAIL",
    }
    (out / "v12b_permutation_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "v12b_changes_top.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "v11", "v12b", "option_count",
                                          "current_source", "valid_votes", "vote_table", "margin"])
        w.writeheader(); w.writerows(detail[:50])

    print("=" * 60)
    print("V12B PERMUTATION CANDIDATE AUDIT (offline, no ground truth)")
    for k, v in report.items():
        print(f"{k:26}: {v}")
    print(f"top changes -> {out/'v12b_changes_top.csv'}")
    print("=" * 60)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
