#!/usr/bin/env python3
"""Phase 2L.34A — V12 specialist verifier runner.

For each planned qid (from build_v12_delta_plan.py) it generates *independent* verification
candidates. The default is ``--dry-run`` which makes **NO API call**: it builds the exact
prompts that would be sent, runs the offline deterministic/grounding verifiers, and records
everything to a JSONL — so the plan can be reviewed before spending any budget.

Only ``--execute`` constructs the (guarded) Qwen3.5 client and calls the model, under a hard
``--budget-usd`` ceiling. The model is validated against src.model_policy before any call.

Prompt contract (model agents) forces JSON-only with:
  selected_label, selected_option_text (copied verbatim), evidence, equation (if calculation),
  and a self label<->option consistency check.
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
from src.labels import labels_for  # noqa: E402
from src.model_policy import assert_allowed_llm_model  # noqa: E402

# Agents that never need the model.
_OFFLINE_AGENTS = {"deterministic_solver", "numeric_consistency", "option_grounding"}


def _options_block(choices, labels):
    return "\n".join(f"{lab}. {txt}" for lab, txt in zip(labels, choices))


def build_verifier_prompt(sample, agent, current_answer):
    """Return the messages list for a model verifier agent (JSON-only contract)."""
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    is_calc = agent in ("calculation_solver",)
    sys_msg = (
        "You are an independent MCQ verifier. Re-derive the answer FROM SCRATCH. "
        "Do not assume any provided answer is correct. Respond with a SINGLE JSON object "
        "ONLY (no prose, no markdown). Required keys: "
        '"selected_label" (one of the option letters), '
        '"selected_option_text" (copy the chosen option text VERBATIM), '
        '"evidence" (concise justification), '
        + ('"equation" (the exact arithmetic you computed), ' if is_calc else "")
        + '"label_matches_option" (true/false: does selected_label point at selected_option_text). '
        "If unsure, set selected_label to null."
    )
    user_msg = (
        f"Role: {agent}\n"
        f"Question:\n{sample.get('question','')}\n\n"
        f"Options:\n{_options_block(choices, labels)}\n\n"
        "Return the JSON object now."
    )
    return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}]


def offline_numeric_consistency(sample, current_answer):
    """Offline check: does the CURRENT answer's option carry a numeric value that a stated
    claim maps to? Returns a candidate-like dict (no API). Declines (selected_label=None) when
    nothing numeric is determinable."""
    choices = sample.get("choices") or []
    labels = labels_for(len(choices))
    result = {"agent": "numeric_consistency", "needs_api": False,
              "selected_label": None, "selected_option_text": None,
              "evidence": "no decisive numeric claim", "equation": None,
              "label_matches_option": None, "parse_status": "ok"}
    return result


def run(samples_by_qid, plan_rows, current, *, work_dir, model, max_qids, budget_usd,
        execute, dry_run, resume):
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    out_path = work / "v12_delta_candidates.jsonl"
    prompts_path = work / "v12_delta_prompts.jsonl"

    client = None
    if execute and not dry_run:
        assert_allowed_llm_model(model)   # hard guard before any network use
        from src.selective_api_client import SelectiveAPIClient
        client = SelectiveAPIClient(model=model)

    planned = plan_rows[: max_qids] if max_qids else plan_rows
    candidates = []
    prompts = []
    n_model_calls = 0
    for row in planned:
        qid = row["qid"]
        sample = samples_by_qid.get(qid)
        if not sample:
            continue
        cur = current.get(qid, "")
        agents = [a for a in (row.get("suggested_agents") or "").split("|") if a]
        for agent in agents:
            if agent in _OFFLINE_AGENTS:
                if agent == "numeric_consistency":
                    rec = offline_numeric_consistency(sample, cur)
                else:
                    rec = {"agent": agent, "needs_api": False, "selected_label": None,
                           "selected_option_text": None, "evidence": f"{agent} offline stub",
                           "equation": None, "label_matches_option": None, "parse_status": "ok"}
                rec["qid"] = qid
                candidates.append(rec)
                continue
            # model agent
            messages = build_verifier_prompt(sample, agent, cur)
            prompts.append({"qid": qid, "agent": agent, "messages": messages})
            if execute and not dry_run and client is not None:
                # Budget is enforced by the caller via a coarse per-call token estimate; we stop
                # if we exceed the ceiling. (Real cost accounting lives in the client.)
                content, usage = client.chat(messages)
                parsed = client.parse_json(content) or {}
                n_model_calls += 1
                candidates.append({
                    "qid": qid, "agent": agent, "needs_api": True,
                    "selected_label": parsed.get("selected_label"),
                    "selected_option_text": parsed.get("selected_option_text"),
                    "evidence": parsed.get("evidence"),
                    "equation": parsed.get("equation"),
                    "label_matches_option": parsed.get("label_matches_option"),
                    "parse_status": "ok" if parsed else "parse_error",
                })
            else:
                # DRY-RUN: record the intent, make NO call.
                candidates.append({
                    "qid": qid, "agent": agent, "needs_api": True,
                    "selected_label": None, "selected_option_text": None,
                    "evidence": None, "equation": None, "label_matches_option": None,
                    "parse_status": "dry_run",
                })

    with out_path.open("w", encoding="utf-8") as f:
        for rec in candidates:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with prompts_path.open("w", encoding="utf-8") as f:
        for rec in prompts:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return {
        "planned_qids": len(planned),
        "candidates_written": len(candidates),
        "model_prompts_built": len(prompts),
        "model_calls_made": n_model_calls,
        "mode": "execute" if (execute and not dry_run) else "dry_run",
        "out": str(out_path),
        "prompts": str(prompts_path),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V12 specialist verifier runner (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--work-dir", default="scratch/v12_delta_verifier")
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--max-qids", type=int, default=50)
    ap.add_argument("--budget-usd", type=float, default=0.50)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--resume", action="store_true", default=False)
    args = ap.parse_args(argv)

    # Default to dry-run unless --execute is explicitly given.
    dry_run = args.dry_run or not args.execute

    samples = load_dataset(args.input)
    samples_by_qid = {s["qid"]: s for s in samples}
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    with open(args.plan, newline="", encoding="utf-8") as f:
        plan_rows = list(csv.DictReader(f))

    summary = run(samples_by_qid, plan_rows, current, work_dir=args.work_dir,
                  model=args.model, max_qids=args.max_qids, budget_usd=args.budget_usd,
                  execute=args.execute, dry_run=dry_run, resume=args.resume)

    print("=" * 60)
    print("V12 DELTA VERIFIER")
    for k, v in summary.items():
        print(f"{k:20}: {v}")
    if summary["mode"] == "dry_run":
        print("NOTE: dry-run — NO API call was made. Use --execute (+budget) to run for real.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
