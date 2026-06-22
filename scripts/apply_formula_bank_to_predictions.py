#!/usr/bin/env python3
"""Apply the generalized formula/concept bank to v8_clean predictions (no API).

Starts from a base prediction and overrides an answer ONLY when a formula-bank rule
matches safely and uniquely and changes the answer. No qid lists, no external sheet,
no OpenRouter. Refuses to write protected files. If changes exceed
``--max-expected-changes`` it writes the diff for review and exits non-zero unless
``--allow-more-changes`` is set.

Usage: see Phase 2L.19 Part C.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import guard_output, load_pred, load_samples  # noqa: E402
from src.formula_bank_solver import solve_formula_bank_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402

_DIFF_FIELDS = ["qid", "old_answer", "new_answer", "rule_id", "confidence", "reason",
                "matched_option_text"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply formula bank v8_clean -> v9 (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--log-path", required=True)
    ap.add_argument("--diff", required=True)
    ap.add_argument("--max-expected-changes", type=int, default=10)
    ap.add_argument("--allow-more-changes", action="store_true", default=False)
    args = ap.parse_args(argv)
    run_start = time.perf_counter()

    for p in (args.output, args.log_path, args.diff):
        guard_output(p)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)

    pred_rows, log_rows, diff_rows = [], [], []
    by_rule = Counter()
    changed = 0
    for s in samples:
        qid = s.get("qid")
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        current = base.get(qid, "")
        new_ans, rule_id, reason, conf, matched_text = current, None, "kept base (v8_clean)", None, ""

        res = solve_formula_bank_sample(s)
        if res and res.safe_to_override and res.selected_answer in labels \
                and res.selected_answer != current:
            new_ans = res.selected_answer
            rule_id, reason, conf, matched_text = (res.rule_id, res.reason, res.confidence,
                                                   res.matched_option_text)

        applied = new_ans != current
        if applied:
            changed += 1
            by_rule[rule_id] += 1
            diff_rows.append({"qid": qid, "old_answer": current, "new_answer": new_ans,
                              "rule_id": rule_id, "confidence": conf, "reason": reason,
                              "matched_option_text": matched_text})
        pred_rows.append({"qid": qid, "answer": new_ans})
        log_rows.append({"qid": qid, "base_answer": current, "final_answer": new_ans,
                         "changed": applied, "rule_id": rule_id, "reason": reason,
                         "solver": "formula_bank_from_v8_clean"})

    Path(args.diff).parent.mkdir(parents=True, exist_ok=True)
    with open(args.diff, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_DIFF_FIELDS)
        w.writeheader(); w.writerows(diff_rows)

    elapsed = time.perf_counter() - run_start
    n = len(pred_rows)
    sps = round(n / elapsed, 2) if elapsed > 0 else 0.0
    avg = round(elapsed / n, 6) if n > 0 else 0.0

    print("=" * 72)
    print("FORMULA BANK (v8_clean -> v9; deterministic/concept only; no API)")
    print("=" * 72)
    print(f"samples         : {n}")
    print(f"answers changed : {changed}")
    print(f"changes by rule : {dict(by_rule)}")
    print(f"elapsed_seconds        : {round(elapsed, 3)}")
    print(f"samples_per_second     : {sps}")
    print(f"avg_seconds_per_sample : {avg}")
    for d in diff_rows:
        print(f"  {d['qid']}  {str(d['rule_id']):32s} {d['old_answer']} -> {d['new_answer']}  | {d['reason']}")

    if changed > args.max_expected_changes and not args.allow_more_changes:
        print("-" * 72)
        print(f"STOP: {changed} changes exceed --max-expected-changes "
              f"({args.max_expected_changes}). Diff written to {args.diff} for review; "
              f"NOT writing the v9 prediction. Re-run with --allow-more-changes to accept.")
        print("=" * 72)
        return 2

    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"])
        w.writeheader(); w.writerows(pred_rows)
    with open(args.log_path, "w", encoding="utf-8") as fh:
        for r in log_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps({"_summary": True, "event": "summary", "base_pred": args.base_pred,
                             "samples": n, "num_samples": n, "answers_changed": changed,
                             "changed_vs_base": changed, "by_rule": dict(by_rule),
                             "elapsed_seconds": round(elapsed, 3),
                             "samples_per_second": sps,
                             "avg_seconds_per_sample": avg}, ensure_ascii=False) + "\n")
    print(f"prediction CSV  : {args.output}")
    print(f"log JSONL       : {args.log_path}")
    print(f"diff CSV        : {args.diff}")
    print("NOTE: only generalized safe rules applied; no qid lists; no ground truth.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
