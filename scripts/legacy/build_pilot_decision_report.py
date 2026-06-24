#!/usr/bin/env python3
"""Pilot final-decision report (Phase 2L.28A; no API, no submission).

For each pilot qid, builds the candidate pool (v10 base + offline tool candidates + API
candidates + any judge candidate), runs the consistency-guarded ranker, and records the
final adaptive decision. Produces a human decision report with a proceed/revise/stop
recommendation. NEVER writes a submission CSV and NEVER writes under output/.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate  # noqa: E402
from src.candidate_consistency import detect_placeholder_evidence, is_candidate_consistent  # noqa: E402

_FIELDS = ["qid", "route", "v10_answer", "adaptive_answer", "decision", "selected_source",
           "risk_level", "candidate_votes", "evidence_summary", "proof_summary",
           "consistency_rejections", "requires_manual_review", "question_preview",
           "choices_compact"]


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


def _load_jsonl(path):
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
            if o.get("qid"):
                by_qid.setdefault(o["qid"], []).append(o)
    return by_qid


def _classify(decision_rec, selected, v10, had_conflict):
    d = decision_rec.get("decision")
    if d == "override" and selected != v10:
        return "manual_review" if decision_rec.get("requires_manual_review") else "override_candidate"
    # kept v10: distinguish a clean keep from an active rejection of conflicting candidates
    return "reject" if had_conflict else "keep_v10"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build pilot decision report (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="output/pred_v10_full_production_user_run.csv")
    ap.add_argument("--pilot-qids", required=True)
    ap.add_argument("--pilot-candidates", required=True)
    ap.add_argument("--output-dir", default="scratch/adaptive_pilot_2l28")
    args = ap.parse_args(argv)
    _guard_scratch(args.output_dir)
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    pilot = list(csv.DictReader(open(args.pilot_qids)))
    api = _load_jsonl(args.pilot_candidates)

    rows = []
    tallies = Counter()
    placeholder_ct = mismatch_ct = judge_ct = 0
    for pr in pilot:
        qid = pr.get("qid")
        sample = samples.get(qid)
        if not sample:
            continue
        v10 = base.get(qid)
        pool = build_candidate_pool(sample, v10, None)
        had_conflict = consistency_rej = 0
        for c in api.get(qid, []):
            if c.get("agent") == "pairwise_judge":
                judge_ct += 1
            if c.get("parse_status") == "placeholder_evidence" or detect_placeholder_evidence(c.get("evidence", "")):
                placeholder_ct += 1
            if c.get("parse_status") == "numeric_mismatch":
                mismatch_ct += 1
            ans = c.get("answer")
            if not ans:
                continue
            src = f"api:{c.get('agent')}"
            cand = AnswerCandidate(qid=qid, answer=ans, source=src,
                                   confidence=float(c.get("confidence") or 0.5),
                                   risk_level=c.get("risk") or "medium",
                                   rationale=c.get("rationale", ""), evidence_text=c.get("evidence", ""))
            if ans != v10:
                had_conflict += 1
            if c.get("parse_status") not in ("ok", None) or not is_candidate_consistent(cand, sample):
                consistency_rej += 1
            pool.add(cand)
        pool.deduplicate()
        selected, rec = select_answer(pool, sample, v10)
        decision = _classify(rec, selected, v10, had_conflict)
        tallies[decision] += 1
        winner = pool.best_by_source(rec.get("selected_source")) if rec.get("selected_source") else None
        q = str(sample.get("question", "") or "").replace("\n", " ")
        rows.append({
            "qid": qid, "route": pr.get("route"), "v10_answer": v10, "adaptive_answer": selected,
            "decision": decision, "selected_source": rec.get("selected_source"),
            "risk_level": rec.get("risk_level"),
            "candidate_votes": json.dumps(pool.answer_votes(), ensure_ascii=False),
            "evidence_summary": (winner.evidence_text if winner else "")[:160],
            "proof_summary": (winner.proof_text if winner else "")[:160],
            "consistency_rejections": consistency_rej,
            "requires_manual_review": rec.get("requires_manual_review", False),
            "question_preview": q[:120],
            "choices_compact": " | ".join(str(c) for c in sample.get("choices", []) or [])[:160],
        })

    total = len(rows)
    overrides = tallies["override_candidate"] + tallies["manual_review"]
    placeholder_rate = (placeholder_ct / max(1, sum(len(v) for v in api.values())))
    # model-only override = an override whose winning source is API/consensus with NO proof/evidence
    model_only = sum(1 for r in rows if r["decision"] in ("override_candidate", "manual_review")
                     and not (r["evidence_summary"] or r["proof_summary"]))
    conflicts_present = any(r["decision"] in ("override_candidate", "manual_review", "reject") for r in rows)

    if total == 0:
        rec_label = "revise_prompts_or_ranker"
        rec_reason = "no pilot decisions produced (no candidates?)"
    elif placeholder_rate <= 0.25 and model_only == 0 and \
            (overrides == 0 or all((r["evidence_summary"] or r["proof_summary"])
                                   for r in rows if r["decision"] in ("override_candidate", "manual_review"))) and \
            (judge_ct > 0 or not conflicts_present):
        rec_label = "proceed_full_run"
        rec_reason = "low placeholder rate, evidence-backed overrides, judge present on conflicts"
    elif overrides == 0 and tallies["reject"] == total:
        rec_label = "stop_keep_v10"
        rec_reason = "system rejected every proposal; nothing beats v10 in the pilot"
    else:
        rec_label = "revise_prompts_or_ranker"
        rec_reason = (f"placeholder_rate={placeholder_rate:.2f}, model_only_overrides={model_only}, "
                      f"judge={judge_ct}, conflicts={conflicts_present}")

    with open(outdir / "pilot_decisions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(rows)

    md = ["# Pilot Decision Report (offline; no API; NOT a submission)", "",
          f"- total pilot qids: **{total}**",
          f"- kept v10: **{tallies['keep_v10']}**",
          f"- proposed overrides: **{overrides}** "
          f"(override_candidate {tallies['override_candidate']}, manual_review {tallies['manual_review']})",
          f"- manual-review: **{tallies['manual_review']}**",
          f"- rejected/invalid: **{tallies['reject']}**",
          f"- judge candidates: **{judge_ct}**",
          f"- placeholder rejections: **{placeholder_ct}**   mismatch rejections: **{mismatch_ct}**",
          f"- model-only overrides (no evidence/proof): **{model_only}**", "",
          f"## Recommendation: **{rec_label}**", "", rec_reason, "",
          "## All pilot qids", "",
          "| qid | route | v10 | adaptive | decision | source | risk | review |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['qid']} | {r['route']} | {r['v10_answer']} | {r['adaptive_answer']} | "
                  f"{r['decision']} | {r['selected_source']} | {r['risk_level']} | "
                  f"{r['requires_manual_review']} |")
    md += ["", "_No submission file produced. v10 remains the submission until a full reviewed run._"]
    (outdir / "pilot_decisions.md").write_text("\n".join(md))

    print("=" * 64)
    print("PILOT DECISION REPORT (no API; scratch only)")
    print("=" * 64)
    print(f"total={total} keep_v10={tallies['keep_v10']} overrides={overrides} "
          f"manual_review={tallies['manual_review']} reject={tallies['reject']} judge={judge_ct}")
    print(f"placeholder={placeholder_ct} mismatch={mismatch_ct} model_only_overrides={model_only}")
    print(f"RECOMMENDATION: {rec_label} — {rec_reason}")
    print(f"-> {outdir}/pilot_decisions.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
