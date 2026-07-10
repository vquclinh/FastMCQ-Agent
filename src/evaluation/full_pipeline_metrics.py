"""Deterministic full-pipeline evaluator (Base vs. selector-final accuracy).

Pure, offline, calibration/analysis-only. NEVER imported by ``predict.py`` or any
inference-path module -- it exists solely to score a caller-supplied labeled fixture
against Base and full-pipeline answers already computed elsewhere. It does not read
organizer test data, does not download anything, and makes no assumption about where
its ``expected_answer`` values came from beyond "the caller supplied them" (permitted
synthetic fixtures only, per the governing audits -- this module itself has no
opinion on data provenance).

Records are compared by list position / explicit ``record_ordinal``, never merged or
deduplicated by ``qid`` -- a labeled fixture with repeated qids is scored as that many
distinct records, consistent with the rest of the confidence-routed pipeline's
identity contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class FullPipelineEvalRecord:
    record_ordinal: int
    qid: str
    expected_answer: str
    base_answer: str
    final_answer: str
    final_source: str  # "base" | "v12b" | "v13" | "base_fallback"


@dataclass(frozen=True)
class FullPipelineEvalResult:
    total_records: int
    base_correct: int
    final_correct: int
    base_accuracy: float
    final_accuracy: float
    v12b_override_count: int
    v13_override_count: int
    base_fallback_count: int
    corrections: int
    regressions: int
    net_accuracy_difference: float

    def as_dict(self) -> dict:
        return {
            "total_records": self.total_records,
            "base_correct": self.base_correct,
            "final_correct": self.final_correct,
            "base_accuracy": self.base_accuracy,
            "final_accuracy": self.final_accuracy,
            "v12b_override_count": self.v12b_override_count,
            "v13_override_count": self.v13_override_count,
            "base_fallback_count": self.base_fallback_count,
            "corrections": self.corrections,
            "regressions": self.regressions,
            "net_accuracy_difference": self.net_accuracy_difference,
        }


def evaluate_full_pipeline(records: Iterable[FullPipelineEvalRecord]) -> FullPipelineEvalResult:
    """Score a labeled fixture (already paired with Base/final answers by the
    caller) against Base and the full-pipeline selector's final answer.

    * ``corrections``  -- Base was wrong, the final answer is right.
    * ``regressions``  -- Base was right, the final answer is wrong.
    * ``net_accuracy_difference`` -- ``final_accuracy - base_accuracy`` (may be
      negative). This function computes arithmetic only; it never runs inference
      and is never called from the inference path.
    """
    records = list(records)
    total = len(records)
    base_correct = sum(1 for r in records if r.base_answer == r.expected_answer)
    final_correct = sum(1 for r in records if r.final_answer == r.expected_answer)
    corrections = sum(
        1 for r in records if r.base_answer != r.expected_answer and r.final_answer == r.expected_answer
    )
    regressions = sum(
        1 for r in records if r.base_answer == r.expected_answer and r.final_answer != r.expected_answer
    )
    v12b_overrides = sum(1 for r in records if r.final_source == "v12b")
    v13_overrides = sum(1 for r in records if r.final_source == "v13")
    base_fallback = sum(1 for r in records if r.final_source == "base_fallback")
    base_accuracy = (base_correct / total) if total else 0.0
    final_accuracy = (final_correct / total) if total else 0.0
    return FullPipelineEvalResult(
        total_records=total,
        base_correct=base_correct,
        final_correct=final_correct,
        base_accuracy=base_accuracy,
        final_accuracy=final_accuracy,
        v12b_override_count=v12b_overrides,
        v13_override_count=v13_overrides,
        base_fallback_count=base_fallback,
        corrections=corrections,
        regressions=regressions,
        net_accuracy_difference=final_accuracy - base_accuracy,
    )
