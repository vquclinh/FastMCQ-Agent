"""Shared helpers for adaptive proposal/calibration scripts (no network at import).

Centralizes: protected-file guarding, base-prediction / base-log / risk-CSV loading,
and the single **override gate** used by every branch runner. Keeping the gate in one
tested place is a safety invariant — a proposal is applied ONLY when every condition
holds AND ``allow_override`` is explicitly enabled. No qid logic, no external answer
sheet, no API.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# Frozen prediction files a calibration script must never overwrite.
PROTECTED_PRED = {
    "pred.csv", "pred_v2_calc_rerank.csv",
    "pred_v6_qwen_rerank_calc_verifier.csv",
    "pred_v6b_qwen_rerank_calc_verifier_fast.csv",
    "pred_v7_programmatic_assist_from_v6b.csv",
}


def guard_output(path) -> None:
    if Path(path).name in PROTECTED_PRED:
        raise SystemExit(f"REFUSING to write protected file: {path}")


def load_samples(path) -> list:
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def load_pred(path) -> dict:
    out = {}
    if path and Path(path).exists():
        for row in csv.DictReader(open(path)):
            out[row["qid"]] = row.get("answer")
    return out


def load_log(path) -> dict:
    out = {}
    if path and Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line:
                o = json.loads(line)
                if o.get("qid"):
                    out[o["qid"]] = o
    return out


def load_risk_priority(path) -> dict:
    """qid -> 'P0'/'P1' from the first-100 risk CSV (prioritization/reporting only)."""
    out = {}
    if path and Path(path).exists():
        for r in csv.DictReader(open(path)):
            if r.get("priority") in ("P0", "P1"):
                out[r.get("qid")] = r["priority"]
    return out


def override_gate(proposal: dict, current: str, labels, *, allow_override: bool,
                  min_confidence: float = 0.90,
                  uncertain_values=("uncertain", None, "")) -> bool:
    """The single override gate shared by all branch runners.

    Returns True (apply override) ONLY when ALL hold:
      allow_override is True, should_override is true, selected_answer is a valid
      label, selected_answer != current, confidence >= min_confidence, reason is
      non-empty, and evidence_type is not an "uncertain" value.
    """
    if not allow_override:
        return False
    sel = proposal.get("selected_answer")
    try:
        conf = float(proposal.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.0
    return bool(proposal.get("should_override")
                and sel in labels and sel != current
                and conf >= min_confidence
                and str(proposal.get("reason") or "").strip()
                and proposal.get("evidence_type") not in uncertain_values)


def write_jsonl(path, records) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_csv(path, rows, fields) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
