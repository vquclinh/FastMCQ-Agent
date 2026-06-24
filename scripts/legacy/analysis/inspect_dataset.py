#!/usr/bin/env python3
"""Inspect a dataset: size, choice-count stats, sample qids, detected schema.

Usage:
    python scripts/inspect_dataset.py --input public-test_1780368312.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running the script directly without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.utils.data_io import load_dataset  # noqa: E402


def detect_schema(input_path: Path) -> str:
    suffix = input_path.suffix.lower()
    if suffix == ".json":
        return "json-list-of-objects (qid/question/choices)"
    if suffix == ".csv":
        return "csv (columns normalised by data_io)"
    return f"unknown ({suffix})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect an MCQ dataset")
    parser.add_argument("--input", required=True, help="path to JSON/CSV dataset")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    samples = load_dataset(input_path)

    counts = [len(s["choices"]) for s in samples]
    print(f"file            : {input_path}")
    print(f"detected schema : {detect_schema(input_path)}")
    print(f"dataset size    : {len(samples)} samples")

    if counts:
        print(f"choices min     : {min(counts)}")
        print(f"choices max     : {max(counts)}")
        print(f"choices average : {sum(counts) / len(counts):.2f}")
    else:
        print("choices         : (no samples)")

    print("sample qids     :")
    for sample in samples[:5]:
        print(f"  - {sample['qid']} ({len(sample['choices'])} choices)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
