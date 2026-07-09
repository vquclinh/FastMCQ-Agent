#!/usr/bin/env python3
"""Build a targeted verifier-smoke INPUT subset (no API, no inference).

Selects sample qids that would trigger the MCQ verifier under a chosen policy
(using the real ``should_run_verifier`` logic over a prior run's JSONL log), then
writes a subset JSON in the same format as the public input. This is **test-input
selection only** — it uses routing/trigger signals, never answer correctness or
ground truth, and writes no predictions.

Usage:
    python scripts/create_verifier_smoke_subset.py \
        --input public-test_1780368312.json \
        --log output/run_v2_calc_rerank.jsonl \
        --policy selective \
        --output output/input_v3a_verifier_selective_smoke.json \
        --max-samples 60 --control-samples 10
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.selector.mcq_verifier import should_run_verifier  # noqa: E402


class _VerifierCfg:
    """Mirror of the remote providerConfig verifier fields for a given policy."""

    def __init__(self, policy: str):
        self.mcq_verifier_enabled = True
        self.mcq_verifier_apply_routes = ["long_context", "ambiguous", "law_admin", "safety_ethics"]
        self.mcq_verifier_trigger_below_confidence = 0.70
        self.mcq_verifier_trigger_on_partial_parse = True
        self.mcq_verifier_trigger_on_repair = True
        # The only policy difference: broad also verifies reranked long-context.
        self.mcq_verifier_trigger_on_reranked_long_context = (policy == "broad")


def _load_log(path: Path) -> list:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in rows if not r.get("_summary")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create a verifier-smoke input subset")
    ap.add_argument("--input", required=True)
    ap.add_argument("--log", required=True, help="prior run JSONL (e.g. v2) with trigger fields")
    ap.add_argument("--policy", choices=["selective", "broad"], required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-samples", type=int, default=60)
    ap.add_argument("--control-samples", type=int, default=10)
    args = ap.parse_args(argv)

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    samples = data if isinstance(data, list) else data.get("data", [])
    by_qid = {s["qid"]: s for s in samples}
    log_rows = _load_log(Path(args.log))
    cfg = _VerifierCfg(args.policy)

    # Classify every logged sample: does it trigger the verifier under this policy?
    triggers, reasons = [], {}
    for r in log_rows:
        run, reason = should_run_verifier(r, cfg)
        if run and r.get("qid") in by_qid:
            triggers.append(r)
            reasons[r["qid"]] = reason

    # Ordering: prioritise partial-parse / low-confidence first (most uncertain),
    # then the rest (e.g. reranked long-context for the broad policy).
    def _priority(r):
        reason = reasons.get(r["qid"], "")
        return (0 if ("partial_parse" in reason or "low_confidence" in reason) else 1,
                r["qid"])
    triggers.sort(key=_priority)

    selected, selected_reasons = [], {}
    for r in triggers[: max(0, args.max_samples)]:
        selected.append(r["qid"]); selected_reasons[r["qid"]] = reasons[r["qid"]]

    # Controls: samples that do NOT trigger (diverse routes), for contrast.
    trigger_qids = {r["qid"] for r in triggers}
    controls = []
    if args.control_samples > 0:
        seen_routes = collections.Counter()
        for r in log_rows:
            qid = r.get("qid")
            if qid in trigger_qids or qid in selected or qid not in by_qid:
                continue
            route = r.get("route", "?")
            # spread controls across routes
            if seen_routes[route] >= max(1, args.control_samples // 3):
                continue
            controls.append(qid); seen_routes[route] += 1
            if len(controls) >= args.control_samples:
                break

    chosen_qids = selected + controls
    subset = [by_qid[q] for q in chosen_qids if q in by_qid]

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(subset, ensure_ascii=False, indent=2), encoding="utf-8")

    # Report (no answers, no correctness).
    route_dist = collections.Counter()
    reason_dist = collections.Counter()
    log_by_qid = {r.get("qid"): r for r in log_rows}
    for q in chosen_qids:
        route_dist[log_by_qid.get(q, {}).get("route", "?")] += 1
        reason_dist[selected_reasons.get(q, "control")] += 1
    print(f"policy           : {args.policy}")
    print(f"trigger samples  : {len(selected)} (of {len(triggers)} that trigger)")
    print(f"control samples  : {len(controls)}")
    print(f"total selected   : {len(subset)}")
    print(f"route distribution: {dict(route_dist)}")
    print(f"reason distribution: {dict(reason_dist)}")
    print(f"selected qids    : {chosen_qids}")
    print(f"output           : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
