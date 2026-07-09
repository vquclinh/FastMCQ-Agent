"""FastMCQ dynamic system orchestrator.

The real production architecture: runs a full dynamic pipeline over ANY input (public, private,
unseen, larger sets) and outputs predictions for EXACTLY the input qids. It never depends on
public-test qids and never requires the public frozen CSV (that is only for public_replay).

Pipeline: validate -> dynamic base predictions -> per-qid metadata -> V12B target selection ->
V12B layer -> V13 layers -> system selector -> assemble + validate -> write CSV.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from src.utils.data_io import write_predictions
from src.utils.labels import is_valid_label, labels_for
from src.base.dynamic_base_predictor import predict_base_answers, base_prediction_is_valid
from src.layers.v12b_dynamic_layer import select_v12b_targets, run_v12b_layer
from src.layers.v13_dynamic_layer import select_v13_targets, run_v13_layer
from src.selector.system_candidate_selector import select_system_overrides
from src.local_model.local_qwen_backend import DEFAULT_MODEL_PATH, get_local_qwen_backend

_GLOBAL_LABELS = set("ABCDEFGHIJK")


def _log(msg):
    print(msg, flush=True)


def _write_progress(work_dir, stage, **fields):
    """Best-effort monitoring file <work_dir>/progress.json. Never required for correctness."""
    try:
        p = Path(work_dir); p.mkdir(parents=True, exist_ok=True)
        rec = {"stage": stage, "timestamp": datetime.now(timezone.utc).isoformat(), **fields}
        (p / "progress.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    except Exception:
        pass   # monitoring only — must not break the run


@dataclass
class FastMCQSystemConfig:
    mode: str = "dynamic_full"
    base_mode: str = "dynamic"
    enable_v12b: bool = True
    enable_v13: bool = True   # promoted to official architecture layer in 2L.38A (V13 79.7)
    v12b_policy: str = "conservative"
    v12b_max_qids: int | None = None
    v12b_permutations: int = 6
    v13_max_qids: int | None = None
    # Raw flag spec ('auto' / 'all' / an int string) the resolved cap came from — used only to
    # format the [FASTMCQ] log (e.g. 'auto(250/2000)' vs 'all(2000)' vs '50'). None -> infer.
    v12b_max_qids_source: str | None = None
    v13_max_qids_source: str | None = None
    system_policy: str = "conservative"
    max_overrides: int | None = None
    profile: str | None = None
    model_path: str | None = DEFAULT_MODEL_PATH
    device: str = "auto"
    max_new_tokens: int = 64
    layer_max_new_tokens: int = 768
    local_backend: object | None = None
    work_dir: str = "scratch/fastmcq_run"
    resume: bool = False


@dataclass
class FastMCQSystemReport:
    input_count: int
    output_count: int
    resolved_mode: str
    base_predictions_count: int
    v12b_enabled: bool
    v12b_executed: bool
    v12b_targets: int
    v12b_overrides: int
    v13_enabled: bool
    v13_executed: bool
    v13_targets: int
    v13_overrides: int
    output_csv: str
    output_md5: str
    warnings: list = field(default_factory=list)
    status: str = "PASS"


def _md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _fmt_cap(resolved, source, n):
    """Render a max-qids cap for the [FASTMCQ] log.
    'auto' -> 'auto(<cap>/<N>)' (cap = resolved int, or N if unbounded); None -> 'all(<N>)';
    an int -> the int as-is."""
    if (source or "").strip().lower() == "auto":
        cap = resolved if resolved is not None else n
        return f"auto({cap}/{n})"
    if resolved is None:
        return f"all({n})"
    return str(resolved)


def _label_valid(answer, sample):
    choices = sample.get("choices") or []
    if not choices:
        return answer in _GLOBAL_LABELS
    return is_valid_label(answer, sample)


def run_fastmcq_system(samples, output_csv, config: FastMCQSystemConfig) -> FastMCQSystemReport:
    warnings = []
    # 1) Validate input.
    if not samples:
        raise ValueError("REFUSING: empty input samples")
    qids = [s.get("qid") for s in samples]
    if any(not q for q in qids):
        raise ValueError("REFUSING: a sample is missing 'qid'")
    if len(set(qids)) != len(qids):
        raise ValueError("REFUSING: duplicate qids in input")

    wd = config.work_dir
    backend = config.local_backend or get_local_qwen_backend(
        config.model_path, device=config.device, default_max_new_tokens=config.max_new_tokens)
    # max-qids display: 'auto' -> auto(<cap>/<N>); None -> all(<N>); an int -> the int.
    # (Never a hardcoded size — 'auto' caps derive from the input count: ceil(N/8), min 1.)
    v12b_cap = _fmt_cap(config.v12b_max_qids, config.v12b_max_qids_source, len(samples))
    v13_cap = _fmt_cap(config.v13_max_qids, config.v13_max_qids_source, len(samples))
    _log(f"[FASTMCQ] input_count={len(samples)} output={output_csv} work_dir={wd} "
         f"mode={config.mode} profile={config.profile or '-'} "
         f"local_model={config.model_path or DEFAULT_MODEL_PATH} "
         f"v12b_max_qids={v12b_cap} v13_max_qids={v13_cap} "
         f"public_replay=disabled")

    try:
        # 2) Dynamic base predictions (arbitrary qids; no public frozen CSV).
        _write_progress(wd, "base_start", input_count=len(samples), output=str(output_csv),
                        local_model=str(config.model_path or DEFAULT_MODEL_PATH))
        base = predict_base_answers(
            samples, model_path=config.model_path, local_backend=backend,
            max_new_tokens=config.max_new_tokens, work_dir=config.work_dir, resume=config.resume)
        _write_progress(wd, "base_done", base_predictions=len(base),
                        base_local_model_calls=sum(1 for b in base if b.source == "dynamic_local_qwen"))
        answers = {}
        for bp, s in zip(base, samples):
            if not base_prediction_is_valid(bp, s):
                warnings.append(f"base prediction invalid for {bp.qid}; coerced to a valid label")
                choices = s.get("choices") or []
                bp.answer = "A" if not choices else labels_for(len(choices))[0]
            answers[bp.qid] = bp.answer

        # 4/5) V12B target selection + layer (official).
        v12b_targets, v12b_results, v12b_executed = [], [], False
        if config.enable_v12b:
            v12b_targets = select_v12b_targets(samples, base, max_qids=config.v12b_max_qids)
            _write_progress(wd, "v12b_start", v12b_targets=len(v12b_targets))
            v12b_results = run_v12b_layer(
                samples, base, v12b_targets, model_path=config.model_path, local_backend=backend,
                max_new_tokens=config.layer_max_new_tokens, permutations=config.v12b_permutations,
                policy=config.v12b_policy, work_dir=config.work_dir, resume=config.resume)
            v12b_executed = bool(v12b_targets)
            _write_progress(wd, "v12b_done", v12b_targets=len(v12b_targets),
                            v12b_results=len(v12b_results))

        # 6) V13 multi-layer.
        v13_targets, v13_results, v13_executed = [], [], False
        if config.enable_v13:
            v13_targets = select_v13_targets(samples, base, max_qids=config.v13_max_qids)
            _write_progress(wd, "v13_start", v13_targets=len(v13_targets))
            v13_results = run_v13_layer(
                samples, base, v13_targets, model_path=config.model_path, local_backend=backend,
                max_new_tokens=config.layer_max_new_tokens,
                work_dir=config.work_dir, resume=config.resume)
            v13_executed = bool(v13_targets)
            _write_progress(wd, "v13_done", v13_targets=len(v13_targets),
                            v13_results=len(v13_results))

        # 7) Unified conservative selector over V12B + V13, on top of base predictions.
        decisions = select_system_overrides(
            samples, base, v12b_results, v13_results,
            policy=config.system_policy, max_overrides=config.max_overrides)
        by_qid = {s["qid"]: s for s in samples}
        v12b_overrides = v13_overrides = 0
        for d in decisions:
            if d.accept and d.proposed_answer and _label_valid(d.proposed_answer, by_qid[d.qid]):
                answers[d.qid] = d.proposed_answer
                if "v12b" in d.source_layers:
                    v12b_overrides += 1
                if any(x in d.source_layers for x in
                       ("programmatic_solver", "content_first", "least_to_most")):
                    v13_overrides += 1
        _log(f"[SELECTOR] done overrides={v12b_overrides + v13_overrides}")
        _write_progress(wd, "selector_done", overrides=v12b_overrides + v13_overrides)

        # 8) Assemble + validate output (exactly input qids).
        rows = [{"qid": s["qid"], "answer": answers[s["qid"]]} for s in samples]
        if [r["qid"] for r in rows] != qids:
            raise ValueError("REFUSING: output qid order/set differs from input")
        for r in rows:
            s = next(x for x in samples if x["qid"] == r["qid"])
            if not r["answer"] or not _label_valid(r["answer"], s):
                raise ValueError(f"REFUSING: invalid label {r['answer']!r} for {r['qid']}")

        # 9) Write.
        outp = Path(output_csv); outp.parent.mkdir(parents=True, exist_ok=True)
        write_predictions(rows, output_csv)
        _log(f"[FASTMCQ] output_written path={outp}")
        _write_progress(wd, "output_written", output=str(outp), output_md5=_md5(outp),
                        rows=len(rows))
    except BaseException as e:                       # best-effort failure marker
        _write_progress(wd, "failed", error=f"{type(e).__name__}: {e}")
        raise

    return FastMCQSystemReport(
        input_count=len(samples), output_count=len(rows), resolved_mode=config.mode,
        base_predictions_count=len(base), v12b_enabled=config.enable_v12b,
        v12b_executed=v12b_executed, v12b_targets=len(v12b_targets),
        v12b_overrides=v12b_overrides, v13_enabled=config.enable_v13,
        v13_executed=v13_executed, v13_targets=len(v13_targets),
        v13_overrides=v13_overrides, output_csv=str(outp), output_md5=_md5(outp),
        warnings=warnings, status="PASS")
