#!/usr/bin/env python3
"""Controlled short_knowledge selective-verifier sample runner.

DRY-RUN BY DEFAULT — it does NOT call any API unless ``--execute`` is passed AND
``--max-calls`` > 0. In dry-run it selects verifier-eligible short_knowledge items
(up to ``--max-calls``), builds the verifier prompt it *would* send, and logs the
gating decision — without contacting OpenRouter and without changing any answer.

Override gate (only applied in --execute mode, and only when allow_override=true):
  should_override AND selected_answer valid AND selected_answer != current AND
  confidence >= 0.90 AND reason non-empty AND evidence_type != "uncertain".

Never uses the external 3-LLM sheet. Never overwrites protected prediction files.

Dry-run (default; NO API):
    python scripts/run_short_knowledge_verifier_sample.py \
      --input public-test_1780368312.json \
      --base-pred outputs/pred_v7_programmatic_assist_from_v6b.csv \
      --base-log outputs/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --max-calls 5
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_routing import sk_verifier_eligibility  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.question_profiler import profile_question  # noqa: E402
from src.question_router import route_question  # noqa: E402

_PROTECTED = {"pred.csv", "pred_v2_calc_rerank.csv",
              "pred_v6_qwen_rerank_calc_verifier.csv",
              "pred_v6b_qwen_rerank_calc_verifier_fast.csv",
              "pred_v7_programmatic_assist_from_v6b.csv"}

_CSV_FIELDS = ["qid", "route", "current_answer", "original_confidence", "priority",
               "trigger_reasons", "verifier_selected", "should_override",
               "verifier_confidence", "evidence_type", "reason", "would_change_answer",
               "override_applied", "dry_run"]

_SYS = ("Bạn là người kiểm tra đáp án trắc nghiệm. Chỉ dùng kiến thức nội tại và "
        "loại trừ phương án — KHÔNG dùng bất kỳ bảng đáp án ngoài nào. Trả về DUY "
        "NHẤT một JSON: {\"selected_answer\":\"<NHÃN>\",\"should_override\":<bool>,"
        "\"confidence\":<0..1>,\"reason\":\"<ngắn>\",\"evidence_type\":"
        "\"internal_knowledge|option_elimination|uncertain\"}. Nếu không chắc chắn "
        "hơn đáp án hiện tại, giữ nguyên đáp án hiện tại.")


def _verifier_messages(question, choices, labels, current, rationale):
    opts = "\n".join(f"{labels[i]}. {c}" for i, c in enumerate(choices))
    user = (f"Câu hỏi:\n{question}\n\nLựa chọn:\n{opts}\n\n"
            f"Đáp án hiện tại: {current}\n"
            f"Lý do hiện tại: {rationale or '(không có)'}\n\n"
            f"Hãy chọn đúng một nhãn trong [{', '.join(labels)}] hoặc giữ đáp án hiện tại.")
    return [{"role": "system", "content": _SYS}, {"role": "user", "content": user}]


def _gate(v, current, labels, *, allow_override):
    return bool(allow_override and v.get("should_override")
                and v.get("selected_answer") in labels
                and v.get("selected_answer") != current
                and (v.get("confidence") or 0) >= 0.90
                and str(v.get("reason") or "").strip()
                and v.get("evidence_type") not in (None, "uncertain"))


def _load_samples(path):
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Controlled SK verifier sample (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--base-log", default=None)
    ap.add_argument("--max-calls", type=int, default=5)
    ap.add_argument("--trigger-confidence-max", type=float, default=0.95)
    ap.add_argument("--allow-override", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False,
                    help="ACTUALLY call OpenRouter (default off = dry-run, no API)")
    ap.add_argument("--risk-csv", default=None,
                    help="first-100 risk CSV — used ONLY for prioritization/reporting")
    ap.add_argument("--prioritize-risk", action="store_true", default=False,
                    help="order candidates P0/P1-first then low-confidence (ordering only)")
    ap.add_argument("--output-jsonl", default="outputs/short_knowledge_verifier_sample_dryrun.jsonl")
    ap.add_argument("--output-csv", default="outputs/short_knowledge_verifier_sample_dryrun.csv")
    args = ap.parse_args(argv)

    for p in (args.output_jsonl, args.output_csv):
        if Path(p).name in _PROTECTED:
            raise SystemExit(f"REFUSING to write protected file: {p}")

    dry_run = not (args.execute and args.max_calls > 0)
    samples = _load_samples(args.input)
    base = {r["qid"]: r["answer"] for r in csv.DictReader(open(args.base_pred))}
    log = {}
    if args.base_log and Path(args.base_log).exists():
        for line in Path(args.base_log).read_text().splitlines():
            line = line.strip()
            if line:
                o = json.loads(line)
                if o.get("qid"):
                    log[o["qid"]] = o

    client = None
    if not dry_run:
        from src.openrouter_client import OpenRouterClient   # lazy; only on --execute
        client = OpenRouterClient()

    # Optional risk CSV for PRIORITIZATION/REPORTING ONLY (never answer selection).
    risk_priority = {}   # qid -> "P0"/"P1"
    if args.risk_csv and Path(args.risk_csv).exists():
        for r in csv.DictReader(open(args.risk_csv)):
            if r.get("priority") in ("P0", "P1"):
                risk_priority[r.get("qid")] = r["priority"]

    # Collect ALL eligible short_knowledge candidates (then prioritize, then cap).
    cands = []
    for s in samples:
        qid = s.get("qid")
        route = route_question(profile_question(s)).route
        tr_log = log.get(qid, {})
        conf = tr_log.get("confidence")
        state = {"final_answer": base.get(qid), "confidence": conf,
                 "parsed_answer": tr_log.get("parsed_answer") or {}}
        elig, reasons = sk_verifier_eligibility(
            s, route, state=state, trigger_confidence_max=args.trigger_confidence_max)
        if elig:
            cands.append({"sample": s, "reasons": reasons, "route": route,
                          "confidence": conf, "priority": risk_priority.get(qid)})

    if args.prioritize_risk:
        # P0/P1 first (P0 before P1), then lowest confidence, then most trigger flags.
        rank = {"P0": 0, "P1": 1}
        cands.sort(key=lambda c: (rank.get(c["priority"], 2),
                                  c["confidence"] if isinstance(c["confidence"], (int, float)) else 1.0,
                                  -len(c["reasons"])))
    planned = cands[: max(0, args.max_calls)]

    records, csv_rows = [], []
    proposed_change = 0
    for c in planned:
        s = c["sample"]; reasons = c["reasons"]
        qid = s.get("qid")
        choices = s.get("choices", []) or []
        labels = labels_for(len(choices))
        current = base.get(qid)
        rationale = (log.get(qid, {}).get("parsed_answer") or {}).get("reason_type")
        messages = _verifier_messages(s.get("question", ""), choices, labels, current, rationale)
        rec = {"qid": qid, "route": c["route"], "current_answer": current,
               "original_confidence": c["confidence"], "trigger_reasons": reasons,
               "priority": c["priority"], "dry_run": dry_run,
               "allow_override": args.allow_override,
               "verifier_selected": None, "should_override": None,
               "verifier_confidence": None, "evidence_type": None, "reason": None,
               "would_change_answer": None, "override_applied": False,
               "verifier_messages_preview": messages[1]["content"][:200]}
        if dry_run:
            rec["decision"] = "DRY_RUN: would send verifier prompt; no API; answer unchanged"
        else:  # pragma: no cover - only on explicit --execute
            res = client.chat(messages, response_format={"type": "json_object"})
            try:
                v = json.loads(res.content)
            except Exception:
                v = {}
            sel = v.get("selected_answer")
            would_change = bool(sel in labels and sel != current)
            applied = _gate(v, current, labels, allow_override=args.allow_override)
            proposed_change += int(would_change)
            rec.update({
                "verifier_selected": sel, "should_override": v.get("should_override"),
                "verifier_confidence": v.get("confidence"), "evidence_type": v.get("evidence_type"),
                "reason": v.get("reason"), "would_change_answer": would_change,
                "override_applied": applied,   # False unless --allow-override AND gate passes
                "verifier_raw": v,
            })
        records.append(rec)
        row = {k: rec.get(k) for k in _CSV_FIELDS}
        row["trigger_reasons"] = "|".join(reasons)
        csv_rows.append(row)

    Path(args.output_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_jsonl, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(args.output_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        w.writeheader(); w.writerows(csv_rows)

    patched = sum(1 for r in records if r.get("override_applied"))
    print("=" * 64)
    print("SHORT-KNOWLEDGE VERIFIER " + ("SAMPLE (DRY-RUN; NO API)" if dry_run else "PROPOSALS (EXECUTED)"))
    print("=" * 64)
    print(f"dry_run         : {dry_run}  (execute={args.execute}, max_calls={args.max_calls})")
    print(f"allow_override  : {args.allow_override}   prioritize_risk: {args.prioritize_risk}")
    print(f"eligible total  : {len(cands)}   planned (capped): {len(planned)}")
    if not dry_run:
        print(f"proposed to CHANGE answer : {proposed_change}")
        print(f"override_applied (patches): {patched}  (0 expected without --allow-override)")
    print(f"jsonl -> {args.output_jsonl}")
    print(f"csv   -> {args.output_csv}")
    if dry_run:
        print("No API call was made; no answer changed.")
    elif not args.allow_override:
        print("PROPOSAL-ONLY: API called, but NO prediction was patched (allow_override off).")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
