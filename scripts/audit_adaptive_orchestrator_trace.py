#!/usr/bin/env python3
"""Trace-only audit of the adaptive orchestrator on the public test (no API calls).

Runs the orchestrator in trace_only mode over every public-test question, using the
v6b answers as the "existing answer" baseline, and reports route/branch/risk/formula
distributions. Verifies the trace-only invariant: ``would_override`` is 0 for all
rows and NO prediction is produced. No network, no ground truth, no external answer
sheet, no qid-based decisions (qids only align with the v6b log).

Usage:
    python scripts/audit_adaptive_orchestrator_trace.py \
      --input public-test_1780368312.json \
      --v6b-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --output output/adaptive_orchestrator_trace_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_orchestrator import AdaptiveConfig, AdaptiveOrchestrator  # noqa: E402
from src.formula_registry import all_formula_ids, eligible_formula_ids  # noqa: E402


def _load(path):
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def _v6b_answers(path):
    out = {}
    if not path or not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        if o.get("qid"):
            out[o["qid"]] = o.get("final_answer")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Adaptive orchestrator trace-only audit (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--v6b-log", default=None)
    ap.add_argument("--output", default="output/adaptive_orchestrator_trace_audit.csv")
    args = ap.parse_args(argv)

    samples = _load(args.input)
    v6b = _v6b_answers(args.v6b_log)
    orch = AdaptiveOrchestrator(AdaptiveConfig(enabled=True, mode="trace_only"))

    route_ct = Counter()
    branch_ct = Counter()
    risk_ct = Counter()
    formula_ct = Counter()
    would_override_rows = 0
    candidate_change_rows = 0
    unexpected_branches = []
    rows = []

    for s in samples:
        existing = v6b.get(s.get("qid"))
        tr = orch.analyze(s, existing_answer=existing, state=None)
        route_ct[tr.route] += 1
        branch_ct[tr.selected_branch] += 1
        for f in tr.risk_flags:
            risk_ct[f.split(":")[0]] += 1
        elig = eligible_formula_ids(s.get("question", ""))
        for fid in elig:
            formula_ct[fid] += 1
        if tr.would_override:
            would_override_rows += 1
        if tr.extra.get("any_candidate_would_change"):
            candidate_change_rows += 1
        if tr.selected_branch not in ("calculation", "long_context", "short_knowledge",
                                      "law_admin", "ambiguous"):
            unexpected_branches.append((s.get("qid"), tr.selected_branch))
        cand = tr.branch_candidates[0] if tr.branch_candidates else {}
        rows.append({
            "qid": s.get("qid"), "route": tr.route, "selected_branch": tr.selected_branch,
            "risk_flags": "|".join(tr.risk_flags), "eligible_formulas": "|".join(elig),
            "candidate_method": cand.get("method"), "candidate_answer": cand.get("answer"),
            "candidate_would_change_answer": cand.get("would_change_answer"),
            "v6b_answer": existing, "would_override": tr.would_override,
            "override_allowed": tr.override_allowed, "final_decision": tr.final_decision,
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("=" * 70)
    print("ADAPTIVE ORCHESTRATOR TRACE AUDIT (trace_only; no API; no ground truth)")
    print("=" * 70)
    print(f"total samples         : {len(samples)}")
    print(f"route distribution    : {dict(route_ct)}")
    print(f"branch distribution   : {dict(branch_ct)}")
    print(f"risk flag distribution: {dict(risk_ct)}")
    print("-" * 70)
    print(f"registry formula ids ({len(all_formula_ids())}): {all_formula_ids()}")
    print("metadata-eligible formula candidates (by question text):")
    for fid, n in formula_ct.most_common():
        print(f"  {fid:34s} {n}")
    print("-" * 70)
    print(f"rows where a candidate WOULD change the answer (informational): {candidate_change_rows}")
    print(f"would_override rows (MUST be 0 in trace_only)               : {would_override_rows}")
    print(f"unexpected branch selections                                : {len(unexpected_branches)} {unexpected_branches[:5]}")
    print(f"predictions changed                                         : 0 (no prediction file written)")
    print(f"diagnostic CSV written: {args.output}")
    if would_override_rows != 0:
        print("ERROR: trace_only invariant violated (would_override > 0)!")
        return 1
    print("OK: trace-only invariant holds (no overrides, no prediction produced).")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
