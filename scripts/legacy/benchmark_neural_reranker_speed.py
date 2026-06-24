#!/usr/bin/env python3
"""Benchmark neural reranker speed on long-context samples (no OpenRouter, no CSV).

Measures model load time (cache miss) vs warm rerank time (cache hits), confirming
weights load ONCE per process. Uses LOCAL models only (`local_files_only`); no
network, no download, no ground truth, no qid-based decisions, no prediction CSV.

Usage:
    python scripts/benchmark_neural_reranker_speed.py \
        --input public-test_1780368312.json --method reranker \
        --model-path models/qwen3-reranker-0.6b \
        --max-samples 20 --candidate-top-k 12 --batch-size 8
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.evidence_reranker import (  # noqa: E402
    build_neural_scorer,
    clear_neural_model_cache,
    has_long_context,
    neural_model_cache_size,
    rerank_evidence_for_sample,
)


def _load(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    for k in ("data", "samples", "questions"):
        if isinstance(data.get(k), list):
            return data[k]
    for v in data.values():
        if isinstance(v, list):
            return v
    raise SystemExit(f"no sample list in {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Neural reranker speed benchmark (no OpenRouter)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--method", choices=["reranker", "embedding"], default="reranker")
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--max-samples", type=int, default=20)
    ap.add_argument("--candidate-top-k", type=int, default=12)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args(argv)

    emb = args.model_path if args.method == "embedding" else None
    rer = args.model_path if args.method == "reranker" else None

    clear_neural_model_cache()
    print("=" * 64)
    print("NEURAL RERANKER SPEED BENCHMARK (read-only; no OpenRouter)")
    print("=" * 64)
    print(f"method={args.method}  model={args.model_path}  batch_size={args.batch_size}")

    # Explicit cold load (cache miss) timing.
    t0 = time.perf_counter()
    scorer, ok, reason = build_neural_scorer(args.method, emb, rer)
    load_seconds = time.perf_counter() - t0
    if not ok:
        print(f"NOT usable (reason: {reason}) -> nothing to benchmark.")
        print("=" * 64)
        return 0
    print(f"model load seconds (cold) : {load_seconds:.2f}")
    print(f"cache size after load     : {neural_model_cache_size()}")

    samples = [s for s in _load(args.input) if has_long_context(s)][: max(1, args.max_samples)]
    print(f"long_context samples      : {len(samples)}")

    per = []
    cache_hits = cache_misses = pair_total = 0
    common = dict(max_chars=4500, top_k=args.top_k, candidate_top_k=args.candidate_top_k,
                  method=args.method, optional_embedding_model=emb,
                  optional_reranker_model=rer, neural_batch_size=args.batch_size)
    for i, s in enumerate(samples):
        t = time.perf_counter()
        rr = rerank_evidence_for_sample(s, **common)
        dt = time.perf_counter() - t
        per.append(dt)
        d = rr.diagnostics if rr else {}
        if d.get("cache_hit") is True:
            cache_hits += 1
        elif d.get("cache_hit") is False:
            cache_misses += 1
        pair_total += int(d.get("pair_count") or 0)

    warm = per[1:] if len(per) > 1 else per
    print("-" * 64)
    print(f"first sample seconds        : {per[0]:.3f}")
    print(f"avg rerank seconds (warm)   : {sum(warm)/len(warm):.3f}  (n={len(warm)})")
    print(f"min/max sample seconds      : {min(per):.3f} / {max(per):.3f}")
    print(f"total candidate pairs       : {pair_total}")
    print(f"cache hits / misses (rerank): {cache_hits} / {cache_misses}")
    print(f"final cache size            : {neural_model_cache_size()}  (weights loaded once: {neural_model_cache_size() == 1})")
    print(f"effective batch size        : {args.batch_size}")
    try:
        import torch
        if torch.cuda.is_available():
            print(f"peak CUDA mem (MB)          : {torch.cuda.max_memory_allocated()/1e6:.0f}")
    except Exception:
        pass
    print("NOTE: speed only; no accuracy claimed; no CSV written.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
