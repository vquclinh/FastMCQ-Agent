#!/usr/bin/env python3
"""Repair a failed/partial independent v11 run (Phase 2L.30C; no v10).

Reads an existing ``v11_independent_decisions.csv`` + ``v11_independent_candidates.jsonl``,
finds qids with missing / None / invalid labels (and duplicate qids), and repairs them
WITHOUT v10: first by reusing a valid parsed candidate from the JSONL, else (only with
``--execute``) by a direct allowed-model fallback, else a deterministic first-label last
resort. DRY-RUN reports how many qids need repair + estimated API calls. Writes the repaired
decisions + report under the work-dir; the final CSV under outputs/ only with explicit
acknowledgement. Refuses protected output names. No qid hardcoding, no ground truth.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import guard_output, load_samples  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.model_policy import assert_allowed_llm_model  # noqa: E402

_PROTECTED_NAMES = {"pred.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv"}
# Deterministic preference when several valid candidates exist for a broken qid.
_SOURCE_PRIORITY = ("calculation_solver", "route_specialist", "challenger", "option_elimination",
                    "tool_hint")


def _require_outputs(path):
    p = str(path).replace("\\", "/")
    if "/outputs/" not in p and not p.startswith("outputs/"):
        raise SystemExit(f"REFUSING: --output must be under outputs/ (got {path})")
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite a protected/locked file: {Path(path).name}")
    guard_output(path)


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: --work-dir must be under scratch/ (got {path})")


def _load_candidates(path):
    by_qid = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("qid"):
                by_qid.setdefault(o["qid"], []).append(o)
    return by_qid


def _best_valid_candidate(records, labels):
    """Pick a valid parsed candidate for a broken qid: parse ok + label valid; prefer a
    known agent priority then highest confidence. Returns the record or None."""
    valid = [r for r in records
             if r.get("parse_status") == "ok" and r.get("answer") in labels
             and r.get("agent") != "pairwise_judge"]
    if not valid:
        # a judge with a valid winner counts too
        valid = [r for r in records if r.get("agent") == "pairwise_judge"
                 and r.get("answer") in labels and r.get("parse_status") == "ok"]
    if not valid:
        return None

    def _rank(r):
        ag = r.get("agent") or ""
        pri = _SOURCE_PRIORITY.index(ag) if ag in _SOURCE_PRIORITY else len(_SOURCE_PRIORITY)
        return (pri, -float(r.get("confidence") or 0.0))
    return sorted(valid, key=_rank)[0]


def _is_bad(answer, labels):
    return (answer is None) or (str(answer).strip() in ("", "None")) or (answer not in labels)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Repair a failed independent v11 run (no v10)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--cost-per-call-usd", type=float, default=0.002)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--i-understand-this-writes-outputs", action="store_true", default=False)
    args = ap.parse_args(argv)

    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute are mutually exclusive")
    assert_allowed_llm_model(args.model)
    _guard_scratch(args.work_dir)
    _require_outputs(args.output)

    workdir = Path(args.work_dir)
    dec_path = workdir / "v11_independent_decisions.csv"
    if not dec_path.exists():
        raise SystemExit(f"decisions file not found: {dec_path}")
    samples = {s.get("qid"): s for s in load_samples(args.input)}
    by_qid_cands = _load_candidates(workdir / "v11_independent_candidates.jsonl")
    rows = list(csv.DictReader(open(dec_path)))

    # Detect problems (deduplicate keeping the first valid row per qid).
    seen, deduped, duplicate_qids = {}, [], 0
    for r in rows:
        qid = r.get("qid")
        if qid in seen:
            duplicate_qids += 1
            # prefer a valid row over a previously-stored invalid one
            labels = labels_for(len(samples.get(qid, {}).get("choices", []) or []))
            if _is_bad(seen[qid].get("final_answer"), labels) and not _is_bad(r.get("final_answer"), labels):
                seen[qid] = r
            continue
        seen[qid] = r
    deduped = list(seen.values())

    missing = [q for q in samples if q not in seen]
    invalid, none_labels = [], []
    for q, r in seen.items():
        if q not in samples:
            continue
        labels = labels_for(len(samples[q].get("choices", []) or []))
        a = r.get("final_answer")
        if _is_bad(a, labels):
            invalid.append(q)
            if a is None or str(a).strip() in ("", "None"):
                none_labels.append(q)

    broken = sorted(set(invalid) | set(missing))
    # How many broken qids can be repaired from existing candidates vs need an API call.
    repairable_from_cands = need_api = 0
    for q in broken:
        labels = labels_for(len(samples.get(q, {}).get("choices", []) or []))
        if _best_valid_candidate(by_qid_cands.get(q, []), labels):
            repairable_from_cands += 1
        else:
            need_api += 1
    est_cost = need_api * args.cost_per_call_usd

    report = {"total_in_dataset": len(samples), "decision_rows": len(rows),
              "unique_qids": len(seen), "duplicate_qids": duplicate_qids,
              "missing_qids": len(missing), "invalid_labels": len(invalid),
              "none_labels": len(none_labels), "broken_total": len(broken),
              "repairable_from_candidates": repairable_from_cands,
              "need_direct_fallback_api": need_api, "estimated_api_calls": need_api,
              "estimated_cost_usd": round(est_cost, 4)}

    if not args.execute:
        print("=" * 64)
        print("REPAIR INDEPENDENT V11 — DRY-RUN (no API, no outputs)")
        print("=" * 64)
        for k, v in report.items():
            print(f"  {k}: {v}")
        print("Pass --execute --i-understand-this-writes-outputs to repair + write the CSV.")
        print("=" * 64)
        # diagnostic report only (scratch), no outputs CSV, no API
        (workdir / "v11_independent_repair_report.json").write_text(json.dumps(report, indent=2))
        return 0

    if not args.i_understand_this_writes_outputs:
        raise SystemExit("REFUSING: pass --i-understand-this-writes-outputs to write a real submission.")

    # EXECUTE: repair broken qids (candidate reuse first, then direct fallback, then last resort).
    client = agents = None
    repaired_rows = {q: dict(seen[q]) for q in seen if q in samples}
    repair_log = []
    for q in broken:
        labels = labels_for(len(samples[q].get("choices", []) or []))
        orig = (seen.get(q) or {}).get("final_answer")
        best = _best_valid_candidate(by_qid_cands.get(q, []), labels)
        if best:
            repaired_rows[q] = {"qid": q, "final_answer": best["answer"],
                                "final_source": f"repaired_from_candidate:{best.get('agent')}",
                                "route": best.get("route", ""), "risk": "high",
                                "evidence_summary": str(best.get("evidence", ""))[:160],
                                "proof_summary": "", "candidate_count": len(by_qid_cands.get(q, [])),
                                "rejected_count": 0, "judge_used": False, "fallback_used": False,
                                "parse_status_summary": "{}",
                                "note": f"reused valid candidate (was: {orig!r})"}
            repair_log.append({"qid": q, "method": "candidate_reuse", "answer": best["answer"]})
            continue
        # direct allowed-model fallback (never v10)
        ans = None
        if not (args.budget_usd and client and client.total_calls * args.cost_per_call_usd >= args.budget_usd):  # pragma: no cover
            if client is None:  # pragma: no cover
                from src.selective_api_client import SelectiveAPIClient
                from src import api_candidate_agents as _agents
                client, agents = SelectiveAPIClient(args.model), _agents
            content, _ = client.chat(agents.build_route_specialist(samples[q], "default", None),
                                     temperature=0.0)  # pragma: no cover
            parsed = agents.parse_candidate(content, samples[q])  # pragma: no cover
            ans = parsed.get("answer")  # pragma: no cover
        method = "direct_fallback"
        if ans not in labels:
            ans = labels[0] if labels else None       # deterministic last resort (no v10/truth)
            method = "first_label_last_resort"
        repaired_rows[q] = {"qid": q, "final_answer": ans, "final_source": "direct_fallback_repair",
                            "route": "", "risk": "high", "evidence_summary": "", "proof_summary": "",
                            "candidate_count": len(by_qid_cands.get(q, [])), "rejected_count": 0,
                            "judge_used": False, "fallback_used": True, "parse_status_summary": "{}",
                            "note": f"{method} (was: {orig!r})"}
        repair_log.append({"qid": q, "method": method, "answer": ans})

    # Materialize every dataset qid (in dataset order).
    dec_fields = ["qid", "final_answer", "final_source", "route", "risk", "evidence_summary",
                  "proof_summary", "candidate_count", "rejected_count", "judge_used",
                  "fallback_used", "parse_status_summary", "note"]
    final_rows = []
    for q in samples:
        r = repaired_rows.get(q)
        if r is None:                                   # qid absent everywhere -> last resort
            labels = labels_for(len(samples[q].get("choices", []) or []))
            r = {"qid": q, "final_answer": (labels[0] if labels else None),
                 "final_source": "direct_fallback_repair", "route": "", "risk": "high",
                 "evidence_summary": "", "proof_summary": "", "candidate_count": 0,
                 "rejected_count": 0, "judge_used": False, "fallback_used": True,
                 "parse_status_summary": "{}", "note": "missing qid -> first-label last resort"}
        final_rows.append({k: r.get(k, "") for k in dec_fields})

    # Validate.
    for r in final_rows:
        labels = labels_for(len(samples[r["qid"]].get("choices", []) or []))
        if r["final_answer"] not in labels:
            raise SystemExit(f"REFUSING: invalid label {r['final_answer']} for {r['qid']}")
    if {r["qid"] for r in final_rows} != set(samples) or len(final_rows) != len(samples):
        raise SystemExit("REFUSING: repaired qid set/row-count != dataset")

    with open(workdir / "v11_independent_decisions_repaired.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=dec_fields); w.writeheader(); w.writerows(final_rows)
    report["repaired"] = len(repair_log)
    report["repair_methods"] = dict(Counter(x["method"] for x in repair_log))
    (workdir / "v11_independent_repair_report.json").write_text(json.dumps(report, indent=2))
    (workdir / "v11_independent_repair_report.md").write_text(
        "# Independent v11 Repair Report (no v10)\n\n"
        + "\n".join(f"- {k}: {v}" for k, v in report.items())
        + "\n\n## Repairs\n\n"
        + "\n".join(f"- {x['qid']}: {x['method']} -> {x['answer']}" for x in repair_log[:80]))

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader()
        for r in final_rows:
            w.writerow({"qid": r["qid"], "answer": r["final_answer"]})

    print("=" * 64)
    print("REPAIR INDEPENDENT V11 — DONE")
    print("=" * 64)
    print(f"broken repaired : {len(repair_log)}  methods={report['repair_methods']}")
    print(f"submission      : {outp}  ({len(final_rows)} rows)")
    print(f"repaired CSV    : {workdir / 'v11_independent_decisions_repaired.csv'}")
    print("v10 NOT used. Review before submitting.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
