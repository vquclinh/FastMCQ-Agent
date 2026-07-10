#!/usr/bin/env python3
"""Official BTC submission entry point (Phase 2L.47B — offline local model).

Vietnamese Student HackAIthon — Bảng C Innovator, internet-isolated runtime.

    input  : /code/private_test.json  (BTC official; also /app/data and /data fallbacks)
    outputs: /code/submission.csv       (qid,answer)
             /code/submission_time.csv  (qid,answer,time  — REAL per-sample seconds)

The FINAL path is fully offline: one open-weight local model
(`Qwen/Qwen3-4B-Instruct-2507`, 4.0B < 5B, Apache-2.0) loaded once via Hugging Face Transformers,
answering each question deterministically. No external model provider / internet at runtime.

`--legacy-dynamic-full` keeps the optional local selective pipeline available for development
only; it is NOT the default and is never used in the BTC no-argument submission path.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.utils.data_io import load_dataset  # noqa: E402
from src.utils.labels import is_valid_label, labels_for  # noqa: E402
from src.local_model.qwen_mcq_predictor import DEFAULT_MODEL_PATH  # noqa: E402

_GLOBAL_LABELS = set("ABCDEFGHIJK")

# BTC-first input priority (official /code path first; /app/data and /data are compatibility).
_INPUT_CANDIDATES = (
    "/code/private_test.json", "/code/public_test.json",
    "/app/data/private_test.json", "/app/data/public_test.json",
    "/data/private_test.json", "/data/public_test.json",
    "/data/private_test.csv", "/data/public_test.csv",
)


def _resolve_input(explicit):
    if explicit:
        return explicit
    env = os.environ.get("INPUT_FILE")
    if env:
        return env
    for cand in _INPUT_CANDIDATES:
        if Path(cand).exists():
            return cand
    raise SystemExit(
        "REFUSING: no input file found. Expected (in priority order):\n"
        "  1. --input <path>\n  2. $INPUT_FILE\n"
        "  3. /code/private_test.json   (official BTC path)\n  4. /code/public_test.json\n"
        "  5. /app/data/private_test.json   6. /app/data/public_test.json\n"
        "  7. /data/private_test.json       8. /data/public_test.json\n"
        "  9. /data/private_test.csv       10. /data/public_test.csv")


def _can_mkdir(d) -> bool:
    try:
        Path(d).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _resolve_out(explicit, env_val, basename):
    if explicit:
        return explicit
    if env_val:
        return env_val
    code = Path("/code")
    if code.is_dir() or _can_mkdir(code):
        return str(code / basename)
    return basename


def _fallback_answer(item) -> str:
    """Deterministic per-sample fallback: the first valid label ('A')."""
    choices = item.get("choices") or []
    return (labels_for(len(choices))[0] if choices else "A")


def _coerce_label(ans, item) -> str:
    """Return a VALID label for item: the model's answer if valid, else the deterministic fallback."""
    if ans:
        a = str(ans).strip().upper()
        choices = item.get("choices") or []
        ok = is_valid_label(a, item) if choices else (a in _GLOBAL_LABELS)
        if ok:
            return a
    return _fallback_answer(item)


def _build_predictor(args):
    """Construct + load the single local model. Isolated so tests can stub it (no torch needed)."""
    from src.local_model.qwen_mcq_predictor import QwenMCQPredictor
    p = QwenMCQPredictor(model_path=args.model_path, device=args.device,
                         max_new_tokens=args.max_new_tokens)
    p.load()
    return p


_DEFAULT_TELEMETRY_PATH = "scratch/fastmcq_run/choice_score_telemetry.jsonl"
_DEFAULT_SHADOW_PATH = "scratch/fastmcq_run/confidence_shadow_router.jsonl"
_DEFAULT_SHADOW_SUMMARY_PATH = "scratch/fastmcq_run/confidence_shadow_router_summary.json"


def _compute_score(predictor, item, *, enabled=True):
    """Compute the Phase 1 choice-score once for an item (shared by telemetry and the
    shadow router so scoring runs exactly once per qid). Returns
    (score_dict_or_None, scoring_error, elapsed_sec). Fails closed."""
    if not enabled:
        return None, "disabled_by_config", 0.0
    score_fn = getattr(predictor, "score_choices", None)
    if not callable(score_fn):
        return None, "predictor_has_no_score_choices", 0.0
    t0 = time.time()
    try:
        d = score_fn(item).as_dict()
        return d, d.get("error"), round(time.time() - t0, 6)
    except Exception as e:                       # observational scoring must never break a run
        return None, f"{type(e).__name__}: {e}", round(time.time() - t0, 6)


def _telemetry_record(qid, ans, score, error, elapsed) -> dict:
    """Phase 1 telemetry record from a precomputed score. No question text stored."""
    rec = {
        "qid": qid, "generated_answer": ans,
        "scored_top1": None, "scored_top2": None,
        "scores_by_label": {}, "probabilities_by_label": {},
        "logit_margin": None, "probability_margin": None, "normalized_entropy": None,
        "generated_vs_scored_agree": None,
        "scoring_method": None, "scoring_valid": False, "scoring_error": error,
        "elapsed_sec": elapsed,
    }
    if score is not None:
        rec.update({
            "scored_top1": score["top1_label"], "scored_top2": score["top2_label"],
            "scores_by_label": score["scores_by_label"],
            "probabilities_by_label": score["probabilities_by_label"],
            "logit_margin": score["logit_margin"], "probability_margin": score["probability_margin"],
            "normalized_entropy": score["normalized_entropy"], "scoring_method": score["scoring_method"],
            "scoring_valid": score["valid"], "scoring_error": score["error"],
            "generated_vs_scored_agree": (bool(score["valid"]) and ans == score["top1_label"]),
        })
    return rec


def _shadow_input(qid, idx, ans, score, parser_failed):
    """Build a ShadowRoutingInput from a precomputed score (observational).

    Parser failure is genuinely available (generation returned no valid label).
    Formula-bank source/disagreement is NOT available on the single-pass path, so it
    is left as None (deferred) and never fabricated."""
    from src.local_model.confidence_shadow_router import ShadowRoutingInput
    if score is not None:
        return ShadowRoutingInput(
            qid=qid, input_index=idx, generated_answer=ans,
            scoring_valid=bool(score["valid"]), scoring_error=score["error"],
            top1=score["top1_label"], top2=score["top2_label"],
            logit_margin=score["logit_margin"], probability_margin=score["probability_margin"],
            normalized_entropy=score["normalized_entropy"], scoring_method=score["scoring_method"],
            parser_failure=bool(parser_failed), formula_disagreement=None, formula_source=None)
    return ShadowRoutingInput(
        qid=qid, input_index=idx, generated_answer=ans, scoring_valid=False,
        scoring_error="no_score", parser_failure=bool(parser_failed),
        formula_disagreement=None, formula_source=None)


def _write_shadow(jsonl_path, summary_path, decisions, summary) -> None:
    """Write shadow decisions (JSONL) + summary (JSON). Fails closed with a warning."""
    try:
        p = Path(jsonl_path); p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for d in decisions:
                fh.write(json.dumps(d.as_dict(), ensure_ascii=False, allow_nan=False) + "\n")
        sp = Path(summary_path); sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(summary.as_dict(), ensure_ascii=False, allow_nan=False, indent=2),
                      encoding="utf-8")
        print(f"[predict] shadow router -> {p} ({len(decisions)} decisions), summary -> {sp} "
              f"(selected={summary.selected_count}/{summary.budget_cap})")
    except (OSError, ValueError) as e:
        print(f"[predict] WARN shadow router output not written ({type(e).__name__}: {e})")


def _write_telemetry(path, records) -> None:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[predict] confidence telemetry -> {p} ({len(records)} records)")
    except OSError as e:
        print(f"[predict] WARN telemetry not written ({type(e).__name__}: {e})")


def _mirror(src_csv, dest):
    if not dest:
        return None
    try:
        srcp, destp = Path(src_csv).resolve(), Path(dest)
        if destp.resolve() == srcp:
            return str(destp)
        destp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_csv, destp)
        return str(destp)
    except OSError:
        return None


def _run_legacy_dynamic_full(args, inp, submission):
    """DEV-ONLY: delegate to the optional local selective pipeline."""
    p = _ROOT / "scripts" / "tools" / "final_infer.py"
    spec = importlib.util.spec_from_file_location("final_infer", p)
    fi = importlib.util.module_from_spec(spec); spec.loader.exec_module(fi)
    return fi.main(["--input", inp, "--output", submission, "--profile", "local_selective_auto"])


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description="FASTMCQ — official BTC submission (offline local model)")
    ap.add_argument("--input", default=None, help="test file (default: BTC /code/private_test.json)")
    ap.add_argument("--submission", default=None, help="qid,answer output (default /code/submission.csv)")
    ap.add_argument("--submission-time", default=None,
                    help="qid,answer,time output (default /code/submission_time.csv)")
    ap.add_argument("--output", default=None, help="legacy pred.csv-style output path (also mirrored)")
    ap.add_argument("--model-path", default=os.environ.get("LOCAL_MODEL_PATH", DEFAULT_MODEL_PATH),
                    help="local model dir (default $LOCAL_MODEL_PATH or /models/qwen3-4b-instruct-2507)")
    ap.add_argument("--max-new-tokens", type=int, default=64)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--legacy-dynamic-full", action="store_true", default=False,
                    help="DEV ONLY: use the optional local selective pipeline")
    ap.add_argument("--confidence-telemetry", action="store_true", default=False,
                    help="DEV ONLY: shadow per-choice uncertainty scoring; writes a diagnostics "
                         "JSONL and does NOT change answers or the official CSV output")
    ap.add_argument("--telemetry-path", default=_DEFAULT_TELEMETRY_PATH,
                    help=f"confidence-telemetry JSONL path (default {_DEFAULT_TELEMETRY_PATH})")
    ap.add_argument("--confidence-shadow-router", action="store_true", default=False,
                    help="DEV ONLY: Phase 2 shadow router; records which qids WOULD be selected for "
                         "follow-up (never runs V12B/V13, never changes answers or the official CSV)")
    ap.add_argument("--shadow-router-path", default=_DEFAULT_SHADOW_PATH,
                    help=f"shadow-router decisions JSONL (default {_DEFAULT_SHADOW_PATH})")
    ap.add_argument("--shadow-router-summary-path", default=_DEFAULT_SHADOW_SUMMARY_PATH,
                    help=f"shadow-router summary JSON (default {_DEFAULT_SHADOW_SUMMARY_PATH})")
    args, _extra = ap.parse_known_args(argv)

    inp = _resolve_input(args.input)
    submission = _resolve_out(args.submission, os.environ.get("SUBMISSION_FILE"), "submission.csv")
    submission_time = _resolve_out(args.submission_time, os.environ.get("SUBMISSION_TIME_FILE"),
                                   "submission_time.csv")

    print("=" * 60)
    print("[predict] FASTMCQ — BTC submission pipeline (offline local model)")
    print(f"[predict] input            : {inp}")
    print(f"[predict] submission       : {submission}")
    print(f"[predict] submission_time  : {submission_time}")
    print("=" * 60)

    if args.legacy_dynamic_full:
        print("[predict] mode: LEGACY dynamic-full (dev only)")
        rc = _run_legacy_dynamic_full(args, inp, submission)
        if rc != 0:
            return rc
        from src.utils.data_io import read_predictions
        rows = [(r["qid"], r["answer"]) for r in read_predictions(submission)]
        times = [0.0] * len(rows)
    else:
        print(f"[predict] mode: offline local model ({args.model_path})")
        # Opt-in observational modes (Phase 1 telemetry + Phase 2 shadow router).
        score_enabled, shadow_cfg = True, None
        want_score = bool(args.confidence_telemetry or args.confidence_shadow_router)
        if want_score:
            try:
                from src.local_model.confidence_config import load_choice_scoring_config
                score_enabled = bool(load_choice_scoring_config().enabled)
            except Exception as e:            # bad config must not break the run
                print(f"[predict] WARN choice-scoring config load failed ({type(e).__name__}: {e}); "
                      "using defaults")
        if args.confidence_telemetry:
            print(f"[predict] confidence-telemetry: ON (scoring={'enabled' if score_enabled else 'disabled'}; "
                  "answers unchanged)")
        if args.confidence_shadow_router:
            if not score_enabled:
                print("[predict] confidence-shadow-router: SKIPPED (choice_scoring disabled)")
            else:
                try:
                    from src.local_model.confidence_config import load_shadow_router_config
                    shadow_cfg = load_shadow_router_config()
                    print("[predict] confidence-shadow-router: ON (observational; no answer change, "
                          "no V12B/V13)")
                except Exception as e:        # fail closed: no shadow, official output unaffected
                    print(f"[predict] WARN shadow-router config load failed ({type(e).__name__}: {e}); "
                          "shadow router disabled")
        samples = load_dataset(inp)
        predictor = _build_predictor(args)
        rows, times = [], []
        telemetry = [] if args.confidence_telemetry else None
        shadow_inputs = [] if (shadow_cfg is not None) else None
        failures = 0
        for idx, item in enumerate(samples):
            qid = item.get("qid")
            parser_failed = False
            t0 = time.time()
            try:
                raw = predictor.predict_one(item)
                ans = _coerce_label(raw, item)
                if raw is None or str(raw).strip().upper() != ans:
                    failures += 1           # model gave nothing usable -> deterministic fallback
                    parser_failed = True    # parser could not produce a valid label
            except Exception as e:  # one bad sample must not abort the run
                ans = _fallback_answer(item)
                failures += 1
                parser_failed = True
                print(f"[predict] WARN qid={qid} fell back ({type(e).__name__}: {e})")
            dt = time.time() - t0                 # official per-sample time = generation only
            rows.append((qid, ans))
            times.append(dt)
            # Score ONCE per item; reuse for both telemetry and the shadow router.
            score = err = None
            if (telemetry is not None) or (shadow_inputs is not None):
                score, err, elapsed = _compute_score(predictor, item, enabled=score_enabled)
                if telemetry is not None:
                    telemetry.append(_telemetry_record(qid, ans, score, err, elapsed))
                if shadow_inputs is not None:
                    shadow_inputs.append(_shadow_input(qid, idx, ans, score, parser_failed))
        print(f"[predict] predicted {len(rows)} samples ({failures} fell back to deterministic)")
        if telemetry is not None:
            _write_telemetry(args.telemetry_path, telemetry)
        if shadow_inputs is not None:
            try:                                  # shadow routing/writing must never break output
                from src.local_model.confidence_shadow_router import run_shadow_router
                decisions, summary = run_shadow_router(shadow_inputs, shadow_cfg)
                _write_shadow(args.shadow_router_path, args.shadow_router_summary_path,
                              decisions, summary)
            except Exception as e:
                print(f"[predict] WARN shadow router failed ({type(e).__name__}: {e}); "
                      "official output unaffected")

    # Write submission.csv (qid,answer) and submission_time.csv (qid,answer,time = REAL per-sample s).
    Path(submission).parent.mkdir(parents=True, exist_ok=True)
    with open(submission, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["qid", "answer"])
        for qid, ans in rows:
            w.writerow([qid, ans])
    Path(submission_time).parent.mkdir(parents=True, exist_ok=True)
    with open(submission_time, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["qid", "answer", "time"])
        for (qid, ans), dt in zip(rows, times):
            w.writerow([qid, ans, f"{max(dt, 0.0):.6f}"])

    print(f"[predict] wrote {submission} ({len(rows)} rows)")
    print(f"[predict] wrote {submission_time} (total={round(sum(times), 3)}s)")

    # Legacy compatibility: explicit --output / $OUTPUT_FILE, and /output/pred.csv when writable.
    legacy_out = args.output or os.environ.get("OUTPUT_FILE")
    if legacy_out and _mirror(submission, legacy_out):
        print(f"[predict] mirrored -> {legacy_out} (legacy --output)")
    out_dir = Path("/output")
    if out_dir.is_dir() or _can_mkdir(out_dir):
        if _mirror(submission, "/output/pred.csv"):
            print("[predict] mirrored -> /output/pred.csv (legacy /output contract)")

    print("[predict] status: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
