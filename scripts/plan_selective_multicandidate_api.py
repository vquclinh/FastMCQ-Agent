"""Select ≤N qids for a future expensive multi-candidate API pass (no API; deterministic).

Ranks questions by how much an expensive multi-candidate API call would likely help,
using offline signals only (low v10 confidence, weak long-context evidence, no card
support, calc without tool proof, law_admin without support, ambiguous route, no safe
deterministic candidate in the factory). Writes a plan CSV + Markdown to scratch.
No qid hardcoding (qids are selected by signal, not by literal id), no answer table.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import load_log, load_pred, load_samples  # noqa: E402
from src.formula_bank_solver import solve_formula_bank_sample  # noqa: E402
from src.production_policy import branch_of  # noqa: E402
from src.rag_lite import best_card  # noqa: E402

_LOW_CONF = 0.7
_FIELDS = ["qid", "route", "v10_answer", "model_confidence", "priority_score",
           "signals", "question_preview"]


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: output must be under scratch/ (got {path})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Plan selective multi-candidate API qids (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="outputs/pred_v10_full_production_user_run.csv")
    ap.add_argument("--v10-log", default=None)
    ap.add_argument("--factory-review", default=None, help="answer_factory_proposals.csv (optional)")
    ap.add_argument("--output-dir", default="scratch/answer_factory_2l25")
    ap.add_argument("--max-qids", type=int, default=120)
    args = ap.parse_args(argv)

    outdir = Path(args.output_dir)
    _guard_scratch(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    samples = load_samples(args.input)
    base = load_pred(args.base_pred)
    log = load_log(args.v10_log)
    factory_qids = set()
    if args.factory_review and Path(args.factory_review).exists():
        factory_qids = {r["qid"] for r in csv.DictReader(open(args.factory_review))}

    ranked = []
    for s in samples:
        qid = s.get("qid")
        tr = log.get(qid, {})
        route = tr.get("route") or branch_of(s)
        conf = tr.get("confidence")
        det = solve_formula_bank_sample(s)
        has_safe = det is not None and det.safe_to_override
        signals, score = [], 0.0

        if isinstance(conf, (int, float)) and conf < _LOW_CONF:
            signals.append("low_confidence"); score += 3.0
        if route == "long_context":
            chars = tr.get("evidence_selected_chars")
            if isinstance(chars, int) and chars < 800:
                signals.append("weak_long_context_evidence"); score += 2.0
        if route == "short_knowledge" and best_card(s.get("question", "")) is None:
            signals.append("short_knowledge_no_card"); score += 1.5
        if route == "calculation" and not has_safe:
            signals.append("calculation_no_tool_proof"); score += 2.0
        if route == "law_admin" and best_card(s.get("question", "")) is None:
            signals.append("law_admin_no_support"); score += 2.0
        if route == "ambiguous":
            signals.append("ambiguous_route"); score += 1.5
        if not has_safe:
            signals.append("no_safe_deterministic_candidate"); score += 0.5
        if qid in factory_qids:
            signals.append("factory_proposed_change"); score += 1.0
        # parse-quality signal
        if (tr.get("parsed_answer_source") == "partial_answer_key"
                or tr.get("parsed_answer_error") == "no_json"):
            signals.append("parse_review_needed"); score += 1.5

        if signals:
            q = str(s.get("question", "") or "").replace("\n", " ")
            ranked.append({"qid": qid, "route": route, "v10_answer": base.get(qid),
                           "model_confidence": conf, "priority_score": round(score, 2),
                           "signals": "|".join(signals), "question_preview": q[:100]})

    ranked.sort(key=lambda r: (r["priority_score"], r["qid"]), reverse=True)
    selected = ranked[: max(0, args.max_qids)]

    csv_path = outdir / "selective_api_plan.csv"
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader(); w.writerows(selected)

    sig_ct = Counter()
    for r in selected:
        for sgl in r["signals"].split("|"):
            sig_ct[sgl] += 1
    md = ["# Selective Multi-Candidate API Plan (no API)", "",
          f"Selected **{len(selected)}** / {len(ranked)} flagged (cap {args.max_qids}).", "",
          "## Top signals among selected", ""]
    for sgl, n in sig_ct.most_common():
        md.append(f"- `{sgl}`: {n}")
    md += ["", "_Selection by offline signals only; no qid hardcoded; no API called._"]
    (outdir / "selective_api_plan.md").write_text("\n".join(md))

    print("=" * 64)
    print("SELECTIVE MULTI-CANDIDATE API PLAN (no API)")
    print("=" * 64)
    print(f"flagged: {len(ranked)}   selected (cap {args.max_qids}): {len(selected)}")
    print(f"signal distribution (selected): {dict(sig_ct)}")
    print(f"plan CSV: {csv_path}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
