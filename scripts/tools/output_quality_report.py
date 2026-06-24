#!/usr/bin/env python3
"""Answer-distribution quality report for a prediction CSV (Phase 2L.41A).

Reports label counts/ratios and flags a degenerate distribution (one label exceeding a
threshold, default 70%). It NEVER deletes or rewrites the prediction file. By default it exits 0
(a warning is printed but the final artifact is still allowed); with ``--fail-on-guard`` it exits
nonzero when degenerate so a caller can refuse to promote ``output/pred.csv``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.data_io import read_predictions  # noqa: E402


def compute_quality_report(pred_csv, threshold=0.70):
    rows = read_predictions(pred_csv)
    total = len(rows)
    counts = Counter(r.get("answer") for r in rows)
    ratios = {k: round(v / total, 4) for k, v in counts.items()} if total else {}
    top_label, top_n = (counts.most_common(1)[0] if counts else (None, 0))
    top_ratio = round(top_n / total, 4) if total else 0.0
    return {
        "pred_csv": str(pred_csv),
        "total": total,
        "counts": dict(counts),
        "ratios": ratios,
        "top_label": top_label,
        "top_ratio": top_ratio,
        "threshold": threshold,
        "degenerate": bool(total and top_ratio > threshold),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Answer-distribution quality report (no mutation)")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out", default=None, help="write the JSON report here")
    ap.add_argument("--threshold", type=float, default=0.70)
    ap.add_argument("--fail-on-guard", action="store_true", default=False,
                    help="exit nonzero if the distribution is degenerate (caller can refuse promote)")
    args = ap.parse_args(argv)

    rep = compute_quality_report(args.pred, threshold=args.threshold)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rep, indent=2), encoding="utf-8")

    dist = ", ".join(f"{k}={rep['counts'][k]}({rep['ratios'][k]:.0%})"
                     for k in sorted(rep["counts"]))
    print(f"[QUALITY] total={rep['total']} dist: {dist}")
    print(f"[QUALITY] top_label={rep['top_label']} top_ratio={rep['top_ratio']:.2%} "
          f"threshold={rep['threshold']:.0%}")
    if rep["degenerate"]:
        print(f"WARNING: degenerate answer distribution detected "
              f"({rep['top_label']}={rep['top_ratio']:.1%} > {rep['threshold']:.0%}). "
              "Review before submission.")
        if args.fail_on_guard:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
