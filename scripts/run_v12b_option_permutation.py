#!/usr/bin/env python3
"""Phase 2L.34B/34C — V12B option-permutation verifier (thin CLI wrapper).

Presents each planned qid under several deterministic option orders, asks the model to pick an
answer in the *permuted* label space, then maps it back to the ORIGINAL option label. The
deterministic permutation + map-back + validity logic lives in
``src.mcq_permutation_debiaser`` — this script only owns CLI args, prompting, model I/O, and
JSONL output. Default is ``--dry-run`` (NO API).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.data_io import load_dataset, read_predictions  # noqa: E402
from src.model_policy import assert_allowed_llm_model  # noqa: E402
from src.mcq_permutation_debiaser import (  # noqa: E402
    build_option_permutations, map_permuted_answer_to_original)


def build_permutation_prompt(permutation):
    """Messages for one permuted view (JSON-only contract)."""
    opts = "\n".join(f"{pc['label']}. {pc['text']}" for pc in permutation.permuted_choices)
    sys_msg = (
        "You are an independent MCQ solver. Answer FROM SCRATCH using only the options shown. "
        "Respond with a SINGLE JSON object ONLY. Required keys: "
        '"selected_label" (one shown option letter), '
        '"selected_option_text" (copy the chosen option text VERBATIM), '
        '"confidence" (0..1), "reason_type" (e.g. fact/calculation/elimination), '
        '"label_matches_option" (true/false), "evidence" (concise). '
        "If unsure set selected_label to null."
    )
    return sys_msg, opts


def _record(sample, permutation, parsed, parse_status):
    """Build a stored record from a (possibly None) parsed model response via the core mapper."""
    parsed = parsed or {}
    res = map_permuted_answer_to_original(
        sample, permutation,
        selected_label=parsed.get("selected_label"),
        selected_option_text=parsed.get("selected_option_text"),
        label_matches_option=parsed.get("label_matches_option"))
    valid = res.valid and parse_status == "ok"
    return {
        "original_qid": sample["qid"],
        "permutation_id": permutation.permutation_id,
        "permutation_map": [pc["original_label"] for pc in permutation.permuted_choices],
        "permuted_selected_label": res.selected_label,
        "mapped_original_label": res.mapped_original_label,
        "selected_option_text": res.selected_option_text,
        "parse_status": parse_status,
        "label_option_match": res.label_option_match,
        "self_label_matches_option": parsed.get("label_matches_option"),
        "confidence": parsed.get("confidence"),
        "reason_type": parsed.get("reason_type"),
        "evidence": parsed.get("evidence"),
        "valid": bool(valid),
        "failure_reason": res.failure_reason,
    }


def run(samples_by_qid, plan_rows, *, work_dir, model, max_qids, permutations,
        budget_usd, execute, dry_run, seed=42):
    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    rec_path = work / "permutation_records.jsonl"
    prompt_path = work / "permutation_prompts.jsonl"

    client = None
    if execute and not dry_run:
        assert_allowed_llm_model(model)
        from src.selective_api_client import SelectiveAPIClient
        client = SelectiveAPIClient(model=model)

    planned = plan_rows[:max_qids] if max_qids else plan_rows
    records, prompts, n_calls = [], [], 0
    for row in planned:
        qid = row["qid"]
        sample = samples_by_qid.get(qid)
        if not sample or len(sample.get("choices") or []) < 2:
            continue
        for perm in build_option_permutations(sample, n=permutations, seed=seed):
            sys_msg, opts = build_permutation_prompt(perm)
            user_msg = (f"Question:\n{sample.get('question','')}\n\nOptions:\n{opts}\n\n"
                        "Return the JSON object now.")
            messages = [{"role": "system", "content": sys_msg},
                        {"role": "user", "content": user_msg}]
            prompts.append({"qid": qid, "permutation_id": perm.permutation_id,
                            "permutation_map": [pc["original_label"] for pc in perm.permuted_choices],
                            "messages": messages})
            if execute and not dry_run and client is not None:
                content, _usage = client.chat(messages)
                parsed = client.parse_json(content)
                n_calls += 1
                records.append(_record(sample, perm, parsed, "ok" if parsed else "parse_error"))
            else:
                records.append(_record(sample, perm, None, "dry_run"))

    with rec_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with prompt_path.open("w", encoding="utf-8") as f:
        for p in prompts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    return {"planned_qids": len(planned), "records_written": len(records),
            "prompts_built": len(prompts), "model_calls_made": n_calls,
            "permutations_per_qid": permutations,
            "mode": "execute" if (execute and not dry_run) else "dry_run",
            "records": str(rec_path), "prompts": str(prompt_path)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V12B option-permutation verifier (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--work-dir", default="scratch/v12b_option_permutation")
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--max-qids", type=int, default=30)
    ap.add_argument("--permutations", type=int, default=6)
    ap.add_argument("--budget-usd", type=float, default=0.50)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--resume", action="store_true", default=False)
    args = ap.parse_args(argv)

    dry_run = args.dry_run or not args.execute
    samples = load_dataset(args.input)
    samples_by_qid = {s["qid"]: s for s in samples}
    _ = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    with open(args.plan, newline="", encoding="utf-8") as f:
        plan_rows = list(csv.DictReader(f))

    summary = run(samples_by_qid, plan_rows, work_dir=args.work_dir, model=args.model,
                  max_qids=args.max_qids, permutations=args.permutations,
                  budget_usd=args.budget_usd, execute=args.execute, dry_run=dry_run)

    print("=" * 60)
    print("V12B OPTION-PERMUTATION VERIFIER")
    for k, v in summary.items():
        print(f"{k:20}: {v}")
    if summary["mode"] == "dry_run":
        print("NOTE: dry-run — NO API call was made. Use --execute (+budget) to run for real.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
