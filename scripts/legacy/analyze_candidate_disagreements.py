#!/usr/bin/env python3
"""Candidate disagreement review lab (read-only; no API; no ground truth).

Compares a baseline prediction against one or more candidate predictions and, for
each disagreement, records route/branch, the answers, a change-type + risk-level
classification, and whether the change is backed by a SAFE deterministic
formula/concept rule (via ``formula_bank_solver``). It decides NO correctness — it is
a human-review tool. No qid hardcoding, no external sheet, no network.

Usage: see Phase 2L.23 Part F.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import load_log, load_pred, load_samples  # noqa: E402
from src.formula_bank_solver import solve_formula_bank_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.production_policy import branch_of  # noqa: E402

_FIELDS = ["qid", "question_preview", "choices", "branch", "baseline_answer",
           "candidate_answer", "candidate_source", "rule_id", "change_type",
           "risk_level", "reason", "matches_safe_deterministic_rule"]


def _is_formula_bank_source(name: str) -> bool:
    n = name.lower()
    return "formula_bank" in n or "_v9" in n


def _is_production_source(name: str) -> bool:
    return "production" in name.lower()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Candidate disagreement review (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--baseline", default="output/pred.csv")
    ap.add_argument("--candidate", action="append", default=[], help="candidate CSV (repeatable)")
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--v8-log", default=None)
    ap.add_argument("--v9-log", default=None)
    ap.add_argument("--production-log", default=None)
    ap.add_argument("--output", default="output/candidate_disagreement_review.csv")
    args = ap.parse_args(argv)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    baseline = load_pred(args.baseline)
    # Map candidate file -> its log (for rule_id), by filename heuristic.
    logs_by_source = {}
    for name, path in (("v9", args.v9_log), ("production", args.production_log),
                       ("v8", args.v8_log), ("base", args.base_log)):
        if path and Path(path).exists():
            logs_by_source[name] = load_log(path)

    rows = []
    summary = {}
    for cand_path in args.candidate:
        cand = load_pred(cand_path)
        src_name = Path(cand_path).name
        is_fb = _is_formula_bank_source(src_name)
        is_prod = _is_production_source(src_name)
        log = (logs_by_source.get("v9") if is_fb else
               logs_by_source.get("production") if is_prod else {})
        n_changes = 0
        for qid, c_ans in cand.items():
            b_ans = baseline.get(qid)
            if b_ans is None or c_ans == b_ans:
                continue
            n_changes += 1
            sample = samples.get(qid, {})
            choices = sample.get("choices", []) or []
            labels = labels_for(len(choices))
            det = solve_formula_bank_sample(sample) if sample else None
            det_ans = det.selected_answer if det else None
            matches_safe = bool(det_ans is not None and det_ans == c_ans)
            contradicts_safe = bool(det_ans is not None and det_ans == b_ans and c_ans != b_ans)
            rule_id = (log.get(qid, {}).get("rule_id") if log else None) or (det.rule_id if det else None)

            if is_fb:
                change_type = "deterministic_rule"
            elif matches_safe:
                change_type = "production_safe_override"
            elif is_prod:
                change_type = "production_model_drift"
            else:
                change_type = "unknown"

            if change_type == "deterministic_rule" or matches_safe:
                risk = "low"
            elif contradicts_safe:
                risk = "high"
            else:
                risk = "medium"

            reason = ("backed by safe deterministic rule" if matches_safe
                      else "contradicts a safe deterministic rule" if contradicts_safe
                      else "LLM rerun drift; no deterministic support" if is_prod
                      else "unclassified change")
            q = str(sample.get("question", "") or "").replace("\n", " ")
            rows.append({
                "qid": qid, "question_preview": q[:120],
                "choices": " | ".join(f"{labels[i]}.{c}" for i, c in enumerate(choices))[:160],
                "branch": branch_of(sample) if sample else "unknown",
                "baseline_answer": b_ans, "candidate_answer": c_ans,
                "candidate_source": src_name, "rule_id": rule_id,
                "change_type": change_type, "risk_level": risk, "reason": reason,
                "matches_safe_deterministic_rule": matches_safe,
            })
        summary[src_name] = n_changes

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(rows)

    from collections import Counter
    print("=" * 70)
    print("CANDIDATE DISAGREEMENT REVIEW (read-only; no ground truth)")
    print("=" * 70)
    print(f"baseline: {args.baseline}")
    for src, n in summary.items():
        print(f"  candidate {src}: {n} disagreement(s)")
    print(f"change_type distribution: {dict(Counter(r['change_type'] for r in rows))}")
    print(f"risk_level distribution : {dict(Counter(r['risk_level'] for r in rows))}")
    print(f"backed by safe rule     : {sum(1 for r in rows if r['matches_safe_deterministic_rule'])}")
    print(f"review CSV: {args.output}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
