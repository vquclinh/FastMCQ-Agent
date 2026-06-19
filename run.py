#!/usr/bin/env python3
"""Entry point: read input from /data, predict, write /output/pred.csv.

Usage (baseline, default — no deps):
    python run.py [--input PATH] [--output PATH]

Usage (local LLM, Phase 2B/C — requires torch+transformers and a local model):
    python run.py --solver hf_option_score --model-path /path/to/local/model

If --input is omitted, the input file is auto-detected inside /data following
the competition's naming conventions. CLI flags override values in --config.
Nothing is ever downloaded; hf_* solvers need a LOCAL model path.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from src.data_io import load_dataset, read_predictions, write_predictions
from src.hf_common import HFDependencyError
from src.postprocess import build_predictions
from src.run_logger import RunLogger
from src.solver_factory import build_solver
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
    parser.add_argument("--output", default=None, help="output CSV path (default: /output/pred.csv)")
    parser.add_argument("--config", default="configs/default.yaml", help="YAML config path")
    parser.add_argument("--solver", default=None, help="solver name: always_a | hf_generate | hf_option_score")
    parser.add_argument("--model-path", default=None, help="LOCAL model directory (required for hf_* solvers)")
    parser.add_argument("--max-new-tokens", type=int, default=None, help="max new tokens for generation solver")
    parser.add_argument("--temperature", type=float, default=None, help="sampling temperature (0 = deterministic)")
    parser.add_argument("--max-input-tokens", type=int, default=None, help="prompt token budget (question truncation)")
    parser.add_argument("--score-mode", default=None, choices=["label_only", "label_plus_choice", "choice_only"], help="option-scoring continuation style (hf_option_score)")
    parser.add_argument("--trust-remote-code", action="store_true", default=None, help="allow trust_remote_code on model load")
    parser.add_argument("--device", default=None, help="device: auto | cpu | cuda")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N samples (smoke testing)")
    parser.add_argument("--resume", default=None, help="existing prediction CSV; skip qids already present")
    parser.add_argument("--save-raw", action="store_true", default=None, help="log raw outputs/scores to the debug log")
    parser.add_argument("--log-path", default=None, help="debug JSONL log path (per-sample metadata)")
    return parser.parse_args(argv)


def _resolve(cli_value, config_value, default):
    """CLI overrides config overrides built-in default. None means 'unset'."""
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    hf_cfg = config.get("hf", {}) or {}
    io_cfg = config.get("io", {}) or {}

    # --- Resolve settings (CLI > config > default) ---------------------------
    solver_name = _resolve(args.solver, config.get("solver"), "always_a")
    output_path = Path(_resolve(args.output, io_cfg.get("output"), str(DEFAULT_OUTPUT)))
    model_path = _resolve(args.model_path, hf_cfg.get("model_path"), None)
    max_new_tokens = _resolve(args.max_new_tokens, hf_cfg.get("max_new_tokens"), 8)
    temperature = _resolve(args.temperature, hf_cfg.get("temperature"), 0.0)
    max_input_tokens = _resolve(args.max_input_tokens, hf_cfg.get("max_input_tokens"), 4096)
    score_mode = _resolve(args.score_mode, hf_cfg.get("score_mode"), "label_plus_choice")
    trust_remote_code = bool(_resolve(args.trust_remote_code, hf_cfg.get("trust_remote_code"), False))
    device = _resolve(args.device, hf_cfg.get("device"), "auto")
    save_raw = bool(_resolve(args.save_raw, hf_cfg.get("save_raw"), False))
    # The debug log only matters for LLM runs; default path comes from config.
    default_log = hf_cfg.get("log_path") if solver_name != "always_a" else None
    log_path = _resolve(args.log_path, default_log, None)

    input_path = Path(args.input) if args.input else detect_input()

    log(f"input : {input_path}")
    samples = load_dataset(input_path)
    log(f"loaded {len(samples)} samples")

    # --- Optional sample slicing / resume ------------------------------------
    if args.limit is not None:
        samples = samples[: args.limit]
        log(f"limit : running first {len(samples)} samples")

    resume_preds: list[dict] = []
    if args.resume:
        resume_path = Path(args.resume)
        if resume_path.exists():
            resume_preds = read_predictions(resume_path)
            done = {r["qid"] for r in resume_preds}
            before = len(samples)
            samples = [s for s in samples if s["qid"] not in done]
            log(f"resume: {len(done)} qids already in {resume_path}; "
                f"{before - len(samples)} skipped, {len(samples)} remaining")
        else:
            log(f"resume: {resume_path} not found; running all samples")

    # --- Build solver --------------------------------------------------------
    run_logger = RunLogger(log_path)
    try:
        try:
            solver = build_solver(
                solver_name, model_path=model_path, device=device,
                trust_remote_code=trust_remote_code, max_new_tokens=max_new_tokens,
                temperature=temperature, max_input_tokens=max_input_tokens,
                score_mode=score_mode, save_raw=save_raw, logger=run_logger,
            )
        except (ValueError, HFDependencyError) as exc:
            # Configuration / dependency problems: report cleanly, no traceback.
            log(f"ERROR: {exc}")
            return 2
        log(f"solver: {solver_name} ({type(solver).__name__})")

        # --- Predict ---------------------------------------------------------
        start = time.perf_counter()
        labels = solver.predict_batch(samples)
        elapsed = time.perf_counter() - start

        predictions = build_predictions(samples, labels)
        # Merge resumed predictions back in so the output covers every qid.
        if resume_preds:
            predictions = resume_preds + predictions

        write_predictions(predictions, output_path)

        avg = elapsed / len(samples) if samples else 0.0
        run_logger.record_summary({
            "solver": solver_name, "input": str(input_path),
            "output": str(output_path), "num_samples": len(samples),
            "total_seconds": round(elapsed, 3), "avg_seconds_per_sample": round(avg, 4),
        })
    finally:
        run_logger.close()

    # --- Summary -------------------------------------------------------------
    log("=" * 48)
    log(f"samples processed : {len(samples)}")
    log(f"output path       : {output_path} ({len(predictions)} rows total)")
    log(f"solver            : {solver_name}")
    log(f"total runtime      : {elapsed:.2f}s")
    log(f"avg sec/sample    : {avg:.4f}s")
    if log_path:
        log(f"debug log         : {log_path}")
    log("=" * 48)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
