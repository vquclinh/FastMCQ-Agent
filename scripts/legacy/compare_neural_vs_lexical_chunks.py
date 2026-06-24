#!/usr/bin/env python3
"""Compare lexical vs neural in-question chunk selection on long-context samples.

Diagnostic only: it inspects WHICH evidence chunks each method selects. It does
NOT call OpenRouter, does NOT produce a prediction CSV, does NOT use ground truth
or answer correctness, and does NOT read qids for any decision. The neural backend
is LOCAL-only and fails closed to lexical when unavailable (nothing is downloaded).

Usage:
    python scripts/compare_neural_vs_lexical_chunks.py \
        --input public-test_1780368312.json \
        --method reranker --model-path /mnt/vquclinh/models/<local_reranker> \
        --max-samples 30 --top-k 4 --candidate-top-k 12 \
        --output output/neural_vs_lexical_reranker_chunk_report.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.evidence_reranker import (  # noqa: E402
    build_neural_scorer,
    has_long_context,
    rerank_evidence_for_sample,
)


def _load_samples(path: str) -> list:
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data
    for key in ("data", "samples", "questions"):
        if isinstance(data.get(key), list):
            return data[key]
    for v in data.values():
        if isinstance(v, list):
            return v
    raise SystemExit(f"Could not find a sample list in {path}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lexical vs neural chunk-selection comparison (no OpenRouter)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--method", choices=["reranker", "embedding"], default="reranker")
    ap.add_argument("--model-path", default=None, help="LOCAL model dir (never downloaded)")
    ap.add_argument("--max-samples", type=int, default=30)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--candidate-top-k", type=int, default=12)
    ap.add_argument("--max-chars", type=int, default=4500)
    ap.add_argument("--output", default="output/neural_vs_lexical_chunk_report.jsonl")
    args = ap.parse_args(argv)

    # Fail gracefully if the neural backend is not usable — no work, clear reason.
    emb = args.model_path if args.method == "embedding" else None
    rer = args.model_path if args.method == "reranker" else None
    scorer, available, reason = build_neural_scorer(args.method, emb, rer)
    print("=" * 60)
    print("NEURAL vs LEXICAL CHUNK COMPARISON (read-only; no OpenRouter)")
    print("=" * 60)
    print(f"method        : {args.method}")
    print(f"model-path    : {args.model_path or '(none)'}")
    print(f"neural usable : {available}" + ("" if available else f"  (reason: {reason})"))
    if not available:
        print("=> Neural backend NOT usable; nothing to compare. Stage a LOCAL model")
        print("   and install the matching dependency, then re-run. No file written.")
        print("=" * 60)
        return 0

    samples = _load_samples(args.input)
    long_ctx = [s for s in samples if has_long_context(s)]
    selected = long_ctx[: max(1, args.max_samples)]
    print(f"long_context  : {len(long_ctx)} (comparing first {len(selected)})")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    changed = neural_ok = fallback = 0
    lex_chunks_sum = neu_chunks_sum = lex_chars_sum = neu_chars_sum = 0
    changed_examples = []

    with out_path.open("w", encoding="utf-8") as fh:
        for idx, sample in enumerate(selected):
            common = dict(max_chars=args.max_chars, top_k=args.top_k,
                          candidate_top_k=args.candidate_top_k)
            lex = rerank_evidence_for_sample(sample, method="hybrid_lexical", **common)
            neu = rerank_evidence_for_sample(
                sample, method=args.method,
                optional_embedding_model=emb, optional_reranker_model=rer,
                neural_scorer=scorer, **common)

            lex_ids = lex.diagnostics.get("kept_chunk_ids", [])
            neu_ids = neu.diagnostics.get("kept_chunk_ids", [])
            neu_eff = neu.diagnostics.get("effective_method")
            is_neural = neu_eff == args.method
            did_fallback = not is_neural
            did_change = is_neural and (neu_ids != lex_ids)

            neural_ok += int(is_neural)
            fallback += int(did_fallback)
            changed += int(did_change)
            lex_chunks_sum += len(lex_ids); neu_chunks_sum += len(neu_ids)
            lex_chars_sum += lex.diagnostics.get("selected_chars", 0)
            neu_chars_sum += neu.diagnostics.get("selected_chars", 0)

            rec = {
                "i": idx,
                "lex_chunk_ids": lex_ids,
                "neural_chunk_ids": neu_ids,
                "neural_effective_method": neu_eff,
                "neural_available": neu.diagnostics.get("neural_available"),
                "neural_fallback_reason": neu.diagnostics.get("neural_fallback_reason"),
                "candidate_chunk_count": neu.diagnostics.get("candidate_chunk_count"),
                "lex_selected_chars": lex.diagnostics.get("selected_chars"),
                "neural_selected_chars": neu.diagnostics.get("selected_chars"),
                "changed": did_change,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if did_change and len(changed_examples) < 5:
                changed_examples.append({"i": idx, "lex": lex_ids, "neural": neu_ids})

    n = max(1, len(selected))
    print("-" * 60)
    print(f"samples compared       : {len(selected)}")
    print(f"neural usable count    : {neural_ok}")
    print(f"fallback count         : {fallback}")
    print(f"changed selected chunks: {changed}")
    print(f"avg chunks  lexical/neural : {lex_chunks_sum / n:.2f} / {neu_chunks_sum / n:.2f}")
    print(f"avg chars   lexical/neural : {lex_chars_sum / n:.0f} / {neu_chars_sum / n:.0f}")
    if changed_examples:
        print("changed examples (chunk ids):")
        for ex in changed_examples:
            print(f"  [{ex['i']}] lexical={ex['lex']} -> neural={ex['neural']}")
    print(f"report written: {out_path}")
    print("NOTE: chunk-selection diagnostic only; no accuracy is claimed.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
