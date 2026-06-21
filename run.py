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
    parser.add_argument("--solver", default=None, help="solver name: always_a | hf_generate | hf_option_score | adaptive_agent | openrouter_graph")
    parser.add_argument("--model-path", default=None, help="LOCAL model directory (required for hf_* solvers)")
    parser.add_argument("--max-new-tokens", type=int, default=None, help="max new tokens for generation solver")
    parser.add_argument("--temperature", type=float, default=None, help="sampling temperature (0 = deterministic)")
    parser.add_argument("--max-input-tokens", type=int, default=None, help="prompt token budget (question truncation)")
    parser.add_argument("--score-mode", default=None, choices=["label_only", "label_plus_choice", "choice_only"], help="option-scoring continuation style (hf_option_score)")
    parser.add_argument("--quantization-mode", default=None, choices=["4bit", "8bit"], help="optional bitsandbytes quantized loading (requires CUDA + bitsandbytes)")
    parser.add_argument("--quantization-compute-dtype", default=None, choices=["float16", "bfloat16", "float32"], help="compute dtype for 4-bit quantization")
    parser.add_argument("--openrouter-model", default=None, help="OpenRouter model id (default: qwen/qwen3.5-9b)")
    parser.add_argument("--openrouter-temperature", type=float, default=None, help="OpenRouter sampling temperature")
    parser.add_argument("--openrouter-max-tokens", type=int, default=None, help="OpenRouter max output tokens")
    parser.add_argument("--openrouter-timeout-sec", type=float, default=None, help="OpenRouter request timeout (seconds)")
    parser.add_argument("--openrouter-self-consistency", action="store_true", default=None, help="enable gated self-consistency for low-confidence samples")
    parser.add_argument("--openrouter-reasoning-enabled", action="store_true", default=None, help="send a reasoning control map (for reasoning-capable models)")
    parser.add_argument("--openrouter-reasoning-effort", default=None, choices=["low", "medium", "high"], help="reasoning effort (when reasoning enabled)")
    parser.add_argument("--openrouter-reasoning-max-tokens", type=int, default=None, help="cap reasoning tokens (when reasoning enabled)")
    parser.add_argument("--openrouter-reasoning-exclude", action="store_true", default=None, help="exclude reasoning from the response body (when reasoning enabled)")
    parser.add_argument("--calculation-solver", dest="calculation_solver", action="store_true", default=None, help="enable the deterministic calculation helper (calculation route)")
    parser.add_argument("--no-calculation-solver", dest="calculation_solver", action="store_false", help="disable the deterministic calculation helper")
    parser.add_argument("--evidence-reranker", dest="evidence_reranker", action="store_true", default=None, help="enable in-question evidence reranking (long_context route)")
    parser.add_argument("--no-evidence-reranker", dest="evidence_reranker", action="store_false", help="disable in-question evidence reranking")
    parser.add_argument("--evidence-reranker-method", default=None, choices=["hybrid_lexical", "embedding", "reranker"], help="evidence reranker backend (neural falls back to lexical if unavailable)")
    parser.add_argument("--evidence-embedding-model", default=None, help="LOCAL embedding model path (method=embedding); never downloaded")
    parser.add_argument("--evidence-reranker-model", default=None, help="LOCAL cross-encoder reranker path (method=reranker); never downloaded")
    parser.add_argument("--evidence-candidate-top-k", type=int, default=None, help="stage-1 lexical candidate count fed to the neural reranker")
    parser.add_argument("--mcq-verifier", dest="mcq_verifier", action="store_true", default=None, help="enable the selective second-pass MCQ verifier")
    parser.add_argument("--no-mcq-verifier", dest="mcq_verifier", action="store_false", help="disable the MCQ verifier")
    parser.add_argument("--mcq-verifier-threshold", type=float, default=None, help="min verifier confidence to override the original answer")
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
    or_cfg = config.get("openrouter", {}) or {}

    # --- Resolve settings (CLI > config > default) ---------------------------
    solver_name = _resolve(args.solver, config.get("solver"), "always_a")
    output_path = Path(_resolve(args.output, io_cfg.get("output"), str(DEFAULT_OUTPUT)))
    model_path = _resolve(args.model_path, hf_cfg.get("model_path"), None)
    max_new_tokens = _resolve(args.max_new_tokens, hf_cfg.get("max_new_tokens"), 8)
    temperature = _resolve(args.temperature, hf_cfg.get("temperature"), 0.0)
    max_input_tokens = _resolve(args.max_input_tokens, hf_cfg.get("max_input_tokens"), 4096)
    score_mode = _resolve(args.score_mode, hf_cfg.get("score_mode"), "label_plus_choice")
    # Adaptive-agent settings come from config (hf.adaptive); CLI --score-mode,
    # when given, overrides the adaptive primary score mode too.
    adaptive_config = dict(hf_cfg.get("adaptive", {}) or {})
    if args.score_mode is not None:
        adaptive_config["primary_score_mode"] = args.score_mode
    # Quantization: config (hf.quantization) with optional CLI overrides.
    quantization = dict(hf_cfg.get("quantization", {}) or {})
    if args.quantization_mode is not None:
        quantization["mode"] = args.quantization_mode
    if args.quantization_compute_dtype is not None:
        quantization["compute_dtype"] = args.quantization_compute_dtype
    # OpenRouter settings: config (openrouter.*) with optional CLI overrides.
    openrouter_config = dict(or_cfg)
    if args.openrouter_model is not None:
        openrouter_config["model"] = args.openrouter_model
    if args.openrouter_temperature is not None:
        openrouter_config["temperature"] = args.openrouter_temperature
    if args.openrouter_max_tokens is not None:
        openrouter_config["max_tokens"] = args.openrouter_max_tokens
    if args.openrouter_timeout_sec is not None:
        openrouter_config["timeout_sec"] = args.openrouter_timeout_sec
    if args.openrouter_self_consistency:
        openrouter_config["enable_self_consistency"] = True
    if args.openrouter_reasoning_enabled:
        openrouter_config["reasoning_enabled"] = True
    if args.openrouter_reasoning_effort is not None:
        openrouter_config["reasoning_effort"] = args.openrouter_reasoning_effort
    if args.openrouter_reasoning_max_tokens is not None:
        openrouter_config["reasoning_max_tokens"] = args.openrouter_reasoning_max_tokens
    if args.openrouter_reasoning_exclude:
        openrouter_config["reasoning_exclude"] = True
    if args.calculation_solver is not None:
        openrouter_config["calc_enabled"] = args.calculation_solver
    # Flatten the nested evidence_reranker config block into flat solver fields.
    er_cfg = openrouter_config.pop("evidence_reranker", {}) or {}
    _er_map = {"enabled": "evidence_reranker_enabled", "method": "evidence_reranker_method",
               "top_k": "evidence_reranker_top_k", "max_chars": "evidence_reranker_max_chars",
               "include_global_context": "evidence_reranker_global_context",
               "global_context_chars": "evidence_reranker_global_context_chars",
               "optional_embedding_model": "evidence_embedding_model",
               "optional_reranker_model": "evidence_reranker_model",
               "candidate_top_k": "evidence_candidate_top_k",
               "neural_fallback_to_lexical": "evidence_neural_fallback_to_lexical"}
    for k, flat in _er_map.items():
        if er_cfg.get(k) is not None:
            openrouter_config[flat] = er_cfg[k]
    if args.evidence_reranker is not None:
        openrouter_config["evidence_reranker_enabled"] = args.evidence_reranker
    if args.evidence_reranker_method is not None:
        openrouter_config["evidence_reranker_method"] = args.evidence_reranker_method
    if args.evidence_embedding_model is not None:
        openrouter_config["evidence_embedding_model"] = args.evidence_embedding_model
    if args.evidence_reranker_model is not None:
        openrouter_config["evidence_reranker_model"] = args.evidence_reranker_model
    if args.evidence_candidate_top_k is not None:
        openrouter_config["evidence_candidate_top_k"] = args.evidence_candidate_top_k
    # Flatten the nested mcq_verifier config block into flat solver fields.
    mv_cfg = openrouter_config.pop("mcq_verifier", {}) or {}
    _mv_map = {"enabled": "mcq_verifier_enabled", "apply_routes": "mcq_verifier_apply_routes",
               "min_confidence_to_override": "mcq_verifier_min_confidence_to_override",
               "trigger_below_confidence": "mcq_verifier_trigger_below_confidence",
               "trigger_on_partial_parse": "mcq_verifier_trigger_on_partial_parse",
               "trigger_on_repair": "mcq_verifier_trigger_on_repair",
               "trigger_on_reranked_long_context": "mcq_verifier_trigger_on_reranked_long_context",
               "max_extra_calls_per_sample": "mcq_verifier_max_extra_calls"}
    for k, flat in _mv_map.items():
        if mv_cfg.get(k) is not None:
            openrouter_config[flat] = mv_cfg[k]
    if args.mcq_verifier is not None:
        openrouter_config["mcq_verifier_enabled"] = args.mcq_verifier
    if args.mcq_verifier_threshold is not None:
        openrouter_config["mcq_verifier_min_confidence_to_override"] = args.mcq_verifier_threshold
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
                score_mode=score_mode, adaptive_config=adaptive_config,
                quantization=quantization, openrouter_config=openrouter_config,
                save_raw=save_raw, logger=run_logger,
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
