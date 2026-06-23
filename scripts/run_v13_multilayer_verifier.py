#!/usr/bin/env python3
"""Phase 2L.35A — Unified V13 multi-layer verifier runner.

For each planned qid, runs each assigned layer (programmatic_solver / content_first /
least_to_most): builds the layer prompt, (optionally) calls the guarded model, parses the
structured response with the corresponding src core module, maps it to an option label, and
records a candidate. Default is ``--dry-run`` (NO API).
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
from src import programmatic_solver_layer as PS  # noqa: E402
from src import content_first_answerer as CF  # noqa: E402
from src import least_to_most_constraint_solver as LTM  # noqa: E402


def _prompt_for_layer(layer, sample, route):
    if layer == "programmatic_solver":
        return PS.build_programmatic_prompt(sample, PS.classify_programmatic_domain(sample))
    if layer == "content_first":
        return CF.build_content_first_prompt(sample, route)
    if layer == "least_to_most":
        return LTM.build_ltm_constraint_prompt(sample, route)
    raise ValueError(f"unknown layer {layer}")


def _interpret(layer, sample, parsed):
    """Return (proposed_label, proposed_option_text, confidence, valid, rejection_reason, evidence)."""
    choices = sample.get("choices") or []
    labels = [chr(ord("A") + i) for i in range(len(choices))]
    if layer == "programmatic_solver":
        spec = PS.parse_calculation_spec(parsed)
        res = PS.safe_execute_calculation(spec)
        res = PS.match_result_to_options(res, sample)
        lab = res.mapped_label
        text = choices[labels.index(lab)] if lab in labels else None
        return lab, text, parsed.get("confidence"), bool(res.ok and lab), res.failure_reason, \
            parsed.get("evidence") or spec.raw.get("result_hint")
    if layer == "content_first":
        ca = CF.parse_content_answer(parsed)
        m = CF.match_content_to_options(ca, sample)
        lab = m.mapped_label
        text = choices[labels.index(lab)] if lab in labels else None
        return lab, text, ca.confidence, bool(m.ok and lab), m.failure_reason, ca.evidence
    if layer == "least_to_most":
        dec = LTM.parse_constraint_table(parsed)
        out = LTM.select_answer_from_constraint_table(dec, sample)
        lab = out.get("proposed_label")
        text = choices[labels.index(lab)] if lab in labels else None
        return lab, text, out.get("confidence"), bool(out.get("ok")), out.get("rejection_reason"), \
            f"survivors={out.get('survivors')}"
    return None, None, None, False, "unknown_layer", None


def run(samples_by_qid, plan_rows, current, *, work_dir, model, max_qids, budget_usd,
        execute, dry_run):
    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    out_path = work / "v13_multilayer_candidates.jsonl"
    prompt_path = work / "v13_multilayer_prompts.jsonl"

    client = None
    if execute and not dry_run:
        assert_allowed_llm_model(model)
        from src.selective_api_client import SelectiveAPIClient
        client = SelectiveAPIClient(model=model)

    planned = plan_rows[:max_qids] if max_qids else plan_rows
    candidates, prompts, n_calls = [], [], 0
    for row in planned:
        qid = row["qid"]
        sample = samples_by_qid.get(qid)
        if not sample:
            continue
        cur = current.get(qid, "")
        route = row.get("route", "")
        layers = [l for l in (row.get("target_layers") or "").split("|") if l]
        for layer in layers:
            prompt = _prompt_for_layer(layer, sample, route)
            messages = [{"role": "user", "content": prompt}]
            prompts.append({"qid": qid, "layer": layer, "messages": messages})
            rec = {"qid": qid, "layer": layer, "current_answer": cur,
                   "proposed_label": None, "proposed_option_text": None, "confidence": None,
                   "parse_status": "dry_run", "valid": False, "rejection_reason": "dry_run",
                   "evidence": None, "raw_response": None}
            if execute and not dry_run and client is not None:
                content, _usage = client.chat(messages)
                parsed = client.parse_json(content) or {}
                n_calls += 1
                lab, text, conf, valid, reason, evid = _interpret(layer, sample, parsed)
                rec.update({"proposed_label": lab, "proposed_option_text": text,
                            "confidence": conf, "parse_status": "ok" if parsed else "parse_error",
                            "valid": bool(valid and parsed), "rejection_reason": reason or "",
                            "evidence": evid, "raw_response": content[:2000] if content else None})
            candidates.append(rec)

    with out_path.open("w", encoding="utf-8") as f:
        for r in candidates:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with prompt_path.open("w", encoding="utf-8") as f:
        for p in prompts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    return {"planned_qids": len(planned), "candidates_written": len(candidates),
            "prompts_built": len(prompts), "model_calls_made": n_calls,
            "mode": "execute" if (execute and not dry_run) else "dry_run",
            "candidates": str(out_path), "prompts": str(prompt_path)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V13 multi-layer verifier (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--work-dir", default="scratch/v13_multilayer")
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--max-qids", type=int, default=30)
    ap.add_argument("--budget-usd", type=float, default=0.50)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--resume", action="store_true", default=False)
    args = ap.parse_args(argv)

    dry_run = args.dry_run or not args.execute
    samples = load_dataset(args.input)
    samples_by_qid = {s["qid"]: s for s in samples}
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    with open(args.plan, newline="", encoding="utf-8") as f:
        plan_rows = list(csv.DictReader(f))

    summary = run(samples_by_qid, plan_rows, current, work_dir=args.work_dir, model=args.model,
                  max_qids=args.max_qids, budget_usd=args.budget_usd,
                  execute=args.execute, dry_run=dry_run)
    print("=" * 60)
    print("V13 MULTI-LAYER VERIFIER")
    for k, v in summary.items():
        print(f"{k:20}: {v}")
    if summary["mode"] == "dry_run":
        print("NOTE: dry-run — NO API call was made. Use --execute (+budget) to run for real.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
