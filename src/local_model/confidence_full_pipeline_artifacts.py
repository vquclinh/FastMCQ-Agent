"""Phase 3B full confidence pipeline: privacy-safe diagnostics writer.

Writes exactly the closed, text-free schema the selector already computed
(``FullPipelineRecord``/``FullPipelineSummary`` in ``confidence_full_pipeline.py``):
labels, closed status codes, booleans, and ordinals only. Never writes question,
choices, prompt, raw model output, reasoning, evidence, expected answer,
correctness, or ground truth. Two independently atomic files; either may fail
without affecting the other or the official submission (already written by the
caller before this module runs).
"""

from __future__ import annotations

import json
from pathlib import Path

from src.local_model.confidence_full_pipeline import FullPipelineRecord, FullPipelineSummary


def _write_json_atomic(path: str, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(p)


def write_full_pipeline_artifacts(
    *,
    records: list[FullPipelineRecord],
    summary: FullPipelineSummary,
    jsonl_path: str,
    summary_path: str,
) -> dict:
    """Best-effort, independently atomic write of the full-pipeline diagnostics.
    Never raises past the caller; each file has its own status. The official
    submission is written by the caller before this runs and is never touched
    here."""
    status = {"jsonl_written": False, "summary_written": False}
    try:
        lines = [json.dumps(record.as_dict(), ensure_ascii=False, allow_nan=False) for record in records]
        _write_json_atomic(jsonl_path, ("\n".join(lines) + "\n") if lines else "")
        status["jsonl_written"] = True
    except (OSError, ValueError, TypeError) as e:
        print(f"[predict] WARN full-pipeline JSONL not written ({type(e).__name__})")
    try:
        _write_json_atomic(
            summary_path,
            json.dumps(summary.as_dict(), ensure_ascii=False, allow_nan=False, indent=2),
        )
        status["summary_written"] = True
    except (OSError, ValueError, TypeError) as e:
        print(f"[predict] WARN full-pipeline summary not written ({type(e).__name__})")
    print(f"[predict] full pipeline -> {jsonl_path} ({len(records)} records)")
    return status
