#!/usr/bin/env python3
"""Independent full v11 submission runner (Phase 2L.30B).

A TRUE independent v11 answering system — NOT a v10 overlay. It answers every question
from v11's own candidates (deterministic tools + evidence packs + allowed-model API agents
+ a direct fallback) and selects one final answer per qid via the independent selector. It
has NO ``--base-pred`` and never reads v10 for generation; ``--compare-pred`` is read only
AFTER all decisions are finalized, for a report. DRY-RUN BY DEFAULT. Writes the final CSV
under output/ and logs/summaries under the work-dir. Enforces the model policy, refuses
protected output names, requires explicit acknowledgement, and validates the output.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.layers.adaptive_proposal_common import guard_output, load_pred, load_samples  # noqa: E402
from src.layers.adaptive_routing import route_to_branch  # noqa: E402
from src.base.answer_factory import build_candidate_pool  # noqa: E402
from src.solvers.calculation_first_planner import (build_calculation_tool_context,  # noqa: E402
                                           format_tool_context_for_prompt)
from src.selector.candidate_answer import AnswerCandidate  # noqa: E402
from src.selector.independent_answer_selector import select_independent_answer  # noqa: E402
from src.utils.labels import labels_for  # noqa: E402
from src.api.model_policy import assert_allowed_llm_model  # noqa: E402
from src.layers.question_profiler import profile_question  # noqa: E402
from src.layers.question_router import route_question  # noqa: E402

_PROTECTED_NAMES = {"pred.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv"}
_DEFAULT_COST_PER_CALL_USD = 0.002


def _require_outputs(path):
    p = str(path).replace("\\", "/")
    if "/output/" not in p and not p.startswith("output/"):
        raise SystemExit(f"REFUSING: --output must be under output/ (got {path})")
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite a protected/locked file: {Path(path).name}")
    guard_output(path)


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: --work-dir must be under scratch/ (got {path})")


def _sample_labels(sample):
    return labels_for(len(sample.get("choices", []) or []))


def _is_valid_label(answer, labels):
    return answer in labels and answer is not None and str(answer).strip() not in ("", "None")


def _finalize_decision(dec, sample, *, direct_fallback_fn=None, pool=None):
    """Guarantee a valid-label decision before write. Order: keep valid -> direct allowed-
    model fallback -> best valid-label candidate in the pool -> first available option label
    from THIS sample's choices. NEVER uses v10 and NEVER leaves ``final_answer`` None/invalid.
    Raises a clear error only if the sample itself cannot yield any label (preflight defense)."""
    labels = _sample_labels(sample)
    if not labels:
        raise SystemExit(f"REFUSING: qid {dec.get('qid')} has no usable choice labels "
                         "(empty/invalid choices) — preflight should have caught this.")
    if _is_valid_label(dec.get("final_answer"), labels) and not dec.get("needs_direct_fallback"):
        return dec
    orig = dec.get("note") or dec.get("final_source")
    # 2) direct allowed-model fallback
    fb = direct_fallback_fn() if direct_fallback_fn else None
    ans = fb.get("answer") if fb else None
    if _is_valid_label(ans, labels):
        dec.update(final_answer=ans, final_source="direct_fallback_repair", risk="high",
                   fallback_used=True, needs_direct_fallback=False,
                   note=f"repaired via direct fallback (was: {orig})")
        return dec
    # 4) best valid-label candidate already in the pool
    if pool is not None:
        valid = [c for c in pool.candidates if _is_valid_label(c.answer, labels)]
        if valid:
            w = max(valid, key=lambda c: c.confidence)
            dec.update(final_answer=w.answer, final_source="pool_valid_label_repair", risk="high",
                       fallback_used=True, needs_direct_fallback=False,
                       note=f"repaired from pool candidate {w.source} (was: {orig})")
            return dec
    # 5) last resort: first available option label FROM THIS SAMPLE'S choices (not a global "A")
    dec.update(final_answer=labels[0], final_source="last_resort_valid_choice", risk="high",
               fallback_used=True, needs_direct_fallback=False,
               note=f"last-resort valid choice {labels[0]} (was: {orig})")
    return dec


def _collect_problems(decisions, samples, *, full_dataset):
    """Return a dict of integrity problems over decision rows. No raising."""
    labels_by = {q: set(_sample_labels(s)) for q, s in samples.items()}
    seen = Counter()
    invalid, none_labels = [], []
    for d in decisions:
        q = d.get("qid"); seen[q] += 1
        a = d.get("final_answer")
        if a is None or str(a).strip() in ("", "None"):
            none_labels.append(q)
        elif q in labels_by and a not in labels_by[q]:
            invalid.append(q)
    duplicates = sorted(q for q, c in seen.items() if c > 1)
    missing = sorted(q for q in samples if q not in seen) if full_dataset else []
    return {"missing": missing, "duplicates": duplicates, "invalid": sorted(set(invalid)),
            "none_labels": sorted(set(none_labels))}


def _validate_decisions(decisions, samples, *, full_dataset):
    """Validate labels and (for a full run) the qid set. Raises SystemExit on any problem."""
    p = _collect_problems(decisions, samples, full_dataset=full_dataset)
    if p["none_labels"] or p["invalid"]:
        bad = (p["none_labels"] + p["invalid"])[0]
        ans = next((d.get("final_answer") for d in decisions if d.get("qid") == bad), None)
        raise SystemExit(f"REFUSING: invalid label {ans} for {bad}")
    if p["duplicates"]:
        raise SystemExit(f"REFUSING: duplicate decision rows for qids {p['duplicates'][:5]}")
    if full_dataset and (p["missing"] or {d["qid"] for d in decisions} != set(samples)):
        raise SystemExit("REFUSING: decision qid set != dataset (row-count mismatch)")
    return True


def _assert_ready_for_output(decisions, samples, outdir, *, full_dataset):
    """Pre-output guard: write a failure report and raise if anything is wrong; else True."""
    p = _collect_problems(decisions, samples, full_dataset=full_dataset)
    if any(p.values()):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "v11_independent_pre_output_failure_report.json").write_text(
            json.dumps(p, indent=2))
        (Path(outdir) / "v11_independent_pre_output_failure_report.md").write_text(
            "# v11 pre-output validation FAILED (no CSV written)\n\n"
            + "\n".join(f"- {k}: {len(v)} {v[:10]}" for k, v in p.items()))
        raise SystemExit("REFUSING: pre-output validation failed "
                         f"(missing={len(p['missing'])}, dup={len(p['duplicates'])}, "
                         f"invalid={len(p['invalid'])}, none={len(p['none_labels'])}); "
                         "see v11_independent_pre_output_failure_report.md")
    return True


def _preflight(samples, *, full_dataset=True):
    """Validate the dataset itself BEFORE a run: every sample has a qid and usable choices.
    Raises a clear SystemExit early (not at output time). Returns the dataset label map."""
    if not samples:
        raise SystemExit("REFUSING: empty dataset")
    no_qid = [i for i, s in enumerate(samples.values()) if not s.get("qid")]
    if no_qid:
        raise SystemExit(f"REFUSING: {len(no_qid)} sample(s) missing 'qid'")
    no_choices = [q for q, s in samples.items() if not _sample_labels(s)]
    if no_choices:
        raise SystemExit(f"REFUSING: {len(no_choices)} sample(s) have no usable choice labels "
                         f"(e.g. {no_choices[:5]}); cannot assign a valid answer — aborting "
                         "before the run.")
    return {q: _sample_labels(s) for q, s in samples.items()}


def _scan_resume_decisions(workdir, samples):
    """Scan an existing decisions CSV: classify qids as completed-valid vs invalid/duplicate.
    Returns (completed_valid_rows_by_qid, summary). Invalid rows are NEVER treated as done."""
    path = Path(workdir) / "v11_independent_decisions.csv"
    completed, summary = {}, {"prior_rows": 0, "valid": 0, "invalid": 0, "duplicate": 0,
                             "none_or_empty": 0}
    if not path.exists():
        return completed, summary
    seen = Counter()
    for r in csv.DictReader(open(path)):
        summary["prior_rows"] += 1
        q = r.get("qid")
        seen[q] += 1
        labels = set(_sample_labels(samples.get(q, {})))
        a = r.get("final_answer")
        bad_flag = str(r.get("needs_direct_fallback", "")).lower() == "true"
        if a is None or str(a).strip() in ("", "None"):
            summary["none_or_empty"] += 1
            continue
        if a not in labels or bad_flag:
            summary["invalid"] += 1
            continue
        # valid; keep the LATEST valid row per qid
        if q in completed:
            summary["duplicate"] += 1
        completed[q] = r
        summary["valid"] += 1
    summary["completed_unique"] = len(completed)
    return completed, summary


def _route_of(sample):
    try:
        return route_to_branch(route_question(profile_question(sample)).route)
    except Exception:
        return "default"


def _agents_temps(mode, route):
    """v11 independent agent plan per (mode, route). Calculation is tool-first."""
    if route == "calculation":
        if mode == "cheap":
            return ["calculation_solver"], [0.0]          # + option_elimination fallback
        if mode == "balanced":
            return ["calculation_solver", "challenger", "option_elimination"], [0.0]
        return ["calculation_solver", "challenger", "option_elimination", "tool_hint"], [0.0, 0.2]
    if mode == "cheap":
        return ["route_specialist", "option_elimination"], [0.0]
    if mode == "balanced":
        return ["route_specialist", "challenger", "option_elimination"], [0.0]
    return ["route_specialist", "challenger", "option_elimination", "tool_hint"], [0.0, 0.2]


def _deterministic_low_risk(pool):
    from src.selector.answer_ranker import _is_deterministic
    det = [c for c in pool.candidates if _is_deterministic(c)]
    return len(det) >= 1 and len({c.answer for c in det}) == 1


def _estimate(samples, qids, mode):
    """Per-qid API-call upper bound (0 when a deterministic tool already answers)."""
    total = 0
    det_qids = 0
    for qid in qids:
        sample = samples[qid]
        pool = build_candidate_pool(sample, None, None)   # base_answer=None -> NO v10 candidate
        if _deterministic_low_risk(pool):
            det_qids += 1
            continue
        route = _route_of(sample)
        ags, temps = _agents_temps(mode, route)
        fallback = 1 if (route == "calculation" and mode == "cheap") else 0
        total += len(ags) * len(temps) + fallback + 1     # +fallback +1 possible judge
    return total, det_qids


# --------------------------------------------------------------------------- #
# Execute-path helpers (human-run only; not exercised by the test suite).
# --------------------------------------------------------------------------- #

def _load_agents_module():   # pragma: no cover
    from src.api import api_candidate_agents as agents
    return agents


def _generate_api_candidates(client, agents, sample, route, mode, jf, qid):  # pragma: no cover
    """Call the allowed-model API agents for one qid; append raw records; return valid ones."""
    labels = labels_for(len(sample.get("choices", []) or []))
    ags, temps = _agents_temps(mode, route)
    calc_ctx = (format_tool_context_for_prompt(build_calculation_tool_context(sample))
                if route == "calculation" else None)
    valid, parse_counts = [], Counter()
    for temp in temps:
        for agent in ags:
            if agent == "calculation_solver":
                content, usage = client.chat(agents.build_calculation_solver(sample, calc_ctx),
                                             temperature=temp, max_tokens=384)
                parsed = agents.parse_calculation_candidate(content, sample)
            elif agent == "route_specialist":
                content, usage = client.chat(agents.build_route_specialist(sample, route, None),
                                             temperature=temp)
                parsed = agents.parse_candidate(content, sample)
            elif agent == "challenger":
                # challenger needs a "current" answer; use the best valid candidate so far, NOT v10.
                cur = valid[0]["answer"] if valid else (labels[0] if labels else None)
                content, usage = client.chat(agents.build_challenger(sample, cur), temperature=temp)
                parsed = agents.parse_candidate(content, sample)
            elif agent == "option_elimination":
                content, usage = client.chat(agents.build_option_elimination(sample), temperature=temp)
                parsed = agents.parse_candidate(content, sample)
            else:
                content, usage = client.chat(agents.build_tool_hint(sample, None, None), temperature=temp)
                parsed = agents.parse_candidate(content, sample)
            parse_counts[parsed.get("parse_status")] += 1
            rec = {"qid": qid, "agent": agent, "temperature": temp, **parsed, "route": route,
                   "total_tokens": usage.get("total_tokens")}
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n"); jf.flush()
            if parsed.get("parse_status") == "ok" and parsed.get("answer"):
                valid.append(rec)
    # calculation cheap fallback: option_elimination once if no valid calc candidate.
    if route == "calculation" and mode == "cheap" and not valid:
        content, usage = client.chat(agents.build_option_elimination(sample), temperature=0.0)
        parsed = agents.parse_candidate(content, sample)
        parse_counts[parsed.get("parse_status")] += 1
        rec = {"qid": qid, "agent": "option_elimination", "temperature": 0.0, **parsed,
               "route": route, "total_tokens": usage.get("total_tokens")}
        jf.write(json.dumps(rec, ensure_ascii=False) + "\n"); jf.flush()
        if parsed.get("parse_status") == "ok" and parsed.get("answer"):
            valid.append(rec)
    return valid, parse_counts


def _maybe_judge(client, agents, sample, valid, jf, qid):  # pragma: no cover
    answers = {c["answer"] for c in valid}
    if len(answers) < 2:
        return None
    jmsgs = agents.build_pairwise_judge(sample, None, [
        {"source": f"api:{c['agent']}", "answer": c["answer"], "risk_level": c.get("risk"),
         "evidence_text": c.get("evidence", "")} for c in valid])
    content, usage = client.chat(jmsgs, temperature=0.0)
    jp = agents.parse_judge(content, sample)
    jf.write(json.dumps({"qid": qid, "agent": "pairwise_judge", **jp,
                         "total_tokens": usage.get("total_tokens")}, ensure_ascii=False) + "\n")
    jf.flush()
    return {"answer": jp.get("winner_answer"), "parse_status": jp.get("parse_status")}


def _direct_fallback(client, agents, sample):  # pragma: no cover
    """One direct allowed-model answer; high-risk; never uses v10."""
    content, usage = client.chat(agents.build_route_specialist(sample, "default", None), temperature=0.0)
    parsed = agents.parse_candidate(content, sample)
    return {"answer": parsed.get("answer"), "parse_status": parsed.get("parse_status")}


def _compare_to_v10(decisions, compare_path, samples, outdir):
    """Report-only diff vs a comparison prediction. Read AFTER decisions are finalized."""
    other = load_pred(compare_path)
    changed = [d for d in decisions if other.get(d["qid"]) and d["final_answer"] != other.get(d["qid"])]
    by_route, by_source = Counter(), Counter()
    for d in changed:
        by_route[d["route"]] += 1
        by_source[d["final_source"]] += 1
    label_dist = Counter(d["final_answer"] for d in decisions)
    with open(outdir / "compare_to_v10.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "v11", "compare", "route", "final_source"])
        w.writeheader()
        for d in changed:
            w.writerow({"qid": d["qid"], "v11": d["final_answer"], "compare": other.get(d["qid"]),
                        "route": d["route"], "final_source": d["final_source"]})
    (outdir / "compare_to_v10.md").write_text(
        f"# v11 vs `{Path(compare_path).name}` (report-only; did NOT affect selection)\n\n"
        f"- changed vs comparison: **{len(changed)}** / {len(decisions)}\n"
        f"- changed by route: {dict(by_route)}\n- changed by final_source: {dict(by_source)}\n"
        f"- v11 label distribution: {dict(label_dist)}\n")
    return len(changed)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Independent full v11 submission runner (no v10 base)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work-dir", default="scratch/full_v11_independent")
    ap.add_argument("--output", required=True)
    ap.add_argument("--mode", default="cheap", choices=["cheap", "balanced", "rich"])
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--cost-per-call-usd", type=float, default=_DEFAULT_COST_PER_CALL_USD)
    ap.add_argument("--max-qids", type=int, default=463)
    ap.add_argument("--resume", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--i-understand-this-writes-outputs", action="store_true", default=False)
    ap.add_argument("--compare-pred", default=None, help="report-only; never affects answers")
    args = ap.parse_args(argv)

    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute are mutually exclusive")
    assert_allowed_llm_model(args.model)
    _guard_scratch(args.work_dir)
    _require_outputs(args.output)

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    qids = list(samples)[: args.max_qids] if args.max_qids else list(samples)

    if not args.execute:
        upper, det_qids = _estimate(samples, qids, args.mode)
        est_cost = upper * args.cost_per_call_usd
        print("=" * 64)
        print(f"INDEPENDENT V11 — DRY-RUN ({args.mode}; no API, no outputs)")
        print("=" * 64)
        print(f"model            : {args.model}")
        print(f"qids             : {len(qids)} (max {args.max_qids})")
        print(f"deterministic now: {det_qids} (0 API calls)   need API: {len(qids) - det_qids}")
        print(f"upper-bound calls: {upper}   est. cost USD: {est_cost:.2f}"
              + (f"   budget={args.budget_usd}" if args.budget_usd else ""))
        if args.compare_pred:
            print(f"compare-pred     : {args.compare_pred} (REPORT-ONLY; not used for answers)")
        print("NO --base-pred: v11 answers every qid independently. Pass --execute to run.")
        print("=" * 64)
        return 0

    if not args.i_understand_this_writes_outputs:
        raise SystemExit("REFUSING: pass --i-understand-this-writes-outputs to write a real submission.")

    # EXECUTE (human-initiated).  # pragma: no cover
    return _execute(args, samples, qids)  # pragma: no cover


def _execute(args, samples, qids):  # pragma: no cover
    outdir = Path(args.work_dir); outdir.mkdir(parents=True, exist_ok=True)
    cand_path = outdir / "v11_independent_candidates.jsonl"

    # PREFLIGHT — fail early (before any API spend) if the dataset can't yield valid labels.
    _preflight(samples, full_dataset=(len(qids) == len(samples)))

    # RESUME — only qids with a VALID final label count as completed; invalid/None/flagged
    # rows are regenerated. Duplicates resolved by keeping the latest valid row.
    completed = {}
    if args.resume:
        completed, resume_summary = _scan_resume_decisions(outdir, samples)
        resume_summary["resume_requested"] = True
        resume_summary["to_process"] = len([q for q in qids if q not in completed])
        (outdir / "resume_state_summary.json").write_text(json.dumps(resume_summary, indent=2))
        (outdir / "resume_state_summary.md").write_text(
            "# v11 resume state\n\n" + "\n".join(f"- {k}: {v}" for k, v in resume_summary.items())
            + "\n\n_Invalid/None/flagged rows are NOT treated as completed._\n")
        print(f"[resume] completed-valid={len(completed)} to-process={resume_summary['to_process']}")

    from src.api.selective_api_client import SelectiveAPIClient
    client = SelectiveAPIClient(args.model)
    agents = _load_agents_module()

    start_perf = time.perf_counter(); start_wall = datetime.now(timezone.utc).isoformat()
    decisions = []
    src_ct, route_ct = Counter(), Counter()
    parse_fail = placeholder = mismatch = nojson = judge_used_ct = fallback_ct = 0
    det_ct = api_ct = ev_ct = 0

    with open(cand_path, "a", encoding="utf-8") as jf:
        for qid in qids:
            sample = samples[qid]
            if qid in completed:                 # carry forward a prior VALID decision
                row = dict(completed[qid]); row["qid"] = qid
                row.setdefault("final_source", "resumed")
                decisions.append(row)
                src_ct[row.get("final_source", "resumed")] += 1
                continue
            route = _route_of(sample)
            pool = build_candidate_pool(sample, None, {"route": route})   # NO v10
            judge = fallback = None
            parse_counts = Counter()
            need_api = not _deterministic_low_risk(pool)
            if need_api and not (args.budget_usd
                                 and client.total_calls * args.cost_per_call_usd >= args.budget_usd):
                valid, parse_counts = _generate_api_candidates(client, agents, sample, route,
                                                               args.mode, jf, qid)
                for c in valid:
                    pool.add(AnswerCandidate(qid=qid, answer=c["answer"], source=f"api:{c['agent']}",
                                             route=route, confidence=float(c.get("confidence") or 0.5),
                                             risk_level=c.get("risk") or "medium",
                                             rationale=c.get("rationale", ""),
                                             evidence_text=c.get("evidence", "")))
                judge = _maybe_judge(client, agents, sample, valid, jf, qid)
                if not pool.candidates:
                    fallback = _direct_fallback(client, agents, sample)
            placeholder += parse_counts.get("placeholder_evidence", 0)
            mismatch += parse_counts.get("numeric_mismatch", 0)
            nojson += parse_counts.get("no_json", 0)
            parse_fail += sum(v for k, v in parse_counts.items() if k not in ("ok", None))

            final, dec = select_independent_answer(pool, sample, route=route, judge=judge,
                                                   fallback=fallback,
                                                   parse_summary=dict(parse_counts))
            # Fail-safe: never append a None/invalid decision — repair via direct fallback,
            # then pool candidate, then a valid choice label from THIS sample.
            dec = _finalize_decision(
                dec, sample, pool=pool,
                direct_fallback_fn=lambda: _direct_fallback(client, agents, sample))
            dec["qid"] = qid
            decisions.append(dec)
            src_ct[dec["final_source"]] += 1
            route_ct[route] += 1
            if dec["judge_used"]:
                judge_used_ct += 1
            if dec["fallback_used"]:
                fallback_ct += 1
            if dec["final_source"] in ("formula_bank", "concept") or dec["final_source"].startswith("tool:"):
                det_ct += 1
            elif dec["final_source"] in ("consensus", "pairwise_judge") or dec["final_source"].startswith("api:"):
                api_ct += 1
            elif dec["final_source"] == "card":
                ev_ct += 1

    # Write decisions + final CSV.
    dec_fields = ["qid", "final_answer", "final_source", "route", "risk", "evidence_summary",
                  "proof_summary", "candidate_count", "rejected_count", "judge_used",
                  "fallback_used", "parse_status_summary", "note"]
    with open(outdir / "v11_independent_decisions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=dec_fields, extrasaction="ignore")
        w.writeheader()
        for d in decisions:
            row = dict(d)
            psum = d.get("parse_status_summary", {})
            row["parse_status_summary"] = psum if isinstance(psum, str) else json.dumps(psum)
            w.writerow(row)

    full = (len(qids) == len(samples))
    # PRE-OUTPUT WRITE GUARD: never write the CSV unless decisions are fully valid.
    _assert_ready_for_output(decisions, samples, outdir, full_dataset=full)

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader()
        for d in decisions:
            w.writerow({"qid": d["qid"], "answer": d["final_answer"]})

    # POST-WRITE VALIDATION: re-read the CSV and re-validate it on disk.
    reread = load_pred(str(outp))
    post = _collect_problems([{"qid": q, "final_answer": a} for q, a in reread.items()],
                             samples, full_dataset=full)
    final_ok = not any(post.values())
    (outdir / "v11_independent_final_validation.json").write_text(
        json.dumps({"output_file": str(outp), "rows": len(reread), "ok": final_ok, **post}, indent=2))
    (outdir / "v11_independent_final_validation.md").write_text(
        f"# v11 final output validation\n\n- output: `{outp}`\n- rows: {len(reread)}\n"
        f"- ok: **{final_ok}**\n- missing: {len(post['missing'])}  dup: {len(post['duplicates'])}  "
        f"invalid: {len(post['invalid'])}  none: {len(post['none_labels'])}\n")
    if not final_ok:
        raise SystemExit(f"REFUSING: post-write validation failed for {outp}: {post}")

    elapsed = time.perf_counter() - start_perf
    summary = {"total_qids": len(decisions), "output_file": str(outp), "work_dir": str(outdir),
               "start_time": start_wall, "end_time": datetime.now(timezone.utc).isoformat(),
               "elapsed_seconds": round(elapsed, 3), "api_calls": client.total_calls,
               "estimated_cost_usd": round(client.total_calls * args.cost_per_call_usd, 4),
               "route_breakdown": dict(route_ct), "final_source_breakdown": dict(src_ct),
               "deterministic_answers": det_ct, "api_answers": api_ct,
               "evidence_pack_answers": ev_ct, "fallback_direct_answers": fallback_ct,
               "judge_used": judge_used_ct, "parser_failures": parse_fail,
               "placeholder_rejections": placeholder, "numeric_mismatch": mismatch,
               "invalid_or_no_json": nojson}
    (outdir / "v11_independent_summary.json").write_text(json.dumps(summary, indent=2))
    (outdir / "v11_independent_summary.md").write_text(
        f"# Independent v11 Submission Summary\n\n"
        f"- output: `{outp}`\n- total qids: {len(decisions)}\n- elapsed: {summary['elapsed_seconds']}s\n"
        f"- API calls: {client.total_calls}   est. cost USD: {summary['estimated_cost_usd']}\n"
        f"- route breakdown: {dict(route_ct)}\n- final source breakdown: {dict(src_ct)}\n"
        f"- deterministic/api/evidence/fallback: {det_ct}/{api_ct}/{ev_ct}/{fallback_ct}\n"
        f"- judge used: {judge_used_ct}\n- parser failures: {parse_fail} "
        f"(placeholder {placeholder}, mismatch {mismatch}, no-json {nojson})\n")

    changed = None
    if args.compare_pred:                # report-only, AFTER all decisions finalized
        changed = _compare_to_v10(decisions, args.compare_pred, samples, outdir)

    print("=" * 64)
    print("INDEPENDENT V11 SUBMISSION — DONE")
    print("=" * 64)
    print(f"submission : {outp}")
    print(f"qids       : {len(decisions)}   api_calls: {client.total_calls}   elapsed: {summary['elapsed_seconds']}s")
    print(f"sources    : {dict(src_ct)}")
    if changed is not None:
        print(f"changed vs compare-pred (report-only): {changed}")
    print("v10 NOT used for generation. Review before submitting.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
