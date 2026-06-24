#!/usr/bin/env python3
"""One-shot integrity audit of an independent v11 run (Phase 2L.30D; read-only, no API).

Inspects existing run artifacts (decisions CSV + candidates JSONL) and, optionally, a
submission CSV, against the dataset. Reports dataset/candidate/decision counts, missing /
duplicate / invalid / none-empty qids, fallback-used + last-resort counts, and submission
validity. Writes a Markdown + JSON report under the work-dir. Never writes outputs, never
calls an API, never uses v10/ground truth.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.layers.adaptive_proposal_common import load_samples  # noqa: E402
from src.utils.labels import labels_for  # noqa: E402


def _labels(sample):
    return set(labels_for(len(sample.get("choices", []) or [])))


def _bad(answer, labels):
    return (answer is None) or (str(answer).strip() in ("", "None")) or (answer not in labels)


def _count_jsonl(path):
    n = 0
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if line.strip():
                n += 1
    return n


def _audit_rows(rows, samples, answer_key):
    seen = Counter()
    invalid, none_empty = [], []
    fallback_used = last_resort = 0
    for r in rows:
        q = r.get("qid"); seen[q] += 1
        labels = _labels(samples.get(q, {}))
        a = r.get(answer_key)
        if a is None or str(a).strip() in ("", "None"):
            none_empty.append(q)
        elif a not in labels:
            invalid.append(q)
        if str(r.get("fallback_used", "")).lower() == "true":
            fallback_used += 1
        if r.get("final_source") == "last_resort_valid_choice":
            last_resort += 1
    return {
        "rows": len(rows), "unique_qids": len(seen),
        "duplicate_qids": sorted(q for q, c in seen.items() if c > 1),
        "missing_qids": sorted(q for q in samples if q not in seen),
        "invalid_labels": sorted(set(invalid)), "none_or_empty": sorted(set(none_empty)),
        "fallback_used": fallback_used, "last_resort_valid_choice": last_resort,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit independent v11 run integrity (no API)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--submission", default=None)
    args = ap.parse_args(argv)

    workdir = Path(args.work_dir)
    samples = {s.get("qid"): s for s in load_samples(args.input)}
    dec_path = workdir / "v11_independent_decisions.csv"
    cand_path = workdir / "v11_independent_candidates.jsonl"

    report = {"dataset_qids": len(samples),
              "candidate_records": _count_jsonl(cand_path),
              "decisions_file_present": dec_path.exists(),
              "candidates_file_present": cand_path.exists()}
    if dec_path.exists():
        rows = list(csv.DictReader(open(dec_path)))
        dec = _audit_rows(rows, samples, "final_answer")
        report["decisions"] = dec
        report["decisions_clean"] = not (dec["duplicate_qids"] or dec["missing_qids"]
                                         or dec["invalid_labels"] or dec["none_or_empty"])

    if args.submission:
        if Path(args.submission).exists():
            srows = list(csv.DictReader(open(args.submission)))
            sub = _audit_rows(srows, samples, "answer")
            sub["valid_submission"] = not (sub["duplicate_qids"] or sub["missing_qids"]
                                           or sub["invalid_labels"] or sub["none_or_empty"])
            report["submission"] = {"path": args.submission, **sub}
        else:
            report["submission"] = {"path": args.submission, "present": False,
                                    "note": "submission file does not exist (nothing to validate)"}

    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "v11_independent_integrity_audit.json").write_text(json.dumps(report, indent=2))
    lines = ["# Independent v11 Integrity Audit (read-only; no API)", "",
             f"- dataset qids: {report['dataset_qids']}",
             f"- candidate records: {report['candidate_records']}",
             f"- decisions file present: {report['decisions_file_present']}"]
    if "decisions" in report:
        d = report["decisions"]
        lines += [f"- decision rows: {d['rows']}  unique: {d['unique_qids']}",
                  f"- missing: {len(d['missing_qids'])}  duplicate: {len(d['duplicate_qids'])}  "
                  f"invalid: {len(d['invalid_labels'])}  none/empty: {len(d['none_or_empty'])}",
                  f"- fallback_used: {d['fallback_used']}  last_resort: {d['last_resort_valid_choice']}",
                  f"- **decisions clean: {report['decisions_clean']}**"]
        if d["none_or_empty"]:
            lines.append(f"- none/empty qids: {d['none_or_empty'][:20]}")
        if d["missing_qids"]:
            lines.append(f"- missing qids: {d['missing_qids'][:20]}")
    if "submission" in report:
        s = report["submission"]
        if s.get("present") is False:
            lines.append(f"- submission: NOT PRESENT ({s['path']})")
        else:
            lines.append(f"- submission `{s['path']}`: rows {s['rows']}, "
                         f"**valid: {s['valid_submission']}** "
                         f"(missing {len(s['missing_qids'])}, dup {len(s['duplicate_qids'])}, "
                         f"invalid {len(s['invalid_labels'])}, none {len(s['none_or_empty'])})")
    (workdir / "v11_independent_integrity_audit.md").write_text("\n".join(lines))

    print("=" * 64)
    print("V11 INDEPENDENT INTEGRITY AUDIT (no API)")
    print("=" * 64)
    for ln in lines[2:]:
        print(ln.replace("- ", "  ").replace("**", ""))
    print(f"-> {workdir}/v11_independent_integrity_audit.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
