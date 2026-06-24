#!/usr/bin/env python3
"""Select an exact N-question adaptive pilot set from the overall accuracy plan (no API).

Picks the highest-priority API-eligible questions for the chosen mode (excluding
``tool_only``), preferring route diversity when priority scores tie. Pure CSV in / CSV
out: no qid hardcoding, no answer table, no inference. Output stays under scratch/.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

_FIELDS = ["qid", "route", "recommended_layer", "priority_score", "reason", "expected_calls"]


def _adaptive():
    spec = importlib.util.spec_from_file_location(
        "run_adaptive_selective_api", _ROOT / "scripts" / "legacy" / "run" / "run_adaptive_selective_api.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output must be under scratch/ (got {path})")


def _float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _diversify(rows):
    """Stable reorder: highest priority first; within equal scores, round-robin by route."""
    buckets = {}
    order = []
    for r in rows:
        key = round(_float(r.get("priority_score")), 6)
        if key not in buckets:
            buckets[key] = {}
            order.append(key)
        buckets[key].setdefault(r.get("route", ""), []).append(r)
    out = []
    for key in sorted(order, reverse=True):
        by_route = buckets[key]
        # round-robin across routes (routes ordered by their size desc then name for determinism)
        routes = sorted(by_route, key=lambda rt: (-len(by_route[rt]), rt))
        while any(by_route[rt] for rt in routes):
            for rt in routes:
                if by_route[rt]:
                    out.append(by_route[rt].pop(0))
    return out


def select_pilot(plan_rows, count, mode):
    mode_layers = _adaptive()._MODE_LAYERS[mode]
    atfn = _adaptive()._agents_temps_for
    eligible = [r for r in plan_rows
                if r.get("recommended_layer") != "tool_only"
                and r.get("recommended_layer") in mode_layers]
    chosen = _diversify(eligible)[:count]
    out = []
    for r in chosen:
        layer = r.get("recommended_layer")
        ags, temps = atfn(layer)
        out.append({"qid": r.get("qid"), "route": r.get("route"),
                    "recommended_layer": layer,
                    "priority_score": _float(r.get("priority_score")),
                    "reason": r.get("reason", ""),
                    "expected_calls": len(ags) * len(temps) + 1})  # +1 possible judge
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Select adaptive pilot qids (no API)")
    ap.add_argument("--plan", default="scratch/accuracy_engine_2l27/overall_accuracy_plan.csv")
    ap.add_argument("--output", default="scratch/adaptive_pilot_2l28/pilot_qids.csv")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--mode", default="cheap", choices=["cheap", "balanced", "rich"])
    args = ap.parse_args(argv)
    _guard_scratch(args.output)
    if not Path(args.plan).exists():
        raise SystemExit(f"plan not found: {args.plan}")

    plan_rows = list(csv.DictReader(open(args.plan)))
    pilot = select_pilot(plan_rows, args.count, args.mode)
    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(pilot)

    from collections import Counter
    print("=" * 60)
    print(f"PILOT SELECTION ({args.mode}) — no API")
    print("=" * 60)
    print(f"plan eligible -> selected: {len(pilot)} (requested {args.count})")
    print(f"routes: {dict(Counter(p['route'] for p in pilot))}")
    print(f"layers: {dict(Counter(p['recommended_layer'] for p in pilot))}")
    print(f"-> {outp}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
