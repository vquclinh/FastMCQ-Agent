#!/usr/bin/env python3
"""Clean temporary/diagnostic artifacts from output/ (DRY-RUN by default).

Keeps the real run/submission files (an explicit allow-list) and removes only
proposal/candidate/audit/diagnostic artifacts matching known temporary patterns.
NEVER deletes outside ``output/``; NEVER deletes a protected final output; default
is dry-run (requires ``--execute`` to delete). Touches no source/tests/docs/scripts.
"""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path

OUTPUTS = Path("output")

# Final run/submission outputs that must always be kept.
KEEP = {
    "pred.csv", "pred_phase2i0_baseline.csv",
    "pred_phase2k3_model_provider_full.csv", "run_phase2k3_model_provider_full.jsonl",
    "pred_v2_calc_rerank.csv", "run_v2_calc_rerank.jsonl",
    "pred_v6_qwen_rerank_calc_verifier.csv", "run_v6_qwen_rerank_calc_verifier.jsonl",
    "pred_v6b_qwen_rerank_calc_verifier_fast.csv", "run_v6b_qwen_rerank_calc_verifier_fast.jsonl",
    "pred_v7_programmatic_assist_from_v6b.csv", "run_v7_programmatic_assist_from_v6b.jsonl",
    "pred_v8_clean_generalized_from_v7.csv", "run_v8_clean_generalized_from_v7.jsonl",
    "pred_v8_clean_generalized_diff.csv",
    # optional keep (manual mini fix, kept for provenance):
    "pred_v8_mini_safe_from_v7.csv", "pred_v8_mini_safe_diff.csv",
    ".gitkeep",
}

# Temporary/diagnostic patterns eligible for removal.
TEMP_PATTERNS = [
    "*_proposals_*.csv", "*_proposals_*.jsonl",
    "*_candidates.csv", "*_audit.csv", "*_audit.jsonl",
    "*_sample_dryrun.*", "*_dryrun.csv", "*_dryrun.jsonl",
    "first100_p0p1_review_pack.*", "first100_consensus_risk_audit.csv",
    "programmatic_assist_diff.csv",
    "neural_vs_lexical_*.jsonl",
    "calculation_solver_*_audit.csv",
    "*_speedfix_smoke.*",
]


def _classify():
    keep, delete = [], []
    if not OUTPUTS.is_dir():
        return keep, delete
    for p in sorted(OUTPUTS.iterdir()):
        if not p.is_file():
            continue
        name = p.name
        if name in KEEP:
            keep.append(name)
        elif any(fnmatch.fnmatch(name, pat) for pat in TEMP_PATTERNS):
            delete.append(name)
        else:
            keep.append(name)   # unknown -> KEEP (never delete by default)
    return keep, delete


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Clean temporary output/ artifacts (dry-run default)")
    ap.add_argument("--execute", action="store_true", default=False,
                    help="actually delete (default = dry-run, deletes nothing)")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="explicit dry-run (default behavior; deletes nothing)")
    args = ap.parse_args(argv)
    dry_run = not args.execute   # dry-run unless --execute is given

    keep, delete = _classify()
    print("=" * 64)
    print("OUTPUTS CLEANUP " + ("(DRY-RUN; deletes nothing)" if dry_run else "(EXECUTE)"))
    print("=" * 64)
    print(f"KEEP ({len(keep)}):")
    for n in keep:
        print(f"  keep   {n}")
    print(f"DELETE ({len(delete)}):")
    for n in delete:
        print(f"  delete {n}")

    removed = 0
    if not dry_run:
        for n in delete:
            target = OUTPUTS / n
            # Defense-in-depth: never touch a protected name or anything outside output/.
            if n in KEEP:
                continue
            rp = target.resolve()
            if OUTPUTS.resolve() not in rp.parents:
                print(f"  SKIP (outside output/): {n}")
                continue
            try:
                target.unlink()
                removed += 1
            except OSError as exc:
                print(f"  ERROR deleting {n}: {exc}")
    print("-" * 64)
    if dry_run:
        print(f"Dry-run: would delete {len(delete)} file(s); nothing removed. Use --execute.")
    else:
        print(f"Deleted {removed} file(s). Kept {len(keep)}.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
