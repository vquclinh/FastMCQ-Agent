#!/usr/bin/env python3
"""Production pipeline runner for the hidden/private test (generalized, qid-free).

Given a FRESH input file (JSON or CSV) it runs the base LLM solver, then applies only
SAFE deterministic overrides (calculation → concept → formula bank, via
``production_policy``), and writes ``qid,answer`` + a JSONL log. It depends only on
the input file — never on existing public-test prediction files (v7/v8/v9).

Branch/decision policy (see ``src/production_policy.py``): deterministic safe rule >
base LLM; medium/high-risk detections, verifiers and self-consistency are log-only
and NEVER auto-override in production.

A ``--preset competition_qwen35_9b`` expands to the full stable settings so the
operator can run one short command. Running this contacts OpenRouter for the base
solver — it is NOT run during tests/CI (tests inject a fake solver).

Operator command:
    .venv/bin/python scripts/run_production_pipeline.py \
      --input /data/private_test.csv --output /output/pred.csv \
      --preset competition_qwen35_9b
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.utils.data_io import load_dataset, write_predictions  # noqa: E402
from src.utils.labels import labels_for  # noqa: E402
from src.system.production_policy import decide  # noqa: E402
from src.utils.run_logger import RunLogger  # noqa: E402
from src.base.solver_factory import build_solver  # noqa: E402

# Protected LOCAL output names that must not be overwritten without --allow-overwrite-protected.
_PROTECTED_LOCAL = {
    "output/pred.csv", "output/pred_v2_calc_rerank.csv",
    "output/pred_v6_qwen_rerank_calc_verifier.csv",
    "output/pred_v6b_qwen_rerank_calc_verifier_fast.csv",
    "output/pred_v7_programmatic_assist_from_v6b.csv",
    "output/pred_v8_clean_generalized_from_v7.csv",
    "output/pred_v9_formula_bank_from_v8_clean.csv",
}

# The single stable competition preset. Expands to base-solver + deterministic layers.
PRESETS = {
    "competition_qwen35_9b": {
        "base_solver": "openrouter_graph",
        "openrouter_model": "qwen/qwen3.5-9b",
        "openrouter_temperature": 0.0,
        "openrouter_max_tokens": 512,
        "config": "configs/verifier_selective.yaml",
        "calculation_solver": True,
        "evidence_reranker": True,
        "evidence_reranker_method": "reranker",
        "evidence_reranker_model": "models/qwen3-reranker-0.6b",
        "evidence_candidate_top_k": 12,
        "evidence_neural_batch_size": 8,
        "concept_solver": True,
        "formula_bank": True,
        "safe_overrides_only": True,
    },
}


def expand_preset(name: str) -> dict:
    if name not in PRESETS:
        raise SystemExit(f"unknown preset {name!r}; choose one of {', '.join(PRESETS)}")
    return dict(PRESETS[name])


# Input-file detection priority for the Docker entrypoint (private before public;
# CSV before JSON; then any .csv/.json). Returns a path string or None.
_INPUT_PRIORITY = ("private_test.csv", "public_test.csv", "private-test.csv",
                   "public-test.csv", "private_test.json", "public_test.json",
                   "private-test.json", "public-test.json")


def detect_input_file(data_dir):
    d = Path(data_dir)
    if not d.is_dir():
        return None
    for name in _INPUT_PRIORITY:
        if (d / name).exists():
            return str(d / name)
    for pat in ("*.csv", "*.json"):     # generic fallback: first matching file
        hits = sorted(d.glob(pat))
        if hits:
            return str(hits[0])
    return None


def completed_qids_from_log(path):
    """qid -> final_answer for rows already completed in an append-only JSONL log."""
    out = {}
    p = Path(path) if path else None
    if not (p and p.exists()):
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("qid") and o.get("final_answer") not in (None, ""):
            out[o["qid"]] = o["final_answer"]
    return out


def atomic_write_predictions(predictions, path):
    """Write predictions to a temp file then atomically replace `path` (crash-safe)."""
    import os
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    write_predictions(predictions, tmp)
    os.replace(tmp, p)


def _openrouter_config_from(opts: dict) -> dict:
    """Build the OpenRouterConfig kwargs dict (filtered by build_solver)."""
    cfg = {
        "model": opts["openrouter_model"],
        "temperature": opts["openrouter_temperature"],
        "max_tokens": opts["openrouter_max_tokens"],
        "calc_enabled": bool(opts.get("calculation_solver", True)),
        "evidence_reranker_enabled": bool(opts.get("evidence_reranker", True)),
        "evidence_reranker_method": opts.get("evidence_reranker_method", "hybrid_lexical"),
        "evidence_candidate_top_k": opts.get("evidence_candidate_top_k", 12),
        "evidence_neural_batch_size": opts.get("evidence_neural_batch_size", 8),
    }
    if opts.get("evidence_reranker_model"):
        cfg["evidence_reranker_model"] = opts["evidence_reranker_model"]
    return cfg


def _resolve_options(args) -> dict:
    """Merge preset defaults with explicit CLI flags (explicit flags win)."""
    opts = expand_preset(args.preset) if args.preset else {
        "base_solver": "openrouter_graph", "openrouter_model": "qwen/qwen3.5-9b",
        "openrouter_temperature": 0.0, "openrouter_max_tokens": 512,
        "config": None, "calculation_solver": False, "evidence_reranker": False,
        "evidence_reranker_method": "hybrid_lexical", "evidence_reranker_model": None,
        "evidence_candidate_top_k": 12, "evidence_neural_batch_size": 8,
        "concept_solver": False, "formula_bank": False, "safe_overrides_only": True,
    }
    for key, val in (("base_solver", args.base_solver),
                     ("openrouter_model", args.openrouter_model),
                     ("openrouter_temperature", args.openrouter_temperature),
                     ("openrouter_max_tokens", args.openrouter_max_tokens),
                     ("config", args.config),
                     ("evidence_reranker_method", args.evidence_reranker_method),
                     ("evidence_reranker_model", args.evidence_reranker_model),
                     ("evidence_candidate_top_k", args.evidence_candidate_top_k),
                     ("evidence_neural_batch_size", args.evidence_neural_batch_size)):
        if val is not None:
            opts[key] = val
    for flag, key in (("calculation_solver", "calculation_solver"),
                      ("evidence_reranker", "evidence_reranker"),
                      ("concept_solver", "concept_solver"),
                      ("formula_bank", "formula_bank")):
        if getattr(args, flag):
            opts[key] = True
    return opts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Production pipeline runner (generalized)")
    ap.add_argument("--input", default=None)
    ap.add_argument("--output", default=None)
    ap.add_argument("--detect-only", action="store_true", default=False,
                    help="print the auto-detected input path in --data-dir and exit (no API)")
    ap.add_argument("--data-dir", default="/data")
    ap.add_argument("--preset", default=None, choices=list(PRESETS))
    ap.add_argument("--base-solver", default=None)
    ap.add_argument("--openrouter-model", default=None)
    ap.add_argument("--openrouter-temperature", type=float, default=None)
    ap.add_argument("--openrouter-max-tokens", type=int, default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--calculation-solver", action="store_true", default=False)
    ap.add_argument("--evidence-reranker", action="store_true", default=False)
    ap.add_argument("--evidence-reranker-method", default=None)
    ap.add_argument("--evidence-reranker-model", default=None)
    ap.add_argument("--evidence-candidate-top-k", type=int, default=None)
    ap.add_argument("--evidence-neural-batch-size", type=int, default=None)
    ap.add_argument("--concept-solver", action="store_true", default=False)
    ap.add_argument("--formula-bank", action="store_true", default=False)
    ap.add_argument("--safe-overrides-only", action="store_true", default=False)
    ap.add_argument("--log-path", default=None)
    ap.add_argument("--allow-overwrite-protected", action="store_true", default=False)
    # Production accuracy layers (Phase 2L.21).
    ap.add_argument("--direct-prompt", action="store_true", default=False,
                    help="use the route-aware direct-prompt inference path (default: graph solver)")
    ap.add_argument("--json-repair-retry", action="store_true", default=False)
    ap.add_argument("--route-prompts", action="store_true", default=False)
    ap.add_argument("--option-evidence", action="store_true", default=False)
    # Resume / checkpoint (essential for ~2000-question private runs).
    ap.add_argument("--resume-from-log", default=None,
                    help="JSONL log to resume from (skip qids already completed)")
    ap.add_argument("--skip-existing", action="store_true", default=False)
    ap.add_argument("--checkpoint-every", type=int, default=0,
                    help="atomically write partial predictions every N samples (0=off)")
    args = ap.parse_args(argv)

    # Detection-only mode (used by the Docker entrypoint). No API, no output.
    if args.detect_only:
        found = detect_input_file(args.data_dir)
        if not found:
            sys.stderr.write(f"ERROR: no input file (.csv/.json) found in {args.data_dir}\n")
            return 1
        print(found)
        return 0

    if not args.input or not args.output:
        raise SystemExit("--input and --output are required (or use --detect-only)")

    # Refuse to overwrite a protected LOCAL prediction file unless explicitly allowed.
    norm_out = str(args.output).replace("\\", "/")
    if norm_out in _PROTECTED_LOCAL and not args.allow_overwrite_protected:
        raise SystemExit(f"REFUSING to overwrite protected output {args.output}; "
                         f"pass --allow-overwrite-protected to override.")

    opts = _resolve_options(args)
    enable_bank = bool(opts.get("formula_bank") or opts.get("concept_solver"))

    # Competition model-policy guard: refuse a disallowed base LLM or reranker model.
    if opts.get("base_solver") == "openrouter_graph":
        from src.api.model_policy import assert_allowed_llm_model, assert_allowed_rerank_model
        assert_allowed_llm_model(opts["openrouter_model"])
        if opts.get("evidence_reranker") and opts.get("evidence_reranker_model"):
            assert_allowed_rerank_model(opts["evidence_reranker_model"])

    run_start = time.perf_counter()
    samples = load_dataset(args.input)
    print(f"[production] input={args.input} samples={len(samples)} "
          f"base_solver={opts['base_solver']} formula_bank={enable_bank}")

    # Resume: completed qids (from --resume-from-log, else the log path when --skip-existing).
    resume_src = args.resume_from_log or (args.log_path if args.skip_existing else None)
    completed = completed_qids_from_log(resume_src) if (args.resume_from_log or args.skip_existing) else {}
    pending = [s for s in samples if s.get("qid") not in completed]
    resumed_predictions = [{"qid": q, "answer": a} for q, a in completed.items()]
    print(f"[production] completed(resumed)={len(completed)} pending={len(pending)} "
          f"direct_prompt={args.direct_prompt}")

    logger = RunLogger(args.log_path) if args.log_path else None
    overrides = 0
    new_count = 0
    predictions = list(resumed_predictions)
    try:
        # Base solver: graph (default) or a direct OpenRouter client (--direct-prompt).
        client = None
        solver = None
        if args.direct_prompt:
            from src.api.openrouter_client import OpenRouterClient   # lazy; only on --direct-prompt
            from src.system.production_inference import predict_one_direct
            client = OpenRouterClient(model=opts["openrouter_model"])
        else:
            solver = build_solver(opts["base_solver"],
                                  openrouter_config=_openrouter_config_from(opts),
                                  temperature=opts["openrouter_temperature"], logger=logger)

        t0 = time.perf_counter()
        for idx, s in enumerate(pending, 1):
            qid = s.get("qid")
            labels = labels_for(len(s.get("choices", []) or []))
            if args.direct_prompt:
                base, drec = predict_one_direct(
                    client, s, json_repair_retry=args.json_repair_retry or True,
                    route_prompts=args.route_prompts or True,
                    option_evidence=args.option_evidence or True,
                    temperature=opts["openrouter_temperature"],
                    max_tokens=opts["openrouter_max_tokens"])
            else:
                base = solver.predict_one(s)
                drec = {"qid": qid, "base_answer": base}
            # Safe deterministic override layer (calc -> concept -> formula bank).
            final, rec = decide(s, base, labels, enable_formula_bank=enable_bank)
            overrides += int(rec["override_applied"])
            new_count += 1
            predictions.append({"qid": qid, "answer": final})
            if logger:
                logger.record_event({**drec, **rec, "solver": "production_pipeline"})
            if args.checkpoint_every and idx % args.checkpoint_every == 0:
                atomic_write_predictions(predictions, args.output)
                print(f"[production] checkpoint at {idx}/{len(pending)} -> {args.output}")
        elapsed = time.perf_counter() - t0

        # Final atomic write (crash-safe; covers resumed + newly predicted qids).
        atomic_write_predictions(predictions, args.output)
        run_elapsed = time.perf_counter() - run_start
        sps = round(new_count / run_elapsed, 4) if run_elapsed > 0 else 0.0
        avg = round(run_elapsed / new_count, 4) if new_count > 0 else 0.0
        summary = {
            "event": "summary", "input": args.input, "output": args.output,
            "log_path": args.log_path, "preset": args.preset,
            "elapsed_seconds": round(run_elapsed, 3),
            "predict_loop_seconds": round(elapsed, 3),
            "total_samples": len(samples), "newly_predicted": new_count,
            "resumed_skipped": len(completed),
            "samples_per_second": sps, "avg_seconds_per_sample": avg,
            "overrides_applied": overrides,
        }
        if logger:
            logger.record_summary(summary)
    finally:
        if logger:
            logger.close()

    # --- Runtime report ------------------------------------------------------
    print("=" * 56)
    print("PRODUCTION RUN SUMMARY")
    print("=" * 56)
    print(f"elapsed_seconds        : {summary['elapsed_seconds']}")
    print(f"total_samples          : {summary['total_samples']}")
    print(f"newly_predicted        : {summary['newly_predicted']}")
    print(f"resumed/skipped        : {summary['resumed_skipped']}")
    print(f"samples_per_second     : {summary['samples_per_second']}")
    print(f"avg_seconds_per_sample : {summary['avg_seconds_per_sample']}")
    print(f"safe overrides applied : {summary['overrides_applied']}")
    print(f"output path            : {args.output}")
    print(f"log path               : {args.log_path or '(none)'}")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
