#!/usr/bin/env python3
"""Diagnostic inventory of deterministic calculation-family matches (read-only).

Reports, per sample, which formula family the solver matches (if any), whether it
is a safe override, and the extracted values. It is a PATTERN inventory only: it
NEVER uses ground truth / answer keys, makes NO correctness claim, calls NO
network/LLM, and writes NO prediction CSV. No qid is used for any decision (qids
are printed solely to locate samples).

Usage:
    python scripts/inventory_calculation_families.py --input public-test_1780368312.json
    python scripts/inventory_calculation_families.py --input <file> --jsonl outputs/calc_family_inventory.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.calculation_solver import solve_calculation_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402


def _load(path: str) -> list:
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    for k in ("data", "samples", "questions"):
        if isinstance(data.get(k), list):
            return data[k]
    for v in data.values():
        if isinstance(v, list):
            return v
    raise SystemExit(f"no sample list in {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Calculation family inventory (diagnostic, no labels)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--jsonl", default=None, help="optional path to write per-sample records")
    ap.add_argument("--show", type=int, default=20, help="how many matched samples to print")
    args = ap.parse_args(argv)

    samples = _load(args.input)
    safe = Counter()
    unsafe = Counter()
    fam_category = Counter()
    matched_recs = []

    for s in samples:
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        res = solve_calculation_sample(s, labels)
        if not res.matched:
            continue
        rec = {
            "qid": s.get("qid"),
            "method": res.method,
            "formula_family": res.formula_family,
            "answer_label": res.answer,
            "safe_to_override": res.safe_to_override,
            "confidence": res.confidence,
            "extracted_values": res.extracted_values,
        }
        matched_recs.append(rec)
        if res.safe_to_override:
            safe[res.method] += 1
        else:
            unsafe[res.method] += 1
        fam_category[res.formula_family] += 1

    print("=" * 64)
    print("CALCULATION FAMILY INVENTORY (diagnostic only; no ground truth)")
    print("=" * 64)
    print(f"input            : {args.input}")
    print(f"total samples    : {len(samples)}")
    print(f"matched samples  : {len(matched_recs)}")
    print(f"safe overrides   : {sum(safe.values())}")
    print(f"unsafe/declined  : {sum(unsafe.values())}")
    print("-" * 64)
    print("safe overrides by method:")
    for m, n in safe.most_common():
        print(f"  {m:30s} {n}")
    if unsafe:
        print("matched-but-unsafe by method:")
        for m, n in unsafe.most_common():
            print(f"  {m:30s} {n}")
    print("-" * 64)
    print("formula_family distribution:")
    for fam, n in fam_category.most_common():
        print(f"  {fam:24s} {n}")
    print("-" * 64)
    print(f"first {min(args.show, len(matched_recs))} matched samples:")
    for rec in matched_recs[: args.show]:
        print(f"  {rec['qid']}  {rec['method']:26s} -> {rec['answer_label']} "
              f"(safe={rec['safe_to_override']}) {rec['extracted_values']}")

    if args.jsonl:
        out = Path(args.jsonl)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for rec in matched_recs:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\nper-sample records -> {out}")
    print("NOTE: pattern inventory only; no correctness is claimed.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
