#!/usr/bin/env python3
"""Adaptive, budget-aware selective API runner (Phase 2L.27B).

DRY-RUN BY DEFAULT (``--dry-run``/``--execute`` mutually exclusive). Reads the overall
accuracy plan, skips ``tool_only`` questions, and for the rest picks agents/temperatures
per the question's recommended layer (cheap: challenger+option_elimination @temp 0,
judge only on disagreement; rich: all 4 agents @temp 0,0.2, judge on conflict;
evidence_pack: API only if the offline evidence pack is weak). Enforces the model
policy, writes only under ``scratch/``, and never touches output/. No qid hardcoding.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.api import api_candidate_agents as agents  # noqa: E402
from src.layers.adaptive_proposal_common import load_log, load_pred, load_samples  # noqa: E402
from src.solvers.calculation_first_planner import (build_calculation_tool_context,  # noqa: E402
                                           format_tool_context_for_prompt)
from src.evidence.evidence_pack import build_long_context_evidence_pack  # noqa: E402
from src.solvers.formula_bank_solver import detect_formula_hints  # noqa: E402
from src.api.model_policy import assert_allowed_llm_model  # noqa: E402

_CSV_FIELDS = ["qid", "agent", "model", "temperature", "answer", "confidence", "rationale",
               "evidence", "risk", "parse_status", "v10_answer", "agrees_with_v10",
               "layer", "total_tokens", "timestamp"]
_MODE_LAYERS = {  # which plan layers actually get an API call in each mode
    "cheap": {"cheap_api"},
    "balanced": {"cheap_api", "rich_api"},
    "rich": {"cheap_api", "rich_api", "evidence_pack"},
}


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


_CALC_MAX_TOKENS = 384   # compact calc agent must fit a small budget (pilot truncated at 768+)


def _agents_temps_for(layer, route=None):
    """Route-aware agent/temperature plan. Calculation goes TOOL-FIRST (compact calc agent)."""
    if layer == "cheap_api":
        if route == "calculation":
            return ["calculation_solver"], [0.0]     # + optional option_elimination fallback
        return ["challenger", "option_elimination"], [0.0]
    if layer == "rich_api":
        if route == "calculation":
            return ["calculation_solver", "challenger", "option_elimination"], [0.0, 0.2]
        return ["route_specialist", "challenger", "option_elimination", "tool_hint"], [0.0, 0.2]
    if layer == "evidence_pack":
        return ["route_specialist", "challenger"], [0.0]
    return [], []


def _plan_rows(plan_path, max_qids):
    rows = []
    if plan_path and Path(plan_path).exists():
        rows = [r for r in csv.DictReader(open(plan_path))]
    return rows[: max_qids] if max_qids else rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Adaptive selective API runner (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--output-dir", default="scratch/adaptive_selective_2l27b")
    ap.add_argument("--max-qids", type=int, default=40)
    ap.add_argument("--mode", default="balanced", choices=["cheap", "balanced", "rich"])
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--cost-per-call-usd", type=float, default=0.002)
    ap.add_argument("--resume", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--timestamp", default="")
    ap.add_argument("--out-prefix", default="adaptive",
                    help="basename prefix for candidate/summary files (pilot wrapper uses 'pilot')")
    args = ap.parse_args(argv)

    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute are mutually exclusive")
    assert_allowed_llm_model(args.model)
    _guard_scratch(args.output_dir)

    mode_layers = _MODE_LAYERS[args.mode]
    plan = _plan_rows(args.plan, args.max_qids)
    # Schedule only questions whose recommended layer gets an API call in this mode.
    scheduled = [r for r in plan if r.get("recommended_layer") in mode_layers]

    # Upper-bound call estimate (agents + optional calc fallback + at most one judge).
    upper = 0
    for r in scheduled:
        ags, temps = _agents_temps_for(r["recommended_layer"], r.get("route"))
        fallback = 1 if (r.get("route") == "calculation"
                         and r["recommended_layer"] == "cheap_api") else 0
        upper += len(ags) * len(temps) + fallback + 1   # +fallback (calc) +1 possible judge
    est_cost = upper * args.cost_per_call_usd

    if not args.execute:
        print("=" * 64)
        print(f"ADAPTIVE SELECTIVE API — DRY-RUN ({args.mode}; no API call)")
        print("=" * 64)
        print(f"model            : {args.model}")
        print(f"plan rows        : {len(plan)} (max {args.max_qids})")
        print(f"scheduled (mode) : {len(scheduled)}  layers={sorted(mode_layers)}")
        print(f"upper-bound calls: {upper}   est. cost USD: {est_cost:.2f}"
              + (f"   budget={args.budget_usd}" if args.budget_usd else ""))
        print("Pass --execute to run (human-initiated). No output/ writes ever.")
        print("=" * 64)
        return 0

    # EXECUTE (human-initiated).
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    jsonl_path = outdir / f"{args.out_prefix}_api_candidates.jsonl"
    csv_path = outdir / f"{args.out_prefix}_api_candidates.csv"
    done = set()
    if args.resume and jsonl_path.exists():
        for line in jsonl_path.read_text().splitlines():
            try:
                o = json.loads(line)
                done.add((o.get("qid"), o.get("agent"), o.get("temperature")))
            except Exception:
                pass

    from src.api.selective_api_client import SelectiveAPIClient   # pragma: no cover
    client = SelectiveAPIClient(args.model)                   # pragma: no cover
    samples = {s.get("qid"): s for s in load_samples(args.input)}   # pragma: no cover
    base = load_pred(args.base_pred); log = load_log(args.v10_log)   # pragma: no cover
    judge_ran = 0                                              # pragma: no cover

    with open(jsonl_path, "a", encoding="utf-8") as jf:        # pragma: no cover
        for r in scheduled:
            qid = r["qid"]; sample = samples.get(qid)
            if not sample:
                continue
            layer = r["recommended_layer"]
            if layer == "evidence_pack" and args.mode == "rich":
                pk = build_long_context_evidence_pack(sample)
                if pk.matched and pk.evidence_pack_size > 400:
                    continue                       # evidence is sufficient -> no API
            v10 = base.get(qid); rec = log.get(qid, {})
            route = r.get("route") or rec.get("route")
            ags, temps = _agents_temps_for(layer, route)
            evidence = None
            if route == "long_context":
                pk = build_long_context_evidence_pack(sample)
                evidence = pk.text if pk.matched else None
            hints = [h["hint"] for h in detect_formula_hints(sample) if not h["safe_to_override"]]
            calc_ctx = (format_tool_context_for_prompt(build_calculation_tool_context(sample))
                        if route == "calculation" else None)

            def _budget_left():
                return not (args.budget_usd and client.total_calls * args.cost_per_call_usd >= args.budget_usd)

            def _run(agent, temp):
                if (qid, agent, temp) in done:
                    return None
                if agent == "calculation_solver":
                    msgs = agents.build_calculation_solver(sample, calc_ctx)
                    content, usage = client.chat(msgs, temperature=temp, max_tokens=_CALC_MAX_TOKENS)
                    parsed = agents.parse_calculation_candidate(content, sample)
                elif agent == "route_specialist":
                    msgs = agents.build_route_specialist(sample, route or "default", evidence)
                    content, usage = client.chat(msgs, temperature=temp)
                    parsed = agents.parse_candidate(content, sample)
                elif agent == "challenger":
                    content, usage = client.chat(agents.build_challenger(sample, v10), temperature=temp)
                    parsed = agents.parse_candidate(content, sample)
                elif agent == "option_elimination":
                    content, usage = client.chat(agents.build_option_elimination(sample), temperature=temp)
                    parsed = agents.parse_candidate(content, sample)
                else:
                    content, usage = client.chat(agents.build_tool_hint(sample, hints, None), temperature=temp)
                    parsed = agents.parse_candidate(content, sample)
                out = {"qid": qid, "agent": agent, "model": args.model, "temperature": temp,
                       **parsed, "v10_answer": v10, "agrees_with_v10": parsed.get("answer") == v10,
                       "layer": layer, "total_tokens": usage.get("total_tokens"),
                       "timestamp": args.timestamp}
                jf.write(json.dumps(out, ensure_ascii=False) + "\n"); jf.flush()
                return out

            qcands = []
            for temp in temps:
                for agent in ags:
                    if not _budget_left():
                        break
                    out = _run(agent, temp)
                    if out and out.get("parse_status") == "ok":
                        qcands.append(out)
            # Calculation cheap-mode fallback: if the calc agent gave no usable candidate
            # OR its candidate conflicts with v10, try option_elimination once.
            if route == "calculation" and layer == "cheap_api" and _budget_left() \
                    and (qid, "option_elimination", 0.0) not in done \
                    and (not qcands or any(c["answer"] != v10 for c in qcands)):
                out = _run("option_elimination", 0.0)
                if out and out.get("parse_status") == "ok":
                    qcands.append(out)
            # Judge only on genuine disagreement (vs v10 or among agents) with valid evidence.
            distinct = {c["answer"] for c in qcands}
            conflict = any(c["answer"] != v10 for c in qcands) and len(distinct) >= 1
            if conflict and len(qcands) >= 2 and (qid, "pairwise_judge", None) not in done:
                if not (args.budget_usd and client.total_calls * args.cost_per_call_usd >= args.budget_usd):
                    jmsgs = agents.build_pairwise_judge(sample, v10, [
                        {"source": f"api:{c['agent']}", "answer": c["answer"],
                         "risk_level": c.get("risk"), "evidence_text": c.get("evidence", "")}
                        for c in qcands if c["answer"] != v10])
                    content, usage = client.chat(jmsgs, temperature=0.0)
                    jp = agents.parse_judge(content, sample)
                    jf.write(json.dumps({"qid": qid, "agent": "pairwise_judge", "model": args.model,
                                         "temperature": 0.0, "answer": jp.get("winner_answer"),
                                         "confidence": jp.get("confidence"), "rationale": jp.get("reason", ""),
                                         "evidence": "", "risk": "medium", "parse_status": jp.get("parse_status"),
                                         "requires_manual_review": jp.get("requires_manual_review"),
                                         "v10_answer": v10, "agrees_with_v10": jp.get("winner_answer") == v10,
                                         "layer": layer, "total_tokens": usage.get("total_tokens"),
                                         "timestamp": args.timestamp}, ensure_ascii=False) + "\n")
                    jf.flush(); judge_ran += 1

    with open(csv_path, "w", newline="") as cf:                # pragma: no cover
        w = csv.DictWriter(cf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for line in jsonl_path.read_text().splitlines():
            try:
                w.writerow(json.loads(line))
            except Exception:
                pass
    summary = {"mode": args.mode, "model": args.model, "scheduled": len(scheduled),
               "calls_made": client.total_calls, "judge_ran": judge_ran}
    (outdir / f"{args.out_prefix}_run_summary.json").write_text(json.dumps(summary, indent=2))
    (outdir / f"{args.out_prefix}_run_summary.md").write_text(
        f"# Adaptive Selective API ({args.mode})\n\ncalls: {client.total_calls}\n"
        f"scheduled: {len(scheduled)}\njudge_ran: {judge_ran}\n")
    print(f"[execute] mode={args.mode} calls={client.total_calls} judge_ran={judge_ran}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
