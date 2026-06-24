#!/usr/bin/env python3
"""Phase 2L.35A — Unified V13 multi-layer candidate selector.

Starts from the frozen v11 winner and overrides a qid only when multiple independent layers
agree (or a deterministic programmatic proof is unique). Output is a SHADOW candidate
(``output/pred_v13_multilayer_candidate.csv``); never overwrites the frozen best, v10, v8, or
pred.csv.

Conservative acceptance (proposed label must differ from current and be valid for the sample):
  1) programmatic_solver has a unique deterministic option match; OR
  2) content_first AND least_to_most agree on the same non-current label; OR
  3) content_first agrees with a v12B stable mapped vote; OR
  4) least_to_most uniquely eliminates current and supports a new label, AND another layer agrees.
Reject on: single weak model-only source, label/option mismatch, numeric mismatch, ambiguous
match, parse failure, or label invalid for the sample.
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
from src.utils.labels import is_valid_label  # noqa: E402

_PROTECTED_NAMES = {"pred_v11_independent_rerun1.csv", "pred_v10_full_production_user_run.csv",
                    "pred_v8_clean_generalized_from_v7.csv", "pred.csv"}


def _guard_output(path):
    if Path(path).name in _PROTECTED_NAMES:
        raise SystemExit(f"REFUSING to overwrite protected file: {Path(path).name}")


def _load_jsonl(path, qid_keys=("qid", "original_qid")):
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
                qid = next((rec[k] for k in qid_keys if rec.get(k)), None)
                if qid:
                    out[qid].append(rec)
    return out


def _valid_layer_label(rec):
    if (rec.get("parse_status") or "") != "ok" or not rec.get("valid"):
        return None
    return rec.get("proposed_label")


def _v12b_stable_label(records, current):
    valid = [r for r in records if r.get("valid") and r.get("parse_status") == "ok"]
    if len(valid) < 5:
        return None
    votes = Counter(r.get("mapped_original_label") for r in valid)
    non_cur = {l: c for l, c in votes.items() if l and l != current}
    if not non_cur:
        return None
    best = max(non_cur, key=lambda L: non_cur[L])
    if non_cur[best] >= 4 and votes.get(current, 0) <= 1:
        return best
    return None


def decide_override(qid, current, layer_records, sample, *, policy, v12b_records=None):
    by_layer = defaultdict(list)
    for r in layer_records:
        lab = _valid_layer_label(r)
        if lab and lab != current and is_valid_label(lab, sample):
            by_layer[r["layer"]].append(lab)

    def _maj(layer):
        labs = by_layer.get(layer, [])
        if not labs:
            return None
        c = Counter(labs)
        top = max(c, key=lambda L: c[L])
        return top

    prog = _maj("programmatic_solver")
    content = _maj("content_first")
    ltm = _maj("least_to_most")
    v12b = _v12b_stable_label(v12b_records or [], current)

    base = {"qid": qid, "current": current, "policy": policy,
            "programmatic": prog, "content_first": content, "least_to_most": ltm, "v12b": v12b}

    # Rule 1: deterministic programmatic unique match.
    if prog:
        return prog, {**base, "verdict": "accept", "proposed": prog, "rule": "programmatic_unique"}
    # Rule 2: content_first AND least_to_most agree.
    if content and ltm and content == ltm:
        return content, {**base, "verdict": "accept", "proposed": content,
                         "rule": "content+ltm_agree"}
    # Rule 3: content_first agrees with v12B stable vote.
    if content and v12b and content == v12b:
        return content, {**base, "verdict": "accept", "proposed": content,
                         "rule": "content+v12b_agree"}
    # Rule 4: least_to_most unique survivor + another layer agrees.
    if ltm and ((content == ltm) or (prog == ltm) or (v12b == ltm)):
        return ltm, {**base, "verdict": "accept", "proposed": ltm, "rule": "ltm+corroborated"}
    # Balanced: content_first alone may pass only with strong confidence (handled upstream by
    # validity); here we keep conservative — single weak source is rejected.
    proposed = content or ltm or v12b
    return None, {**base, "verdict": "reject" if proposed else "keep",
                  "proposed": proposed, "rule": "insufficient_agreement"}


def _validate(rows, samples):
    by_qid = {s["qid"]: s for s in samples}
    if not rows:
        raise SystemExit("REFUSING: empty output")
    if set(rows[0].keys()) < {"qid", "answer"}:
        raise SystemExit("REFUSING: missing columns")
    qids = [r["qid"] for r in rows]
    if len(set(qids)) != len(qids):
        raise SystemExit("REFUSING: duplicate qids")
    if set(qids) != set(by_qid):
        raise SystemExit("REFUSING: qid set mismatch")
    for r in rows:
        if not r.get("answer") or not is_valid_label(r["answer"], by_qid[r["qid"]]):
            raise SystemExit(f"REFUSING: invalid label {r.get('answer')!r} for {r['qid']}")
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V13 multi-layer candidate selector")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--v12b-records", default=None)
    ap.add_argument("--output", default="output/pred_v13_multilayer_candidate.csv")
    ap.add_argument("--review-dir", default="scratch/v13_multilayer/review")
    ap.add_argument("--policy", choices=["conservative", "balanced"], default="conservative")
    ap.add_argument("--max-overrides", type=int, default=None)
    args = ap.parse_args(argv)

    _guard_output(args.output)
    samples = load_dataset(args.input)
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    layer_recs = _load_jsonl(args.candidates)
    v12b = _load_jsonl(args.v12b_records)

    review = Path(args.review_dir); review.mkdir(parents=True, exist_ok=True)
    accepted, rejected = [], []
    new_answers = dict(current)
    for s in samples:
        qid = s["qid"]
        new_label, dec = decide_override(qid, current.get(qid, ""), layer_recs.get(qid, []),
                                         s, policy=args.policy, v12b_records=v12b.get(qid, []))
        if dec["verdict"] == "accept":
            accepted.append(dec)
        elif dec["verdict"] == "reject":
            rejected.append(dec)

    accepted.sort(key=lambda d: d["qid"])
    applied = accepted if args.max_overrides is None else accepted[:args.max_overrides]
    for d in applied:
        new_answers[d["qid"]] = d["proposed"]

    rows = [{"qid": s["qid"], "answer": new_answers[s["qid"]]} for s in samples]
    n = _validate(rows, samples)
    write_predictions(rows, args.output)

    diff = [{"qid": q, "v11_answer": current[q], "v13_answer": new_answers[q],
             "rule": next((d["rule"] for d in applied if d["qid"] == q), "")}
            for q in current if current[q] != new_answers[q]]
    with (review / "v13_delta_diff.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "v11_answer", "v13_answer", "rule"])
        w.writeheader(); w.writerows(diff)
    with (review / "v13_rejected_overrides.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["qid", "current", "proposed", "rule",
                                          "programmatic", "content_first", "least_to_most", "v12b"])
        w.writeheader()
        for d in rejected:
            w.writerow({k: d.get(k, "") for k in
                        ("qid", "current", "proposed", "rule", "programmatic",
                         "content_first", "least_to_most", "v12b")})

    summary = {"policy": args.policy, "total_qids": len(samples),
               "overrides_accepted": len(accepted), "overrides_applied": len(applied),
               "overrides_rejected": len(rejected), "changed_vs_v11": len(diff),
               "validation": "PASS", "rows": n, "output": args.output}
    (review / "v13_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (review / "v13_summary.md").write_text(
        "# V13 Multi-Layer Candidate Summary\n\n"
        + "\n".join(f"- **{k}**: {v}" for k, v in summary.items())
        + f"\n\n- changed qids: {', '.join(d['qid'] for d in diff) or '(none)'}\n", encoding="utf-8")

    print("=" * 60)
    print("V13 MULTI-LAYER CANDIDATE")
    for k, v in summary.items():
        print(f"{k:20}: {v}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
