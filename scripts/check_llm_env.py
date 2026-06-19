#!/usr/bin/env python3
"""Check the local environment for running the LLM solvers — no downloads.

Reports whether torch/transformers are installed, CUDA availability, and GPU
info. Optionally validates a model path and (only if asked) loads the tokenizer
and/or the full model from local files. By default it does NOT load the model.

Usage:
    python scripts/check_llm_env.py
    python scripts/check_llm_env.py --model-path /path/to/model --load-tokenizer
    python scripts/check_llm_env.py --model-path /path/to/model --load-model
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def check_torch() -> bool:
    if not _installed("torch"):
        print("torch         : NOT installed  (pip install -r requirements-llm.txt)")
        return False
    import torch
    print(f"torch         : {torch.__version__}")
    cuda = torch.cuda.is_available()
    print(f"CUDA available: {cuda}")
    if cuda:
        try:
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                vram_gb = props.total_memory / (1024 ** 3)
                print(f"  GPU[{i}]     : {props.name} ({vram_gb:.1f} GB VRAM)")
        except Exception as exc:  # pragma: no cover - hardware dependent
            print(f"  (could not read GPU properties: {exc})")
    else:
        print("  device      : CPU (inference will be slower)")
    return True


def check_transformers() -> bool:
    if not _installed("transformers"):
        print("transformers  : NOT installed  (pip install -r requirements-llm.txt)")
        return False
    import transformers
    print(f"transformers  : {transformers.__version__}")
    return True


def check_model_path(model_path: str | None) -> Path | None:
    if not model_path:
        print("model-path    : (not provided; pass --model-path to validate one)")
        return None
    path = Path(model_path)
    if not path.exists():
        print(f"model-path    : DOES NOT EXIST -> {path}")
        return None
    if not path.is_dir():
        print(f"model-path    : exists but is not a directory -> {path}")
        return path
    # Light sanity hint: typical HF model dirs have a config.json.
    has_config = (path / "config.json").exists()
    print(f"model-path    : OK -> {path}"
          + ("" if has_config else "  (warning: no config.json found)"))
    return path


def try_load_tokenizer(path: Path) -> None:
    try:
        from transformers import AutoTokenizer
        AutoTokenizer.from_pretrained(str(path), local_files_only=True,
                                      trust_remote_code=False)
        print("load-tokenizer: OK")
    except Exception as exc:
        print(f"load-tokenizer: FAILED -> {type(exc).__name__}: {exc}")
        print("  hint: some models need --trust-remote-code at run time, or a "
              "tokenizer backend (sentencepiece). Nothing is downloaded.")


def try_load_model(path: Path) -> None:
    try:
        from transformers import AutoModelForCausalLM
        AutoModelForCausalLM.from_pretrained(str(path), local_files_only=True,
                                             trust_remote_code=False)
        print("load-model    : OK")
    except Exception as exc:
        print(f"load-model    : FAILED -> {type(exc).__name__}: {exc}")
        print("  hint: check the path is a complete local checkpoint, you have "
              "enough RAM/VRAM, and torch matches your hardware. No downloads.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the local LLM environment")
    parser.add_argument("--model-path", default=None, help="local model directory to validate")
    parser.add_argument("--load-tokenizer", action="store_true", help="attempt to load the tokenizer")
    parser.add_argument("--load-model", action="store_true", help="attempt to load the full model (heavy)")
    args = parser.parse_args(argv)

    print("=" * 56)
    print("LLM ENVIRONMENT CHECK (no downloads)")
    print("=" * 56)
    has_torch = check_torch()
    has_transformers = check_transformers()
    path = check_model_path(args.model_path)

    if args.load_tokenizer or args.load_model:
        if not (has_torch and has_transformers):
            print("\ncannot load: install torch + transformers first "
                  "(pip install -r requirements-llm.txt)")
        elif path is None:
            print("\ncannot load: a valid --model-path is required")
        else:
            if args.load_tokenizer:
                try_load_tokenizer(path)
            if args.load_model:
                try_load_model(path)

    print("=" * 56)
    ready = has_torch and has_transformers
    print(f"LLM-ready (deps installed): {'YES' if ready else 'NO'}")
    print("=" * 56)
    # Exit 0 always: this is a diagnostic, not a gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
