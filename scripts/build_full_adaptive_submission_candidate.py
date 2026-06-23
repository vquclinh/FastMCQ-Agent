#!/usr/bin/env python3
"""Full-run adaptive submission candidate builder (Phase 2L.28A — FOR LATER HUMAN USE).

This is the ONLY script permitted to write a real candidate CSV under ``outputs/``. It
refuses pilot inputs and partial runs, ranks the full candidate set with the
consistency-guarded ranker under explicit review-policy gates, validates the output
format, and writes a review diff under ``scratch/``. It uses NO ground truth and NO qid
hardcoding. Do NOT run this in a coding phase — it is invoked by a human after a full
adaptive execution and a ``proceed_full_run`` pilot recommendation.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adaptive_proposal_common import guard_output, load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate  # noqa: E402
from src.labels import labels_for  # noqa: E402

_PRED_FIELDS = ["qid", "answer"]


def _require_outputs(path):
    p = str(path).replace("\\", "/")
    if "/outputs/" not in p and not p.startswith("outputs/"):
        raise SystemExit(f"REFUSING: full candidate must be written under outputs/ (got {path})")
    guard_output(path)  # never overwrite a protected pred file


def _refuse_pilot(candidates_path):
    name = Path(candidates_path).name.lower()
    if "pilot" in name:
        raise SystemExit(f"REFUSING: this builder will not consume a pilot candidate file ({name}). "
                         "Run the full adaptive execution first.")


def _load_jsonl(path):
    by_qid = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("qid"):
            by_qid.setdefault(o["qid"], []).append(o)
    return by_qid


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build FULL adaptive submission candidate (human-run only)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="outputs/pred_v10_full_production_user_run.csv")
    ap.add_argument("--api-candidates", required=True, help="FULL adaptive candidate JSONL (not pilot)")
    ap.add_argument("--output", required=True, help="real candidate CSV path under outputs/")
    ap.add_argument("--review-dir", default="scratch/full_adaptive_candidate")
    ap.add_argument("--min-coverage", type=float, default=0.80,
                    help="require API candidates covering >= this fraction of dataset qids")
    ap.add_argument("--require-low-risk-or-reviewed", action="store_true", default=False)
    ap.add_argument("--max-model-only-overrides", type=int, default=0)
    ap.add_argument("--max-total-overrides", type=int, default=50)
    ap.add_argument("--min-evidence-score", type=float, default=1.0)
    ap.add_argument("--i-understand-this-writes-outputs", action="store_true", default=False,
                    help="explicit human acknowledgement required to write under outputs/")
    args = ap.parse_args(argv)

    if not args.i_understand_this_writes_outputs:
        raise SystemExit("REFUSING: pass --i-understand-this-writes-outputs to write a real candidate.")
    _refuse_pilot(args.api_candidates)
    _require_outputs(args.output)
    if "scratch/" not in str(args.review_dir).replace("\\", "/"):
        raise SystemExit("REFUSING: --review-dir must be under scratch/")
    if not Path(args.api_candidates).exists():
        raise SystemExit(f"candidates not found: {args.api_candidates}")

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    api = _load_jsonl(args.api_candidates)

    coverage = len(set(api) & set(samples)) / max(1, len(samples))
    if coverage < args.min_coverage:
        raise SystemExit(f"REFUSING: candidate coverage {coverage:.2f} < --min-coverage "
                         f"{args.min_coverage}; this looks like a partial/pilot run, not a full run.")

    pred_rows, overrides, model_only, violations = [], [], 0, []
    for qid, sample in samples.items():
        v10 = base.get(qid)
        pool = build_candidate_pool(sample, v10, None)
        for c in api.get(qid, []):
            if c.get("answer") and c.get("parse_status") in ("ok", None):
                pool.add(AnswerCandidate(qid=qid, answer=c["answer"], source=f"api:{c.get('agent')}",
                                         confidence=float(c.get("confidence") or 0.5),
                                         risk_level=c.get("risk") or "medium",
                                         rationale=c.get("rationale", ""),
                                         evidence_text=c.get("evidence", "")))
        pool.deduplicate()
        selected, rec = select_answer(pool, sample, v10)
        if rec.get("decision") == "override" and selected != v10:
            winner = pool.best_by_source(rec.get("selected_source"))
            has_ev = bool(winner and (winner.proof_text or winner.evidence_text))
            if not has_ev:
                model_only += 1
            if args.require_low_risk_or_reviewed and rec.get("risk_level") != "low" \
                    and not rec.get("requires_manual_review"):
                violations.append(f"{qid}: override not low-risk and not reviewed")
                selected = v10  # gate blocks this override
            else:
                overrides.append(qid)
        pred_rows.append({"qid": qid, "answer": selected})

    # Policy gates (fail closed BEFORE writing outputs).
    if model_only > args.max_model_only_overrides:
        raise SystemExit(f"REFUSING: model-only overrides {model_only} > "
                         f"--max-model-only-overrides {args.max_model_only_overrides}")
    if len(overrides) > args.max_total_overrides:
        raise SystemExit(f"REFUSING: total overrides {len(overrides)} > "
                         f"--max-total-overrides {args.max_total_overrides}")

    # Validate output format.
    for r in pred_rows:
        labels = labels_for(len(samples[r["qid"]].get("choices", []) or []))
        if r["answer"] not in labels:
            raise SystemExit(f"REFUSING: invalid label {r['answer']} for {r['qid']}")
    if len(pred_rows) != len(samples):
        raise SystemExit("REFUSING: candidate row count != dataset size")

    reviewdir = Path(args.review_dir); reviewdir.mkdir(parents=True, exist_ok=True)
    diff = [{"qid": q, "v10": base.get(q),
             "candidate": next(r["answer"] for r in pred_rows if r["qid"] == q)} for q in overrides]
    with open(reviewdir / "full_candidate_diff.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "v10", "candidate"]); w.writeheader(); w.writerows(diff)

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PRED_FIELDS); w.writeheader(); w.writerows(pred_rows)

    print("=" * 64)
    print("FULL ADAPTIVE SUBMISSION CANDIDATE (human-run)")
    print("=" * 64)
    print(f"coverage={coverage:.2f} rows={len(pred_rows)} overrides={len(overrides)} "
          f"model_only={model_only} blocked={len(violations)}")
    print(f"candidate -> {outp}")
    print(f"diff -> {reviewdir / 'full_candidate_diff.csv'}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
