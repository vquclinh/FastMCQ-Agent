#!/usr/bin/env python3
"""Export a human-review pack for P0/P1 risk qids (diagnostic only; no overrides).

Joins the first-100 consensus risk CSV with the public-test questions and the v6b
trace log, and writes a Markdown + CSV pack containing ONLY P0/P1 rows for manual
review. It proposes NO answer override and treats the external 3-model sheet purely
as a risk signal (never ground truth, never a qid->answer table).

Usage:
    python scripts/export_risk_review_pack.py \
      --public-test public-test_1780368312.json \
      --risk-csv output/first100_consensus_risk_audit.csv \
      --v6b-log output/run_v6b_qwen_rerank_calc_verifier_fast.jsonl \
      --output-md output/first100_p0p1_review_pack.md \
      --output-csv output/first100_p0p1_review_pack.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.utils.labels import labels_for  # noqa: E402  (project import)


def _load_public(path):
    data = json.loads(Path(path).read_text())
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    return {r.get("qid"): r for r in rows}


def _load_log(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("qid"):
            out[obj["qid"]] = obj
    return out


def _load_risk(path):
    return [r for r in csv.DictReader(open(path))]


# Columns carried into the review CSV (human-review pack).
_PACK_FIELDS = [
    "priority", "row_index", "qid", "route", "external_majority",
    "external_majority_count", "gemini_answer", "gpt_answer", "claude_answer",
    "v6_answer", "v6b_answer", "confidence", "calculation_matched",
    "calculation_method", "calculation_safe_to_override", "verifier_triggered",
    "verifier_override_applied", "parsed_answer_source", "parsed_answer_error",
    "openrouter_completion_tokens", "evidence_reranker_effective_method",
    "evidence_reranker_cache_hit", "suspected_root_cause", "recommended_general_fix",
    "question", "choices",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Export P0/P1 human-review pack (no overrides)")
    ap.add_argument("--public-test", required=True)
    ap.add_argument("--risk-csv", required=True)
    ap.add_argument("--v6b-log", required=True)
    ap.add_argument("--output-md", default="output/first100_p0p1_review_pack.md")
    ap.add_argument("--output-csv", default="output/first100_p0p1_review_pack.csv")
    args = ap.parse_args(argv)

    public = _load_public(args.public_test)
    log = _load_log(args.v6b_log)
    risk = _load_risk(args.risk_csv)
    p0p1 = [r for r in risk if r.get("priority") in ("P0", "P1")]
    # P0 first, then P1; stable by row_index within each.
    p0p1.sort(key=lambda r: (0 if r["priority"] == "P0" else 1, int(r.get("row_index") or 0)))

    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)

    # --- CSV pack ---
    with open(args.output_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PACK_FIELDS)
        w.writeheader()
        for r in p0p1:
            sample = public.get(r["qid"], {})
            choices = sample.get("choices", []) or []
            labels = labels_for(len(choices))
            w.writerow({
                **{k: r.get(k, "") for k in _PACK_FIELDS if k not in ("question", "choices")},
                "question": (sample.get("question", "") or "").replace("\n", " ⏎ "),
                "choices": " | ".join(f"{labels[i]}. {c}" for i, c in enumerate(choices)),
            })

    # --- Markdown pack ---
    n_p0 = sum(1 for r in p0p1 if r["priority"] == "P0")
    n_p1 = sum(1 for r in p0p1 if r["priority"] == "P1")
    lines = [
        "# First-100 P0/P1 Risk Review Pack",
        "",
        "> **The external Gemini/ChatGPT/Claude majority is a RISK SIGNAL, NOT ground "
        "truth.** This pack is for human review only. It proposes **no answer "
        "overrides** and contains **no qid→answer table** for the pipeline.",
        "",
        f"P0 (3/3 external agree, v6b differs): **{n_p0}**  |  "
        f"P1 (≥2/3 differ from v6b): **{n_p1}**  |  total **{len(p0p1)}**",
        "",
    ]
    for r in p0p1:
        qid = r["qid"]
        sample = public.get(qid, {})
        choices = sample.get("choices", []) or []
        labels = labels_for(len(choices))
        tr = log.get(qid, {})
        lines.append(f"## [{r['priority']}] {qid}  (row {r['row_index']}, route: {r.get('route')})")
        lines.append("")
        lines.append(f"- **External**: Gemini={r.get('gemini_answer')}, "
                     f"GPT={r.get('gpt_answer')}, Claude={r.get('claude_answer')} "
                     f"→ majority **{r.get('external_majority')}** ({r.get('external_majority_count')}/3)")
        lines.append(f"- **Ours**: v6={r.get('v6_answer')}, v6b={r.get('v6b_answer')}, "
                     f"confidence={r.get('confidence')}")
        lines.append(f"- **Calc**: matched={r.get('calculation_matched')}, "
                     f"method={r.get('calculation_method') or '-'}, "
                     f"safe_override={r.get('calculation_safe_to_override')}")
        lines.append(f"- **Verifier**: triggered={r.get('verifier_triggered')}, "
                     f"override_applied={r.get('verifier_override_applied')}")
        lines.append(f"- **Parse**: source={r.get('parsed_answer_source')}, "
                     f"error={r.get('parsed_answer_error') or '-'}, "
                     f"completion_tokens={r.get('openrouter_completion_tokens')}")
        if r.get("route") == "long_context":
            lines.append(f"- **Reranker**: method={r.get('evidence_reranker_effective_method')}, "
                         f"cache_hit={r.get('evidence_reranker_cache_hit')}")
        lines.append(f"- **Suspected root cause**: `{r.get('suspected_root_cause')}`")
        lines.append(f"- **Recommended general fix**: {r.get('recommended_general_fix')}")
        lines.append("")
        lines.append("**Question:**")
        lines.append("")
        lines.append("> " + (sample.get("question", "") or "").replace("\n", "\n> "))
        lines.append("")
        lines.append("**Choices:**")
        lines.append("")
        for i, c in enumerate(choices):
            lines.append(f"- {labels[i]}. {c}")
        lines.append("")
        # Compressed question / evidence (long_context only), if present in the trace.
        if r.get("route") == "long_context" and tr.get("compressed_question"):
            lines.append("**Compressed evidence (v6b reranker):**")
            lines.append("")
            cq = str(tr.get("compressed_question"))
            lines.append("```")
            lines.append(cq if len(cq) <= 3000 else cq[:3000] + " …[truncated]")
            lines.append("```")
            lines.append("")
        lines.append("---")
        lines.append("")

    Path(args.output_md).write_text("\n".join(lines))

    print("=" * 64)
    print("P0/P1 REVIEW PACK (human review only; no overrides; not ground truth)")
    print("=" * 64)
    print(f"P0={n_p0}  P1={n_p1}  total={len(p0p1)}")
    print(f"markdown -> {args.output_md}")
    print(f"csv      -> {args.output_csv}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
