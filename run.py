#!/usr/bin/env python3
"""Entry point: read input from /data, predict, write /output/pred.csv.

Usage:
    python run.py [--input PATH] [--output PATH] [--config configs/default.yaml]

If --input is omitted, the input file is auto-detected inside /data following
the competition's naming conventions.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.baseline_solver import AlwaysASolver
from src.data_io import load_dataset, write_predictions
from src.postprocess import build_predictions
from src.utils import load_config, log

# Default mount points used by the competition harness (BTC).
DEFAULT_DATA_DIR = Path("/data")
DEFAULT_OUTPUT = Path("/output/pred.csv")

# Auto-detect priority, highest first. Private test is preferred over public.
_INPUT_CANDIDATES = (
    "private_test.csv",
    "private-test.json",
    "public_test.csv",
    "public-test.json",
)


def detect_input(data_dir: Path = DEFAULT_DATA_DIR) -> Path:
    """Find the input file inside ``data_dir`` by priority, else any .csv/.json."""
    for name in _INPUT_CANDIDATES:
        candidate = data_dir / name
        if candidate.exists():
            return candidate

    # Fall back to any CSV or JSON file present, deterministically (sorted).
    fallbacks = sorted(
        p for p in data_dir.glob("*") if p.suffix.lower() in (".csv", ".json")
    )
    if fallbacks:
        return fallbacks[0]

    raise FileNotFoundError(
        f"no input file found in {data_dir}; pass --input explicitly"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FastMCQ-Agent inference runner")
    parser.add_argument("--input", default=None, help="input JSON/CSV file (default: auto-detect in /data)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="output CSV path (default: /output/pred.csv)")
    parser.add_argument("--config", default="configs/default.yaml", help="optional YAML config path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)

    input_path = Path(args.input) if args.input else detect_input()
    output_path = Path(args.output)

    log(f"input : {input_path}")
    samples = load_dataset(input_path)
    log(f"loaded {len(samples)} samples")

    solver = AlwaysASolver()  # Phase 1 baseline; swap for an LLM solver in Phase 2.
    log(f"solver: {type(solver).__name__}")

    labels = solver.predict_batch(samples)
    predictions = build_predictions(samples, labels)

    write_predictions(predictions, output_path)
    log(f"output: {output_path} ({len(predictions)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
