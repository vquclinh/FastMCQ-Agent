#!/usr/bin/env python3
"""Selective multi-candidate API runner (Phase 2L.26A).

DRY-RUN BY DEFAULT. ``--dry-run`` and ``--execute`` are mutually exclusive; without
``--execute`` no API call is made (it prints the plan + an upper-bound call count and
exits). With ``--execute`` it runs the selected agents on the planned qids, writing
candidate records to JSONL after every qid (crash-safe resume). The competition model
policy is asserted before any call. Writes only under ``scratch/``; never to output/.

See the audit for exact human-run commands.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import api_candidate_agents as agents  # noqa: E402
from src.adaptive_proposal_common import load_log, load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.formula_bank_solver import detect_formula_hints  # noqa: E402
from src.model_policy import assert_allowed_llm_model  # noqa: E402
from src.option_evidence import build_option_aware_evidence_pack  # noqa: E402

_AGENT_BUILDERS = ("route_specialist", "challenger", "option_elimination", "tool_hint")
_CSV_FIELDS = ["qid", "agent", "model", "temperature", "answer", "confidence", "rationale",
               "evidence", "risk", "parse_status", "v10_answer", "agrees_with_v10",
               "total_tokens", "timestamp"]


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


def _plan_qids(plan_path, max_qids):
    qids = []
    if plan_path and Path(plan_path).exists():
        qids = [r["qid"] for r in csv.DictReader(open(plan_path))]
    return qids[: max_qids] if max_qids else qids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Selective multi-candidate API runner")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--output-dir", default="scratch/selective_multicandidate_2l26")
    ap.add_argument("--max-qids", type=int, default=120)
    ap.add_argument("--agents", default=",".join(_AGENT_BUILDERS))
    ap.add_argument("--judge", default="pairwise", choices=["pairwise", "none"])
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--temperature-grid", default="0,0.2")
    ap.add_argument("--max-tokens", type=int, default=768)
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--cost-per-call-usd", type=float, default=0.002)
    ap.add_argument("--resume", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--timestamp", default="", help="run timestamp (no system clock in code)")
    args = ap.parse_args(argv)

    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute are mutually exclusive")
    # Hard model-policy guard BEFORE anything else (blocks disallowed --model).
    assert_allowed_llm_model(args.model)

    outdir = Path(args.output_dir)
    _guard_scratch(outdir)

    agent_list = [a.strip() for a in args.agents.split(",") if a.strip()]
    temps = [float(t) for t in args.temperature_grid.split(",") if t.strip() != ""]
    qids = _plan_qids(args.plan, args.max_qids)
    calls_per_qid = len(agent_list) * len(temps) + (1 if args.judge == "pairwise" else 0)
    upper_bound_calls = len(qids) * calls_per_qid
    est_cost = upper_bound_calls * args.cost_per_call_usd

    # DRY-RUN (default): print the plan and exit, no API.
    if not args.execute:
        print("=" * 64)
        print("SELECTIVE MULTI-CANDIDATE API — DRY-RUN (no API call)")
        print("=" * 64)
        print(f"model           : {args.model}")
        print(f"agents          : {agent_list}  judge: {args.judge}")
        print(f"temperature grid: {temps}")
        print(f"planned qids    : {len(qids)} (max {args.max_qids})")
        print(f"calls/qid       : {calls_per_qid}")
        print(f"upper-bound calls: {upper_bound_calls}")
        print(f"est. cost (USD) : {est_cost:.2f} (@ {args.cost_per_call_usd}/call)"
              + (f"  budget={args.budget_usd}" if args.budget_usd else ""))
        print("Pass --execute to run (human-initiated). No output/ writes ever.")
        print("=" * 64)
        return 0

    # EXECUTE path (human-initiated). Build the client lazily.
    outdir.mkdir(parents=True, exist_ok=True)
    jsonl_path = outdir / "api_candidates.jsonl"
    csv_path = outdir / "api_candidates.csv"

    done = set()
    if args.resume and jsonl_path.exists():
        for line in jsonl_path.read_text().splitlines():
            try:
                o = json.loads(line)
                if o.get("qid") and o.get("agent"):
                    done.add((o["qid"], o["agent"], o.get("temperature")))
            except Exception:
                pass

    from src.selective_api_client import SelectiveAPIClient   # pragma: no cover
    client = SelectiveAPIClient(args.model, max_tokens=args.max_tokens)   # pragma: no cover

    samples = {s.get("qid"): s for s in load_samples(args.input)}         # pragma: no cover
    base = load_pred(args.base_pred)                                      # pragma: no cover
    log = load_log(args.v10_log)                                          # pragma: no cover

    rows = []                                                            # pragma: no cover
    judge_ran = 0                                                        # pragma: no cover
    judge_skips = {}                                                     # pragma: no cover
    with open(jsonl_path, "a", encoding="utf-8") as jf:                  # pragma: no cover
        for qid in qids:
            sample = samples.get(qid)
            if not sample:
                continue
            v10 = base.get(qid)
            rec = log.get(qid, {})
            pool = build_candidate_pool(sample, v10, rec)
            evidence = None
            if rec.get("route") == "long_context":
                pk = build_option_aware_evidence_pack(sample)
                evidence = pk.pack_text if pk.matched else None
            hints = [h["hint"] for h in detect_formula_hints(sample) if not h["safe_to_override"]]
            tool_cands = [c.to_dict() for c in pool.candidates if c.source.startswith("tool:")]

            qid_candidates = []           # this qid's valid agent candidates (for the judge)
            for temp in temps:
                for agent in agent_list:
                    if args.budget_usd and client.total_calls * args.cost_per_call_usd >= args.budget_usd:
                        print(f"[budget] stopping: {client.total_calls} calls reached budget")
                        break
                    if (qid, agent, temp) in done:
                        continue
                    if agent == "route_specialist":
                        msgs = agents.build_route_specialist(sample, rec.get("route", "default"), evidence)
                    elif agent == "challenger":
                        msgs = agents.build_challenger(sample, v10)
                    elif agent == "option_elimination":
                        msgs = agents.build_option_elimination(sample)
                    elif agent == "tool_hint":
                        msgs = agents.build_tool_hint(sample, hints, tool_cands)
                    else:
                        continue
                    content, usage = client.chat(msgs, temperature=temp)
                    parsed = agents.parse_candidate(content, sample)
                    out = {"qid": qid, "agent": agent, "model": args.model, "temperature": temp,
                           **parsed, "v10_answer": v10,
                           "agrees_with_v10": parsed["answer"] == v10,
                           "total_tokens": usage.get("total_tokens"), "timestamp": args.timestamp}
                    jf.write(json.dumps(out, ensure_ascii=False) + "\n"); jf.flush()
                    rows.append(out)
                    if parsed.get("parse_status") == "ok":
                        qid_candidates.append(out)

            # Pairwise judge: run when requested AND a valid candidate conflicts with v10.
            if args.judge == "pairwise" and (qid, "pairwise_judge", None) not in done:
                alts = [c for c in qid_candidates if c["answer"] != v10]
                if not alts:
                    judge_skips[qid] = "no alternative candidate conflicts with v10"
                elif args.budget_usd and client.total_calls * args.cost_per_call_usd >= args.budget_usd:
                    judge_skips[qid] = "budget reached before judge"
                else:
                    jmsgs = agents.build_pairwise_judge(
                        sample, v10, [{"source": f"api:{c['agent']}", "answer": c["answer"],
                                       "risk_level": c.get("risk"),
                                       "evidence_text": c.get("evidence", "")} for c in alts])
                    content, usage = client.chat(jmsgs, temperature=0.0)
                    jparsed = agents.parse_judge(content, sample)
                    jout = {"qid": qid, "agent": "pairwise_judge", "model": args.model,
                            "temperature": 0.0, "answer": jparsed.get("winner_answer"),
                            "confidence": jparsed.get("confidence"),
                            "rationale": jparsed.get("reason", ""), "evidence": "",
                            "risk": "medium", "parse_status": jparsed.get("parse_status"),
                            "requires_manual_review": jparsed.get("requires_manual_review"),
                            "v10_answer": v10,
                            "agrees_with_v10": jparsed.get("winner_answer") == v10,
                            "total_tokens": usage.get("total_tokens"), "timestamp": args.timestamp}
                    jf.write(json.dumps(jout, ensure_ascii=False) + "\n"); jf.flush()
                    rows.append(jout)
                    judge_ran += 1

    with open(csv_path, "w", newline="") as cf:                          # pragma: no cover
        w = csv.DictWriter(cf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for line in jsonl_path.read_text().splitlines():
            try:
                w.writerow(json.loads(line))
            except Exception:
                pass
    summary = {"model": args.model, "agents": agent_list, "judge": args.judge,
               "planned_qids": len(qids), "calls_made": client.total_calls,
               "total_tokens": client.total_tokens, "judge_ran": judge_ran,
               "judge_skipped": len(judge_skips), "judge_skip_reasons": judge_skips}
    (outdir / "api_run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (outdir / "api_run_summary.md").write_text(
        f"# Selective API Run\n\nmodel: {args.model}\ncalls: {client.total_calls}\n"
        f"planned qids: {len(qids)}\njudge_ran: {judge_ran}\njudge_skipped: {len(judge_skips)}\n")
    print(f"[execute] calls={client.total_calls} judge_ran={judge_ran} -> {jsonl_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
