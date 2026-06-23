#!/usr/bin/env python3
"""Final inference entrypoint (Phase 2L.31A).

Production default is OFFLINE, reproducible ``frozen_csv`` mode: it copies the frozen
current-best independent-v11 CSV to the requested output and validates it against the
dataset — no API, no v10. Other modes are explicit:
  * ``v11_independent`` — runs the independent v11 runner (needs --execute + budget; no v10);
  * ``v10`` — explicit fallback only (copies the locked v10 CSV; no API).

Never overwrites a protected/locked file (current-best v11, v10, v8, pred.csv) as its
output. Always validates row count / qid set / labels / columns. No qid hardcoding.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.data_io import load_dataset, read_predictions  # noqa: E402
from src.labels import is_valid_label  # noqa: E402

_DEFAULT_CONFIG = "configs/production_v13_multilayer_7970.json"
# Frozen/locked artifacts that must NEVER be written as an output by this entrypoint.
# NOTE: ``pred.csv`` is intentionally NOT protected — writing it is the explicit final
# export use case (`--output pred.csv`).
_PROTECTED_NAMES = {"pred_v13_multilayer_candidate_api30_from_v12b.csv",
                    "pred_v12b_permutation_candidate_api30.csv", "pred_v11_independent_rerun1.csv",
                    "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv"}
# Global MCQ label space when the input carries no choices (BTC qid-only CSV). The public
# test has 2–11 choices (labels A–K), so the frozen winner legitimately uses up to 'K';
# validating against A–H would wrongly reject valid 'I'/'J'/'K' answers.
_GLOBAL_LABELS = set("ABCDEFGHIJK")
# Input autodetect order (BTC: doc_public_test.csv / private_test.csv under /data first).
_INPUT_CANDIDATES = (
    "/data/doc_public_test.csv", "/data/private_test.csv",
    "/data/public-test.json", "/data/public-test_1780368312.json",
    "doc_public_test.csv", "private_test.csv",
    "public-test_1780368312.json", "public-test.json",
)


def _md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _repo_path(p):
    """Resolve a path: use as-is if it exists (cwd-relative or absolute), else fall back to
    the repo root. Lets `final_infer.py` be invoked from any working directory."""
    if p is None:
        return p
    if Path(p).exists():
        return p
    rooted = _ROOT / p
    return str(rooted) if rooted.exists() else p


def _resolve_input(explicit):
    """Resolve the test input path: --input -> $FASTMCQ_INPUT -> known names -> lone /data file."""
    if explicit:
        return explicit
    env = os.environ.get("FASTMCQ_INPUT")
    if env:
        return env
    for cand in _INPUT_CANDIDATES:
        if Path(cand).exists():
            return cand
    data = Path("/data")
    if data.is_dir():
        found = sorted([p for p in data.iterdir()
                        if p.suffix.lower() in (".csv", ".json")])
        if len(found) == 1:
            return str(found[0])
    raise SystemExit("REFUSING: no input found. Pass --input, set $FASTMCQ_INPUT, or place "
                     "doc_public_test.csv / private_test.csv / public-test*.json under /data "
                     "or the current directory.")


def _resolve_output(explicit):
    """Resolve the output path: --output -> $FASTMCQ_OUTPUT -> /output/pred.csv -> ./pred.csv."""
    if explicit:
        return explicit
    env = os.environ.get("FASTMCQ_OUTPUT")
    if env:
        return env
    out = Path("/output")
    if out.is_dir() or _can_create("/output"):
        return "/output/pred.csv"
    return "pred.csv"


def _can_create(path):
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def _load_config(path):
    p = Path(_repo_path(path))
    if not p.exists():
        raise SystemExit(f"REFUSING: config not found: {path}")
    return json.loads(p.read_text())


def _guard_output_name(output, *, allow_pred_csv=False):
    """Refuse to write a frozen/locked artifact (best v11 / v10 / v8). ``pred.csv`` is allowed
    as the explicit final export. ``allow_pred_csv`` is accepted for backward compatibility
    but is no longer required (kept as a harmless no-op)."""
    name = Path(output).name
    if name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite protected/locked file: {name} "
                         "(use a different --output)")


def _validate(output, dataset_path):
    """Validate the written CSV against the dataset. Raises SystemExit on any problem."""
    samples = load_dataset(dataset_path)
    rows = read_predictions(output)
    if not rows:
        raise SystemExit("REFUSING: output is empty")
    header = set(rows[0].keys())
    for col in ("qid", "answer"):
        if col not in header:
            raise SystemExit(f"REFUSING: output missing required column: {col}")
    by_qid = {s["qid"]: s for s in samples}
    pred_qids = [r["qid"] for r in rows]
    dups = sorted({q for q in pred_qids if pred_qids.count(q) > 1})
    if dups:
        raise SystemExit(f"REFUSING: duplicate qids in output: {dups[:10]}")
    missing = sorted(set(by_qid) - set(pred_qids))
    if missing:
        raise SystemExit(f"REFUSING: output missing {len(missing)} qids: {missing[:10]}")
    extra = sorted(set(pred_qids) - set(by_qid))
    if extra:
        raise SystemExit(f"REFUSING: output has {len(extra)} qids not in dataset: {extra[:10]}")
    if len(rows) != len(samples):
        raise SystemExit(f"REFUSING: row count {len(rows)} != dataset {len(samples)}")
    for r in rows:
        ans = r.get("answer")
        sample = by_qid[r["qid"]]
        has_choices = bool(sample.get("choices"))
        # Per-sample validation when choices are present; otherwise fall back to the global
        # A-H label space (BTC qid-only CSV carries no choices).
        ok = is_valid_label(ans, sample) if has_choices else (ans in _GLOBAL_LABELS)
        if not ans or not ok:
            raise SystemExit(f"REFUSING: invalid label {ans!r} for {r['qid']}")
    return len(rows)


def _copy_and_validate(source, output, dataset_path, label):
    src = Path(source)
    if not src.exists():
        raise SystemExit(f"REFUSING: {label} source CSV not found: {source}")
    outp = Path(output); outp.parent.mkdir(parents=True, exist_ok=True)
    # Validate the SOURCE first, then copy (so we never write an invalid file).
    _validate(source, dataset_path)
    shutil.copyfile(src, outp)
    n = _validate(output, dataset_path)
    return n


def _print_complete(mode, source, output, n, md5, elapsed, status):
    print("=" * 60)
    print("FINAL INFER COMPLETE")
    print(f"mode: {mode}")
    print(f"source: {source}")
    print(f"output: {output}")
    print(f"questions: {n}")
    print(f"md5: {md5}")
    print(f"elapsed_seconds: {round(elapsed, 3)}")
    print(f"status: {status}")
    print("=" * 60)


def _frozen_csv(args, config):
    """Return (mode_label, source, n_rows). Offline copy+validate of the frozen best CSV."""
    source = args.source_csv or config.get("current_best_csv")
    if not source:
        raise SystemExit("REFUSING: no frozen source CSV (pass --source-csv or set "
                         "current_best_csv in the config)")
    source = _repo_path(source)
    n = _copy_and_validate(source, args.output, args.input, "frozen_csv")
    return "frozen_csv", source, n


def _v10_fallback(args, config):
    """Return (mode_label, source, n_rows). Explicit v10 fallback copy (never the default)."""
    source = _repo_path(config.get("baseline_v10_csv"))
    n = _copy_and_validate(source, args.output, args.input, "v10")
    return "v10 (fallback only)", source, n


def _v11_independent(args, config):
    """Return (mode_label, source, n_rows). Regenerate via the independent runner (no v10)."""
    if not args.execute:
        raise SystemExit("REFUSING: v11_independent requires --execute (it spends API budget). "
                         "Use the default frozen_csv mode for a reproducible offline run.")
    if args.budget_usd is None:
        raise SystemExit("REFUSING: v11_independent requires an explicit --budget-usd.")
    spec = importlib.util.spec_from_file_location(
        "rv11", _ROOT / "scripts" / "run_full_v11_independent_submission.py")
    runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
    delegate = ["--input", args.input, "--output", args.output,
                "--model", args.model or config.get("model"),
                "--budget-usd", str(args.budget_usd), "--execute",
                "--i-understand-this-writes-outputs"]
    if args.resume:
        delegate += ["--resume"]
    if args.compare_pred:
        delegate += ["--compare-pred", args.compare_pred]   # report-only; never a base
    print("[final_infer] mode=v11_independent (no v10 base) -> delegating to independent runner")
    rc = runner.main(delegate)
    if rc != 0:
        raise SystemExit(f"v11_independent runner failed (rc={rc})")
    n = _validate(args.output, args.input)
    return "v11_independent", config.get("independent_runner"), n


def _public_qids(config):
    """The qid set of the public frozen best artifact (current_best_csv)."""
    src = _repo_path(config.get("current_best_csv"))
    if not Path(src).exists():
        return set(), src
    return {r["qid"] for r in read_predictions(src)}, src


def _public_replay(args, config):
    """Reproducibility-only: copy the public frozen best CSV, but ONLY when the input qid set
    exactly matches it. Fails clearly otherwise (never replays public answers onto unseen qids)."""
    public_qids, src = _public_qids(config)
    input_qids = {s["qid"] for s in load_dataset(args.input)}
    if not public_qids:
        raise SystemExit(f"REFUSING: public frozen artifact not found: {src}")
    if public_qids != input_qids:
        raise SystemExit(
            "REFUSING: public_replay requires the input qid set to EXACTLY match the public "
            f"frozen artifact ({len(public_qids)} qids); input has {len(input_qids)}. "
            "Use --mode dynamic_full for private/unseen inputs.")
    n = _copy_and_validate(src, args.output, args.input, "public_replay")
    return "public_replay", src, n


def _dynamic_full(args, config):
    """The real production system: run the full dynamic architecture over the given input."""
    from src.fastmcq_system import run_fastmcq_system, FastMCQSystemConfig
    samples = load_dataset(args.input)
    cfg = FastMCQSystemConfig(
        mode="dynamic_full", enable_v12b=args.enable_v12b, enable_v13=args.enable_v13,
        v12b_policy=args.v12b_policy, v12b_max_qids=args.v12b_max_qids,
        v12b_permutations=args.v12b_permutations, v13_max_qids=args.v13_max_qids,
        system_policy=args.system_policy, max_overrides=args.max_overrides,
        model=args.model or config.get("model"),
        budget_usd=args.budget_usd, execute_api=args.execute_api,
        work_dir=args.work_dir or "scratch/fastmcq_run", resume=args.resume)
    report = run_fastmcq_system(samples, args.output, cfg)
    print(f"[final_infer] base predictions : {report.base_predictions_count}")
    print(f"[final_infer] V12B enabled={report.v12b_enabled} executed={report.v12b_executed} "
          f"targets={report.v12b_targets} overrides={report.v12b_overrides}")
    print(f"[final_infer] V13 enabled={report.v13_enabled} executed={report.v13_executed} "
          f"targets={report.v13_targets} overrides={report.v13_overrides}")
    print(f"[final_infer] system overrides : {report.v12b_overrides + report.v13_overrides}")
    for w in report.warnings:
        print(f"[final_infer] warning: {w}")
    return "dynamic_full", "src.fastmcq_system", report.output_count


def _resolve_mode(args, config):
    """Resolve --mode auto. Never silently replays public answers onto private/unseen qids."""
    if args.mode != "auto":
        return args.mode
    if args.allow_public_replay:
        public_qids, _src = _public_qids(config)
        input_qids = {s["qid"] for s in load_dataset(args.input)}
        if public_qids and public_qids == input_qids:
            print("[final_infer] auto -> public_replay (qid set matches public artifact)")
            return "public_replay"
    print("[final_infer] auto -> dynamic_full")
    return "dynamic_full"


_PROFILES_PATH = "configs/run_profiles.json"
# Profile JSON key -> the CLI option strings that, if explicitly passed, override the profile.
_PROFILE_FLAGS = {
    "mode": ["--mode"],
    "allow_public_replay": ["--allow-public-replay"],
    "execute_api": ["--execute-api", "--no-api"],
    "enable_v12b": ["--enable-v12b", "--disable-v12b"],
    "enable_v13": ["--enable-v13", "--disable-v13"],
    "model": ["--model"],
    "budget_usd": ["--budget-usd"],
    "v12b_max_qids": ["--v12b-max-qids"],
    "v12b_permutations": ["--v12b-permutations"],
    "v12b_policy": ["--v12b-policy"],
    "v13_max_qids": ["--v13-max-qids"],
    "system_policy": ["--system-policy"],
    "max_overrides": ["--max-overrides"],
}


def _load_profiles():
    p = Path(_repo_path(_PROFILES_PATH))
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _apply_profile(args, raw_argv):
    """Apply a named run profile to args. CLI flags ALWAYS override profile values. Unknown
    profile fails clearly. Profiles cannot bypass model-policy (validated later in the layers)."""
    if not getattr(args, "profile", None):
        return
    profiles = _load_profiles()
    if args.profile not in profiles:
        raise SystemExit(f"REFUSING: unknown profile {args.profile!r}; "
                         f"available: {sorted(profiles)}")
    passed = list(raw_argv or [])

    def _explicit(flags):
        return any(tok == f or tok.startswith(f + "=") for tok in passed for f in flags)

    for key, val in profiles[args.profile].items():
        flags = _PROFILE_FLAGS.get(key)
        if flags is None:        # ignore unrecognized profile keys safely
            continue
        if not _explicit(flags):  # CLI flag wins
            setattr(args, key, val)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Final inference entrypoint (dynamic_full default)")
    ap.add_argument("--input", default=None,
                    help="test file; if omitted: $FASTMCQ_INPUT -> /data/private_test.* / doc_public_test.* etc.")
    ap.add_argument("--output", default=None,
                    help="output CSV; if omitted: $FASTMCQ_OUTPUT -> /output/pred.csv -> ./pred.csv")
    ap.add_argument("--profile", default=None,
                    help="named run profile from configs/run_profiles.json (CLI flags override it)")
    ap.add_argument("--mode", default="dynamic_full",
                    choices=["dynamic_full", "public_replay", "auto",
                             "frozen_csv", "v11_independent", "v10"])
    ap.add_argument("--allow-public-replay", action="store_true", default=False,
                    help="auto mode only: allow public_replay when input qids match the public artifact")
    ap.add_argument("--source-csv", default=None, help="frozen_csv only: explicit source CSV")
    ap.add_argument("--config", default=_DEFAULT_CONFIG)
    ap.add_argument("--model", default=None)
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--work-dir", default=None)
    # API gating for dynamic_full: no-api by default; --execute-api to call the model.
    ap.add_argument("--execute-api", dest="execute_api", action="store_true", default=False)
    ap.add_argument("--no-api", dest="execute_api", action="store_false")
    # V12B / V13 layer toggles.
    ap.add_argument("--enable-v12b", dest="enable_v12b", action="store_true", default=True)
    ap.add_argument("--disable-v12b", dest="enable_v12b", action="store_false")
    ap.add_argument("--v12b-max-qids", type=int, default=None)
    ap.add_argument("--v12b-permutations", type=int, default=6)
    ap.add_argument("--v12b-policy", choices=["conservative", "balanced"], default="conservative")
    ap.add_argument("--enable-v13", dest="enable_v13", action="store_true", default=True)
    ap.add_argument("--disable-v13", dest="enable_v13", action="store_false")
    ap.add_argument("--v13-max-qids", type=int, default=None)
    ap.add_argument("--system-policy", choices=["conservative", "balanced"], default="conservative")
    ap.add_argument("--max-overrides", type=int, default=None)
    # Legacy flags (v11_independent regeneration).
    ap.add_argument("--execute", action="store_true", default=False)
    ap.add_argument("--dry-run", action="store_true", default=False)
    ap.add_argument("--resume", action="store_true", default=False)
    ap.add_argument("--compare-pred", default=None, help="report-only; never a base")
    ap.add_argument("--allow-pred-csv", action="store_true", default=False,
                    help="deprecated no-op (kept for backward compatibility; pred.csv is allowed)")
    args = ap.parse_args(argv)
    # Apply named profile (CLI flags override); fails clearly on unknown profile.
    _apply_profile(args, argv if argv is not None else sys.argv[1:])

    t0 = time.perf_counter()
    try:
        config = _load_config(args.config)
        # Resolve I/O (no-arg BTC default: input from /data, output to /output/pred.csv).
        args.input = _resolve_input(args.input)
        args.output = _resolve_output(args.output)
        resolved = _resolve_mode(args, config)
        print(f"[final_infer] input detected: {args.input}")
        print(f"[final_infer] output: {args.output}")
        if args.profile:
            print(f"[final_infer] profile: {args.profile}")
        print(f"[final_infer] resolved mode: {resolved} "
              f"(api={'on' if args.execute_api else 'off'})")
        _guard_output_name(args.output)

        if args.dry_run:
            print("=" * 60)
            print(f"FINAL INFER — DRY-RUN (mode={resolved}; no write)")
            print(f"input: {args.input}")
            print(f"output (planned): {args.output}")
            print(f"elapsed_seconds: {round(time.perf_counter() - t0, 3)}")
            print("=" * 60)
            return 0

        if resolved == "dynamic_full":
            mode_label, source, n = _dynamic_full(args, config)
        elif resolved == "public_replay":
            mode_label, source, n = _public_replay(args, config)
        elif resolved == "frozen_csv":
            mode_label, source, n = _frozen_csv(args, config)
        elif resolved == "v10":
            mode_label, source, n = _v10_fallback(args, config)
        else:
            mode_label, source, n = _v11_independent(args, config)

        _print_complete(mode_label, source, args.output, n, _md5(args.output),
                        time.perf_counter() - t0, "PASS")
        return 0
    except BaseException as e:   # always surface elapsed time, even on failure
        print("=" * 60)
        print("FINAL INFER COMPLETE")
        if getattr(args, "profile", None):
            print(f"profile: {args.profile}")
        print(f"mode: {args.mode}")
        print(f"output: {args.output}")
        print(f"elapsed_seconds: {round(time.perf_counter() - t0, 3)}")
        print(f"status: FAIL ({type(e).__name__}: {e})")
        print("=" * 60)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
