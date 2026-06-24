#!/usr/bin/env python3
"""Deterministic audit of the calculation solver on the public test (no network).

Runs ONLY the deterministic calculation solver over the public-test questions and
reports match/route/method statistics, and which qids it would safely override —
compared against the v6b run's `calculation_safe_to_override` set. It calls NO
network/LLM, writes only a diagnostic CSV, uses NO ground truth and NO external
answer sheet, and reads qids only to align with the v6b log (never to decide an
answer).

Usage:
    python scripts/audit_calculation_solver_on_public.py \
      --input public-test_1780368312.json \
      --v6b-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --output output/calculation_solver_2l14b_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.calculation_solver import solve_calculation_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.question_profiler import profile_question  # noqa: E402
from src.question_router import route_question  # noqa: E402


def _load(path):
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def _v6b_safe_override_qids(path):
    out = set()
    if not path or not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("qid") and o.get("calculation_safe_to_override"):
            out.add(o["qid"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic calculation-solver public audit (no network)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--v6b-log", default=None)
    ap.add_argument("--output", default="output/calculation_solver_2l14b_audit.csv")
    args = ap.parse_args(argv)

    samples = _load(args.input)
    v6b_safe = _v6b_safe_override_qids(args.v6b_log)

    rows = []
    method_ct = Counter()
    route_of_match = Counter()
    safe_qids = set()
    nonformula_matches = []     # matched on a route that should not be formula-overridden

    for s in samples:
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        res = solve_calculation_sample(s, labels)
        route = route_question(profile_question(s)).route
        if not res.matched:
            continue
        method_ct[res.method] += 1
        route_of_match[route] += 1
        if res.safe_to_override:
            safe_qids.add(s.get("qid"))
        # Flag matches on routes where a deterministic formula is suspicious.
        if route in ("law_admin", "long_context"):
            nonformula_matches.append((s.get("qid"), route, res.method))
        rows.append({
            "qid": s.get("qid"), "route": route, "method": res.method,
            "answer": res.answer, "confidence": res.confidence,
            "safe_to_override": res.safe_to_override,
            "formula_family": res.formula_family, "rationale": res.rationale,
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "route", "method", "answer",
                                           "confidence", "safe_to_override",
                                           "formula_family", "rationale"])
        w.writeheader()
        w.writerows(rows)

    newly = sorted(safe_qids - v6b_safe)
    dropped = sorted(v6b_safe - safe_qids)

    print("=" * 70)
    print("CALCULATION SOLVER PUBLIC AUDIT (deterministic; no network; no ground truth)")
    print("=" * 70)
    print(f"input               : {args.input}")
    print(f"total samples       : {len(samples)}")
    print(f"matched samples     : {len(rows)}")
    print(f"safe overrides (new): {len(safe_qids)}")
    print(f"v6b safe overrides  : {len(v6b_safe)}")
    print("-" * 70)
    print("method distribution (matched):")
    for m, n in method_ct.most_common():
        print(f"  {m:34s} {n}")
    print(f"route of matches    : {dict(route_of_match)}")
    print("-" * 70)
    print(f"newly safe-overridden vs v6b ({len(newly)}): {newly}")
    print(f"no-longer safe vs v6b ({len(dropped)}): {dropped}")
    print("-" * 70)
    if nonformula_matches:
        print(f"⚠ matches on law_admin/long_context routes ({len(nonformula_matches)}):")
        for x in nonformula_matches:
            print(f"   {x}")
    else:
        print("no matches on law_admin/long_context routes (good).")
    print(f"diagnostic CSV written: {args.output}")
    print("NOTE: deterministic-match diagnostic only; no accuracy is claimed.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
