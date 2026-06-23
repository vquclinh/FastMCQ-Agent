#!/usr/bin/env python3
"""Build an overall accuracy improvement plan (Phase 2L.27A; offline, no API).

Per qid: route, v10 answer, whether a deterministic tool candidate exists, evidence
pack status, consistency issues among existing API candidates, recommended next layer,
estimated API calls, priority score, reason. Writes CSV + MD under scratch/ only.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_accuracy_planner import (recommend_layers_for_question,
                                           score_question_difficulty)
from src.adaptive_proposal_common import load_log, load_pred, load_samples
from src.answer_factory import build_candidate_pool
from src.candidate_consistency import is_candidate_consistent
from src.candidate_answer import AnswerCandidate
from src.evidence_pack import build_evidence_pack
from src.production_policy import branch_of

_FIELDS = ["qid", "route", "v10_answer", "has_tool_candidate", "tool_answer",
           "evidence_pack_status", "consistency_issues", "recommended_layer",
           "est_api_calls", "priority_score", "reason"]
_LAYER_CALLS = {"tool_only": 0, "evidence_pack": 0, "cheap_api": 2, "rich_api": 5, "manual_review": 0}


def _guard_scratch(p):
    if "scratch/" not in str(p).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {p})")


def _api_by_qid(path):
    out = {}
    if path and Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("qid"):
                    out.setdefault(o["qid"], []).append(o)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build overall accuracy plan (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--api-candidates", default=None)
    ap.add_argument("--output-dir", default="scratch/accuracy_engine_2l27")
    args = ap.parse_args(argv)
    outdir = Path(args.output_dir)
    _guard_scratch(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.v10_log)
    api = _api_by_qid(args.api_candidates)

    rows = []
    layer_ct = Counter()
    for s in samples:
        qid = s.get("qid")
        rec = log.get(qid, {})
        route = rec.get("route") or branch_of(s)
        pool = build_candidate_pool(s, base.get(qid), rec)
        tool = next((c for c in pool.candidates if c.source.startswith(("tool:", "formula_bank", "concept"))), None)
        ep = build_evidence_pack(s, route)
        # consistency issues among any existing API candidates
        issues = 0
        for c in api.get(qid, []):
            cand = AnswerCandidate(qid, c.get("answer"), f"api:{c.get('agent')}",
                                   evidence_text=c.get("evidence", ""), rationale=c.get("rationale", ""))
            if c.get("answer") and not is_candidate_consistent(cand, s):
                issues += 1
        layer = recommend_layers_for_question(s, rec)
        layer_ct[layer] += 1
        diff = score_question_difficulty(s, rec)
        rows.append({"qid": qid, "route": route, "v10_answer": base.get(qid),
                     "has_tool_candidate": tool is not None,
                     "tool_answer": tool.answer if tool else None,
                     "evidence_pack_status": ep.matched, "consistency_issues": issues,
                     "recommended_layer": layer, "est_api_calls": _LAYER_CALLS.get(layer, 0),
                     "priority_score": diff,
                     "reason": ("deterministic tool" if tool else f"{route}/{layer}")})

    with open(outdir / "overall_accuracy_plan.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(rows)
    total_calls = sum(r["est_api_calls"] for r in rows)
    md = ["# Overall Accuracy Plan", "",
          f"questions: {len(rows)}", f"recommended-layer distribution: {dict(layer_ct)}",
          f"questions with a deterministic tool candidate: {sum(1 for r in rows if r['has_tool_candidate'])}",
          f"total estimated API calls (all layers): {total_calls}", "",
          "_Offline plan only; no API; no submission written._"]
    (outdir / "overall_accuracy_summary.md").write_text("\n".join(md))
    print("=" * 60)
    print("OVERALL ACCURACY PLAN (no API)")
    print("=" * 60)
    print(f"questions: {len(rows)}  layers: {dict(layer_ct)}")
    print(f"tool candidates: {sum(1 for r in rows if r['has_tool_candidate'])}  est calls: {total_calls}")
    print(f"-> {outdir}/overall_accuracy_plan.csv")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
