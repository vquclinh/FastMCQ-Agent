#!/usr/bin/env python3
"""Submission ensemble merger (Phase 2L.29A — FOR HUMAN USE).

Merges several full submission candidate CSVs against the v10 base by an explicit voting
strategy (majority / at_least_two / non_v10_consensus). Overrides v10 only when the
strategy is satisfied; otherwise keeps v10. Uses NO ground truth and NO qid hardcoding.
Writes the ensemble under outputs/ and a diff + summary under scratch/. Do NOT run in a
coding phase.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import guard_output, load_pred, load_samples  # noqa: E402
from src.labels import labels_for  # noqa: E402

_PROTECTED_NAMES = {"pred.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv"}
_STRATEGIES = ("majority", "at_least_two", "non_v10_consensus")


def _require_outputs(path):
    p = str(path).replace("\\", "/")
    if "/outputs/" not in p and not p.startswith("outputs/"):
        raise SystemExit(f"REFUSING: ensemble must be written under outputs/ (got {path})")
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite a protected/locked file: {Path(path).name}")
    guard_output(path)


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: --review-dir must be under scratch/ (got {path})")


def _validate_candidate(name, pred, samples):
    if set(pred) != set(samples):
        raise SystemExit(f"REFUSING: candidate {name} qid set != dataset (row-count mismatch)")
    for qid, ans in pred.items():
        labels = labels_for(len(samples[qid].get("choices", []) or []))
        if ans not in labels:
            raise SystemExit(f"REFUSING: candidate {name} has invalid label {ans} for {qid}")


def _decide(v10, votes, strategy):
    """votes: list of candidate answers for this qid. Return chosen label."""
    non_v10 = [a for a in votes if a and a != v10]
    if not non_v10:
        return v10
    tally = Counter(non_v10)
    top, n = tally.most_common(1)[0]
    if len(tally) > 1 and sorted(tally.values())[-1] == sorted(tally.values())[-2]:
        return v10                       # tie among alternatives -> keep v10
    if strategy == "majority":
        return top if n > len(votes) / 2 else v10
    if strategy == "at_least_two":
        return top if n >= 2 else v10
    # non_v10_consensus: every non-v10 change agrees on the same label
    return top if len(tally) == 1 else v10


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Merge submission candidates into an ensemble (human-run)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="outputs/pred_v10_full_production_user_run.csv")
    ap.add_argument("--candidates", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--review-dir", required=True)
    ap.add_argument("--strategy", default="at_least_two", choices=_STRATEGIES)
    ap.add_argument("--max-total-overrides", type=int, default=60)
    ap.add_argument("--i-understand-this-writes-outputs", action="store_true", default=False)
    args = ap.parse_args(argv)

    if not args.i_understand_this_writes_outputs:
        raise SystemExit("REFUSING: pass --i-understand-this-writes-outputs to write a real ensemble.")
    _require_outputs(args.output)
    _guard_scratch(args.review_dir)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    cands = {}
    for c in args.candidates:
        if not Path(c).exists():
            raise SystemExit(f"candidate not found: {c}")
        pred = load_pred(c)
        _validate_candidate(Path(c).name, pred, samples)
        cands[Path(c).name] = pred

    pred_rows, overrides = [], []
    for qid in samples:
        v10 = base.get(qid)
        votes = [pred.get(qid) for pred in cands.values()]
        chosen = _decide(v10, votes, args.strategy)
        if chosen != v10:
            overrides.append({"qid": qid, "v10": v10, "ensemble": chosen,
                              "votes": "|".join(f"{n}={cands[n].get(qid)}" for n in cands)})
        pred_rows.append({"qid": qid, "answer": chosen})

    if len(overrides) > args.max_total_overrides:
        raise SystemExit(f"REFUSING: ensemble overrides {len(overrides)} > "
                         f"--max-total-overrides {args.max_total_overrides}")

    # Final validation.
    for r in pred_rows:
        labels = labels_for(len(samples[r["qid"]].get("choices", []) or []))
        if r["answer"] not in labels:
            raise SystemExit(f"REFUSING: invalid ensemble label {r['answer']} for {r['qid']}")
    if len(pred_rows) != len(samples):
        raise SystemExit("REFUSING: ensemble row count != dataset size")

    reviewdir = Path(args.review_dir); reviewdir.mkdir(parents=True, exist_ok=True)
    with open(reviewdir / "ensemble_diff.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "v10", "ensemble", "votes"])
        w.writeheader(); w.writerows(overrides)
    (reviewdir / "ensemble_summary.md").write_text(
        f"# Submission Ensemble — strategy={args.strategy} (NOT v10)\n\n"
        f"- candidates: {list(cands)}\n- rows: {len(pred_rows)}\n"
        f"- overrides vs v10: **{len(overrides)}**\n\n## Changes\n\n"
        + "\n".join(f"- {o['qid']} {o['v10']}→{o['ensemble']} ({o['votes']})" for o in overrides[:60]))

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader(); w.writerows(pred_rows)

    print("=" * 64)
    print(f"SUBMISSION ENSEMBLE ({args.strategy}) — human-run")
    print("=" * 64)
    print(f"candidates={len(cands)} rows={len(pred_rows)} overrides={len(overrides)}")
    print(f"ensemble -> {outp}")
    print(f"review   -> {reviewdir}/ensemble_summary.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
