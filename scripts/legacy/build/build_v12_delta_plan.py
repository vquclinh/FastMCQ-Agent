#!/usr/bin/env python3
"""Phase 2L.34A — V12 delta candidate miner (OFFLINE, no API).

Ranks qids of the frozen v11 winner by *risk / opportunity*: where is the current answer
most likely weak, and therefore worth an independent second look? It NEVER changes any answer
— it only emits a plan CSV that downstream tools (run_v12_delta_verifier.py +
build_v12_delta_candidate.py) consume.

Signals (all derived from already-computed v11 artifacts; no ground truth, no qid hardcoding):
  * direct_fallback / direct_fallback_repair source  (a guess — highest opportunity)
  * high / medium decision risk
  * v11 vs v10 disagreement
  * independent API-candidate disagreement with the current answer
  * calculation route without a deterministic (formula_bank) proof
  * many-choice questions (>= 5 options)
  * parser failures in the candidate pool
  * long-context route
  * weak single-source (api:* single agent) provenance
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.utils.data_io import load_dataset, read_predictions  # noqa: E402

# Source provenance buckets.
_FALLBACK_SOURCES = {"direct_fallback", "direct_fallback_repair"}
_DETERMINISTIC_SOURCES = {"formula_bank"}
_SINGLE_API_PREFIX = "api:"          # single-agent API source => weaker than consensus
_MULTI_SOURCES = {"consensus"}       # >=2 independent agree


def _read_csv_map(path, key, val):
    out = {}
    if not path or not Path(path).exists():
        return out
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get(key):
                out[row[key]] = row.get(val)
    return out


def _read_decisions(path):
    rows = {}
    if not path or not Path(path).exists():
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("qid"):
                rows[row["qid"]] = row
    return rows


def _read_candidates(path):
    """qid -> list of candidate dicts (the per-agent v11 proposals)."""
    out = defaultdict(list)
    if not path or not Path(path).exists():
        return out
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


def _suggested_agents(route, n_choices, disagree_v10):
    route = (route or "").lower()
    if route == "calculation":
        agents = ["deterministic_solver", "numeric_consistency", "calculation_solver"]
    else:
        agents = ["route_specialist", "challenger", "option_grounding"]
    if n_choices >= 5 and "option_grounding" not in agents:
        agents.append("option_elimination")
    elif n_choices >= 5:
        agents.append("option_elimination")
    if disagree_v10:
        agents.append("pairwise_judge")
    return agents


def _needs_api(agents):
    # deterministic_solver / numeric_consistency / option_grounding are offline; the rest call the model.
    offline = {"deterministic_solver", "numeric_consistency", "option_grounding"}
    return any(a not in offline for a in agents)


def build_plan(samples, current, *, v10=None, decisions=None, candidates=None):
    decisions = decisions or {}
    candidates = candidates or {}
    v10 = v10 or {}
    plan = []
    for s in samples:
        qid = s["qid"]
        choices = s.get("choices") or []
        n_choices = len(choices)
        cur = current.get(qid, "")
        dec = decisions.get(qid, {})
        source = (dec.get("final_source") or "").strip()
        route = (dec.get("route") or "").strip()
        risk = (dec.get("risk") or "").strip().lower()

        reasons = []
        score = 0.0

        if source in _FALLBACK_SOURCES:
            score += 5.0
            reasons.append(f"fallback_source:{source}")
        elif source.startswith(_SINGLE_API_PREFIX):
            score += 1.0
            reasons.append(f"single_api_source:{source}")

        if risk == "high":
            score += 3.0
            reasons.append("risk:high")
        elif risk == "medium":
            score += 1.0
            reasons.append("risk:medium")

        v10_ans = (v10.get(qid) or "").strip()
        disagree_v10 = bool(v10_ans) and bool(cur) and v10_ans != cur
        if disagree_v10:
            score += 2.0
            reasons.append(f"v11!=v10({cur}vs{v10_ans})")

        cand_list = candidates.get(qid, [])
        cand_answers = {(c.get("answer") or "").strip() for c in cand_list if c.get("answer")}
        if cand_answers and any(a and a != cur for a in cand_answers):
            score += 2.0
            reasons.append("api_candidate_disagreement")
        bad_parse = sum(1 for c in cand_list if (c.get("parse_status") or "ok") != "ok")
        if bad_parse:
            score += 1.0
            reasons.append(f"parse_failures:{bad_parse}")

        if route == "calculation" and source not in _DETERMINISTIC_SOURCES:
            score += 2.0
            reasons.append("calc_without_deterministic_proof")

        if n_choices >= 5:
            score += 1.0
            reasons.append(f"many_choices:{n_choices}")

        if route == "long_context":
            score += 1.0
            reasons.append("long_context")

        agents = _suggested_agents(route, n_choices, disagree_v10)
        plan.append({
            "qid": qid,
            "current_answer": cur,
            "route": route,
            "current_source": source,
            "risk_reason": ";".join(reasons) if reasons else "none",
            "opportunity_score": round(score, 3),
            "suggested_agents": "|".join(agents),
            "needs_api": "true" if _needs_api(agents) else "false",
            "notes": (dec.get("note") or "")[:160],
        })
    plan.sort(key=lambda r: (-r["opportunity_score"], r["qid"]))
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V12 delta candidate miner (offline)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--v10", default=None)
    ap.add_argument("--decisions", default=None)
    ap.add_argument("--candidates", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-score", type=float, default=0.0,
                    help="only emit qids with opportunity_score > this (default 0: all)")
    args = ap.parse_args(argv)

    samples = load_dataset(args.input)
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    v10 = _read_csv_map(args.v10, "qid", "answer")
    decisions = _read_decisions(args.decisions)
    candidates = _read_candidates(args.candidates)

    plan = build_plan(samples, current, v10=v10, decisions=decisions, candidates=candidates)
    emitted = [r for r in plan if r["opportunity_score"] > args.min_score]

    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    cols = ["qid", "current_answer", "route", "current_source", "risk_reason",
            "opportunity_score", "suggested_agents", "needs_api", "notes"]
    with outp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(emitted)

    top = emitted[:10]
    print("=" * 60)
    print("V12 DELTA PLAN (offline, no API)")
    print(f"input questions     : {len(samples)}")
    print(f"planned (score>{args.min_score}) : {len(emitted)} / {len(plan)}")
    print(f"needs_api qids      : {sum(1 for r in emitted if r['needs_api'] == 'true')}")
    print(f"output              : {outp}")
    print("-- top opportunities --")
    for r in top:
        print(f"  {r['qid']}  score={r['opportunity_score']:<5} {r['route'] or '-':<14} "
              f"{r['current_source'] or '-':<22} {r['risk_reason'][:60]}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
