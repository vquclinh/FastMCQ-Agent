#!/usr/bin/env python3
"""Audit the selective runner's API candidate behavior (read-only; no API).

Inspects an api_candidates.jsonl: agent counts, whether the pairwise judge ran,
parse-failure rate, placeholder-evidence count, answer/evidence mismatch count, and
candidates rejected by the consistency guard. Writes a CSV + MD under scratch/.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.layers.adaptive_proposal_common import load_samples  # noqa: E402
from src.selector.candidate_answer import AnswerCandidate  # noqa: E402
from src.selector.candidate_consistency import (detect_placeholder_evidence,  # noqa: E402
                                       validate_candidate_consistency)


def _guard_scratch(p):
    if "scratch/" not in str(p).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {p})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit selective runner behavior (no API)")
    ap.add_argument("--api-candidates", required=True)
    ap.add_argument("--input", default=None, help="dataset (for consistency checks)")
    ap.add_argument("--output-dir", default="scratch/accuracy_engine_2l27")
    args = ap.parse_args(argv)
    outdir = Path(args.output_dir)
    _guard_scratch(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    samples = {s.get("qid"): s for s in load_samples(args.input)} if args.input else {}
    rows = [json.loads(l) for l in Path(args.api_candidates).read_text().splitlines() if l.strip()] \
        if Path(args.api_candidates).exists() else []

    agent_ct = Counter(r.get("agent") for r in rows)
    parse_fail = sum(1 for r in rows if r.get("parse_status") != "ok")
    placeholder = sum(1 for r in rows if detect_placeholder_evidence(r.get("evidence", "")))
    judge_ran = any(r.get("agent") == "pairwise_judge" for r in rows)
    mismatch = rejected = 0
    detail = []
    for r in rows:
        s = samples.get(r.get("qid"))
        if not s:
            continue
        cand = AnswerCandidate(r.get("qid"), r.get("answer"), f"api:{r.get('agent')}",
                               evidence_text=r.get("evidence", ""), rationale=r.get("rationale", ""))
        rec = validate_candidate_consistency(cand, s)
        if not rec.ok:
            rejected += 1
            if rec.severity == "numeric_mismatch":
                mismatch += 1
            detail.append({"qid": r.get("qid"), "agent": r.get("agent"), "answer": r.get("answer"),
                           "severity": rec.severity, "reason": rec.reason})

    with open(outdir / "selective_runner_behavior.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "agent", "answer", "severity", "reason"])
        w.writeheader(); w.writerows(detail)
    md = ["# Selective Runner Behavior Audit", "",
          f"total candidate records: {len(rows)}",
          f"agent counts: {dict(agent_ct)}",
          f"pairwise_judge ran: {judge_ran}",
          f"parse failures: {parse_fail}",
          f"placeholder evidence: {placeholder}",
          f"answer/evidence mismatches: {mismatch}",
          f"rejected by consistency guard: {rejected}", "",
          "_Read-only; no API; helps decide whether to fix runner/judge before scaling._"]
    (outdir / "selective_runner_behavior.md").write_text("\n".join(md))
    print("=" * 60)
    print("SELECTIVE RUNNER BEHAVIOR (no API)")
    print("=" * 60)
    print(f"records={len(rows)} agents={dict(agent_ct)} judge_ran={judge_ran}")
    print(f"parse_fail={parse_fail} placeholder={placeholder} mismatch={mismatch} rejected={rejected}")
    print(f"-> {outdir}/selective_runner_behavior.md")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
