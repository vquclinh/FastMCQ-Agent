#!/usr/bin/env python3
"""Pilot failure analyzer (Phase 2L.28B; read-only, no API).

Reads the executed pilot candidates + decisions and produces a per-qid breakdown plus a
top-failure-mode summary (placeholder evidence, numeric mismatch, truncation/no-JSON, no
tool candidate, conflicting weak candidates) and a verdict on whether the bottleneck is
prompt / parser / solver-coverage / planner. No API, no inference, scratch-only output.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.candidate_consistency import detect_placeholder_evidence  # noqa: E402

_FIELDS = ["qid", "route", "v10_answer", "candidate_answers", "n_candidates", "ok",
           "placeholder", "numeric_mismatch", "no_json", "truncated", "judge_present",
           "tool_candidate", "primary_failure"]
_TRUNC_TOKENS = 900  # no_json above this token count is almost certainly truncation


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


def _load_jsonl(path):
    by_qid = {}
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


def _primary_failure(ph, mm, nj, tr, has_tool, n_alt_conflict):
    if nj or tr:
        return "truncation"
    if mm:
        return "numeric_mismatch"
    if ph:
        return "placeholder_evidence"
    if not has_tool and n_alt_conflict:
        return "conflicting_weak_candidates"
    if not has_tool:
        return "no_tool_candidate"
    return "none"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Analyze pilot failures (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--pilot-qids", required=True)
    ap.add_argument("--pilot-candidates", required=True)
    ap.add_argument("--pilot-decisions", default=None)
    ap.add_argument("--output-dir", default="scratch/adaptive_pilot_2l28b")
    args = ap.parse_args(argv)
    _guard_scratch(args.output_dir)
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    pilot = list(csv.DictReader(open(args.pilot_qids)))
    api = _load_jsonl(args.pilot_candidates)

    rows = []
    mode_totals = Counter()
    agent_empty_evidence = Counter()
    agent_totals = Counter()
    for pr in pilot:
        qid = pr.get("qid"); sample = samples.get(qid)
        if not sample:
            continue
        recs = api.get(qid, [])
        v10 = base.get(qid)
        ph = mm = nj = tr = judge = 0
        ans = []
        for r in recs:
            ag = r.get("agent"); st = r.get("parse_status")
            agent_totals[ag] += 1
            if not (r.get("evidence") or "").strip():
                agent_empty_evidence[ag] += 1
            if ag == "pairwise_judge":
                judge += 1
                continue
            ans.append(r.get("answer"))
            if st == "no_json":
                nj += 1
                if (r.get("total_tokens") or 0) >= _TRUNC_TOKENS:
                    tr += 1
            elif st == "numeric_mismatch":
                mm += 1
            elif detect_placeholder_evidence(r.get("evidence", "")):
                ph += 1
        pool = build_candidate_pool(sample, v10, None)
        has_tool = any(c.source.startswith("tool:") for c in pool.candidates)
        n_alt_conflict = sum(1 for a in ans if a and a != v10)
        pf = _primary_failure(ph, mm, nj, tr, has_tool, n_alt_conflict)
        for k in ("placeholder_evidence", "numeric_mismatch", "truncation",
                  "no_tool_candidate", "conflicting_weak_candidates", "none"):
            if pf == k:
                mode_totals[k] += 1
        rows.append({"qid": qid, "route": pr.get("route"), "v10_answer": v10,
                     "candidate_answers": "|".join(a or "?" for a in ans),
                     "n_candidates": len(ans), "ok": sum(1 for r in recs
                                                         if r.get("parse_status") == "ok"
                                                         and r.get("agent") != "pairwise_judge"),
                     "placeholder": ph, "numeric_mismatch": mm, "no_json": nj, "truncated": tr,
                     "judge_present": judge, "tool_candidate": has_tool, "primary_failure": pf})

    with open(outdir / "pilot_failure_analysis.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS); w.writeheader(); w.writerows(rows)

    # Diagnose the dominant bottleneck.
    diagnosis = []
    if mode_totals["truncation"]:
        diagnosis.append(f"**prompt/runner**: {mode_totals['truncation']} truncated (no-JSON at "
                         f">= {_TRUNC_TOKENS} tokens) → calculation answers overflow max_tokens; "
                         "use a compact calculation agent with a small token budget.")
    if agent_empty_evidence.get("option_elimination"):
        diagnosis.append(f"**prompt**: option_elimination emitted empty evidence "
                         f"{agent_empty_evidence['option_elimination']}/{agent_totals['option_elimination']} "
                         "times (its schema has no evidence field) → every such candidate is a "
                         "placeholder; do not use it as the primary calc candidate.")
    if mode_totals["numeric_mismatch"]:
        diagnosis.append(f"**parser/prompt**: {mode_totals['numeric_mismatch']} qids show numeric "
                         "mismatch → force the agent to map final_numeric_value to the option text.")
    if mode_totals["no_tool_candidate"] or mode_totals["conflicting_weak_candidates"]:
        diagnosis.append(f"**solver coverage**: {mode_totals['no_tool_candidate']} qids have NO "
                         f"deterministic tool candidate and {mode_totals['conflicting_weak_candidates']} "
                         "rely on conflicting weak model candidates → extend deterministic solvers / "
                         "go tool-first for calculation.")

    md = ["# Pilot Failure Analysis (read-only; no API)", "",
          f"pilot qids: **{len(rows)}**", "",
          "## Top failure modes (per-qid primary)", ""]
    for k, v in mode_totals.most_common():
        md.append(f"- {k}: **{v}**")
    md += ["", "## Empty-evidence by agent (placeholder source)", ""]
    for ag, n in agent_empty_evidence.most_common():
        md.append(f"- {ag}: {n}/{agent_totals[ag]}")
    md += ["", "## Diagnosis", ""] + (diagnosis or ["- no dominant failure mode detected."])
    md += ["", "## Per-qid", "",
           "| qid | route | v10 | cand | ok | ph | mm | trunc | tool |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['qid']} | {r['route']} | {r['v10_answer']} | {r['candidate_answers']} | "
                  f"{r['ok']} | {r['placeholder']} | {r['numeric_mismatch']} | {r['truncated']} | "
                  f"{r['tool_candidate']} |")
    (outdir / "pilot_failure_analysis.md").write_text("\n".join(md))

    print("=" * 64)
    print("PILOT FAILURE ANALYSIS (no API)")
    print("=" * 64)
    print(f"qids={len(rows)} modes={dict(mode_totals)}")
    print(f"empty_evidence_by_agent={dict(agent_empty_evidence)}")
    print(f"-> {outdir}/pilot_failure_analysis.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
