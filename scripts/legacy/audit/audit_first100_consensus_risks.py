#!/usr/bin/env python3
"""First-100 consensus RISK audit (diagnostic only; no overrides, no ground truth).

Compares our v6 and v6b predictions against an EXTERNAL 3-model answer sheet
(Gemini / ChatGPT / Claude, in column order; optional 4th column = old v6) for the
first 100 public-test samples (aligned by file order). It flags qids where the
external models agree but we differ, joins the v6b trace fields, and proposes
GENERALIZABLE root-cause categories.

CRITICAL: the external sheet is a RISK SIGNAL, NOT ground truth. This script never
writes it into the pipeline, never hardcodes a qid->answer table, and proposes no
answer overrides. It only reports.

If --external-sheet is missing/not provided, the script explains what is needed and
exits 0 without inventing any answers.

Usage:
    python scripts/audit_first100_consensus_risks.py \
      --public-test public-test_1780368312.json \
      --external-sheet <first100_external_sheet.csv> \
      --v6 output/pred_v6_qwen_rerank_calc_verifier.csv \
      --v6-log output/run_v6_qwen_rerank_calc_verifier.jsonl \
      --v6b output/pred_v6b_qwen_rerank_calc_verifier_fast.csv \
      --v6b-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --output output/first100_consensus_risk_audit.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

_LABEL_RE = re.compile(r"[A-K]")


def _norm_label(s):
    if s is None:
        return ""
    m = _LABEL_RE.search(str(s).strip().upper())
    return m.group(0) if m else ""


def _load_public_qids(path):
    data = json.loads(Path(path).read_text())
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    return [r.get("qid") for r in rows]


def _load_pred_csv(path):
    out = {}
    if not path or not Path(path).exists():
        return out
    for row in csv.reader(open(path)):
        if not row or row[0].lower() == "qid":
            continue
        out[row[0]] = _norm_label(row[1]) if len(row) > 1 else ""
    return out


def _load_log(path):
    """qid -> trace dict (last occurrence wins). Skips the _summary row."""
    out = {}
    if not path or not Path(path).exists():
        return out
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("qid"):
            out[obj["qid"]] = obj
    return out


def _load_external_sheet(path):
    """Return list of rows; each row = (gemini, gpt, claude, old_v6_or_None).

    Detects and skips a header row. Accepts 3 or 4 columns.
    """
    rows = []
    raw = list(csv.reader(open(path)))
    if not raw:
        return rows
    # Header detection: a row whose first cell is not a bare label letter.
    start = 0
    head = " ".join(raw[0]).lower()
    if any(k in head for k in ("gemini", "gpt", "claude", "chatgpt", "v6", "answer")):
        start = 1
    for r in raw[start:]:
        if not r or not any(c.strip() for c in r):
            continue
        g = _norm_label(r[0]) if len(r) > 0 else ""
        p = _norm_label(r[1]) if len(r) > 1 else ""
        c = _norm_label(r[2]) if len(r) > 2 else ""
        v = _norm_label(r[3]) if len(r) > 3 else None
        rows.append((g, p, c, v))
    return rows


def _majority(labels):
    """(modal_label_or_'', count) over non-empty labels; '' if no clear modal."""
    vals = [x for x in labels if x]
    if not vals:
        return "", 0
    ct = Counter(vals)
    top, n = ct.most_common(1)[0]
    return top, n


def _root_cause(row, ext_majority):
    route = row.get("route")
    if row.get("parsed_answer_error") == "no_json" or row.get("parsed_answer_source") == "partial_answer_key":
        return ("prompt_schema_issue",
                "Output JSON was malformed/recovered; tighten prompt/max-tokens; verify v6b enum schema took effect.")
    if route == "calculation":
        if row.get("calculation_safe_to_override"):
            return ("calculation_possibly_wrong",
                    f"Re-check calc family '{row.get('calculation_method')}' extraction/formula; add a synthetic regression test for this pattern.")
        return ("calculation_solver_missing_formula",
                "No calc family matched a calculation-routed item; consider a new generic formula family (see CALCULATION_TAXONOMY.md).")
    if route == "long_context":
        return ("long_context_evidence_issue",
                "Tune evidence reranker (candidate_top_k / top_k / method); verify the answer-bearing chunk is selected.")
    if route in ("ambiguous", "law_admin"):
        return (f"{route}_needs_verifier",
                f"Enable/loosen the selective MCQ verifier for the '{route}' route (currently selective).")
    if route == "short_knowledge":
        return ("short_knowledge_needs_verifier",
                "Extend verifier triggers to low-confidence short_knowledge; otherwise likely a model-knowledge gap (no safe deterministic fix).")
    return ("route_or_model_knowledge",
            "Review routing; may be an inherent model-knowledge limitation (no safe deterministic override).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="First-100 consensus risk audit (diagnostic only)")
    ap.add_argument("--public-test", required=True)
    ap.add_argument("--external-sheet", default=None,
                    help="CSV: col1 Gemini, col2 ChatGPT, col3 Claude, [col4 old v6]; first-100 in order")
    ap.add_argument("--v6", required=True)
    ap.add_argument("--v6-log", default=None)
    ap.add_argument("--v6b", required=True)
    ap.add_argument("--v6b-log", default=None)
    ap.add_argument("--output", default="output/first100_consensus_risk_audit.csv")
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args(argv)

    print("=" * 72)
    print("FIRST-100 CONSENSUS RISK AUDIT (diagnostic; external sheet is NOT ground truth)")
    print("=" * 72)

    if not args.external_sheet or not Path(args.external_sheet).exists():
        print("External 3-model sheet not provided / not found:")
        print(f"  --external-sheet = {args.external_sheet!r}")
        print("Provide a CSV (col1 Gemini, col2 ChatGPT, col3 Claude, optional col4 old v6),")
        print("rows in the SAME order as the first-100 public-test samples. No answers were")
        print("invented; nothing written. Re-run with --external-sheet to produce the audit.")
        print("=" * 72)
        return 0

    qids = _load_public_qids(args.public_test)[: args.n]
    sheet = _load_external_sheet(args.external_sheet)
    if len(sheet) < len(qids):
        print(f"WARNING: sheet has {len(sheet)} rows < {len(qids)} qids; auditing the first {len(sheet)}.")
        qids = qids[: len(sheet)]

    v6 = _load_pred_csv(args.v6)
    v6b = _load_pred_csv(args.v6b)
    v6log = _load_log(args.v6_log)
    v6blog = _load_log(args.v6b_log)

    fields = ["row_index", "qid", "gemini_answer", "gpt_answer", "claude_answer",
              "external_majority", "external_majority_count", "v6_answer", "v6b_answer",
              "v6_matches_majority", "v6b_matches_majority", "priority", "route",
              "confidence", "calculation_matched", "calculation_method",
              "calculation_safe_to_override", "verifier_triggered",
              "verifier_override_applied", "parsed_answer_source", "parsed_answer_error",
              "model_provider_completion_tokens", "evidence_reranker_effective_method",
              "evidence_reranker_cache_hit", "suspected_root_cause", "recommended_general_fix"]

    out_rows = []
    p0 = p1 = 0
    v6_correct = v6b_correct = 0
    route_pri = Counter()
    cat_counter = Counter()
    changed_v6_to_v6b = []

    for i, qid in enumerate(qids):
        g, p, c, _oldv6 = sheet[i]
        maj, maj_n = _majority([g, p, c])
        a6 = v6.get(qid, "")
        a6b = v6b.get(qid, "")
        v6_ok = bool(maj) and a6 == maj
        v6b_ok = bool(maj) and a6b == maj
        v6_correct += int(v6_ok)
        v6b_correct += int(v6b_ok)
        if a6 != a6b:
            changed_v6_to_v6b.append((qid, a6, a6b))

        all_agree = maj_n == 3
        if all_agree and a6b != maj:
            priority = "P0"; p0 += 1
        elif maj_n >= 2 and bool(maj) and a6b != maj:
            priority = "P1"; p1 += 1
        else:
            priority = "P2"

        tr = v6blog.get(qid, {})
        if priority == "P2":
            cause = "none_matched_or_low_risk"
            fix = "No action; matched diagnostic majority or no actionable disagreement."
        else:
            cause, fix = _root_cause(tr, maj)
            route_pri[tr.get("route")] += 1
            cat_counter[cause] += 1

        out_rows.append({
            "row_index": i, "qid": qid, "gemini_answer": g, "gpt_answer": p,
            "claude_answer": c, "external_majority": maj, "external_majority_count": maj_n,
            "v6_answer": a6, "v6b_answer": a6b, "v6_matches_majority": v6_ok,
            "v6b_matches_majority": v6b_ok, "priority": priority,
            "route": tr.get("route"), "confidence": tr.get("confidence"),
            "calculation_matched": tr.get("calculation_matched"),
            "calculation_method": tr.get("calculation_method"),
            "calculation_safe_to_override": tr.get("calculation_safe_to_override"),
            "verifier_triggered": tr.get("verifier_triggered"),
            "verifier_override_applied": tr.get("verifier_override_applied"),
            "parsed_answer_source": tr.get("parsed_answer_source"),
            "parsed_answer_error": tr.get("parsed_answer_error"),
            "model_provider_completion_tokens": tr.get("model_provider_completion_tokens"),
            "evidence_reranker_effective_method": tr.get("evidence_reranker_effective_method"),
            "evidence_reranker_cache_hit": tr.get("evidence_reranker_cache_hit"),
            "suspected_root_cause": cause, "recommended_general_fix": fix,
        })

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    n = len(qids)
    print(f"samples audited            : {n}")
    print(f"v6  vs external majority   : {v6_correct}/{n}  ({100*v6_correct/n:.1f}%)  [pseudo-accuracy, NOT truth]")
    print(f"v6b vs external majority   : {v6b_correct}/{n}  ({100*v6b_correct/n:.1f}%)  [pseudo-accuracy, NOT truth]")
    print(f"P0 (3/3 agree, v6b differs): {p0}")
    print(f"P1 (>=2/3 differ from v6b) : {p1}")
    print(f"route distribution P0/P1   : {dict(route_pri)}")
    print(f"root-cause categories P0/P1: {dict(cat_counter)}")
    calc = sum(v for k, v in cat_counter.items() if k.startswith("calculation"))
    sk = cat_counter.get("short_knowledge_needs_verifier", 0)
    lc = cat_counter.get("long_context_evidence_issue", 0)
    print(f"  calculation-related P0/P1: {calc}")
    print(f"  short_knowledge P0/P1    : {sk}")
    print(f"  long_context P0/P1       : {lc}")
    print(f"answers changed v6 -> v6b  : {len(changed_v6_to_v6b)}  {changed_v6_to_v6b[:12]}")
    print(f"risk CSV written           : {args.output}")
    print("NOTE: external majority is a RISK SIGNAL, not ground truth; no overrides proposed.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
