#!/usr/bin/env python3
"""Phase 2L.35A — Unified V13 multi-layer plan builder (OFFLINE, no API).

Assigns one or more reasoning layers to each qid of the frozen v11 winner and ranks by
opportunity. Layers: ``programmatic_solver`` (numeric/formula), ``content_first`` (label-error
avoidance), ``least_to_most`` (multi-condition elimination). Changes no answer.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.utils.data_io import load_dataset, read_predictions  # noqa: E402
from src.layers.programmatic_solver_layer import classify_programmatic_domain, extract_numeric_values  # noqa: E402

_FALLBACK_SOURCES = {"direct_fallback", "direct_fallback_repair"}
_MULTI_COND_HINTS = ("đúng", "sai", "phát biểu", "chọn câu", "không đúng", "ngoại trừ",
                     "statement", "which of the following", "true", "false", "except")


def _read_csv_map(path, key, val):
    out = {}
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get(key):
                    out[row[key]] = row.get(val)
    return out


def _read_decisions(path):
    out = {}
    if path and Path(path).exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("qid"):
                    out[row["qid"]] = row
    return out


def _read_jsonl_by_qid(path, qid_key=("qid", "original_qid")):
    out = defaultdict(list)
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                qid = next((rec[k] for k in qid_key if rec.get(k)), None)
                if qid:
                    out[qid].append(rec)
    return out


def _multi_condition(question):
    q = (question or "").lower()
    return any(h in q for h in _MULTI_COND_HINTS)


def build_plan(samples, current, *, v10=None, decisions=None, candidates=None, v12b=None):
    v10 = v10 or {}
    decisions = decisions or {}
    candidates = candidates or {}
    v12b = v12b or {}
    plan = []
    for s in samples:
        qid = s["qid"]
        choices = s.get("choices") or []
        n = len(choices)
        cur = current.get(qid, "")
        dec = decisions.get(qid, {})
        source = (dec.get("final_source") or "").strip()
        route = (dec.get("route") or "").strip()
        risk = (dec.get("risk") or "").strip().lower()
        q = s.get("question") or ""

        layers, reasons, score = set(), [], 0.0
        if source in _FALLBACK_SOURCES:
            score += 5.0; reasons.append(f"fallback_source:{source}")
        if risk == "high":
            score += 3.0; reasons.append("risk:high")
        elif risk == "medium":
            score += 1.0; reasons.append("risk:medium")
        v10_ans = (v10.get(qid) or "").strip()
        if v10_ans and cur and v10_ans != cur:
            score += 2.0; reasons.append(f"v11!=v10({cur}vs{v10_ans})")

        # v12B signal (unstable / strong non-current mapped votes).
        v12b_recs = [r for r in v12b.get(qid, []) if r.get("valid")]
        if v12b_recs:
            from collections import Counter
            votes = Counter(r.get("mapped_original_label") for r in v12b_recs)
            non_cur = {l: c for l, c in votes.items() if l and l != cur}
            if non_cur and max(non_cur.values()) >= 3:
                score += 2.0; reasons.append("v12b_strong_noncurrent")

        # Programmatic layer: numeric/formula domains.
        domain = classify_programmatic_domain(s)
        if domain in ("arithmetic", "economics", "geometry", "binary") or route == "calculation":
            layers.add("programmatic_solver")
            if extract_numeric_values(q):
                reasons.append(f"numeric:{domain}")
        # Content-first: always useful where label errors are likely (knowledge/long routes,
        # many options, fallback).
        if route in ("short_knowledge", "long_context", "ambiguous", "law_admin") or n >= 5 \
                or source in _FALLBACK_SOURCES:
            layers.add("content_first")
        # Least-to-most: multi-condition / statement-selection style.
        if _multi_condition(q) or route in ("law_admin", "long_context") or n >= 5:
            layers.add("least_to_most")
            if _multi_condition(q):
                reasons.append("multi_condition")
        if n >= 5:
            score += 1.0; reasons.append(f"option_count:{n}")

        if not layers:                       # ensure at least one layer
            layers.add("content_first")
        needs_api = True                     # all three layers prompt the model
        plan.append({
            "qid": qid, "current_answer": cur, "route": route,
            "target_layers": "|".join(sorted(layers)),
            "priority_score": round(score, 3),
            "reason": ";".join(reasons) if reasons else "baseline",
            "needs_api": "true" if needs_api else "false",
            "notes": (dec.get("note") or "")[:140],
        })
    plan.sort(key=lambda r: (-r["priority_score"], r["qid"]))
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V13 multi-layer plan builder (offline)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--v10", default=None)
    ap.add_argument("--decisions", default=None)
    ap.add_argument("--candidates", default=None)
    ap.add_argument("--v12b-records", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-score", type=float, default=0.0)
    args = ap.parse_args(argv)

    samples = load_dataset(args.input)
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    v10 = _read_csv_map(args.v10, "qid", "answer")
    decisions = _read_decisions(args.decisions)
    candidates = _read_jsonl_by_qid(args.candidates)
    v12b = _read_jsonl_by_qid(args.v12b_records)

    plan = build_plan(samples, current, v10=v10, decisions=decisions,
                      candidates=candidates, v12b=v12b)
    emitted = [r for r in plan if r["priority_score"] > args.min_score]

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    cols = ["qid", "current_answer", "route", "target_layers", "priority_score",
            "reason", "needs_api", "notes"]
    with outp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(emitted)

    from collections import Counter
    layer_counts = Counter()
    for r in emitted:
        for lyr in r["target_layers"].split("|"):
            layer_counts[lyr] += 1
    print("=" * 60)
    print("V13 MULTI-LAYER PLAN (offline, no API)")
    print(f"input questions  : {len(samples)}")
    print(f"planned (>{args.min_score})  : {len(emitted)} / {len(plan)}")
    print(f"layer assignments: {dict(layer_counts)}")
    print(f"output           : {outp}")
    for r in emitted[:8]:
        print(f"  {r['qid']} score={r['priority_score']:<5} [{r['target_layers']}] {r['reason'][:48]}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
