"""Unit: deterministic full-pipeline evaluator (calibration/analysis only).

Proves corrections/regressions are computed exactly, override counts are counted
by ``final_source``, duplicate qids are scored as distinct records, and the
evaluator makes no organizer-data assumption -- it is pure arithmetic over
caller-supplied records. This module is never imported by the inference path.
"""

from __future__ import annotations

from src.evaluation.full_pipeline_metrics import (
    FullPipelineEvalRecord,
    evaluate_full_pipeline,
)


def _rec(ordinal, qid, expected, base, final, source):
    return FullPipelineEvalRecord(
        record_ordinal=ordinal, qid=qid, expected_answer=expected,
        base_answer=base, final_answer=final, final_source=source)


def test_zero_overrides_all_base():
    records = [
        _rec(0, "a", "A", "A", "A", "base"),
        _rec(1, "b", "B", "C", "C", "base"),
    ]
    result = evaluate_full_pipeline(records)
    assert result.total_records == 2
    assert result.v12b_override_count == 0 and result.v13_override_count == 0
    assert result.base_fallback_count == 0
    assert result.corrections == 0 and result.regressions == 0
    assert result.base_accuracy == result.final_accuracy == 0.5
    assert result.net_accuracy_difference == 0.0


def test_perfect_base_no_change_possible():
    records = [_rec(i, f"q{i}", "A", "A", "A", "base") for i in range(5)]
    result = evaluate_full_pipeline(records)
    assert result.base_accuracy == 1.0 and result.final_accuracy == 1.0
    assert result.corrections == 0 and result.regressions == 0
    assert result.net_accuracy_difference == 0.0


def test_perfect_full_pipeline_all_corrections():
    records = [_rec(i, f"q{i}", "A", "B", "A", "v12b") for i in range(4)]
    result = evaluate_full_pipeline(records)
    assert result.base_accuracy == 0.0
    assert result.final_accuracy == 1.0
    assert result.corrections == 4
    assert result.regressions == 0
    assert result.net_accuracy_difference == 1.0


def test_corrections_and_regressions_computed_exactly():
    records = [
        _rec(0, "a", "A", "B", "A", "v12b"),         # correction (wrong -> right)
        _rec(1, "b", "A", "A", "B", "v13"),           # regression (right -> wrong)
        _rec(2, "c", "A", "A", "A", "base"),          # unchanged correct
        _rec(3, "d", "A", "B", "C", "base_fallback"),  # unchanged wrong (still wrong)
    ]
    result = evaluate_full_pipeline(records)
    assert result.total_records == 4
    assert result.base_correct == 2   # a: wrong, b: correct, c: correct, d: wrong -> 2
    assert result.final_correct == 2  # a: correct, b: wrong, c: correct, d: wrong -> 2
    assert result.corrections == 1
    assert result.regressions == 1
    assert result.net_accuracy_difference == 0.0
    assert result.v12b_override_count == 1
    assert result.v13_override_count == 1
    assert result.base_fallback_count == 1


def test_duplicate_qids_handled_as_distinct_records():
    records = [
        _rec(0, "dup", "A", "B", "A", "v12b"),   # correction
        _rec(1, "dup", "A", "A", "A", "base"),   # unchanged correct
    ]
    result = evaluate_full_pipeline(records)
    assert result.total_records == 2            # both counted, not merged by qid
    assert result.corrections == 1
    assert result.regressions == 0
    assert result.base_accuracy == 0.5


def test_empty_input_is_well_defined():
    result = evaluate_full_pipeline([])
    assert result.total_records == 0
    assert result.base_accuracy == 0.0 and result.final_accuracy == 0.0
    assert result.net_accuracy_difference == 0.0


def test_as_dict_has_no_organizer_or_text_fields():
    records = [_rec(0, "a", "A", "A", "A", "base")]
    result = evaluate_full_pipeline(records)
    d = result.as_dict()
    assert set(d.keys()) == {
        "total_records", "base_correct", "final_correct", "base_accuracy",
        "final_accuracy", "v12b_override_count", "v13_override_count",
        "base_fallback_count", "corrections", "regressions", "net_accuracy_difference",
    }
