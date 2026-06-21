#!/usr/bin/env python3
"""Analyze a v6-style run JSONL for runtime bottlenecks (read-only, no network).

Reports route/runtime distribution, slowest qids, parse-quality counters, and
reranker/verifier/calc activity. Uses ONLY the trace log; no ground truth, no
external answer sheet, no qid is used for any decision (qids are printed only to
locate slow samples). Writes nothing.

Usage:
    python scripts/analyze_v6_runtime.py --log outputs/run_v6_qwen_rerank_calc_verifier.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def _load(path):
    rows, summary = [], None
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("_summary") or ("total_seconds" in obj and "qid" not in obj):
            summary = obj
        else:
            rows.append(obj)
    return rows, summary


def _get(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v6 runtime analyzer (read-only)")
    ap.add_argument("--log", required=True)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args(argv)

    rows, summary = _load(args.log)
    n = len(rows)
    print("=" * 70)
    print("V6 RUNTIME ANALYSIS (read-only; trace only; no ground truth)")
    print("=" * 70)
    print(f"log              : {args.log}")
    print(f"sample rows      : {n}")
    print(f"unique qids      : {len({r.get('qid') for r in rows})}")
    if summary:
        print(f"summary total_s  : {summary.get('total_seconds')}")
        print(f"summary avg_s    : {summary.get('avg_seconds_per_sample')}")

    # Route distribution + per-route timing.
    route_ct = Counter(r.get("route") for r in rows)
    route_time = defaultdict(float)
    route_n = Counter()
    for r in rows:
        es = r.get("elapsed_sec")
        if isinstance(es, (int, float)):
            route_time[r.get("route")] += es
            route_n[r.get("route")] += 1
    print("-" * 70)
    print("route distribution & avg elapsed_sec:")
    for route, ct in route_ct.most_common():
        avg = route_time[route] / route_n[route] if route_n[route] else 0.0
        print(f"  {str(route):16s} n={ct:4d}  avg={avg:8.2f}s  total={route_time[route]:9.1f}s")

    # Elapsed buckets.
    es_all = [r.get("elapsed_sec") for r in rows if isinstance(r.get("elapsed_sec"), (int, float))]
    for thr in (20, 60, 100):
        print(f"rows elapsed_sec > {thr:3d} : {sum(1 for e in es_all if e > thr)}")
    if es_all:
        print(f"elapsed_sec sum/mean/max : {sum(es_all):.1f} / {sum(es_all)/len(es_all):.2f} / {max(es_all):.2f}")

    # API calls.
    api = [r.get("api_calls") for r in rows if isinstance(r.get("api_calls"), int)]
    print("-" * 70)
    print(f"total OpenRouter api_calls (sum) : {sum(api)}")
    print(f"rows with api_calls==0 (override): {sum(1 for a in api if a == 0)}")

    # Parse quality.
    def src(r):
        return _get(r, "parsed_answer", "source") or r.get("parsed_answer_source")

    def err(r):
        return _get(r, "parsed_answer", "error") or r.get("parsed_answer_error")

    partial = sum(1 for r in rows if src(r) == "partial_answer_key")
    no_json = sum(1 for r in rows if err(r) == "no_json")
    needs_review = sum(1 for r in rows if _get(r, "parsed_answer", "needs_review") is True)
    print("-" * 70)
    print(f"parsed_answer.source distribution: {dict(Counter(src(r) for r in rows))}")
    print(f"  partial_answer_key rows : {partial}")
    print(f"  no_json error rows      : {no_json}")
    print(f"  needs_review==true rows : {needs_review}")

    # raw_response length (proxy for overlong responses; token usage not stored).
    rlens = [len(str(r.get("raw_response") or "")) for r in rows]
    if rlens:
        big = sum(1 for x in rlens if x > 1500)
        print(f"raw_response chars mean/max : {sum(rlens)/len(rlens):.0f} / {max(rlens)}; >1500 chars: {big}")

    # Verifier / calc / reranker activity.
    print("-" * 70)
    print(f"verifier_triggered        : {sum(1 for r in rows if r.get('verifier_triggered'))}")
    print(f"verifier_override_applied : {sum(1 for r in rows if r.get('verifier_override_applied'))}")
    print(f"calculation_safe_override : {sum(1 for r in rows if r.get('calculation_safe_to_override'))}")
    print(f"long_context rows         : {sum(1 for r in rows if r.get('route') == 'long_context')}")
    print(f"evidence effective methods: {dict(Counter(r.get('evidence_reranker_effective_method') for r in rows if r.get('evidence_reranker_enabled')))}")
    print(f"neural fallback reasons   : {dict(Counter(r.get('evidence_neural_fallback_reason') for r in rows if r.get('evidence_neural_fallback_reason')))}")
    cand = [r.get("evidence_candidate_chunk_count") for r in rows if isinstance(r.get("evidence_candidate_chunk_count"), int)]
    chars = [r.get("evidence_selected_chars") for r in rows if isinstance(r.get("evidence_selected_chars"), int)]
    if cand:
        print(f"reranker candidate count mean/max : {sum(cand)/len(cand):.1f} / {max(cand)}")
    if chars:
        print(f"selected_chars mean/max           : {sum(chars)/len(chars):.0f} / {max(chars)}")

    # Slowest qids.
    print("-" * 70)
    print(f"top {args.top} slowest samples:")
    ranked = sorted(rows, key=lambda r: r.get("elapsed_sec") or 0, reverse=True)[: args.top]
    print(f"  {'qid':12s} {'route':14s} {'elapsed':>8s} {'api':>4s} {'ans':>4s}  raw_chars")
    for r in ranked:
        print(f"  {str(r.get('qid')):12s} {str(r.get('route')):14s} "
              f"{(r.get('elapsed_sec') or 0):8.2f} {str(r.get('api_calls')):>4s} "
              f"{str(r.get('final_answer')):>4s}  {len(str(r.get('raw_response') or ''))}")

    # Missing fields that would help timing.
    print("-" * 70)
    helpful = ["evidence_reranker_load_seconds", "evidence_reranker_score_seconds",
               "evidence_reranker_cache_hit", "evidence_reranker_batch_size",
               "evidence_reranker_pair_count", "openrouter_call_seconds",
               "verifier_call_seconds", "openrouter_completion_tokens", "openrouter_total_tokens"]
    present = set(rows[0].keys()) if rows else set()
    missing = [h for h in helpful if h not in present]
    print(f"timing fields MISSING (added by this phase): {missing}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
