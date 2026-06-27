#!/usr/bin/env python3
"""Download the single offline open-weight model at Docker BUILD time (Phase 2L.47B).

Fetches a public Hugging Face model snapshot into a local directory so the container can run
fully offline at inference time (TRANSFORMERS_OFFLINE=1 / HF_HUB_OFFLINE=1). Public model — no HF
token required. Default: Qwen/Qwen3-4B-Instruct-2507 -> /models/qwen3-4b-instruct-2507.

Usage:
    python scripts/download_local_model.py \
        --model Qwen/Qwen3-4B-Instruct-2507 --out /models/qwen3-4b-instruct-2507
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DEFAULT_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
_DEFAULT_OUT = "/models/qwen3-4b-instruct-2507"
# Weights + tokenizer/config only; skip duplicate formats and docs to keep the image smaller.
_ALLOW = ["*.safetensors", "*.json", "*.txt", "tokenizer*", "*.model", "*.tiktoken", "merges*",
          "vocab*", "generation_config.json"]
_IGNORE = ["*.bin", "*.pth", "*.h5", "*.msgpack", "*.onnx", "*.gguf", "original/*", "*.md"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Download a public HF model snapshot for offline use")
    ap.add_argument("--model", default=_DEFAULT_MODEL, help="HF repo id (public)")
    ap.add_argument("--out", default=_DEFAULT_OUT, help="local target directory")
    ap.add_argument("--revision", default=None, help="optional pinned revision/commit")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import snapshot_download  # heavy dep installed in the image

    print(f"[download] {args.model} -> {out} (revision={args.revision or 'main'})")
    snapshot_download(
        repo_id=args.model,
        local_dir=str(out),
        revision=args.revision,
        allow_patterns=_ALLOW,
        ignore_patterns=_IGNORE,
        local_dir_use_symlinks=False,
    )
    files = sorted(p.name for p in out.glob("*") if p.is_file())
    print(f"[download] done: {len(files)} files in {out}")
    if not any(f.endswith(".safetensors") for f in files):
        print("[download] WARNING: no .safetensors weights found — check the model id / patterns",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
