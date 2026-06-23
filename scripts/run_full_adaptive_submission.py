#!/usr/bin/env python3
"""One-command full adaptive submission runner (Phase 2L.29B).

Collapses the two-step workflow (adaptive candidate generation → policy variant build)
into a single production command. DRY-RUN BY DEFAULT (`--dry-run`/`--execute` mutually
exclusive). On `--execute` it (1) runs the full adaptive selective API into the work-dir,
(2) builds the real submission candidate under the chosen policy, (3) writes the final CSV
to outputs/ and all summaries/diffs under the work-dir. It reuses the existing adaptive
runner and variant builder verbatim — no duplicated ranking/solver logic. Enforces the
model policy, refuses protected output names, requires an explicit acknowledgement, and
validates the output format. No qid hardcoding, no ground truth.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.adaptive_proposal_common import guard_output, load_pred, load_samples  # noqa: E402
from src.labels import labels_for  # noqa: E402
from src.model_policy import assert_allowed_llm_model  # noqa: E402

_PROTECTED_NAMES = {"pred.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv"}
_CANDIDATES_BASENAME = "adaptive_api_candidates.jsonl"   # written by the adaptive runner (prefix 'adaptive')
_DEFAULT_COST_PER_CALL_USD = 0.002   # matches run_adaptive_selective_api default; logging-only fallback


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _require_outputs(path):
    p = str(path).replace("\\", "/")
    if "/outputs/" not in p and not p.startswith("outputs/"):
        raise SystemExit(f"REFUSING: --output must be under outputs/ (got {path})")
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite a protected/locked file: {Path(path).name}")
    guard_output(path)


def _guard_scratch(path, label):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: {label} must be under scratch/ (got {path})")


def _validate_output(output, samples):
    pred = load_pred(output)
    if set(pred) != set(samples):
        raise SystemExit("REFUSING: output qid set != dataset (row-count mismatch)")
    for qid, ans in pred.items():
        if ans not in labels_for(len(samples[qid].get("choices", []) or [])):
            raise SystemExit(f"REFUSING: invalid label {ans} for {qid}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="One-command full adaptive submission runner")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="outputs/pred_v10_full_production_user_run.csv")
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--work-dir", default="scratch/full_adaptive_v11_final")
    ap.add_argument("--output", required=True)
    ap.add_argument("--mode", default="cheap", choices=["cheap", "balanced", "rich"])
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--max-qids", type=int, default=463)
    ap.add_argument("--policy", default="conservative", choices=["conservative", "balanced", "aggressive"])
    ap.add_argument("--max-total-overrides", type=int, default=60)
    ap.add_argument("--max-model-only-overrides", type=int, default=0)
    ap.add_argument("--min-coverage", type=float, default=0.80)
    ap.add_argument("--resume", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--i-understand-this-writes-outputs", action="store_true", default=False)
    args = ap.parse_args(argv)

    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute are mutually exclusive")
    assert_allowed_llm_model(args.model)         # hard model-policy guard before anything
    _guard_scratch(args.work_dir, "--work-dir")
    _require_outputs(args.output)                # path/protected-name guard (both modes)

    adaptive = _load_script("run_adaptive_selective_api.py")
    variant = _load_script("build_submission_variant.py")
    candidates = str(Path(args.work_dir) / _CANDIDATES_BASENAME)

    common = ["--input", args.input, "--base-pred", args.base_pred, "--plan", args.plan,
              "--output-dir", args.work_dir, "--mode", args.mode, "--model", args.model,
              "--max-qids", str(args.max_qids)]
    if args.v10_log:
        common += ["--v10-log", args.v10_log]
    if args.budget_usd is not None:
        common += ["--budget-usd", str(args.budget_usd)]

    if not args.execute:
        print("=" * 64)
        print("FULL ADAPTIVE SUBMISSION — DRY-RUN (no API, no outputs)")
        print("=" * 64)
        print(f"step 1/2 adaptive generation -> {candidates}")
        adaptive.main(common + ["--dry-run"])    # adaptive runner prints its own estimate
        print(f"step 2/2 variant build (policy={args.policy}) -> {args.output}")
        print(f"  caps: total<= {args.max_total_overrides}, model_only<= "
              f"{args.max_model_only_overrides}, min_coverage>= {args.min_coverage}")
        print("Pass --execute --i-understand-this-writes-outputs to run for real.")
        print("=" * 64)
        return 0

    if not args.i_understand_this_writes_outputs:
        raise SystemExit("REFUSING: pass --i-understand-this-writes-outputs to write a real submission.")

    # Timing instrumentation (pure logging — does not affect ranking/selection/policy).
    run_start_perf = time.perf_counter()
    run_start_wall = datetime.now(timezone.utc).isoformat()

    # STEP 1 — full adaptive candidate generation into work-dir.
    print(f"[1/2] adaptive generation (mode={args.mode}) -> {args.work_dir}")
    gen_args = common + ["--execute"] + (["--resume"] if args.resume else [])
    gen_start = time.perf_counter()
    rc = adaptive.main(gen_args)
    gen_elapsed = time.perf_counter() - gen_start
    if rc != 0:
        raise SystemExit(f"adaptive generation failed (rc={rc})")
    if not Path(candidates).exists():
        raise SystemExit(f"expected candidates not found: {candidates}")

    # STEP 2 — build the real submission candidate under the chosen policy.
    review_dir = str(Path(args.work_dir) / "variant_review")
    print(f"[2/2] variant build (policy={args.policy}) -> {args.output}")
    build_start = time.perf_counter()
    rc = variant.main([
        "--input", args.input, "--base-pred", args.base_pred, "--api-candidates", candidates,
        "--output", args.output, "--review-dir", review_dir, "--plan", args.plan,
        "--policy", args.policy, "--max-total-overrides", str(args.max_total_overrides),
        "--max-model-only-overrides", str(args.max_model_only_overrides),
        "--min-coverage", str(args.min_coverage), "--i-understand-this-writes-outputs"])
    build_elapsed = time.perf_counter() - build_start
    if rc != 0:
        raise SystemExit(f"variant build failed (rc={rc})")

    # Final output validation.
    samples = {s.get("qid"): s for s in load_samples(args.input)}
    _validate_output(args.output, samples)

    total_elapsed = time.perf_counter() - run_start_perf
    run_end_wall = datetime.now(timezone.utc).isoformat()
    # Pull through the adaptive generation stats if available (calls / cost / judge).
    gen_summary = {}
    gsum_path = Path(args.work_dir) / "adaptive_run_summary.json"
    if gsum_path.exists():
        try:
            gen_summary = json.loads(gsum_path.read_text())
        except Exception:
            gen_summary = {}
    summary = {
        "submission_file": str(args.output),
        "work_dir": str(args.work_dir),
        "candidates_file": candidates,
        "review_dir": review_dir,
        "mode": args.mode, "policy": args.policy, "model": args.model,
        "start_time": run_start_wall, "end_time": run_end_wall,
        "elapsed_seconds": round(total_elapsed, 3),
        "adaptive_generation_elapsed_seconds": round(gen_elapsed, 3),
        "variant_build_elapsed_seconds": round(build_elapsed, 3),
        "total_api_calls": gen_summary.get("calls_made"),
        "judge_ran": gen_summary.get("judge_ran"),
        "scheduled": gen_summary.get("scheduled"),
        "cost_per_call_usd": gen_summary.get("cost_per_call_usd") or _DEFAULT_COST_PER_CALL_USD,
        "estimated_cost_usd": (
            round(gen_summary["calls_made"]
                  * (gen_summary.get("cost_per_call_usd") or _DEFAULT_COST_PER_CALL_USD), 4)
            if gen_summary.get("calls_made") is not None else None),
    }
    sum_json = Path(args.work_dir) / "full_adaptive_submission_summary.json"
    sum_md = Path(args.work_dir) / "full_adaptive_submission_summary.md"
    sum_json.write_text(json.dumps(summary, indent=2))
    sum_md.write_text(
        f"# Full Adaptive Submission Summary\n\n"
        f"- submission file: `{summary['submission_file']}`\n"
        f"- mode/policy/model: {args.mode} / {args.policy} / {args.model}\n"
        f"- start: {summary['start_time']}\n- end: {summary['end_time']}\n"
        f"- **elapsed: {summary['elapsed_seconds']}s** "
        f"(generation {summary['adaptive_generation_elapsed_seconds']}s, "
        f"build {summary['variant_build_elapsed_seconds']}s)\n"
        f"- total API calls: {summary['total_api_calls']}\n"
        f"- estimated cost USD: {summary['estimated_cost_usd']}\n"
        f"- judge ran: {summary['judge_ran']}   scheduled: {summary['scheduled']}\n")

    print("=" * 64)
    print("FULL ADAPTIVE SUBMISSION — DONE")
    print("=" * 64)
    print(f"submission file : {args.output}")
    print(f"review/diffs    : {review_dir}")
    print(f"candidates      : {candidates}")
    print(f"elapsed         : {summary['elapsed_seconds']}s "
          f"(generation {summary['adaptive_generation_elapsed_seconds']}s, "
          f"build {summary['variant_build_elapsed_seconds']}s)")
    print(f"api calls       : {summary['total_api_calls']}   "
          f"est. cost USD: {summary['estimated_cost_usd']}")
    print(f"run summary     : {sum_json}")
    print("v10 baseline left untouched. Review the diff before submitting.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
