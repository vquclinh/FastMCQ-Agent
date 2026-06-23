#!/usr/bin/env python3
"""V10 geography analyzer (read-only; no API; no correctness decision).

Joins the v10 prediction with its trace log and classifies each question into a risk
bucket for the answer factory. Writes a CSV + a Markdown summary under the output dir.
No qid hardcoding, no external sheet, no network.

Usage: see Phase 2L.25 Part K.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_log, load_pred, load_samples  # noqa: E402
from src.formula_bank_solver import solve_formula_bank_sample  # noqa: E402
from src.production_policy import branch_of  # noqa: E402

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_LOW_CONF = 0.7
_FIELDS = ["qid", "route", "v10_answer", "base_llm_answer", "final_answer", "override_applied",
           "rule_id", "model_confidence", "openrouter_call_seconds", "api_calls",
           "question_length", "numeric_count", "branch", "risk_bucket",
           "question_preview", "choices_compact"]


def _risk_bucket(route, conf, has_safe_rule, tr):
    if has_safe_rule:
        return "deterministic_safe"
    if isinstance(conf, (int, float)) and conf < _LOW_CONF:
        return "low_confidence_candidate"
    if route == "calculation":
        return "calculation_candidate"
    if route == "long_context":
        return "long_context_candidate"
    if route == "law_admin":
        return "law_admin_candidate"
    if route == "ambiguous":
        return "ambiguous_candidate"
    if route == "short_knowledge":
        return "short_knowledge_candidate"
    return "model_drift_candidate"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v10 geography analyzer (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--v10-pred", required=True)
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--v8-pred", default=None)
    ap.add_argument("--v9-pred", default=None)
    ap.add_argument("--output-dir", default="scratch/answer_factory_2l25")
    args = ap.parse_args(argv)

    samples = load_samples(args.input)
    v10 = load_pred(args.v10_pred)
    log = load_log(args.v10_log)
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    bucket_ct = Counter()
    route_ct = Counter()
    for s in samples:
        qid = s.get("qid")
        tr = log.get(qid, {})
        route = tr.get("route") or branch_of(s)
        conf = tr.get("confidence")
        choices = s.get("choices", []) or []
        det = solve_formula_bank_sample(s)
        has_safe = det is not None and det.safe_to_override
        bucket = _risk_bucket(route, conf, has_safe, tr)
        bucket_ct[bucket] += 1
        route_ct[route] += 1
        q = str(s.get("question", "") or "").replace("\n", " ")
        rows.append({
            "qid": qid, "route": route, "v10_answer": v10.get(qid),
            "base_llm_answer": tr.get("parsed_answer", {}).get("answer") if isinstance(tr.get("parsed_answer"), dict) else None,
            "final_answer": tr.get("final_answer"), "override_applied": tr.get("verifier_override_applied"),
            "rule_id": tr.get("calculation_method") or (det.rule_id if det else None),
            "model_confidence": conf, "openrouter_call_seconds": tr.get("openrouter_call_seconds"),
            "api_calls": tr.get("api_calls"), "question_length": tr.get("question_length") or len(q),
            "numeric_count": len(_NUM.findall(q)), "branch": branch_of(s), "risk_bucket": bucket,
            "question_preview": q[:120],
            "choices_compact": " | ".join(str(c) for c in choices)[:160],
        })

    csv_path = outdir / "v10_geography.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(rows)

    md = ["# V10 Geography Summary", "",
          f"Total questions: {len(rows)}", "",
          "## Risk-bucket distribution", ""]
    for b, n in bucket_ct.most_common():
        md.append(f"- `{b}`: {n}")
    md += ["", "## Route distribution", ""]
    for r, n in route_ct.most_common():
        md.append(f"- `{r}`: {n}")
    md += ["", "_Diagnostic only — no correctness decided; no API._"]
    (outdir / "v10_geography_summary.md").write_text("\n".join(md))

    print("=" * 64)
    print("V10 GEOGRAPHY (read-only; no API)")
    print("=" * 64)
    print(f"questions: {len(rows)}")
    print(f"risk buckets: {dict(bucket_ct)}")
    print(f"CSV: {csv_path}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
