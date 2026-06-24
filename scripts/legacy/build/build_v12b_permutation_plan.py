#!/usr/bin/env python3
"""Phase 2L.34B — V12B option-permutation target plan (OFFLINE, no API).

Selects/ranks qids of the frozen v11 winner that are most likely to suffer MCQ
label-position / option-order bias, so an option-permutation verifier can re-probe them.
It changes no answer — it only writes a plan CSV.

Priority signals (derived from existing v11 artifacts; no ground truth, no qid hardcoding):
  * direct_fallback / direct_fallback_repair provenance
  * high decision risk
  * v11 != v10 disagreement
  * option_count >= 5 (more positions => more room for position bias)
  * near-duplicate / highly-similar option texts (label choice is fragile)
  * API-candidate disagreement history
  * parser failures in the candidate pool
  * weak single-source provenance (api:* single agent)
  * many-choice labels beyond H (I/J/K ...)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))

from src.utils.data_io import load_dataset, read_predictions  # noqa: E402
from src.evidence.option_grounding import extract_option_features  # noqa: E402

_FALLBACK_SOURCES = {"direct_fallback", "direct_fallback_repair"}
_SINGLE_API_PREFIX = "api:"


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


def _read_candidates(path):
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
                if rec.get("qid"):
                    out[rec["qid"]].append(rec)
    return out


def has_similar_options(choices):
    """True if any two options share a strong majority of content words (fragile to position)."""
    feats = extract_option_features(choices)
    for a, b in combinations(feats, 2):
        if not a.phrases or not b.phrases:
            continue
        inter = len(a.phrases & b.phrases)
        smaller = min(len(a.phrases), len(b.phrases))
        if smaller and inter / smaller >= 0.6:
            return True
    return False


def _suggested_permutations(option_count):
    perms = ["original", "reverse", "rotate+1", "rotate+2", "random_seed1", "random_seed2"]
    # With very few options some permutations collide; still list the canonical set.
    return perms if option_count >= 2 else ["original"]


def build_plan(samples, current, *, v10=None, decisions=None, candidates=None):
    v10 = v10 or {}
    decisions = decisions or {}
    candidates = candidates or {}
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

        reasons, score = [], 0.0
        if source in _FALLBACK_SOURCES:
            score += 5.0; reasons.append(f"fallback_source:{source}")
        elif source.startswith(_SINGLE_API_PREFIX):
            score += 1.0; reasons.append(f"single_api_source:{source}")
        if risk == "high":
            score += 3.0; reasons.append("risk:high")
        elif risk == "medium":
            score += 1.0; reasons.append("risk:medium")
        v10_ans = (v10.get(qid) or "").strip()
        if v10_ans and cur and v10_ans != cur:
            score += 2.0; reasons.append(f"v11!=v10({cur}vs{v10_ans})")
        if n >= 5:
            score += 2.0; reasons.append(f"option_count:{n}")
        if n > 8:   # labels beyond H
            score += 1.0; reasons.append("labels_beyond_H")
        if has_similar_options(choices):
            score += 1.5; reasons.append("near_duplicate_options")
        cand_list = candidates.get(qid, [])
        cand_answers = {(c.get("answer") or "").strip() for c in cand_list if c.get("answer")}
        if cand_answers and any(a and a != cur for a in cand_answers):
            score += 1.5; reasons.append("api_candidate_disagreement")
        bad_parse = sum(1 for c in cand_list if (c.get("parse_status") or "ok") != "ok")
        if bad_parse:
            score += 1.0; reasons.append(f"parse_failures:{bad_parse}")

        plan.append({
            "qid": qid,
            "current_answer": cur,
            "option_count": n,
            "current_source": source,
            "risk_reason": ";".join(reasons) if reasons else "none",
            "permutation_priority": round(score, 3),
            "suggested_permutations": "|".join(_suggested_permutations(n)),
            "notes": (dec.get("note") or "")[:160],
        })
    plan.sort(key=lambda r: (-r["permutation_priority"], r["qid"]))
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="V12B option-permutation target plan (offline)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--v10", default=None)
    ap.add_argument("--decisions", default=None)
    ap.add_argument("--candidates", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--min-priority", type=float, default=0.0)
    args = ap.parse_args(argv)

    samples = load_dataset(args.input)
    current = {r["qid"]: r["answer"] for r in read_predictions(args.current)}
    v10 = _read_csv_map(args.v10, "qid", "answer")
    decisions = _read_decisions(args.decisions)
    candidates = _read_candidates(args.candidates)

    plan = build_plan(samples, current, v10=v10, decisions=decisions, candidates=candidates)
    emitted = [r for r in plan if r["permutation_priority"] > args.min_priority]

    outp = Path(args.output); outp.parent.mkdir(parents=True, exist_ok=True)
    cols = ["qid", "current_answer", "option_count", "current_source", "risk_reason",
            "permutation_priority", "suggested_permutations", "notes"]
    with outp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(emitted)

    print("=" * 60)
    print("V12B OPTION-PERMUTATION PLAN (offline, no API)")
    print(f"input questions       : {len(samples)}")
    print(f"planned (prio>{args.min_priority})   : {len(emitted)} / {len(plan)}")
    print(f"many-option (>=5) qids: {sum(1 for r in emitted if r['option_count'] >= 5)}")
    print(f"output                : {outp}")
    print("-- top targets --")
    for r in emitted[:10]:
        print(f"  {r['qid']}  prio={r['permutation_priority']:<5} n={r['option_count']:<2} "
              f"{r['current_source'] or '-':<22} {r['risk_reason'][:54]}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
