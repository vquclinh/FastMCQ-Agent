#!/usr/bin/env python3
"""Offline v11 proposal generator (no API; writes to scratch only; no submission CSV).

For every question, builds a candidate pool (answer factory) and ranks it. Emits a
proposal ONLY where the ranked selection differs from the v10 base answer. Writes
candidate JSONL + proposal CSV + review Markdown under the output dir. Never writes a
submission CSV, never modifies output/. No qid hardcoding, no answer table.

Usage: see Phase 2L.25 Part K.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_log, load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402

_PROPOSAL_FIELDS = ["qid", "v10_answer", "proposed_answer", "decision", "selected_source",
                    "risk_level", "reason", "candidate_sources", "answer_votes",
                    "proof_text", "evidence_text", "question_preview", "choices_compact"]


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output must be under scratch/ (got {path})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build v11 answer-factory proposals (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="output/pred_v10_full_production_user_run.csv")
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--output-dir", default="scratch/answer_factory_2l25")
    args = ap.parse_args(argv)

    outdir = Path(args.output_dir)
    _guard_scratch(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.v10_log)

    cand_path = outdir / "answer_factory_candidates.jsonl"
    prop_path = outdir / "answer_factory_proposals.csv"
    proposals = []
    source_ct = Counter()
    with open(cand_path, "w", encoding="utf-8") as cfh:
        for s in samples:
            qid = s.get("qid")
            base_ans = base.get(qid)
            rec = log.get(qid, {})
            pool = build_candidate_pool(s, base_ans, rec)
            cfh.write(json.dumps(pool.to_dict(), ensure_ascii=False) + "\n")
            selected, decision = select_answer(pool, s, base_ans)
            if decision["decision"] == "override" and selected != base_ans:
                winner = pool.best_by_source(decision["selected_source"])
                source_ct[decision["selected_source"]] += 1
                q = str(s.get("question", "") or "").replace("\n", " ")
                proposals.append({
                    "qid": qid, "v10_answer": base_ans, "proposed_answer": selected,
                    "decision": decision["decision"], "selected_source": decision["selected_source"],
                    "risk_level": decision["risk_level"], "reason": decision["reason"],
                    "candidate_sources": "|".join(pool.sources()),
                    "answer_votes": json.dumps(pool.answer_votes(), ensure_ascii=False),
                    "proof_text": (winner.proof_text if winner else "")[:200],
                    "evidence_text": (winner.evidence_text if winner else "")[:200],
                    "question_preview": q[:120],
                    "choices_compact": " | ".join(str(c) for c in s.get("choices", []) or [])[:160],
                })

    with open(prop_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PROPOSAL_FIELDS)
        w.writeheader(); w.writerows(proposals)

    md = ["# Answer-Factory v11 Proposals (offline; no API; not a submission)", "",
          f"Base: `{args.base_pred}` (v10).  Total questions: {len(samples)}.",
          f"Proposed overrides vs v10: **{len(proposals)}**.", "",
          "## Proposed changes by selected source", ""]
    for src, n in source_ct.most_common():
        md.append(f"- `{src}`: {n}")
    md += ["", "## Proposals", ""]
    for p in proposals:
        md.append(f"- **{p['qid']}** {p['v10_answer']}→{p['proposed_answer']} "
                  f"({p['selected_source']}, {p['risk_level']}): {p['reason']}")
    md += ["", "_No submission CSV written; review before any v11 build._"]
    (outdir / "answer_factory_review.md").write_text("\n".join(md))

    print("=" * 64)
    print("ANSWER FACTORY v11 PROPOSALS (no API; scratch only)")
    print("=" * 64)
    print(f"questions: {len(samples)}   proposed overrides: {len(proposals)}")
    print(f"by source: {dict(source_ct)}")
    print(f"candidates: {cand_path}")
    print(f"proposals : {prop_path}")
    print("NOTE: no submission CSV written; output/ untouched.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
