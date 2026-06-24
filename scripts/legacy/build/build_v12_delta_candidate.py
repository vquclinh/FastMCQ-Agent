#!/usr/bin/env python3
"""Phase 2L.34A — V12 conservative delta selector.

Starts from the frozen v11 winner and applies *only* high-confidence, independently-supported
answer overrides. Everything else is left exactly as v11. The output is a SHADOW candidate
(``output/pred_v12_delta_candidate.csv``) — it is NOT the production default and NEVER
overwrites the frozen best or ``pred.csv``.

Override gates (a proposed label != current must pass ALL applicable safety checks):
  * label must match the verifier's own copied option text (no label/text mismatch);
  * no numeric mismatch (equation result must map to the selected option);
  * never on model-only weak evidence.
Acceptance (policy):
  * conservative: >=2 independent non-current sources agree on the SAME new label, OR a
    deterministic-solver proof at low risk, OR (judge picks new label AND >=1 grounded verifier agrees);
  * balanced: additionally allows a single strong deterministic proof.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.utils.data_io import load_dataset, read_predictions, write_predictions  # noqa: E402
from src.utils.labels import is_valid_label, labels_for  # noqa: E402

# Frozen/locked artifacts that must NEVER be written by this tool.
_PROTECTED_NAMES = {"pred_v11_independent_rerun1.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv", "pred.csv"}

_DETERMINISTIC_AGENTS = {"deterministic_solver", "calculation_solver_deterministic", "formula_bank"}
_GROUNDED_AGENTS = {"option_grounding", "numeric_consistency", "deterministic_solver"}


def _guard_output(path):
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite protected file: {Path(path).name}")


def _load_candidates(path):
    out = defaultdict(list)
    if not Path(path).exists():
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("qid"):
                out[rec["qid"]].append(rec)
    return out


def _usable(c):
    """A candidate is usable as evidence only if it produced a concrete, self-consistent label."""
    if (c.get("parse_status") or "") != "ok":
        return False
    lab = c.get("selected_label")
    if not lab:
        return False
    # Reject explicit label/option-text mismatch (the verifier's own self-check).
    if c.get("label_matches_option") is False:
        return False
    return True


def decide_override(qid, current, candidates, sample, *, policy):
    """Return (new_label or None, decision_dict). None => keep current."""
    labels = set(labels_for(len(sample.get("choices") or [])))
    usable = [c for c in candidates if _usable(c)]
    # Group usable support by proposed label, counting DISTINCT agents (independent sources).
    by_label = defaultdict(set)
    for c in usable:
        lab = c.get("selected_label")
        if lab in labels:
            by_label[lab].add(c.get("agent"))
    # Only labels DIFFERENT from current are override candidates.
    alt_labels = {lab: agents for lab, agents in by_label.items() if lab and lab != current}

    base = {"qid": qid, "current": current, "policy": policy,
            "usable_candidates": len(usable), "alt_labels": {k: sorted(v) for k, v in alt_labels.items()}}

    if not alt_labels:
        return None, {**base, "verdict": "keep", "reason": "no usable alternative"}

    # Pick the strongest alternative (most independent agents; ties -> stable by label).
    best_label = sorted(alt_labels, key=lambda L: (-len(alt_labels[L]), L))[0]
    supporters = alt_labels[best_label]
    n_support = len(supporters)
    has_determ = bool(supporters & _DETERMINISTIC_AGENTS)
    has_grounded = bool(supporters & _GROUNDED_AGENTS)
    has_judge = "pairwise_judge" in supporters

    # Numeric-mismatch guard: if ANY verifier (even one filtered from `usable`) explicitly
    # flagged a label<->option mismatch for the proposed label, abort the override.
    for c in candidates:
        if c.get("selected_label") == best_label and c.get("label_matches_option") is False:
            return None, {**base, "verdict": "reject", "reason": "numeric/label mismatch",
                          "proposed": best_label}

    accept = False
    reason = "insufficient independent support"
    if n_support >= 2:
        accept = True
        reason = f">=2 independent sources agree ({sorted(supporters)})"
    elif has_determ and has_grounded:
        accept = True
        reason = "deterministic low-risk proof"
    elif has_judge and has_grounded:
        accept = True
        reason = "judge + grounded verifier agree"
    elif policy == "balanced" and has_determ:
        accept = True
        reason = "balanced: single strong deterministic proof"

    if accept:
        return best_label, {**base, "verdict": "accept", "proposed": best_label,
                            "support": sorted(supporters), "reason": reason}
    return None, {**base, "verdict": "reject", "proposed": best_label,
                  "support": sorted(supporters), "reason": reason}


def _validate(rows, samples):
    by_qid = {s["qid"]: s for s in samples}
    if not rows:
        raise SystemExit("REFUSING: empty output")
    header = set(rows[0].keys())
    for col in ("qid", "answer"):
        if col not in header:
            raise SystemExit(f"REFUSING: missing column {col}")
    pred_qids = [r["qid"] for r in rows]
    if len(set(pred_qids)) != len(pred_qids):
        raise SystemExit("REFUSING: duplicate qids")
    if set(pred_qids) != set(by_qid):
        raise SystemExit("REFUSING: qid set mismatch with dataset")
    for r in rows:
        if not r.get("answer") or not is_valid_label(r["answer"], by_qid[r["qid"]]):
            raise SystemExit(f"REFUSING: invalid label {r.get('answer')!r} for {r['qid']}")
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V12 conservative delta selector")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--output", default="output/pred_v12_delta_candidate.csv")
    ap.add_argument("--review-dir", default="scratch/v12_delta_verifier/review")
    ap.add_argument("--max-overrides", type=int, default=None)
    ap.add_argument("--policy", choices=["conservative", "balanced"], default="conservative")
    args = ap.parse_args(argv)

    _guard_output(args.output)
    samples = load_dataset(args.input)
    samples_by_qid = {s["qid"]: s for s in samples}
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    candidates = _load_candidates(args.candidates)

    review = Path(args.review_dir)
    review.mkdir(parents=True, exist_ok=True)

    accepted, rejected, decisions = [], [], []
    new_answers = dict(current)
    for s in samples:
        qid = s["qid"]
        cur = current.get(qid, "")
        new_label, dec = decide_override(qid, cur, candidates.get(qid, []), s, policy=args.policy)
        decisions.append(dec)
        if dec["verdict"] == "accept":
            accepted.append(dec)
        elif dec["verdict"] == "reject":
            rejected.append(dec)

    # Apply accepted overrides (respecting --max-overrides by strongest support first).
    accepted.sort(key=lambda d: (-len(d.get("support", [])), d["qid"]))
    applied = accepted if args.max_overrides is None else accepted[: args.max_overrides]
    for d in applied:
        new_answers[d["qid"]] = d["proposed"]

    rows = [{"qid": q, "answer": new_answers[q]} for q in (s["qid"] for s in samples)]
    n = _validate(rows, samples)
    write_predictions(rows, args.output)

    # Delta diff vs current.
    diff = [{"qid": q, "v11_answer": current[q], "v12_answer": new_answers[q]}
            for q in current if current[q] != new_answers[q]]
    with (review / "delta_diff.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "v11_answer", "v12_answer"])
        w.writeheader(); w.writerows(diff)
    with (review / "rejected_overrides.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "current", "proposed", "reason", "support"])
        w.writeheader()
        for d in rejected:
            w.writerow({"qid": d["qid"], "current": d["current"], "proposed": d.get("proposed", ""),
                        "reason": d["reason"], "support": "|".join(d.get("support", []))})

    summary = {
        "policy": args.policy,
        "total_qids": len(samples),
        "overrides_accepted": len(accepted),
        "overrides_applied": len(applied),
        "overrides_rejected": len(rejected),
        "changed_vs_v11": len(diff),
        "validation": "PASS",
        "rows": n,
        "output": args.output,
    }
    (review / "delta_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = ["# V12 Delta Candidate Summary", ""]
    for k, v in summary.items():
        md.append(f"- **{k}**: {v}")
    md.append("")
    md.append(f"- changed qids: {', '.join(d['qid'] for d in diff) or '(none)'}")
    (review / "delta_summary.md").write_text("\n".join(md), encoding="utf-8")

    print("=" * 60)
    print("V12 DELTA CANDIDATE")
    for k, v in summary.items():
        print(f"{k:20}: {v}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
