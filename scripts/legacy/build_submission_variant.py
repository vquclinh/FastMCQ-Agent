#!/usr/bin/env python3
"""Submission variant builder (Phase 2L.29A — FOR HUMAN USE after a full adaptive run).

Builds a real full-run submission candidate from adaptive API candidates under an explicit
override POLICY (conservative / balanced / aggressive), using the existing
consistency-guarded ranker. Refuses pilot inputs, partial runs, and protected output
names. Uses NO ground truth and NO qid hardcoding. Writes the candidate under output/ and
a diff + summary under scratch/. Do NOT run in a coding phase.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.adaptive_proposal_common import guard_output, load_pred, load_samples  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate  # noqa: E402
from src.candidate_consistency import detect_placeholder_evidence, is_candidate_consistent  # noqa: E402
from src.labels import labels_for  # noqa: E402

# Locked / baseline names that must never be written.
_PROTECTED_NAMES = {"pred.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv"}
_DETERMINISTIC_PREFIXES = ("tool:", "rule:", "calc:", "concept:", "formula")
_POLICIES = ("conservative", "balanced", "aggressive")


def _require_outputs(path):
    p = str(path).replace("\\", "/")
    if "/output/" not in p and not p.startswith("output/"):
        raise SystemExit(f"REFUSING: candidate must be written under output/ (got {path})")
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite a protected/locked file: {Path(path).name}")
    guard_output(path)


def _refuse_pilot(path):
    if "pilot" in Path(path).name.lower():
        raise SystemExit(f"REFUSING: pilot candidate file ({Path(path).name}); run the full adaptive set.")


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: --review-dir must be under scratch/ (got {path})")


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


def _is_deterministic(source):
    return bool(source) and str(source).startswith(_DETERMINISTIC_PREFIXES)


def _policy_allows(policy, *, deterministic, has_evidence, risk, model_only):
    """Decide whether an override survives the policy gate."""
    if model_only:                       # no policy permits a model-only (evidence-less) override
        return False
    if policy == "conservative":
        return deterministic and risk == "low"
    if policy == "balanced":
        return deterministic or (has_evidence and risk in ("low", "medium"))
    # aggressive: evidence-backed low/medium (placeholder/mismatch already filtered upstream)
    return deterministic or (has_evidence and risk in ("low", "medium"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build a policy-gated submission variant (human-run)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--base-pred", default="output/pred_v10_full_production_user_run.csv")
    ap.add_argument("--api-candidates", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--review-dir", required=True)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--policy", default="conservative", choices=_POLICIES)
    ap.add_argument("--max-total-overrides", type=int, default=60)
    ap.add_argument("--max-model-only-overrides", type=int, default=0)
    ap.add_argument("--min-coverage", type=float, default=0.80)
    ap.add_argument("--i-understand-this-writes-outputs", action="store_true", default=False)
    args = ap.parse_args(argv)

    if not args.i_understand_this_writes_outputs:
        raise SystemExit("REFUSING: pass --i-understand-this-writes-outputs to write a real candidate.")
    _refuse_pilot(args.api_candidates)
    _require_outputs(args.output)
    _guard_scratch(args.review_dir)
    if not Path(args.api_candidates).exists():
        raise SystemExit(f"candidates not found: {args.api_candidates}")

    samples = {s.get("qid"): s for s in load_samples(args.input)}
    base = load_pred(args.base_pred)
    api = _load_jsonl(args.api_candidates)
    plan = {r["qid"]: r for r in csv.DictReader(open(args.plan))} if args.plan and Path(args.plan).exists() else {}

    coverage = len(set(api) & set(samples)) / max(1, len(samples))
    if coverage < args.min_coverage:
        raise SystemExit(f"REFUSING: candidate coverage {coverage:.2f} < --min-coverage "
                         f"{args.min_coverage}; this looks like a partial/pilot run.")

    pred_rows, overrides = [], []
    placeholder_ct = mismatch_ct = consistency_rej = model_only_ct = 0
    by_source, by_route, by_risk = Counter(), Counter(), Counter()
    for qid, sample in samples.items():
        v10 = base.get(qid)
        pool = build_candidate_pool(sample, v10, None)
        for c in api.get(qid, []):
            if c.get("parse_status") == "placeholder_evidence" or \
                    (c.get("evidence") is not None and detect_placeholder_evidence(c.get("evidence", ""))):
                placeholder_ct += 1
            if c.get("parse_status") == "numeric_mismatch":
                mismatch_ct += 1
            if c.get("answer") and c.get("parse_status") in ("ok", None):
                cand = AnswerCandidate(qid=qid, answer=c["answer"], source=f"api:{c.get('agent')}",
                                       confidence=float(c.get("confidence") or 0.5),
                                       risk_level=c.get("risk") or "medium",
                                       rationale=c.get("rationale", ""), evidence_text=c.get("evidence", ""))
                if not is_candidate_consistent(cand, sample):
                    consistency_rej += 1
                    continue
                pool.add(cand)
        pool.deduplicate()
        selected, rec = select_answer(pool, sample, v10)
        if rec.get("decision") == "override" and selected != v10:
            winner = pool.best_by_source(rec.get("selected_source"))
            deterministic = _is_deterministic(rec.get("selected_source"))
            # Consensus overrides aggregate several candidates → evidence lives on the
            # agreeing candidates, not a single best_by_source entry.
            supporters = [c for c in pool.candidates if c.answer == selected
                          and (c.proof_text or c.evidence_text)]
            if winner is None and supporters:
                winner = supporters[0]
            has_evidence = bool((winner and (winner.proof_text or winner.evidence_text)) or supporters)
            model_only = not has_evidence and not deterministic
            if model_only:
                model_only_ct += 1
            if _policy_allows(args.policy, deterministic=deterministic, has_evidence=has_evidence,
                              risk=rec.get("risk_level"), model_only=model_only):
                overrides.append({"qid": qid, "v10": v10, "candidate": selected,
                                  "source": rec.get("selected_source"), "risk": rec.get("risk_level"),
                                  "route": (plan.get(qid) or {}).get("route", "?"),
                                  "evidence": (winner.evidence_text if winner else "")[:140],
                                  "proof": (winner.proof_text if winner else "")[:140]})
                by_source[rec.get("selected_source")] += 1
                by_route[(plan.get(qid) or {}).get("route", "?")] += 1
                by_risk[rec.get("risk_level")] += 1
            else:
                selected = v10                       # policy blocks this override
        pred_rows.append({"qid": qid, "answer": selected})

    if model_only_ct > args.max_model_only_overrides:
        raise SystemExit(f"REFUSING: model-only overrides {model_only_ct} > "
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
    with open(reviewdir / "variant_diff.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "v10", "candidate", "source", "risk",
                                           "route", "evidence", "proof"])
        w.writeheader(); w.writerows(overrides)

    md = [f"# Submission Variant — policy={args.policy} (NOT v10)", "",
          f"- coverage: **{coverage:.3f}**", f"- rows: **{len(pred_rows)}**",
          f"- overrides: **{len(overrides)}**",
          f"- override by source: {dict(by_source)}",
          f"- override by route: {dict(by_route)}",
          f"- risk breakdown: {dict(by_risk)}",
          f"- consistency rejections: **{consistency_rej}**",
          f"- placeholder rejections: **{placeholder_ct}**",
          f"- numeric mismatch: **{mismatch_ct}**",
          f"- model-only overrides (blocked): **{model_only_ct}**", "",
          "## Top changed qids", ""]
    for o in overrides[:40]:
        md.append(f"- {o['qid']} {o['v10']}→{o['candidate']} ({o['source']}, {o['risk']}, "
                  f"{o['route']}): {o['evidence'] or o['proof']}")
    (reviewdir / "variant_summary.md").write_text("\n".join(md))

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader(); w.writerows(pred_rows)

    print("=" * 64)
    print(f"SUBMISSION VARIANT ({args.policy}) — human-run")
    print("=" * 64)
    print(f"coverage={coverage:.3f} rows={len(pred_rows)} overrides={len(overrides)} "
          f"model_only_blocked={model_only_ct} consistency_rej={consistency_rej}")
    print(f"candidate -> {outp}")
    print(f"review    -> {reviewdir}/variant_summary.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
