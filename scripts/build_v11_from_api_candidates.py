#!/usr/bin/env python3
"""Build v11 proposals from API candidates + the offline factory (Phase 2L.26A; no API).

Loads v10 as base, merges the offline tool/card candidate pool with the API candidate
records (and optional pairwise-judge results), ranks with ``answer_ranker.select_answer``,
and emits proposals ONLY where the selection differs from v10. Writes to scratch only;
refuses any path under outputs/. Does NOT promote to pred.csv. No qid hardcoding.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate  # noqa: E402

_FIELDS = ["qid", "v10_answer", "selected_answer", "decision", "selected_source", "risk_level",
           "ranker_score", "reason", "candidate_votes", "agreeing_agents", "disagreeing_agents",
           "proof_text", "evidence_text", "requires_manual_review", "question_preview",
           "choices_compact"]


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


def _load_api_candidates(path):
    by_qid = {}
    if path and Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("qid") and o.get("answer") and o.get("parse_status") == "ok":
                by_qid.setdefault(o["qid"], []).append(o)
    return by_qid


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build v11 from API candidates (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="outputs/pred_v10_full_production_user_run.csv")
    ap.add_argument("--api-candidates", required=True,
                    help="candidate JSONL: api_candidates.jsonl OR adaptive_api_candidates.jsonl")
    ap.add_argument("--output-dir", default="scratch/selective_multicandidate_2l26")
    ap.add_argument("--write-candidate-csv", action="store_true", default=False)
    args = ap.parse_args(argv)

    outdir = Path(args.output_dir)
    _guard_scratch(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    api = _load_api_candidates(args.api_candidates)

    proposals = []
    pred_rows = []
    for qid, sample in samples.items():
        v10 = base.get(qid)
        pool = build_candidate_pool(sample, v10, None)
        # Merge API candidates as distinct sources (api:<agent>).
        agreeing, disagreeing = [], []
        for c in api.get(qid, []):
            src = f"api:{c.get('agent')}"
            pool.add(AnswerCandidate(qid=qid, answer=c["answer"], source=src,
                                     confidence=float(c.get("confidence") or 0.5),
                                     risk_level=c.get("risk") or "medium",
                                     rationale=c.get("rationale", ""), evidence_text=c.get("evidence", "")))
            (agreeing if c["answer"] == v10 else disagreeing).append(c.get("agent"))
        pool.deduplicate()
        selected, decision = select_answer(pool, sample, v10)
        pred_rows.append({"qid": qid, "answer": selected})
        if decision["decision"] == "override" and selected != v10:
            winner = pool.best_by_source(decision["selected_source"])
            q = str(sample.get("question", "") or "").replace("\n", " ")
            proposals.append({
                "qid": qid, "v10_answer": v10, "selected_answer": selected,
                "decision": decision["decision"], "selected_source": decision["selected_source"],
                "risk_level": decision["risk_level"], "ranker_score": decision.get("score"),
                "reason": decision["reason"],
                "candidate_votes": json.dumps(pool.answer_votes(), ensure_ascii=False),
                "agreeing_agents": "|".join(filter(None, agreeing)),
                "disagreeing_agents": "|".join(filter(None, disagreeing)),
                "proof_text": (winner.proof_text if winner else "")[:200],
                "evidence_text": (winner.evidence_text if winner else "")[:200],
                "requires_manual_review": decision.get("requires_manual_review", False),
                "question_preview": q[:120],
                "choices_compact": " | ".join(str(c) for c in sample.get("choices", []) or [])[:160],
            })

    with open(outdir / "v11_api_ranked_proposals.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(proposals)
    (outdir / "v11_api_ranked_review.md").write_text(
        "# v11 API-Ranked Proposals (offline; no API; not a submission)\n\n"
        f"Base v10: `{args.base_pred}`.  Proposed overrides: **{len(proposals)}**.\n\n"
        + "\n".join(f"- {p['qid']} {p['v10_answer']}→{p['selected_answer']} "
                    f"({p['selected_source']}, {p['risk_level']}, "
                    f"review={p['requires_manual_review']}): {p['reason']}" for p in proposals))

    if args.write_candidate_csv:
        cand_csv = outdir / "pred_v11_api_ranked_candidate.csv"
        _guard_scratch(cand_csv)
        with open(cand_csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["qid", "answer"])
            w.writeheader(); w.writerows(pred_rows)

    print("=" * 64)
    print("BUILD v11 FROM API CANDIDATES (no API; scratch only)")
    print("=" * 64)
    print(f"questions: {len(samples)}   proposed overrides: {len(proposals)}")
    print(f"proposals: {outdir / 'v11_api_ranked_proposals.csv'}")
    print("NOTE: not promoted to pred.csv; outputs/ untouched.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
