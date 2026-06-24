#!/usr/bin/env python3
"""Pilot runner wrapper (Phase 2L.28A): run the adaptive selective API over a pilot set.

Thin, DRY-RUN-BY-DEFAULT wrapper over ``run_adaptive_selective_api``. It treats the
``pilot_qids.csv`` (qid + recommended_layer columns) as the plan and reuses the exact
adaptive logic, but writes pilot-prefixed artifacts (``pilot_api_candidates.jsonl/.csv``,
``pilot_run_summary.json/.md``). Refuses non-scratch output; ``--dry-run``/``--execute``
mutually exclusive; model policy enforced by the delegate. No output/ writes ever.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _adaptive():
    spec = importlib.util.spec_from_file_location(
        "run_adaptive_selective_api", _ROOT / "scripts" / "run_adaptive_selective_api.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output dir must be under scratch/ (got {path})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Adaptive pilot runner (dry-run default)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", required=True)
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--pilot-qids", required=True)
    ap.add_argument("--output-dir", default="scratch/adaptive_pilot_2l28")
    ap.add_argument("--mode", default="cheap", choices=["cheap", "balanced", "rich"])
    ap.add_argument("--model", default="qwen/qwen3.5-9b-20260310")
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--resume", action="store_true", default=False)
    ap.add_argument("--timestamp", default="")
    args = ap.parse_args(argv)

    if args.dry_run and args.execute:
        raise SystemExit("--dry-run and --execute are mutually exclusive")
    _guard_scratch(args.output_dir)
    if not Path(args.pilot_qids).exists():
        raise SystemExit(f"pilot qids not found: {args.pilot_qids}")
    n = sum(1 for _ in csv.DictReader(open(args.pilot_qids)))

    print(f"[pilot] {n} qids from {args.pilot_qids} (mode={args.mode}); delegating to adaptive runner")
    delegate = ["--input", args.input, "--base-pred", args.base_pred,
                "--plan", args.pilot_qids, "--output-dir", args.output_dir,
                "--mode", args.mode, "--model", args.model,
                "--max-qids", str(max(n, 1)), "--out-prefix", "pilot",
                "--timestamp", args.timestamp]
    if args.v10_log:
        delegate += ["--v10-log", args.v10_log]
    if args.budget_usd is not None:
        delegate += ["--budget-usd", str(args.budget_usd)]
    if args.resume:
        delegate += ["--resume"]
    delegate += ["--execute"] if args.execute else ["--dry-run"] if args.dry_run else []
    return _adaptive().main(delegate)


if __name__ == "__main__":
    raise SystemExit(main())
