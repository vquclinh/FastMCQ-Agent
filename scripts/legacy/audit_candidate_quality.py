#!/usr/bin/env python3
"""Audit candidate quality from any candidate JSONL (read-only; no API).

Reports total/unique-qid/agent/judge counts, parse-failure & placeholder-evidence &
answer/evidence-mismatch rates, consistency-rejected count, candidates eligible for the
ranker, and an estimated useful-proposal count. Works for both api_candidates.jsonl and
adaptive_api_candidates.jsonl. Writes CSV + MD under scratch/ only.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import load_samples  # noqa: E402
from src.candidate_answer import AnswerCandidate  # noqa: E402
from src.candidate_consistency import detect_placeholder_evidence, is_candidate_consistent  # noqa: E402


def _guard_scratch(p):
    if "scratch/" not in str(p).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {p})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit candidate quality (no API)")
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-dir", default="scratch/adaptive_selective_2l27b")
    args = ap.parse_args(argv)
    outdir = Path(args.output_dir); _guard_scratch(outdir); outdir.mkdir(parents=True, exist_ok=True)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    rows = [json.loads(l) for l in Path(args.candidates).read_text().splitlines() if l.strip()] \
        if Path(args.candidates).exists() else []

    agent_ct = Counter(r.get("agent") for r in rows)
    judge_ct = agent_ct.get("pairwise_judge", 0)
    parse_fail = sum(1 for r in rows if r.get("parse_status") not in ("ok", None))
    placeholder = sum(1 for r in rows if detect_placeholder_evidence(r.get("evidence", "")))
    eligible = consistency_reject = mismatch = 0
    detail = []
    for r in rows:
        s = samples.get(r.get("qid"))
        if not s or not r.get("answer"):
            continue
        cand = AnswerCandidate(r.get("qid"), r.get("answer"), f"api:{r.get('agent')}",
                               evidence_text=r.get("evidence", ""), rationale=r.get("rationale", ""))
        ok = (r.get("parse_status") in ("ok", None)) and is_candidate_consistent(cand, s)
        if r.get("parse_status") == "numeric_mismatch":
            mismatch += 1
        if ok:
            eligible += 1
        else:
            consistency_reject += 1
            detail.append({"qid": r.get("qid"), "agent": r.get("agent"), "answer": r.get("answer"),
                           "parse_status": r.get("parse_status"), "reason": "rejected"})

    # Useful proposals ~ qids with >=2 eligible non-v10 candidates agreeing.
    by_qid = {}
    for r in rows:
        s = samples.get(r.get("qid"))
        if not s or not r.get("answer") or r.get("agent") == "pairwise_judge":
            continue
        cand = AnswerCandidate(r.get("qid"), r.get("answer"), f"api:{r.get('agent')}",
                               evidence_text=r.get("evidence", ""), rationale=r.get("rationale", ""))
        if (r.get("parse_status") in ("ok", None)) and is_candidate_consistent(cand, s) \
                and not r.get("agrees_with_v10"):
            by_qid.setdefault(r["qid"], Counter())[r["answer"]] += 1
    useful = sum(1 for qid, c in by_qid.items() if max(c.values()) >= 2)

    with open(outdir / "candidate_quality_audit.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "agent", "answer", "parse_status", "reason"])
        w.writeheader(); w.writerows(detail)
    md = ["# Candidate Quality Audit", "",
          f"total candidates: {len(rows)}", f"unique qids: {len({r.get('qid') for r in rows})}",
          f"agent counts: {dict(agent_ct)}", f"judge count: {judge_ct}",
          f"parse failures: {parse_fail}", f"placeholder evidence: {placeholder}",
          f"answer/evidence mismatches: {mismatch}",
          f"consistency rejected: {consistency_reject}",
          f"eligible for ranker: {eligible}", f"estimated useful proposals: {useful}", "",
          "_Read-only; no API._"]
    (outdir / "candidate_quality_audit.md").write_text("\n".join(md))
    print("=" * 60)
    print("CANDIDATE QUALITY AUDIT (no API)")
    print("=" * 60)
    print(f"total={len(rows)} agents={dict(agent_ct)} judge={judge_ct}")
    print(f"parse_fail={parse_fail} placeholder={placeholder} mismatch={mismatch} "
          f"rejected={consistency_reject} eligible={eligible} useful={useful}")
    print(f"-> {outdir}/candidate_quality_audit.md")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
