#!/usr/bin/env python3
"""Read-only inventory for the optional neural evidence reranker — no downloads.

Reports whether the optional neural-rerank dependencies are importable, CUDA
availability, and any LOCAL candidate model directories. It NEVER downloads or
modifies anything; it only checks existence and import specs.

Usage:
    python scripts/check_neural_reranker_env.py
    python scripts/check_neural_reranker_env.py --model-path /mnt/vquclinh/models
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

_SEARCH_DIRS = ["/mnt/vquclinh/models", "models", "/mnt/models"]
_NAME_HINTS = ("bge-m3", "bge", "baai", "qwen", "rerank", "reranker", "m3")


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


def _candidates(extra: str | None) -> list:
    dirs = list(_SEARCH_DIRS) + ([extra] if extra else [])
    hits = []
    for d in dirs:
        p = Path(d)
        if not p.exists() or not p.is_dir():
            continue
        for child in sorted(p.iterdir()):
            if child.is_dir() and any(h in child.name.lower() for h in _NAME_HINTS):
                has_cfg = (child / "config.json").exists()
                hits.append((str(child), "config.json" if has_cfg else "no-config"))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Neural evidence-reranker env inventory (read-only)")
    ap.add_argument("--model-path", default=None, help="extra local dir to scan")
    args = ap.parse_args(argv)

    st = _installed("sentence_transformers")
    flag = _installed("FlagEmbedding")
    torch_ok = _installed("torch")
    cands = _candidates(args.model_path)

    print("=" * 60)
    print("NEURAL EVIDENCE-RERANKER ENV (read-only; no downloads)")
    print("=" * 60)
    print(f"sentence_transformers : {'installed' if st else 'NOT installed'}")
    print(f"FlagEmbedding         : {'installed' if flag else 'NOT installed'}")
    print(f"torch                 : {'installed' if torch_ok else 'NOT installed'}")
    print(f"CUDA                  : {_cuda()}")
    print(f"candidate model dirs  : {len(cands)}")
    for path, note in cands:
        print(f"  - {path}  [{note}]")

    embedding_usable = st and any(n == "config.json" for _, n in cands)
    reranker_usable = flag and any(n == "config.json" for _, n in cands)
    print("-" * 60)
    print(f"embedding method usable now : {embedding_usable}")
    print(f"reranker  method usable now : {reranker_usable}")
    if not (embedding_usable or reranker_usable):
        print("=> Neural rerank NOT usable now. The pipeline will fail closed to")
        print("   hybrid_lexical. To enable: install the dep AND place a LOCAL model,")
        print("   then set evidence_reranker.method + optional_*_model in config.")
    print("-" * 60)
    print("Recommended config (only if a local model is staged):")
    print("  openrouter.evidence_reranker.method: \"reranker\"   # or \"embedding\"")
    print("  openrouter.evidence_reranker.optional_reranker_model: <LOCAL_PATH>")
    print("  openrouter.evidence_reranker.candidate_top_k: 12")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
