#!/usr/bin/env python3
"""Phase 2L.35A — V13 multi-layer candidate review tool (OFFLINE, no ground truth)."""

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


def _load_jsonl(path, keys=("qid",)):
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
                qid = next((rec[k] for k in keys if rec.get(k)), None)
                if qid:
                    out[qid].append(rec)
    return out


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit V13 multi-layer candidate vs v11 (offline)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--candidates", default=None)
    ap.add_argument("--output-dir", default="scratch/v13_multilayer/audit")
    args = ap.parse_args(argv)

    samples = load_dataset(args.input)
    by_qid = {s["qid"]: s for s in samples}
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    cand = {r["qid"]: r["answer"] for r in read_predictions(args.candidate)}
    layer_recs = _load_jsonl(args.candidates)

    valid = (set(cand) == set(by_qid)
             and all(is_valid_label(a, by_qid[q]) for q, a in cand.items()))
    changed = [q for q in current if current.get(q) != cand.get(q)]

    # Layer-level descriptive stats (across all records, not just changed).
    layer_valid = Counter()
    layer_total = Counter()
    for recs in layer_recs.values():
        for r in recs:
            layer_total[r.get("layer")] += 1
            if r.get("valid") and r.get("parse_status") == "ok":
                layer_valid[r.get("layer")] += 1

    detail = []
    for q in changed:
        recs = layer_recs.get(q, [])
        support = sorted({r.get("layer") for r in recs
                          if r.get("valid") and r.get("proposed_label") == cand[q]})
        detail.append({"qid": q, "v11": current[q], "v13": cand[q],
                       "supporting_layers": "|".join(support),
                       "evidence": "; ".join(str(r.get("evidence") or "")[:60]
                                             for r in recs if r.get("proposed_label") == cand[q])[:200]})

    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    report = {
        "total_qids": len(samples),
        "changed_vs_v11": len(changed),
        "valid_records_by_layer": dict(layer_valid),
        "total_records_by_layer": dict(layer_total),
        "label_dist_v11": dict(Counter(current.values())),
        "label_dist_v13": dict(Counter(cand.values())),
        "candidate_md5": _md5(args.candidate),
        "v11_md5": _md5(args.current),
        "identical_to_v11": _md5(args.candidate) == _md5(args.current),
        "validation": "PASS" if valid else "FAIL",
    }
    (out / "v13_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "v13_changes_top.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "v11", "v13", "supporting_layers", "evidence"])
        w.writeheader(); w.writerows(detail[:50])

    print("=" * 60)
    print("V13 MULTI-LAYER CANDIDATE AUDIT (offline, no ground truth)")
    for k, v in report.items():
        print(f"{k:24}: {v}")
    print(f"top changes -> {out/'v13_changes_top.csv'}")
    print("=" * 60)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
