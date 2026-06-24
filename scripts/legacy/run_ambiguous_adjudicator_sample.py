#!/usr/bin/env python3
"""Controlled ambiguous-route adjudicator sample (DRY-RUN by default; no API).

Calls OpenRouter only with ``--execute``; patches only with ``--allow-override`` AND
when the shared override gate passes. Proposal-only by default; never reads the
external answer sheet.

Dry-run (default; NO API):
    python scripts/run_ambiguous_adjudicator_sample.py \
      --input public-test_1780368312.json \
      --base-pred output/pred_v7_programmatic_assist_from_v6b.csv \
      --base-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --max-calls 7
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import (guard_output, load_log, load_pred,  # noqa: E402
                                          load_risk_priority, load_samples,
                                          override_gate, write_csv, write_jsonl)
from src.labels import labels_for  # noqa: E402
from src.question_profiler import profile_question  # noqa: E402
from src.question_router import route_question  # noqa: E402

_FIELDS = ["qid", "route", "current_answer", "original_confidence", "priority",
           "verifier_selected", "should_override", "verifier_confidence",
           "evidence_type", "reason", "uncertainty_reason", "would_change_answer",
           "override_applied", "dry_run"]

_SYS = ("Bạn là trọng tài phân xử cho câu hỏi trắc nghiệm có lựa chọn dễ gây nhầm "
        "lẫn. So sánh kỹ các phương án, ưu tiên GIỮ đáp án hiện tại nếu không chắc. "
        "KHÔNG dùng bảng đáp án ngoài. Trả về DUY NHẤT JSON: "
        "{\"selected_answer\":\"<NHÃN>\",\"should_override\":<bool>,"
        "\"confidence\":<0..1>,\"reason\":\"<ngắn>\",\"uncertainty_reason\":\"<ngắn>\","
        "\"evidence_type\":\"option_elimination|internal_reasoning|uncertain\"}.")


def _messages(question, choices, labels, current, conf, rationale):
    opts = "\n".join(f"{labels[i]}. {c}" for i, c in enumerate(choices))
    user = (f"Câu hỏi:\n{question}\n\nLựa chọn:\n{opts}\n\nĐáp án hiện tại: {current}\n"
            f"Độ tin cậy hiện tại: {conf}\nLý do hiện tại: {rationale or '(không có)'}\n\n"
            f"Hãy chọn đúng một nhãn trong [{', '.join(labels)}] hoặc giữ đáp án hiện tại.")
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Controlled ambiguous adjudicator (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--risk-csv", default=None)
    ap.add_argument("--prioritize-risk", action="store_true", default=False)
    ap.add_argument("--max-calls", type=int, default=7)
    ap.add_argument("--allow-override", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--output-jsonl", default="output/ambiguous_adjudicator_dryrun.jsonl")
    ap.add_argument("--output-csv", default="output/ambiguous_adjudicator_dryrun.csv")
    args = ap.parse_args(argv)

    guard_output(args.output_jsonl); guard_output(args.output_csv)
    dry_run = not (args.execute and args.max_calls > 0)
    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.base_log)
    risk = load_risk_priority(args.risk_csv)

    client = None
    if not dry_run:
        from src.openrouter_client import OpenRouterClient   # lazy; only on --execute
        client = OpenRouterClient()

    cands = []
    for s in samples:
        qid = s.get("qid")
        if route_question(profile_question(s)).route != "ambiguous":
            continue
        if not base.get(qid):
            continue
        cands.append((s, log.get(qid, {}).get("confidence"), risk.get(qid)))
    if args.prioritize_risk:
        rank = {"P0": 0, "P1": 1}
        cands.sort(key=lambda c: (rank.get(c[2], 2),
                                  c[1] if isinstance(c[1], (int, float)) else 1.0))
    planned = cands[: max(0, args.max_calls)]

    records, rows, proposed = [], [], 0
    for s, conf, pri in planned:
        qid = s.get("qid"); choices = s.get("choices", []) or []
        labels = labels_for(len(choices)); current = base.get(qid)
        rationale = (log.get(qid, {}).get("parsed_answer") or {}).get("reason_type")
        rec = {"qid": qid, "route": "ambiguous", "current_answer": current,
               "original_confidence": conf, "priority": pri, "verifier_selected": None,
               "should_override": None, "verifier_confidence": None, "evidence_type": None,
               "reason": None, "uncertainty_reason": None, "would_change_answer": None,
               "override_applied": False, "dry_run": dry_run}
        if not dry_run:  # pragma: no cover - only on explicit --execute
            res = client.chat(_messages(s.get("question", ""), choices, labels, current, conf, rationale),
                              response_format={"type": "json_object"})
            try:
                v = json.loads(res.content)
            except Exception:
                v = {}
            sel = v.get("selected_answer")
            wc = bool(sel in labels and sel != current)
            applied = override_gate(v, current, labels, allow_override=args.allow_override,
                                    uncertain_values=("uncertain", None, ""))
            proposed += int(wc)
            rec.update({"verifier_selected": sel, "should_override": v.get("should_override"),
                        "verifier_confidence": v.get("confidence"), "evidence_type": v.get("evidence_type"),
                        "reason": v.get("reason"), "uncertainty_reason": v.get("uncertainty_reason"),
                        "would_change_answer": wc, "override_applied": applied, "verifier_raw": v})
        records.append(rec)
        rows.append({k: rec.get(k) for k in _FIELDS})

    write_jsonl(args.output_jsonl, records)
    write_csv(args.output_csv, rows, _FIELDS)
    patched = sum(1 for r in records if r.get("override_applied"))
    print("=" * 64)
    print("AMBIGUOUS ADJUDICATOR " + ("(DRY-RUN; NO API)" if dry_run else "PROPOSALS (EXECUTED)"))
    print("=" * 64)
    print(f"dry_run={dry_run}  allow_override={args.allow_override}  planned={len(planned)}/{len(cands)}")
    if not dry_run:
        print(f"proposed to change: {proposed}   override_applied: {patched}")
    print(f"jsonl -> {args.output_jsonl}\ncsv   -> {args.output_csv}")
    if dry_run:
        print("No API call was made; no answer changed.")
    elif not args.allow_override:
        print("PROPOSAL-ONLY: API called, NO prediction patched (allow_override off).")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
