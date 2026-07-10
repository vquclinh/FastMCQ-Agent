"""Unit tests for the confidence-promotion benchmark generator.

These tests prove that the committed benchmark is reproducible, that every gold
label comes from deterministic local logic, and that malformed/imbalanced
payloads are rejected before any real-model evaluation can use them.
"""

from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

import scripts.validation.build_confidence_promotion_benchmark as bench
from src.utils.labels import index_to_label, labels_for


def _payloads():
    return bench.build_benchmark_payload(), bench.build_manifest_payload()


def _choice_for_expected(record):
    return record["choices"][labels_for(record["choice_count"]).index(record["expected_answer"])]


def test_deterministic_regeneration():
    b1, m1 = _payloads()
    b2, m2 = _payloads()
    assert bench._canonical_json_bytes(b1) == bench._canonical_json_bytes(b2)
    assert bench._canonical_json_bytes(m1) == bench._canonical_json_bytes(m2)
    summary = bench.validate_payloads(b1, m1)
    assert summary["records"] == 120


def test_committed_files_match_deterministic_generator():
    expected_benchmark, expected_manifest = _payloads()
    benchmark_path = Path("validation/confidence_promotion_benchmark.json")
    manifest_path = Path("validation/confidence_promotion_manifest.json")
    assert benchmark_path.read_bytes() == bench._canonical_json_bytes(expected_benchmark)
    assert manifest_path.read_bytes() == bench._canonical_json_bytes(expected_manifest)
    bench.validate_payloads(
        json.loads(benchmark_path.read_text(encoding="utf-8")),
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )


def test_answer_key_correctness():
    benchmark, manifest = _payloads()
    bench.validate_payloads(benchmark, manifest)
    for record in manifest["records"]:
        assert bench.expected_label_for_manifest_record(record) == record["expected_answer"]
        assert bench.solve_gold_choice(record["deterministic_gold"]) == _choice_for_expected(record)


def test_arithmetic_generator_correctness():
    _benchmark, manifest = _payloads()
    records = [r for r in manifest["records"] if r["category"] == bench.CATEGORY_PROGRAMMATIC]
    assert len(records) == 40
    for record in records:
        gold = record["deterministic_gold"]
        value = bench._programmatic_value(gold["operation"], gold["params"])
        assert bench._format_value(value, gold.get("unit")) == _choice_for_expected(record)
        assert gold["gold_source"] == "computed_by_python_arithmetic"


def test_content_fact_mapping_correctness():
    _benchmark, manifest = _payloads()
    records = [r for r in manifest["records"] if r["category"] == bench.CATEGORY_CONTENT]
    assert len(records) == 40
    for record in records:
        gold = record["deterministic_gold"]
        assert bench.solve_content_gold(gold) == _choice_for_expected(record)
        assert gold["gold_source"] == "explicit_local_fact_table"


def test_least_to_most_solver_correctness():
    _benchmark, manifest = _payloads()
    records = [r for r in manifest["records"] if r["category"] == bench.CATEGORY_LOGIC]
    assert len(records) == 40
    for record in records:
        gold = record["deterministic_gold"]
        assert bench.solve_gold_choice(gold) == _choice_for_expected(record)
        assert gold["gold_source"] in {
            "exhaustive_permutation_solver",
            "exhaustive_assignment_solver",
            "deterministic_logic_table_solver",
        }


def test_choice_label_validity():
    _benchmark, manifest = _payloads()
    for record in manifest["records"]:
        valid_labels = labels_for(record["choice_count"])
        assert record["expected_answer"] in valid_labels
        assert 2 <= record["choice_count"] <= 26
        assert len(record["choices"]) == record["choice_count"]
        assert len(record["choices"]) == len(set(record["choices"]))


def test_duplicate_qid_rejection():
    benchmark, manifest = _payloads()
    benchmark = copy.deepcopy(benchmark)
    manifest = copy.deepcopy(manifest)
    duplicate = manifest["records"][0]["qid"]
    benchmark[1]["qid"] = duplicate
    manifest["records"][1]["qid"] = duplicate
    with pytest.raises(bench.BenchmarkValidationError, match="duplicate qid"):
        bench.validate_payloads(benchmark, manifest)


def test_malformed_record_rejection():
    benchmark, manifest = _payloads()
    bad_benchmark = copy.deepcopy(benchmark)
    bad_benchmark[0]["expected_answer"] = "A"
    with pytest.raises(bench.BenchmarkValidationError, match="non-input fields"):
        bench.validate_payloads(bad_benchmark, copy.deepcopy(manifest))

    bad_manifest = copy.deepcopy(manifest)
    bad_manifest["records"][0]["expected_answer"] = "Z"
    with pytest.raises(bench.BenchmarkValidationError, match="not canonical"):
        bench.validate_payloads(copy.deepcopy(benchmark), bad_manifest)


def test_category_layer_coverage():
    _benchmark, manifest = _payloads()
    category_counts = Counter(r["category"] for r in manifest["records"])
    layer_counts = Counter(r["intended_v13_layer"] for r in manifest["records"])
    language_counts = Counter(r["language"] for r in manifest["records"])
    assert category_counts == {
        bench.CATEGORY_PROGRAMMATIC: 40,
        bench.CATEGORY_CONTENT: 40,
        bench.CATEGORY_LOGIC: 40,
    }
    assert layer_counts == {
        bench.LAYER_PROGRAMMATIC: 40,
        bench.LAYER_CONTENT: 40,
        bench.LAYER_LOGIC: 40,
    }
    assert language_counts == {"en": 60, "vi": 60}


def test_answer_position_distribution():
    _benchmark, manifest = _payloads()
    positions_by_choice_count = defaultdict(Counter)
    for record in manifest["records"]:
        expected_index = labels_for(record["choice_count"]).index(record["expected_answer"])
        assert index_to_label(expected_index) == record["expected_answer"]
        positions_by_choice_count[record["choice_count"]][record["expected_answer"]] += 1

    for choice_count, counts in positions_by_choice_count.items():
        values = [counts.get(label, 0) for label in labels_for(choice_count)]
        assert max(values) - min(values) <= 1


def test_subset30_deterministic_regeneration():
    full_benchmark, full_manifest = _payloads()
    subset_benchmark_1 = bench.build_subset30_benchmark_payload()
    subset_manifest_1 = bench.build_subset30_manifest_payload()
    subset_benchmark_2 = bench.build_subset30_benchmark_payload()
    subset_manifest_2 = bench.build_subset30_manifest_payload()
    assert bench._canonical_json_bytes(subset_benchmark_1) == bench._canonical_json_bytes(subset_benchmark_2)
    assert bench._canonical_json_bytes(subset_manifest_1) == bench._canonical_json_bytes(subset_manifest_2)
    summary = bench.validate_subset30_payloads(
        subset_benchmark_1, subset_manifest_1, full_benchmark, full_manifest
    )
    assert summary["records"] == 30


def test_committed_subset30_files_match_deterministic_generator():
    full_benchmark, full_manifest = _payloads()
    expected_benchmark = bench.build_subset30_benchmark_payload()
    expected_manifest = bench.build_subset30_manifest_payload()
    benchmark_path = Path("validation/confidence_promotion_subset30.json")
    manifest_path = Path("validation/confidence_promotion_subset30_manifest.json")
    assert benchmark_path.read_bytes() == bench._canonical_json_bytes(expected_benchmark)
    assert manifest_path.read_bytes() == bench._canonical_json_bytes(expected_manifest)
    bench.validate_subset30_payloads(
        json.loads(benchmark_path.read_text(encoding="utf-8")),
        json.loads(manifest_path.read_text(encoding="utf-8")),
        full_benchmark,
        full_manifest,
    )


def test_subset30_shape_counts_and_labels():
    full_benchmark, full_manifest = _payloads()
    subset_benchmark = bench.build_subset30_benchmark_payload()
    subset_manifest = bench.build_subset30_manifest_payload()
    bench.validate_subset30_payloads(subset_benchmark, subset_manifest, full_benchmark, full_manifest)
    records = subset_manifest["records"]
    assert len(records) == 30
    assert len({record["qid"] for record in records}) == 30
    assert Counter(record["category"] for record in records) == {
        bench.CATEGORY_PROGRAMMATIC: 10,
        bench.CATEGORY_CONTENT: 10,
        bench.CATEGORY_LOGIC: 10,
    }
    for record in records:
        assert record["expected_answer"] in labels_for(record["choice_count"])
        assert bench.expected_label_for_manifest_record(record) == record["expected_answer"]


def test_subset30_records_all_come_from_committed_120_record_benchmark():
    full_benchmark, full_manifest = _payloads()
    full_by_qid = {record["qid"]: record for record in full_manifest["records"]}
    full_input_by_qid = {record["qid"]: record for record in full_benchmark}
    subset_benchmark = bench.build_subset30_benchmark_payload()
    subset_manifest = bench.build_subset30_manifest_payload()
    for subset_record in subset_manifest["records"]:
        assert subset_record == full_by_qid[subset_record["qid"]]
    for subset_input in subset_benchmark:
        assert subset_input == full_input_by_qid[subset_input["qid"]]
