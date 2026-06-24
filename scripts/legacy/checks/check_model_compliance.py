#!/usr/bin/env python3
"""Check whether a model appears to match the allowed families — no downloads.

A guardrail, not an authority: it matches the model name / path basename against
the patterns in ``configs/allowed_models.yaml`` (our current safe interpretation
of the competition constraints; see docs/MODEL_COMPLIANCE.md).

Outcomes:
  * PASS    — matches an allowed family and respects its size cap.
  * WARNING — unrecognized, or a soft concern (e.g. size unknown, looks
              disallowed) in non-strict mode.
  * FAIL    — clear problem (disallowed family, or size over cap) in any mode;
              and, under --strict, anything that is not a clean PASS.

Usage:
    python scripts/check_model_compliance.py --model-name "Qwen3.5-7B"
    python scripts/check_model_compliance.py --model-path /models/gemma-4-9b --strict
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.utils import load_config  # noqa: E402  (reuses the YAML loader)

DEFAULT_CONFIG = "configs/allowed_models.yaml"
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")


def _haystack(model_name: str | None, model_path: str | None) -> str:
    parts = []
    if model_name:
        parts.append(model_name)
    if model_path:
        parts.append(Path(model_path).name)  # basename only
    return " ".join(parts).lower()


def _matches_any(haystack: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if re.search(pat.lower(), haystack):
            return True
    return False


def _extract_size_b(haystack: str) -> float | None:
    match = _SIZE_RE.search(haystack)
    return float(match.group(1)) if match else None


def evaluate(model_name: str | None, model_path: str | None,
             config: dict) -> tuple[str, list[str]]:
    """Return (verdict, messages). verdict is PASS / WARNING / FAIL."""
    haystack = _haystack(model_name, model_path)
    messages: list[str] = []
    if not haystack:
        return "FAIL", ["no --model-name or --model-path provided"]

    # 1) Disallowed families are a clear red flag.
    disallowed = [f for f in (config.get("disallowed_families") or [])
                  if re.search(re.escape(f.lower()), haystack)]
    if disallowed:
        return "FAIL", [
            f"matches a family treated as NOT allowed: {', '.join(disallowed)}",
            "unless the organizer explicitly confirms it, do not use this model.",
        ]

    size_b = _extract_size_b(haystack)

    # 2) Allowed generation LLMs (with optional size cap).
    for fam in (config.get("generation_llms") or []):
        if _matches_any(haystack, fam.get("patterns", [])):
            cap = fam.get("max_params_b")
            if cap is not None and size_b is not None and size_b > cap:
                return "FAIL", [
                    f"matches '{fam['name']}' but size {size_b:g}B exceeds the "
                    f"{cap}B cap for this family.",
                ]
            msg = [f"matches allowed family '{fam['name']}'"]
            if cap is not None and size_b is None:
                msg.append(f"could not read a size token; ensure it is <= {cap}B.")
            return "PASS", msg

    # 3) Allowed embedding / rerank families.
    for fam in (config.get("embedding_rerank") or []):
        if _matches_any(haystack, fam.get("patterns", [])):
            return "PASS", [f"matches allowed embedding/rerank family '{fam['name']}'"]

    # 4) No match: unrecognized.
    return "WARNING", [
        "did not match any known allowed family pattern.",
        "this may still be allowed — confirm the exact model list with the organizer.",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check model compliance (no downloads)")
    parser.add_argument("--model-name", default=None, help="model name string to check")
    parser.add_argument("--model-path", default=None, help="local model path (basename is checked)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="allowed-models YAML")
    parser.add_argument("--strict", action="store_true", help="treat WARNING as FAIL")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    if not config:
        print(f"WARNING: could not load {args.config} (PyYAML missing or file absent); "
              "cannot check compliance.")
        return 0 if not args.strict else 1

    verdict, messages = evaluate(args.model_name, args.model_path, config)

    # In strict mode a WARNING is escalated to FAIL.
    effective = "FAIL" if (args.strict and verdict == "WARNING") else verdict

    print("=" * 56)
    print("MODEL COMPLIANCE CHECK")
    print("=" * 56)
    print(f"model-name : {args.model_name or '(none)'}")
    print(f"model-path : {args.model_path or '(none)'}")
    print(f"strict     : {args.strict}")
    print("-" * 56)
    print(f"VERDICT    : {effective}")
    for m in messages:
        print(f"  - {m}")
    if effective == "WARNING":
        print("  (non-strict: not blocking, but verify before a final submission.)")
    print("=" * 56)

    return 1 if effective == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
