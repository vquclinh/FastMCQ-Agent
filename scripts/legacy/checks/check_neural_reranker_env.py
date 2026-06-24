#!/usr/bin/env python3
"""Read-only inventory for the optional neural evidence reranker — no downloads.

Reports whether the transformers-native neural backends are usable with the LOCAL
competition-compliant models (BGE-M3 embedding, Qwen3-Reranker), CUDA status, and
local model directories. It NEVER downloads or installs anything. With ``--deep``
it additionally loads the local tokenizer/model (still ``local_files_only``, no
network) to confirm the backend actually initializes.

Usage:
    python scripts/check_neural_reranker_env.py
    python scripts/check_neural_reranker_env.py --deep
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.evidence.evidence_reranker import (  # noqa: E402
    _looks_like_bge_m3,
    _looks_like_qwen3_reranker,
    build_neural_scorer,
)

_BGE = "models/bge-m3"
_QWEN = "models/qwen3-reranker-0.6b"


def _installed(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def _cuda() -> str:
    if not _installed("torch"):
        return "torch not installed"
    try:
        import torch
        if torch.cuda.is_available():
            return f"available ({torch.cuda.get_device_name(0)})"
        return "not available (CPU)"
    except Exception as exc:  # pragma: no cover
        return f"unknown ({type(exc).__name__})"


def _exists(p: str) -> bool:
    return Path(p).is_dir() and (Path(p) / "config.json").exists()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Neural evidence-reranker env inventory (read-only)")
    ap.add_argument("--deep", action="store_true",
                    help="also load local tokenizer/model (local_files_only; no network)")
    ap.add_argument("--bge-path", default=_BGE)
    ap.add_argument("--qwen-path", default=_QWEN)
    args = ap.parse_args(argv)

    tr = _installed("transformers")
    torch_ok = _installed("torch")
    st = _installed("sentence_transformers")
    flag = _installed("FlagEmbedding")

    bge_exists = _exists(args.bge_path)
    qwen_exists = _exists(args.qwen_path)
    bge_shape = bge_exists and _looks_like_bge_m3(args.bge_path)
    qwen_shape = qwen_exists and _looks_like_qwen3_reranker(args.qwen_path)

    print("=" * 64)
    print("NEURAL EVIDENCE-RERANKER ENV (read-only; no downloads)")
    print("=" * 64)
    print(f"transformers          : {'installed' if tr else 'NOT installed'}")
    print(f"torch                 : {'installed' if torch_ok else 'NOT installed'}")
    print(f"sentence_transformers : {'installed (optional)' if st else 'not installed (optional)'}")
    print(f"FlagEmbedding         : {'installed (optional)' if flag else 'not installed (optional)'}")
    print(f"CUDA                  : {_cuda()}")
    print("-" * 64)
    print(f"{args.bge_path:28s}: {'present' if bge_exists else 'MISSING'}"
          f"{' (looks like BGE-M3)' if bge_shape else (' (NOT BGE-M3 shape)' if bge_exists else '')}")
    print(f"{args.qwen_path:28s}: {'present' if qwen_exists else 'MISSING'}"
          f"{' (looks like Qwen3-Reranker)' if qwen_shape else (' (NOT reranker shape)' if qwen_exists else '')}")

    # Cheap usability decision (no weight loading): path + shape + deps.
    deps_ok = tr and torch_ok

    def _decide(exists, shape, kind):
        if not exists:
            return False, f"{kind}_model_path_not_found"
        if not shape:
            return False, f"unsupported_{kind}_model_path"
        if not deps_ok:
            return False, "dependency_missing:transformers"
        return True, None

    emb_ok, emb_reason = _decide(bge_exists, bge_shape, "embedding")
    rer_ok, rer_reason = _decide(qwen_exists, qwen_shape, "reranker")

    print("-" * 64)
    print(f"embedding method usable now : {emb_ok}" + ("" if emb_ok else f"  (reason: {emb_reason})"))
    print(f"reranker  method usable now : {rer_ok}" + ("" if rer_ok else f"  (reason: {rer_reason})"))

    if args.deep:
        print("-" * 64)
        print("DEEP CHECK (local_files_only; loads weights; no network):")

        class _C:
            def __init__(self, t):
                self.text = t

        chunks = [_C("Sông Nile chảy qua thủ đô Cairo của Ai Cập."),
                  _C("Bóng đá là môn thể thao phổ biến trên thế giới.")]
        query = "Thủ đô Ai Cập nằm bên bờ sông nào?"
        for label, method, emb, rer, ok in (
                ("BGE-M3 embedding", "embedding", args.bge_path, None, emb_ok),
                ("Qwen3-Reranker", "reranker", None, args.qwen_path, rer_ok)):
            if not ok:
                print(f"  {label}: skipped (not usable per shallow check)")
                continue
            scorer, built_ok, reason = build_neural_scorer(method, emb, rer)
            if not built_ok or scorer is None:
                print(f"  {label}: build FAILED (reason: {reason})")
                continue
            try:
                scores = scorer.score(query, chunks)
                rel = "relevant chunk[0] scored higher" if scores[0] > scores[1] else "chunk[1] higher"
                print(f"  {label}: OK, scores={[round(s, 4) for s in scores]} ({rel})")
            except Exception as exc:
                print(f"  {label}: score FAILED ({type(exc).__name__}: {exc})")

    print("-" * 64)
    if emb_ok:
        print("Recommended (BGE-M3 embedding):")
        print(f"  --evidence-reranker --evidence-reranker-method embedding \\")
        print(f"    --evidence-embedding-model {args.bge_path} --evidence-candidate-top-k 12")
    if rer_ok:
        print("Recommended (Qwen3-Reranker):")
        print(f"  --evidence-reranker --evidence-reranker-method reranker \\")
        print(f"    --evidence-reranker-model {args.qwen_path} --evidence-candidate-top-k 12")
    if not (emb_ok or rer_ok):
        print("=> Neural rerank NOT usable now. The pipeline fails closed to hybrid_lexical.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
