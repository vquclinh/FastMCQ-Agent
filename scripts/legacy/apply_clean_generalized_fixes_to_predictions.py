#!/usr/bin/env python3
"""Apply ONLY generalized safe deterministic rules to v7 predictions (no API).

Starts from v7 and applies generalized concept rules (`src/concept_solver.py`) and
the deterministic calculation candidate (`src/programmatic_solver.py`), overriding an
answer ONLY when a rule matches safely and uniquely and changes the answer. No qid
lists, no external sheet, no OpenRouter.

Safety: if the number of changes exceeds ``--max-expected-changes`` (default 2), the
script STOPS — it writes the diff for review but does NOT write the v8 prediction —
so an over-broad rule can never be silently accepted.

Usage: see Phase 2L.17 Part B.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import guard_output, load_log, load_pred, load_samples  # noqa: E402
from src.concept_solver import solve_concept_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.programmatic_solver import candidate_for  # noqa: E402

_DIFF_FIELDS = ["qid", "old_answer", "new_answer", "rule_id", "reason",
                "safe_to_override", "matched_option_text"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply generalized safe rules v7 -> v8 (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--log-path", required=True)
    ap.add_argument("--diff", required=True)
    ap.add_argument("--max-expected-changes", type=int, default=2)
    args = ap.parse_args(argv)

    for p in (args.output, args.log_path, args.diff):
        guard_output(p)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    _ = load_log(args.base_log)  # reserved for future signals; not required

    pred_rows, log_rows, diff_rows = [], [], []
    changed = 0
    for s in samples:
        qid = s.get("qid")
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        current = base.get(qid, "")
        new_ans = current
        rule_id = None
        reason = "kept base (v7)"
        matched_text = ""

        # 1) Generalized concept rules (qualitative).
        cr = solve_concept_sample(s, labels)
        if cr.matched and cr.safe_to_override and cr.answer in labels and cr.answer != current:
            new_ans, rule_id, reason, matched_text = cr.answer, cr.rule_id, cr.reason, cr.matched_option_text
        else:
            # 2) Deterministic calculation candidate (already baked into v7; expect no-op).
            try:
                cand = candidate_for(s, existing_answer=current)
            except Exception:
                cand = None
            if cand and cand.would_change_answer and cand.answer in labels:
                new_ans, rule_id, reason = cand.answer, cand.method, cand.note

        applied = new_ans != current
        if applied:
            changed += 1
            diff_rows.append({"qid": qid, "old_answer": current, "new_answer": new_ans,
                              "rule_id": rule_id, "reason": reason,
                              "safe_to_override": True, "matched_option_text": matched_text})
        pred_rows.append({"qid": qid, "answer": new_ans})
        log_rows.append({"qid": qid, "base_answer": current, "final_answer": new_ans,
                         "changed": applied, "rule_id": rule_id, "reason": reason,
                         "matched_option_text": matched_text,
                         "solver": "clean_generalized_from_v7"})

    Path(args.diff).parent.mkdir(parents=True, exist_ok=True)
    with open(args.diff, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_DIFF_FIELDS)
        w.writeheader(); w.writerows(diff_rows)

    print("=" * 70)
    print("CLEAN GENERALIZED FIXES (v7 -> v8; deterministic/concept only; no API)")
    print("=" * 70)
    print(f"samples         : {len(pred_rows)}")
    print(f"answers changed : {changed}")
    for d in diff_rows:
        print(f"  {d['qid']}  {d['rule_id']:26s} {d['old_answer']} -> {d['new_answer']}  | {d['reason']}")

    if changed > args.max_expected_changes:
        print("-" * 70)
        print(f"STOP: {changed} changes exceed --max-expected-changes "
              f"({args.max_expected_changes}). NOT writing the v8 prediction; diff written "
              f"for review at {args.diff}. Tighten the rule(s) before accepting.")
        print("=" * 70)
        return 2

    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"])
        w.writeheader(); w.writerows(pred_rows)
    with open(args.log_path, "w", encoding="utf-8") as fh:
        for r in log_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps({"_summary": True, "base_pred": args.base_pred,
                             "num_samples": len(pred_rows), "changed_vs_base": changed,
                             "source": "generalized_concept+calc_rules"}, ensure_ascii=False) + "\n")
    print(f"prediction CSV  : {args.output}")
    print(f"log JSONL       : {args.log_path}")
    print(f"diff CSV        : {args.diff}")
    print("NOTE: only generalized safe rules applied; no qid lists; no ground truth.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
