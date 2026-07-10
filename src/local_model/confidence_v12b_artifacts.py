"""Phase 3A-1 observational V12B shadow: selected-record validation, safe
result pairing, and privacy-safe artifact writing.

This module is the integration boundary between the Phase 2 shadow router and the
approved, write-free Phase 3A-0 runner (`confidence_v12b_runner`). It is
OBSERVATIONAL ONLY: it never changes a generated answer or the official CSV, never
runs V13/selector/legacy code, and never persists question/choice/prompt/response
text. It imports no torch/transformers.

Identity contract (AUDIT 87 §10): the authoritative per-record identity is the
``source_record_ordinal`` = ``enumerate(samples)`` index, which equals the router
decision-list position. ``router_selected_rank`` is risk-rank metadata only.
``selected_sequence_ordinal`` is the position among valid selected inputs passed to
the runner. The runner's own ``record_ordinal`` is runner-local (nested under
``aggregate``) and is NEVER used as the record's global identity. Records are paired
with runner results by list position only, never by qid/input_index.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from src.local_model.confidence_v12b_runner import V12BRunInput, run_v12b_for_selected
from src.utils.labels import is_valid_label, labels_for

# Closed, privacy-safe input-validation codes (no text, no exception strings).
VALIDATION_OK = "ok"
VALIDATION_CODES = (
    "ok",
    "invalid_record_shape",
    "invalid_question",
    "invalid_choices",
    "unsupported_choice_count",
    "invalid_canonical_labels",
    "invalid_base_answer",
    "invalid_score_diagnostic",
    "invalid_router_rank",
    "input_validation_error",
)

# Choice-count contract (AUDIT 87 §12): scorer needs >= 2 labels; labels_for caps 26.
_MIN_CHOICES = 2
_MAX_CHOICES = 26


def _finite_or_none(value: Any) -> bool:
    if value is None:
        return True
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _validation_code(sample: Any, decision: Any) -> str:
    """Return a closed validation code for one router-selected record. 'ok' means the
    record is safe to build a V12BRunInput for; any other code means skip V12B."""
    try:
        if not isinstance(sample, dict):
            return "invalid_record_shape"
        question = sample.get("question")
        if not isinstance(question, str) or not question.strip():
            return "invalid_question"
        choices = sample.get("choices")
        if isinstance(choices, (str, bytes)) or not isinstance(choices, (list, tuple)):
            return "invalid_choices"
        n = len(choices)
        if n < _MIN_CHOICES or n > _MAX_CHOICES:
            return "unsupported_choice_count"
        # canonical labels are derived; guard the derivation itself.
        try:
            labels_for(n)
        except ValueError:
            return "invalid_canonical_labels"
        base_answer = decision.generated_answer
        if base_answer is None or not is_valid_label(str(base_answer), sample):
            return "invalid_base_answer"
        for lab in (decision.top1, decision.top2):
            if lab is not None and not is_valid_label(str(lab), sample):
                return "invalid_score_diagnostic"
        if not _finite_or_none(decision.logit_margin) or not _finite_or_none(decision.normalized_entropy):
            return "invalid_score_diagnostic"
        rank = decision.selected_rank
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            return "invalid_router_rank"
        return VALIDATION_OK
    except Exception:
        return "input_validation_error"


def _build_input(sample: dict, decision: Any) -> V12BRunInput:
    choices = tuple(str(c) for c in sample.get("choices") or [])
    return V12BRunInput(
        qid=str(sample.get("qid")),
        input_index=int(decision.input_index),
        question=str(sample.get("question")),
        choices=choices,
        canonical_labels=tuple(labels_for(len(choices))),
        base_answer=str(decision.generated_answer),
        router_selected_rank=int(decision.selected_rank),
        router_candidate_reasons=tuple(str(r) for r in (decision.candidate_reasons or ())),
        base_top1=decision.top1,
        base_top2=decision.top2,
        base_logit_margin=decision.logit_margin,
        base_normalized_entropy=decision.normalized_entropy,
    )


def _wrapper_row(entry: dict) -> dict:
    """Privacy-safe per-record wrapper metadata (no question/choice text)."""
    decision = entry["decision"]
    return {
        "observational_only": True,
        "source_record_ordinal": entry["source_record_ordinal"],
        "selected_sequence_ordinal": entry.get("selected_sequence_ordinal"),
        "qid": str(decision.qid),
        "input_index": decision.input_index,
        "router_selected_rank": decision.selected_rank,
        "router_candidate_reasons": [str(r) for r in (decision.candidate_reasons or ())],
        "base_answer": decision.generated_answer,
        "base_top1": decision.top1,
        "base_top2": decision.top2,
        "base_logit_margin": decision.logit_margin,
        "base_normalized_entropy": decision.normalized_entropy,
        "official_answer_source": "base",
    }


def build_selected_entries(samples, decisions) -> tuple[list[dict], list[dict]]:
    """Split router-selected records (in input order) into valid and invalid entries.

    ``decisions`` is one-per-record in input order, so index == source_record_ordinal.
    Valid entries are assigned a contiguous ``selected_sequence_ordinal`` (their
    position among the valid inputs later passed to the runner)."""
    selected: list[dict] = []
    for source_ordinal, decision in enumerate(decisions):
        if not getattr(decision, "selected", False):
            continue
        sample = samples[source_ordinal] if source_ordinal < len(samples) else None
        code = _validation_code(sample, decision)
        selected.append({
            "source_record_ordinal": source_ordinal,
            "decision": decision,
            "sample": sample,
            "code": code,
        })
    valid = [e for e in selected if e["code"] == VALIDATION_OK]
    for seq, entry in enumerate(valid):
        entry["selected_sequence_ordinal"] = seq
        entry["v12b_input"] = _build_input(entry["sample"], entry["decision"])
    invalid = [e for e in selected if e["code"] != VALIDATION_OK]
    return selected, valid  # selected keeps input order (valid+invalid interleaved)


def _build_records(selected: list[dict], results) -> list[dict]:
    """Assemble per-record JSONL rows in input order, pairing valid entries with
    runner results by list position only (never by qid/input_index)."""
    rows: list[dict] = []
    for entry in selected:
        row = _wrapper_row(entry)
        row["input_validation_status"] = entry["code"]
        if entry["code"] == VALIDATION_OK:
            aggregate = results[entry["selected_sequence_ordinal"]]
            row["v12b_attempted"] = True
            row["aggregate"] = aggregate.as_dict()   # text-free; nests runner-local record_ordinal
        else:
            row["v12b_attempted"] = False
            row["selected_sequence_ordinal"] = None
        rows.append(row)
    return rows


def _build_summary(samples, decisions, selected, valid, results, run_summary) -> dict:
    invalid = [e for e in selected if e["code"] != VALIDATION_OK]
    validation_counts: dict[str, int] = {}
    for entry in selected:
        validation_counts[entry["code"]] = validation_counts.get(entry["code"], 0) + 1
    candidate_count = sum(1 for d in decisions if getattr(d, "candidate", False))
    # selected items in risk-rank order, each carrying the authoritative source ordinal.
    selected_items = sorted(
        (
            {
                "qid": str(e["decision"].qid),
                "input_index": e["decision"].input_index,
                "selected_rank": e["decision"].selected_rank,
                "source_record_ordinal": e["source_record_ordinal"],
            }
            for e in selected
        ),
        key=lambda it: (it["selected_rank"] is None, it["selected_rank"]),
    )
    rs = run_summary.as_dict()
    return {
        "observational_only": True,
        "total_input_records": len(samples),
        "total_router_candidates": candidate_count,
        "total_router_selected": len(selected),
        "total_v12b_attempted": rs["attempted_records"],
        "total_v12b_skipped_invalid": len(invalid),
        "total_v12b_failed": rs["failed_records"],
        "total_permutation_attempts": rs["total_permutation_attempts"],
        "total_valid_permutations": rs["total_valid_permutations"],
        "parse_failure_total": rs["parse_failure_total"],
        "generation_failure_total": rs["generation_failure_total"],
        "input_validation_error_counts": validation_counts,
        "aggregate_status_counts": rs["aggregate_status_counts"],
        "base_v12b_disagreement_count": rs["base_v12b_disagreement_count"],
        "selected_qids": [it["qid"] for it in selected_items],
        "selected_items": selected_items,
        "note": ("observational V12B shadow; official answer is always Base; provisional "
                 "statuses/thresholds are NOT final; selected_qids is risk-rank order and may "
                 "contain duplicate qids — use source_record_ordinal for record identity"),
    }


def _write_json_atomic(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def run_and_write_v12b_shadow(*, samples, decisions, router_summary, backend, v12b_config,
                              jsonl_path, summary_path) -> dict:
    """Run the Phase 3A-0 runner on router-selected+valid records and write privacy-safe
    JSONL + summary artifacts. Two independently atomic files, each failing closed with a
    class-name-only warning. Never changes official output. Returns a per-file status dict."""
    selected, valid = build_selected_entries(samples, decisions)

    results, run_summary = run_v12b_for_selected(
        [entry["v12b_input"] for entry in valid],
        backend=backend,
        permutation_count=int(v12b_config.permutation_count),
    )
    if len(results) != len(valid):        # positional pairing invariant (AUDIT 87 §11)
        raise AssertionError("v12b result count does not match valid selected-input count")

    records = _build_records(selected, results)
    summary = _build_summary(samples, decisions, selected, valid, results, run_summary)

    status = {"jsonl_written": False, "summary_written": False}
    try:
        lines = [json.dumps(r, ensure_ascii=False, allow_nan=False) for r in records]
        _write_json_atomic(jsonl_path, ("\n".join(lines) + "\n") if lines else "")
        status["jsonl_written"] = True
    except (OSError, ValueError, TypeError) as e:
        print(f"[predict] WARN v12b shadow JSONL not written ({type(e).__name__})")
    try:
        _write_json_atomic(
            summary_path,
            json.dumps(summary, ensure_ascii=False, allow_nan=False, indent=2),
        )
        status["summary_written"] = True
    except (OSError, ValueError, TypeError) as e:
        print(f"[predict] WARN v12b shadow summary not written ({type(e).__name__})")

    print(f"[predict] v12b shadow -> {jsonl_path} ({len(records)} records; "
          f"attempted={run_summary.attempted_records}, "
          f"skipped_invalid={len(selected) - len(valid)})")
    return status
