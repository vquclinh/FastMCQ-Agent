#!/usr/bin/env python3
"""Diagnostic pseudo-comparison of v6b vs v7 against the external 3-LLM majority.

READ-ONLY. The external Gemini/ChatGPT/Claude majority is a RISK SIGNAL, **NOT
ground truth** — a "pseudo-accuracy" drop can simply mean the 3 LLMs shared a common
error while our deterministic answer is correct. This script reports the first-100
agreement of v6b and v7 with that majority and shows which changed calculation rows
moved toward or away from it. No API, no pipeline use of the sheet, no qid logic.

Usage:
    python scripts/compare_v7_programmatic_assist_pseudo.py \
      --public-test public-test_1780368312.json \
      --external-sheet scratch/first100_external_3llm.csv \
      --v6b outputs/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
      --v7 outputs/pred_v7_programmatic_assist_from_v6b.csv \
      --v7-log outputs/run_v7_programmatic_assist_from_v6b.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

_LABEL = re.compile(r"[A-K]")


def _norm(s):
    m = _LABEL.search(str(s).strip().upper()) if s is not None else None
    return m.group(0) if m else ""


def _qids(path, n):
    data = json.loads(Path(path).read_text())
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    return [r.get("qid") for r in rows][:n]


def _pred(path):
    return {r["qid"]: _norm(r["answer"]) for r in csv.DictReader(open(path))}


def _sheet(path):
    out = []
    for line in csv.reader(open(path)):
        if line and any(c.strip() for c in line):
            out.append([_norm(c) for c in line[:3]])
    return out


def _majority(triple):
    vals = [x for x in triple if x]
    if not vals:
        return "", 0
    top, n = Counter(vals).most_common(1)[0]
    return top, n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v6b vs v7 pseudo-comparison (diagnostic only)")
    ap.add_argument("--public-test", required=True)
    ap.add_argument("--external-sheet", required=True)
    ap.add_argument("--v6b", required=True)
    ap.add_argument("--v7", required=True)
    ap.add_argument("--v7-log", default=None)
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args(argv)

    qids = _qids(args.public_test, args.n)
    sheet = _sheet(args.external_sheet)
    n = min(len(qids), len(sheet))
    qids = qids[:n]
    v6b, v7 = _pred(args.v6b), _pred(args.v7)

    v6b_ok = v7_ok = 0
    p0 = p1 = 0
    changed_calc = []
    for i, qid in enumerate(qids):
        maj, mc = _majority(sheet[i])
        a6 = v6b.get(qid, "")
        a7 = v7.get(qid, "")
        if maj and a6 == maj:
            v6b_ok += 1
        if maj and a7 == maj:
            v7_ok += 1
        if mc == 3 and a7 != maj:
            p0 += 1
        elif mc >= 2 and maj and a7 != maj:
            p1 += 1
        if a6 != a7:
            changed_calc.append((qid, maj, mc, a6, a7,
                                 "toward_majority" if (a7 == maj and a6 != maj)
                                 else "away_from_majority" if (a6 == maj and a7 != maj)
                                 else "neither"))

    print("=" * 72)
    print("v6b vs v7 PSEUDO-COMPARISON (external majority is a RISK SIGNAL, NOT truth)")
    print("=" * 72)
    print(f"first-{n} v6b vs external majority : {v6b_ok}/{n} ({100*v6b_ok/n:.1f}%)")
    print(f"first-{n} v7  vs external majority : {v7_ok}/{n} ({100*v7_ok/n:.1f}%)")
    print(f"P0 remaining (3/3 differ from v7) : {p0}")
    print(f"P1 remaining (>=2/3 differ from v7): {p1}")
    print("-" * 72)
    print("changed rows v6b -> v7 (deterministic calc overrides):")
    for qid, maj, mc, a6, a7, dir_ in changed_calc:
        print(f"  {qid}: ext_majority={maj}({mc}/3)  v6b={a6} -> v7={a7}  [{dir_}]")
    print("-" * 72)
    print("INTERPRETATION: a move 'away_from_majority' is NOT necessarily worse — the 3")
    print("LLMs can share a common mistake. v7's calculation overrides are deterministic")
    print("and were validated by synthetic unit tests; the leaderboard is the only truth.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
