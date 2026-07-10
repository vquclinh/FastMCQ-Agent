#!/usr/bin/env python3
"""Filter and score confidence-promotion validation outputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.utils.labels import labels_for


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    records = payload.get("records")
    if not isinstance(records, list):
        raise SystemExit(f"manifest has no records list: {path}")
    return records


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["qid", "answer"])
        writer.writeheader()
        writer.writerows(rows)


def filter_submission(*, manifest_path: Path, source_csv: Path, output_csv: Path) -> dict[str, Any]:
    manifest = _read_manifest(manifest_path)
    source_rows = _read_csv(source_csv)
    by_qid = {row["qid"]: row["answer"] for row in source_rows}
    out: list[dict[str, str]] = []
    missing: list[str] = []
    for record in manifest:
        qid = record["qid"]
        if qid not in by_qid:
            missing.append(qid)
        else:
            out.append({"qid": qid, "answer": by_qid[qid]})
    if missing:
        raise SystemExit(f"source CSV is missing {len(missing)} subset qids: {missing[:5]}")
    _write_csv(output_csv, out)
    return {"rows": len(out), "output_csv": str(output_csv)}


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ordered_answers(path: Path, manifest: list[dict[str, Any]]) -> list[str]:
    rows = _read_csv(path)
    expected_qids = [record["qid"] for record in manifest]
    actual_qids = [row["qid"] for row in rows]
    if actual_qids != expected_qids:
        raise SystemExit(f"CSV qid order mismatch for {path}")
    return [str(row["answer"]).strip().upper() for row in rows]


def _empty_metric_bucket() -> dict[str, int]:
    return {
        "total": 0,
        "base_correct": 0,
        "final_correct": 0,
        "corrections": 0,
        "regressions": 0,
        "changed": 0,
    }


def _finish_bucket(bucket: dict[str, int]) -> dict[str, Any]:
    total = bucket["total"]
    out: dict[str, Any] = dict(bucket)
    out["base_accuracy"] = bucket["base_correct"] / total if total else 0.0
    out["final_accuracy"] = bucket["final_correct"] / total if total else 0.0
    return out


def score_outputs(
    *,
    manifest_path: Path,
    base_csv: Path,
    final_csv: Path,
    output_json: Path,
    pipeline_jsonl: Path | None = None,
    pipeline_summary_path: Path | None = None,
    router_summary_path: Path | None = None,
) -> dict[str, Any]:
    manifest = _read_manifest(manifest_path)
    base_answers = _ordered_answers(base_csv, manifest)
    final_answers = _ordered_answers(final_csv, manifest)
    pipeline_rows = _read_jsonl(pipeline_jsonl)
    source_by_qid = {row.get("qid"): row.get("final_source", "unknown") for row in pipeline_rows}
    if not source_by_qid:
        source_by_qid = {record["qid"]: "base" for record in manifest}

    totals = _empty_metric_bucket()
    by_category: dict[str, dict[str, int]] = defaultdict(_empty_metric_bucket)
    by_source: dict[str, dict[str, int]] = defaultdict(_empty_metric_bucket)
    invalid_labels: list[dict[str, str]] = []
    changed_qids: list[str] = []
    correction_qids: list[str] = []
    regression_qids: list[str] = []

    for ordinal, record in enumerate(manifest):
        expected = str(record["expected_answer"]).strip().upper()
        valid = labels_for(int(record["choice_count"]))
        base = base_answers[ordinal]
        final = final_answers[ordinal]
        if base not in valid:
            invalid_labels.append({"qid": record["qid"], "which": "base", "answer": base})
        if final not in valid:
            invalid_labels.append({"qid": record["qid"], "which": "final", "answer": final})
        base_ok = base == expected
        final_ok = final == expected
        changed = base != final
        source = str(source_by_qid.get(record["qid"], "unknown"))
        for bucket in (totals, by_category[str(record["category"])], by_source[source]):
            bucket["total"] += 1
            bucket["base_correct"] += int(base_ok)
            bucket["final_correct"] += int(final_ok)
            bucket["corrections"] += int((not base_ok) and final_ok)
            bucket["regressions"] += int(base_ok and (not final_ok))
            bucket["changed"] += int(changed)
        if changed:
            changed_qids.append(record["qid"])
        if (not base_ok) and final_ok:
            correction_qids.append(record["qid"])
        if base_ok and (not final_ok):
            regression_qids.append(record["qid"])

    if invalid_labels:
        raise SystemExit(f"non-canonical labels found: {invalid_labels[:5]}")

    pipeline_summary = _read_json(pipeline_summary_path) if pipeline_summary_path and pipeline_summary_path.exists() else {}
    router_summary = _read_json(router_summary_path) if router_summary_path and router_summary_path.exists() else {}
    result = _finish_bucket(totals)
    result.update({
        "net_corrected_records": totals["corrections"] - totals["regressions"],
        "neutral_changes": totals["changed"] - totals["corrections"] - totals["regressions"],
        "correction_precision": (totals["corrections"] / totals["changed"]) if totals["changed"] else 0.0,
        "regression_rate": (totals["regressions"] / totals["changed"]) if totals["changed"] else 0.0,
        "changed_qids": changed_qids,
        "correction_qids": correction_qids,
        "regression_qids": regression_qids,
        "by_category": {key: _finish_bucket(value) for key, value in sorted(by_category.items())},
        "by_final_source": {key: _finish_bucket(value) for key, value in sorted(by_source.items())},
        "final_source_counts": dict(Counter(source_by_qid.get(record["qid"], "unknown") for record in manifest)),
        "router": {
            "candidate_count": router_summary.get("candidate_count"),
            "selected_count": router_summary.get("selected_count"),
            "reason_counts": router_summary.get("reason_counts"),
            "selected_qids": router_summary.get("selected_qids"),
        },
        "pipeline_summary": pipeline_summary,
    })
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_filter = sub.add_parser("filter")
    p_filter.add_argument("--manifest", required=True)
    p_filter.add_argument("--source-csv", required=True)
    p_filter.add_argument("--output-csv", required=True)

    p_score = sub.add_parser("score")
    p_score.add_argument("--manifest", required=True)
    p_score.add_argument("--base-csv", required=True)
    p_score.add_argument("--final-csv", required=True)
    p_score.add_argument("--output-json", required=True)
    p_score.add_argument("--pipeline-jsonl")
    p_score.add_argument("--pipeline-summary")
    p_score.add_argument("--router-summary")

    args = parser.parse_args(argv)
    if args.cmd == "filter":
        result = filter_submission(
            manifest_path=Path(args.manifest),
            source_csv=Path(args.source_csv),
            output_csv=Path(args.output_csv),
        )
    else:
        result = score_outputs(
            manifest_path=Path(args.manifest),
            base_csv=Path(args.base_csv),
            final_csv=Path(args.final_csv),
            output_json=Path(args.output_json),
            pipeline_jsonl=Path(args.pipeline_jsonl) if args.pipeline_jsonl else None,
            pipeline_summary_path=Path(args.pipeline_summary) if args.pipeline_summary else None,
            router_summary_path=Path(args.router_summary) if args.router_summary else None,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
