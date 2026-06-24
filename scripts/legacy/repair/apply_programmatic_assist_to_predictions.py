#!/usr/bin/env python3
"""Apply deterministic calculation assist overrides to v6b predictions (no API).

Starts from a base prediction CSV (v6b) and, for each sample, runs the adaptive
orchestrator's **calculation branch in assist mode**. It patches the answer ONLY
when a deterministic family matched with ``safe_to_override=True`` AND the branch is
calculation AND the new answer differs from the base. Everything else keeps the base
answer. No OpenRouter, no full inference, no qid-specific logic, no external answer
sheet — purely deterministic patching of frozen v6b predictions.

Usage:
    python scripts/apply_programmatic_assist_to_predictions.py \
      --input public-test_1780368312.json \
      --base-pred output/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
      --base-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --output output/pred_v7_programmatic_assist_from_v6b.csv \
      --log-path output/run_v7_programmatic_assist_from_v6b.jsonl \
      --diff output/programmatic_assist_diff.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.layers.adaptive_orchestrator import AdaptiveConfig, AdaptiveOrchestrator  # noqa: E402
from src.utils.labels import labels_for  # noqa: E402

_PROTECTED = {"pred.csv", "pred_v2_calc_rerank.csv",
              "pred_v6_qwen_rerank_calc_verifier.csv",
              "pred_v6b_qwen_rerank_calc_verifier_fast.csv"}


def _load_samples(path):
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def _load_pred(path):
    out = {}
    for row in csv.DictReader(open(path)):
        out[row["qid"]] = row["answer"]
    return out


def _guard_output(path):
    if Path(path).name in _PROTECTED:
        raise SystemExit(f"REFUSING to write protected file: {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic calculation assist patch from v6b (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--log-path", required=True)
    ap.add_argument("--diff", required=True)
    args = ap.parse_args(argv)

    for p in (args.output, args.log_path, args.diff):
        _guard_output(p)

    samples = _load_samples(args.input)
    base = _load_pred(args.base_pred)

    # Assist mode: ONLY the calculation branch may change answers, only when safe.
    orch = AdaptiveOrchestrator(AdaptiveConfig(
        enabled=True, mode="assist",
        calculation_programmatic_enabled=True, calculation_allow_override=True))

    pred_rows, log_rows, diff_rows = [], [], []
    changed = 0

    for s in samples:
        qid = s.get("qid")
        base_ans = base.get(qid, "")
        labels = labels_for(len(s.get("choices", []) or []))
        tr = orch.analyze(s, existing_answer=base_ans)
        cand = tr.branch_candidates[0] if tr.branch_candidates else {}
        new_ans = base_ans
        applied = False
        # Apply ONLY a safe, answer-changing deterministic calculation override.
        if (tr.selected_branch == "calculation" and tr.would_override
                and cand.get("answer") in labels):
            new_ans = cand["answer"]
            applied = True
            changed += 1

        pred_rows.append({"qid": qid, "answer": new_ans})
        rec = {
            "qid": qid, "route": tr.route, "selected_branch": tr.selected_branch,
            "base_answer": base_ans, "final_answer": new_ans, "changed": applied,
            "override_method": cand.get("method") if applied else None,
            "candidate_answer": cand.get("answer"), "candidate_note": cand.get("note"),
            "would_override": tr.would_override, "override_allowed": tr.override_allowed,
            "final_decision": tr.final_decision, "risk_flags": tr.risk_flags,
            "reason": (f"deterministic calculation override via {cand.get('method')}: "
                       f"{base_ans}->{new_ans}") if applied else "kept base (v6b)",
            "solver": "programmatic_assist_from_v6b",
        }
        log_rows.append(rec)
        if applied:
            diff_rows.append({"qid": qid, "route": tr.route, "method": cand.get("method"),
                              "old_answer": base_ans, "new_answer": new_ans,
                              "reason": rec["reason"], "candidate_note": cand.get("note")})

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"])
        w.writeheader(); w.writerows(pred_rows)
    with open(args.log_path, "w", encoding="utf-8") as fh:
        for r in log_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps({"_summary": True, "base_pred": args.base_pred,
                             "num_samples": len(pred_rows), "changed_vs_base": changed,
                             "mode": "assist", "branch": "calculation_only"},
                            ensure_ascii=False) + "\n")
    with open(args.diff, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "route", "method", "old_answer",
                                           "new_answer", "reason", "candidate_note"])
        w.writeheader(); w.writerows(diff_rows)

    print("=" * 70)
    print("PROGRAMMATIC ASSIST PATCH (v6b -> v7; deterministic calc only; no API)")
    print("=" * 70)
    print(f"base predictions : {args.base_pred}")
    print(f"samples          : {len(pred_rows)}")
    print(f"answers changed  : {changed}")
    for d in diff_rows:
        print(f"  {d['qid']}  {d['route']:12s} {d['method']:30s} {d['old_answer']} -> {d['new_answer']}")
    print(f"prediction CSV   : {args.output}")
    print(f"log JSONL        : {args.log_path}")
    print(f"diff CSV         : {args.diff}")
    print("NOTE: only safe deterministic calculation overrides applied; no ground truth used.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
