#!/usr/bin/env python3
"""Production candidate audit (Phase 2L.31A; read-only, no API, no ground truth).

Validates the production candidate CSV against the dataset, compares it to the v10
baseline (changed count / label distribution), and — if the repaired independent-v11
decisions are available — reports the final-source / fallback / last-resort breakdown.
Recommends ``freeze_as_default`` when the candidate is valid and the manifest score beats
v10. Writes a Markdown + JSON report under scratch/. Never writes outputs, never uses v10
as truth, no qid hardcoding.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_io import load_dataset, read_predictions  # noqa: E402
from src.labels import is_valid_label  # noqa: E402

_MANIFEST = "experiments/best_candidate_manifest.json"
_REPAIRED = "scratch/full_v11_independent_rerun1/v11_independent_decisions_repaired.csv"


def _md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _guard_scratch(path):
    if "scratch/" not in str(path).replace("\\", "/"):
        raise SystemExit(f"REFUSING: --output-dir must be under scratch/ (got {path})")


def _validate(rows, by_qid):
    pred_qids = [r["qid"] for r in rows]
    dups = sorted({q for q in pred_qids if pred_qids.count(q) > 1})
    missing = sorted(set(by_qid) - set(pred_qids))
    invalid = [r["qid"] for r in rows
               if not r.get("answer") or r["qid"] not in by_qid
               or not is_valid_label(r["answer"], by_qid[r["qid"]])]
    none_empty = [r["qid"] for r in rows if not (r.get("answer") or "").strip()]
    return {"rows": len(rows), "duplicates": dups, "missing": missing,
            "invalid": sorted(set(invalid)), "none_empty": sorted(set(none_empty)),
            "qid_set_valid": (not dups and not missing and set(pred_qids) == set(by_qid))}


def _decision_breakdown():
    if not Path(_REPAIRED).exists():
        return None
    rows = list(csv.DictReader(open(_REPAIRED)))
    return {"final_source": dict(Counter(r.get("final_source") for r in rows).most_common()),
            "fallback_used": sum(1 for r in rows if str(r.get("fallback_used")).lower() == "true"),
            "last_resort": sum(1 for r in rows if r.get("final_source") == "last_resort_valid_choice"),
            "rows": len(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit the production candidate (no API, no truth)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--baseline", default="outputs/pred_v10_full_production_user_run.csv")
    ap.add_argument("--output-dir", default="scratch/production_candidate_audit")
    args = ap.parse_args(argv)
    _guard_scratch(args.output_dir)
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)

    samples = load_dataset(args.input)
    by_qid = {s["qid"]: s for s in samples}
    cand = read_predictions(args.candidate)
    val = _validate(cand, by_qid)
    cand_map = {r["qid"]: r["answer"] for r in cand}
    label_dist = dict(Counter(cand_map.values()).most_common())

    changed = None
    if Path(args.baseline).exists():
        base = {r["qid"]: r["answer"] for r in read_predictions(args.baseline)}
        changed = sum(1 for q in cand_map if base.get(q) and cand_map[q] != base.get(q))

    manifest = json.loads(Path(_MANIFEST).read_text()) if Path(_MANIFEST).exists() else {}
    cb = manifest.get("current_best", {})
    pb = manifest.get("previous_best", {})
    beats_v10 = (cb.get("public_score") or 0) > (pb.get("public_score") or 0)
    md5_match_manifest = cb.get("md5") == _md5(args.candidate)

    valid = val["qid_set_valid"] and not val["invalid"] and not val["none_empty"]
    recommendation = ("freeze_as_default" if (valid and beats_v10 and md5_match_manifest)
                      else "do_not_freeze")
    breakdown = _decision_breakdown()

    report = {"candidate": args.candidate, "md5": _md5(args.candidate),
              "manifest_current_best_md5": cb.get("md5"), "md5_matches_manifest": md5_match_manifest,
              "rows": val["rows"], "qid_set_valid": val["qid_set_valid"],
              "duplicates": len(val["duplicates"]), "missing": len(val["missing"]),
              "invalid_labels": len(val["invalid"]), "none_empty": len(val["none_empty"]),
              "changed_vs_baseline": changed, "label_distribution": label_dist,
              "candidate_score": cb.get("public_score"), "baseline_score": pb.get("public_score"),
              "beats_v10": beats_v10, "decision_breakdown": breakdown,
              "recommendation": recommendation}
    (outdir / "production_candidate_audit.json").write_text(json.dumps(report, indent=2))
    md = ["# Production Candidate Audit (read-only; no API; no ground truth)", "",
          f"- candidate: `{args.candidate}`  md5 `{report['md5']}`",
          f"- md5 matches manifest current_best: **{md5_match_manifest}**",
          f"- rows: {val['rows']}  qid_set_valid: **{val['qid_set_valid']}**",
          f"- duplicates {len(val['duplicates'])} / missing {len(val['missing'])} / "
          f"invalid {len(val['invalid'])} / none-empty {len(val['none_empty'])}",
          f"- changed vs baseline (`{Path(args.baseline).name}`): {changed}",
          f"- label distribution: {label_dist}",
          f"- candidate score {report['candidate_score']} vs v10 {report['baseline_score']} "
          f"-> beats_v10: **{beats_v10}**"]
    if breakdown:
        md += [f"- decision final_source: {breakdown['final_source']}",
               f"- fallback_used: {breakdown['fallback_used']}  last_resort: {breakdown['last_resort']}"]
    md += ["", f"## Recommendation: **{recommendation}**"]
    (outdir / "production_candidate_audit.md").write_text("\n".join(md))

    print("=" * 64)
    print("PRODUCTION CANDIDATE AUDIT (no API)")
    print("=" * 64)
    print(f"candidate valid={valid} qid_set_valid={val['qid_set_valid']} "
          f"changed_vs_v10={changed} beats_v10={beats_v10}")
    print(f"RECOMMENDATION: {recommendation}")
    print(f"-> {outdir}/production_candidate_audit.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
