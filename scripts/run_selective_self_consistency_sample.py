#!/usr/bin/env python3
"""Selective self-consistency / best-of-N sample runner (DRY-RUN by default; no API).

For each candidate it would draw ``--n-samples`` answers at ``--temperature`` and
aggregate a majority vote (proposal-only). Calls OpenRouter only with ``--execute``.
**No override is implemented in this phase** — `override_applied` is always False.
Never reads the external answer sheet.

Dry-run (default; NO API):
    python scripts/run_selective_self_consistency_sample.py \
      --input public-test_1780368312.json \
      --candidates outputs/self_consistency_candidates.csv \
      --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
      --max-calls 20
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import guard_output, load_pred, load_samples, write_csv, write_jsonl  # noqa: E402
from src.labels import labels_for  # noqa: E402

_FIELDS = ["qid", "current_answer", "n_samples", "vote_distribution", "majority_answer",
           "majority_count", "consensus_strength", "would_change_answer",
           "override_applied", "dry_run"]

_SYS = ("Trả lời câu hỏi trắc nghiệm. KHÔNG dùng bảng đáp án ngoài. Trả về DUY NHẤT "
        "JSON: {\"selected_answer\":\"<NHÃN>\",\"confidence\":<0..1>,\"reason\":"
        "\"<ngắn>\",\"evidence_type\":\"internal_knowledge|option_elimination|uncertain\"}.")


def _messages(question, choices, labels):
    opts = "\n".join(f"{labels[i]}. {c}" for i, c in enumerate(choices))
    return [{"role": "system", "content": _SYS},
            {"role": "user", "content": f"Câu hỏi:\n{question}\n\nLựa chọn:\n{opts}\n\n"
                                        f"Chọn đúng một nhãn trong [{', '.join(labels)}]."}]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Selective self-consistency sample (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--candidates", required=True, help="self_consistency_candidates.csv")
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--n-samples", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-calls", type=int, default=20)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--output-jsonl", default="outputs/selective_self_consistency_dryrun.jsonl")
    ap.add_argument("--output-csv", default="outputs/selective_self_consistency_dryrun.csv")
    args = ap.parse_args(argv)

    guard_output(args.output_jsonl); guard_output(args.output_csv)
    dry_run = not (args.execute and args.max_calls > 0)
    by_qid = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    cand_qids = [r["qid"] for r in csv.DictReader(open(args.candidates))][: max(0, args.max_calls)]

    client = None
    if not dry_run:
        from src.openrouter_client import OpenRouterClient   # lazy; only on --execute
        client = OpenRouterClient()

    records, rows = [], []
    for qid in cand_qids:
        s = by_qid.get(qid)
        if not s:
            continue
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        current = base.get(qid)
        rec = {"qid": qid, "current_answer": current, "n_samples": args.n_samples,
               "vote_distribution": None, "majority_answer": None, "majority_count": None,
               "consensus_strength": None, "would_change_answer": None,
               "override_applied": False, "dry_run": dry_run}
        if not dry_run:  # pragma: no cover - only on explicit --execute
            votes = []
            for _ in range(args.n_samples):
                res = client.chat(_messages(s.get("question", ""), choices, labels),
                                  response_format={"type": "json_object"},
                                  temperature=args.temperature)
                try:
                    sel = (json.loads(res.content) or {}).get("selected_answer")
                except Exception:
                    sel = None
                if sel in labels:
                    votes.append(sel)
            dist = Counter(votes)
            maj, mc = (dist.most_common(1)[0] if dist else (None, 0))
            strength = (mc / len(votes)) if votes else 0.0
            rec.update({"vote_distribution": dict(dist), "majority_answer": maj,
                        "majority_count": mc, "consensus_strength": round(strength, 3),
                        "would_change_answer": bool(maj and maj != current),
                        "override_applied": False})   # NO override in this phase
        records.append(rec)
        row = {k: rec.get(k) for k in _FIELDS}
        row["vote_distribution"] = json.dumps(rec.get("vote_distribution"), ensure_ascii=False)
        rows.append(row)

    write_jsonl(args.output_jsonl, records)
    write_csv(args.output_csv, rows, _FIELDS)
    print("=" * 64)
    print("SELECTIVE SELF-CONSISTENCY " + ("(DRY-RUN; NO API)" if dry_run else "PROPOSALS (EXECUTED)"))
    print("=" * 64)
    print(f"dry_run={dry_run}  n_samples={args.n_samples}  temperature={args.temperature}")
    print(f"planned candidates: {len(records)}")
    print(f"jsonl -> {args.output_jsonl}\ncsv   -> {args.output_csv}")
    if dry_run:
        print("No API call was made; no answer changed.")
    else:
        print("PROPOSAL-ONLY: override not implemented this phase; no prediction patched.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
