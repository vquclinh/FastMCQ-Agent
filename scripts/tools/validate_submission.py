#!/usr/bin/env python3
"""Validate a submission CSV against its dataset.

Checks:
  * required columns (qid, answer) present
  * every dataset qid has a prediction
  * no duplicate qids
  * no missing/empty answers
  * each answer is a valid label given that question's number of choices

Usage:
    python scripts/validate_submission.py --input DATA --submission pred.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.data_io import load_dataset, read_predictions  # noqa: E402
from src.utils.labels import is_valid_label  # noqa: E402


def validate(input_path: Path, submission_path: Path) -> tuple[bool, list[str]]:
    """Return (ok, problems). ``problems`` is empty when ok is True."""
    samples = load_dataset(input_path)
    rows = read_predictions(submission_path)
    problems: list[str] = []

    # 1. Required columns.
    header = set(rows[0].keys()) if rows else set()
    if not rows:
        problems.append("submission is empty")
        return False, problems
    for col in ("qid", "answer"):
        if col not in header:
            problems.append(f"missing required column: {col}")
    if problems:
        return False, problems

    sample_by_qid = {s["qid"]: s for s in samples}
    pred_qids = [r["qid"] for r in rows]

    # 2. Duplicate qids.
    duplicates = sorted({q for q in pred_qids if pred_qids.count(q) > 1})
    if duplicates:
        problems.append(f"duplicate qids ({len(duplicates)}): {duplicates[:10]}")

    # 3. All dataset qids present.
    missing = sorted(set(sample_by_qid) - set(pred_qids))
    if missing:
        problems.append(f"missing predictions for {len(missing)} qids: {missing[:10]}")

    # 4. Extra qids not in dataset.
    extra = sorted(set(pred_qids) - set(sample_by_qid))
    if extra:
        problems.append(f"unexpected qids not in dataset ({len(extra)}): {extra[:10]}")

    # 5 & 6. Missing answers and label validity.
    empty = []
    invalid = []
    for row in rows:
        qid, answer = row["qid"], (row.get("answer") or "").strip()
        if not answer:
            empty.append(qid)
            continue
        sample = sample_by_qid.get(qid)
        if sample is not None and not is_valid_label(answer, sample):
            invalid.append(f"{qid}={answer} (choices={len(sample['choices'])})")
    if empty:
        problems.append(f"empty answers for {len(empty)} qids: {empty[:10]}")
    if invalid:
        problems.append(f"invalid labels for {len(invalid)} qids: {invalid[:10]}")

    return (not problems), problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an MCQ submission CSV")
    parser.add_argument("--input", required=True, help="dataset JSON/CSV")
    parser.add_argument("--submission", required=True, help="submission CSV (qid,answer)")
    args = parser.parse_args(argv)

    ok, problems = validate(Path(args.input), Path(args.submission))

    print("=" * 50)
    print("SUBMISSION VALIDATION REPORT")
    print("=" * 50)
    print(f"dataset    : {args.input}")
    print(f"submission : {args.submission}")
    print("-" * 50)
    if ok:
        print("RESULT: PASS — submission is valid.")
    else:
        print("RESULT: FAIL")
        for problem in problems:
            print(f"  - {problem}")
    print("=" * 50)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
