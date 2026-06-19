#!/usr/bin/env python3
"""Summarise runtime from a run debug JSONL log.

Reads the per-sample records written by ``RunLogger`` and prints total time,
average, and percentiles (p50/p90/p95), with a per-question-shape breakdown.

Usage:
    python scripts/benchmark_runtime.py --log-path outputs/run_debug.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """Nearest-rank percentile of an already-sorted list."""
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round(pct / 100 * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def load_records(log_path: Path) -> tuple[list[dict], dict | None]:
    """Return (per-sample records, summary record or None)."""
    records, summary = [], None
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("_summary"):
                summary = obj
            else:
                records.append(obj)
    return records, summary


def _report_times(label: str, times: list[float]) -> None:
    if not times:
        print(f"  {label}: (no samples)")
        return
    times_sorted = sorted(times)
    total = sum(times)
    print(f"  {label}: n={len(times)} total={total:.2f}s "
          f"avg={total / len(times):.4f}s "
          f"p50={_percentile(times_sorted, 50):.4f}s "
          f"p90={_percentile(times_sorted, 90):.4f}s "
          f"p95={_percentile(times_sorted, 95):.4f}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark runtime from a debug log")
    parser.add_argument("--log-path", default="outputs/run_debug.jsonl")
    args = parser.parse_args(argv)

    log_path = Path(args.log_path)
    if not log_path.exists():
        print(f"no debug log found at {log_path}; run an LLM solver with --log-path first")
        return 1

    records, summary = load_records(log_path)
    if not records:
        print(f"{log_path} has no per-sample records")
        return 1

    print(f"runtime benchmark from {log_path}")
    print("=" * 60)
    all_times = [r.get("elapsed_s", 0.0) for r in records]
    _report_times("overall", all_times)

    # Breakdown by question shape, if shapes were logged.
    by_shape: dict[str, list[float]] = defaultdict(list)
    for r in records:
        by_shape[r.get("shape") or "unknown"].append(r.get("elapsed_s", 0.0))
    if len(by_shape) > 1 or "unknown" not in by_shape:
        print("by question shape:")
        for shape, times in sorted(by_shape.items()):
            _report_times(shape, times)

    # Fallbacks, if any.
    fallbacks = [r for r in records if r.get("fallback_reason")]
    if fallbacks:
        print(f"fallbacks: {len(fallbacks)} / {len(records)} samples")

    if summary:
        print("=" * 60)
        print(f"solver={summary.get('solver')} "
              f"total={summary.get('total_seconds')}s "
              f"avg/sample={summary.get('avg_seconds_per_sample')}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
