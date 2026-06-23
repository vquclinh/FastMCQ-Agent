#!/usr/bin/env python3
"""Phase 2L.34B — V12B permutation consensus selector.

Starts from the frozen v11 winner and overrides a qid ONLY when the mapped-back answer is
stable across option permutations (i.e. position-bias resistant). Output is a SHADOW candidate
(``outputs/pred_v12b_permutation_candidate.csv``); it never overwrites the frozen best, v10,
v8, or pred.csv.

Conservative override:
  * >= 5 valid permutation records for the qid;
  * >= 4 of them map to the SAME non-current original label;
  * the current v11 label receives at most 1 mapped vote;
  * no label/option mismatch among supporting votes; no parse failure among them.
Balanced override:
  * 3/5 (or 4/6) stable mapped votes accepted if mean supporting confidence is strong (>=0.6).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.data_io import load_dataset, read_predictions, write_predictions  # noqa: E402
from src.labels import is_valid_label  # noqa: E402
from src.mcq_permutation_debiaser import (  # noqa: E402
    summarize_permutation_votes, select_permutation_override)

_PROTECTED_NAMES = {"pred_v11_independent_rerun1.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv", "pred.csv"}


def _guard_output(path):
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite protected file: {Path(path).name}")


def decide_override(qid, current, records, *, policy):
    """Thin wrapper around the core module: summarize votes then decide. Returns
    (new_label_or_None, decision_dict) preserving the prior script return shape."""
    summary = summarize_permutation_votes(qid, current, records)
    dec = select_permutation_override(summary, policy=policy)
    verdict = "accept" if dec.accept else ("reject" if summary.top_non_current_label else "keep")
    out = {"qid": qid, "current": current, "policy": policy,
           "valid_records": summary.valid_records, "votes": summary.vote_counts,
           "verdict": verdict, "proposed": summary.top_non_current_label,
           "best_votes": summary.top_non_current_votes, "current_votes": summary.current_votes,
           "mean_conf": round(summary.mean_support_confidence, 3)
           if summary.mean_support_confidence is not None else None,
           "reason": dec.reason}
    return (dec.proposed_answer if dec.accept else None), out


def _load_records(path):
    out = defaultdict(list)
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                qid = rec.get("original_qid") or rec.get("qid")
                if qid:
                    out[qid].append(rec)
    return out


def _validate(rows, samples):
    by_qid = {s["qid"]: s for s in samples}
    if not rows:
        raise SystemExit("REFUSING: empty output")
    if set(rows[0].keys()) < {"qid", "answer"}:
        raise SystemExit("REFUSING: missing qid/answer columns")
    pred_qids = [r["qid"] for r in rows]
    if len(set(pred_qids)) != len(pred_qids):
        raise SystemExit("REFUSING: duplicate qids")
    if set(pred_qids) != set(by_qid):
        raise SystemExit("REFUSING: qid set mismatch")
    for r in rows:
        if not r.get("answer") or not is_valid_label(r["answer"], by_qid[r["qid"]]):
            raise SystemExit(f"REFUSING: invalid label {r.get('answer')!r} for {r['qid']}")
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V12B permutation consensus selector")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--permutation-records", required=True)
    ap.add_argument("--output", default="outputs/pred_v12b_permutation_candidate.csv")
    ap.add_argument("--review-dir", default="scratch/v12b_option_permutation/review")
    ap.add_argument("--policy", choices=["conservative", "balanced"], default="conservative")
    ap.add_argument("--max-overrides", type=int, default=None)
    args = ap.parse_args(argv)

    _guard_output(args.output)
    samples = load_dataset(args.input)
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    records = _load_records(args.permutation_records)

    review = Path(args.review_dir); review.mkdir(parents=True, exist_ok=True)
    accepted, rejected = [], []
    new_answers = dict(current)
    for s in samples:
        qid = s["qid"]
        new_label, dec = decide_override(qid, current.get(qid, ""), records.get(qid, []),
                                         policy=args.policy)
        if dec["verdict"] == "accept":
            accepted.append(dec)
        elif dec["verdict"] == "reject":
            rejected.append(dec)

    accepted.sort(key=lambda d: (-d["best_votes"], d["qid"]))
    applied = accepted if args.max_overrides is None else accepted[:args.max_overrides]
    for d in applied:
        new_answers[d["qid"]] = d["proposed"]

    rows = [{"qid": s["qid"], "answer": new_answers[s["qid"]]} for s in samples]
    n = _validate(rows, samples)
    write_predictions(rows, args.output)

    diff = [{"qid": q, "v11_answer": current[q], "v12b_answer": new_answers[q],
             "votes": next((str(d.get("best_votes")) for d in applied if d["qid"] == q), "")}
            for q in current if current[q] != new_answers[q]]
    with (review / "permutation_delta_diff.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "v11_answer", "v12b_answer", "votes"])
        w.writeheader(); w.writerows(diff)
    with (review / "rejected_permutation_overrides.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "current", "proposed", "best_votes",
                                          "current_votes", "valid_records", "reason"])
        w.writeheader()
        for d in rejected:
            w.writerow({k: d.get(k, "") for k in
                        ("qid", "current", "proposed", "best_votes", "current_votes",
                         "valid_records", "reason")})

    summary = {"policy": args.policy, "total_qids": len(samples),
               "overrides_accepted": len(accepted), "overrides_applied": len(applied),
               "overrides_rejected": len(rejected), "changed_vs_v11": len(diff),
               "validation": "PASS", "rows": n, "output": args.output}
    (review / "permutation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (review / "permutation_summary.md").write_text(
        "# V12B Permutation Candidate Summary\n\n"
        + "\n".join(f"- **{k}**: {v}" for k, v in summary.items())
        + f"\n\n- changed qids: {', '.join(d['qid'] for d in diff) or '(none)'}\n",
        encoding="utf-8")

    print("=" * 60)
    print("V12B PERMUTATION CANDIDATE")
    for k, v in summary.items():
        print(f"{k:20}: {v}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
