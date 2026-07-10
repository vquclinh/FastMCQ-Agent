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


def _score_telemetry_record(predictor, item, qid, ans) -> dict:
    """Phase 1 shadow scoring: numeric/categorical diagnostics for one item.

    Observational only — it never affects ``ans`` or the official output, and it
    fails closed (any error is recorded, never raised). No question text is stored.
    """
    rec = {
        "qid": qid, "generated_answer": ans,
        "scored_top1": None, "scored_top2": None,
        "scores_by_label": {}, "probabilities_by_label": {},
        "logit_margin": None, "probability_margin": None, "normalized_entropy": None,
        "generated_vs_scored_agree": None,
        "scoring_method": None, "scoring_valid": False, "scoring_error": None,
        "elapsed_sec": 0.0,
    }
    score_fn = getattr(predictor, "score_choices", None)
    if not callable(score_fn):
        rec["scoring_error"] = "predictor_has_no_score_choices"
        return rec
    t0 = time.time()
    try:
        d = score_fn(item).as_dict()
        rec.update({
            "scored_top1": d["top1_label"], "scored_top2": d["top2_label"],
            "scores_by_label": d["scores_by_label"],
            "probabilities_by_label": d["probabilities_by_label"],
            "logit_margin": d["logit_margin"], "probability_margin": d["probability_margin"],
            "normalized_entropy": d["normalized_entropy"], "scoring_method": d["scoring_method"],
            "scoring_valid": d["valid"], "scoring_error": d["error"],
            "generated_vs_scored_agree": (bool(d["valid"]) and ans == d["top1_label"]),
        })
    except Exception as e:                       # telemetry must never break a submission
        rec["scoring_error"] = f"{type(e).__name__}: {e}"
    rec["elapsed_sec"] = round(time.time() - t0, 6)
    return rec


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
        if args.confidence_telemetry:
            print("[predict] confidence-telemetry: ON (shadow scoring; answers unchanged)")
        samples = load_dataset(inp)
        predictor = _build_predictor(args)
        rows, times = [], []
        telemetry = [] if args.confidence_telemetry else None
        failures = 0
        for item in samples:
            qid = item.get("qid")
            t0 = time.time()
            try:
                raw = predictor.predict_one(item)
                ans = _coerce_label(raw, item)
                if raw is None or str(raw).strip().upper() != ans:
                    failures += 1   # model gave nothing usable -> deterministic fallback
            except Exception as e:  # one bad sample must not abort the run
                ans = _fallback_answer(item)
                failures += 1
                print(f"[predict] WARN qid={qid} fell back ({type(e).__name__}: {e})")
            dt = time.time() - t0                 # official per-sample time = generation only
            rows.append((qid, ans))
            times.append(dt)
            if telemetry is not None:             # shadow scoring, measured separately
                telemetry.append(_score_telemetry_record(predictor, item, qid, ans))
        print(f"[predict] predicted {len(rows)} samples ({failures} fell back to deterministic)")
        if telemetry is not None:
            _write_telemetry(args.telemetry_path, telemetry)

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
