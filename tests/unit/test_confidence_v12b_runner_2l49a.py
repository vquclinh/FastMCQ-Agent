import json
import math
import pathlib
from dataclasses import FrozenInstanceError

import pytest

from src.layers.mcq_permutation_debiaser import build_option_permutations
from src.local_model import confidence_v12b_runner as runner
from src.local_model.confidence_v12b_runner import (
    V12BAggregateStatus,
    V12BErrorCode,
    V12BRunInput,
    run_v12b_for_selected,
)
from src.utils.labels import labels_for


class FakeBackend:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_text(self, prompt_or_messages, *, max_new_tokens=None, temperature=0.0):
        self.calls.append(
            {
                "prompt_or_messages": prompt_or_messages,
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("fake backend response queue exhausted")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response(prompt_or_messages)
        return response


def _input(
    *,
    qid="q1",
    input_index=0,
    question="Which option is correct?",
    choices=("Alpha", "Bravo", "Charlie", "Delta"),
    base_answer="A",
    rank=1,
):
    return V12BRunInput(
        qid=qid,
        input_index=input_index,
        question=question,
        choices=tuple(choices),
        canonical_labels=tuple(labels_for(len(choices))),
        base_answer=base_answer,
        router_selected_rank=rank,
        router_candidate_reasons=("low_margin",),
        base_top1=base_answer,
        base_top2="B",
        base_logit_margin=1.25,
        base_normalized_entropy=0.4,
    )


def _response_for_label(permutation, original_label, *, text=None, label_matches=True, extra=None):
    selected_label = permutation.original_to_permuted[original_label]
    selected_text = text
    if selected_text is None:
        selected_text = next(
            choice["text"] for choice in permutation.permuted_choices if choice["label"] == selected_label
        )
    payload = {
        "selected_label": selected_label,
        "selected_option_text": selected_text,
        "label_matches_option": label_matches,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=True)


def _responses_for_votes(choices, votes):
    sample = {"question": "Which option is correct?", "choices": list(choices)}
    permutations = build_option_permutations(sample, n=6)
    assert len(votes) == len(permutations)
    return [_response_for_label(permutation, vote) for permutation, vote in zip(permutations, votes)]


def _run_one(responses, *, choices=("Alpha", "Bravo", "Charlie", "Delta"), base_answer="A"):
    backend = FakeBackend(responses)
    results, summary = run_v12b_for_selected(
        [_input(choices=choices, base_answer=base_answer)],
        backend=backend,
    )
    assert len(results) == 1
    return results[0], summary, backend


def _json_blob(*objects):
    return json.dumps(
        [
            obj.as_dict() if hasattr(obj, "as_dict") else obj
            for obj in objects
        ],
        sort_keys=True,
        allow_nan=False,
    )


@pytest.mark.parametrize(
    ("choice_count", "expected_calls"),
    [
        (1, 1),
        (2, 2),
        (3, 4),
        (4, 6),
        (5, 6),
        (10, 6),
    ],
)
def test_unique_permutation_counts_and_label_only_mappings(choice_count, expected_calls):
    choices = tuple(f"choice-{index}" for index in range(choice_count))
    labels = labels_for(choice_count)
    responses = _responses_for_votes(choices, [labels[0]] * expected_calls)

    result, summary, backend = _run_one(responses, choices=choices, base_answer=labels[0])

    assert len(backend.calls) == expected_calls
    assert result.attempted_permutation_count == expected_calls
    assert summary.total_permutation_attempts == expected_calls
    expected_permutations = build_option_permutations({"choices": list(choices)}, n=6)
    assert [p.permutation_id for p in expected_permutations] == [
        item.permutation_id for item in result.permutation_results
    ]
    for actual, expected in zip(result.permutation_results, expected_permutations):
        assert actual.permuted_to_original == expected.permuted_to_original
        rendered = json.dumps(actual.as_dict(), sort_keys=True)
        assert "choice-" not in rendered
        assert set(actual.permuted_to_original) == set(labels)
        assert set(actual.permuted_to_original.values()) == set(labels)


def test_runner_uses_only_injected_backend_and_no_global_backend_lookup(monkeypatch):
    from src.local_model import local_qwen_backend

    def forbidden_lookup(*args, **kwargs):
        raise AssertionError("global lookup must not be used")

    monkeypatch.setattr(local_qwen_backend, "get_local_qwen_backend", forbidden_lookup)
    responses = _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B"] * 6)

    result, _summary, backend = _run_one(responses)

    assert len(backend.calls) == 6
    assert result.aggregate_status == V12BAggregateStatus.VALID_UNIQUE_MAJORITY


def test_runner_performs_no_filesystem_writes(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("filesystem operation must not be used")

    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(pathlib.Path, "mkdir", forbidden)
    monkeypatch.setattr(pathlib.Path, "write_text", forbidden)
    monkeypatch.setattr(pathlib.Path, "write_bytes", forbidden)
    responses = _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B"] * 6)

    result, _summary, _backend = _run_one(responses)

    assert result.aggregate_status == V12BAggregateStatus.VALID_UNIQUE_MAJORITY


def test_static_scope_has_no_forbidden_runtime_imports():
    source = pathlib.Path(runner.__file__).read_text()
    forbidden = [
        "run_v12b_layer",
        "select_v12b_targets",
        "get_local_qwen_backend",
        "v12b_dynamic_records",
        "V13",
        "selector",
        "legacy_dynamic_full",
        "submission",
        "pred.csv",
        "open(",
        "write_text",
        "write_bytes",
        "mkdir",
        "confidence",
    ]
    assert [token for token in forbidden if token in source] == []


def test_prompt_is_minimal_and_does_not_request_extra_fields():
    responses = _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B"] * 6)

    _result, _summary, backend = _run_one(responses)

    first_prompt = json.dumps(backend.calls[0]["prompt_or_messages"], sort_keys=True)
    assert "selected_label" in first_prompt
    assert "selected_option_text" in first_prompt
    assert "label_matches_option" in first_prompt
    for forbidden in ("confidence", "evidence", "reasoning", "explanation"):
        assert forbidden not in first_prompt.lower()


def test_unanimous_valid_votes_strong_majority_and_hypothetical_acceptance():
    result, summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B"] * 6)
    )

    assert result.aggregate_status == V12BAggregateStatus.VALID_UNIQUE_MAJORITY
    assert result.valid_permutation_count == 6
    assert result.winning_label == "B"
    assert result.winning_votes == 6
    assert result.runner_up_label is None
    assert result.runner_up_votes == 0
    assert result.vote_margin == 6
    assert result.consensus_ratio == 1.0
    assert result.unique_answer_count == 1
    assert result.base_v12b_agreement is False
    assert result.hypothetical_answer == "B"
    assert result.hypothetical_conservative_acceptance is True
    assert result.official_answer_source == "base"
    assert summary.base_v12b_disagreement_count == 1
    assert summary.observational_only is True


def test_unique_strong_majority_runner_up_margin_and_disagreement():
    result, _summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B", "B", "B", "B", "A", "C"])
    )

    assert result.aggregate_status == V12BAggregateStatus.VALID_UNIQUE_MAJORITY
    assert result.vote_counts == {"A": 1, "B": 4, "C": 1}
    assert result.winning_label == "B"
    assert result.runner_up_label == "A"
    assert result.vote_margin == 3
    assert result.consensus_ratio == pytest.approx(4 / 6)
    assert result.base_v12b_agreement is False
    assert result.hypothetical_conservative_acceptance is True


def test_unique_weak_consensus_does_not_accept_hypothetical_override():
    result, _summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B", "B", "B", "A", "C", "D"])
    )

    assert result.aggregate_status == V12BAggregateStatus.VALID_WEAK_CONSENSUS
    assert result.winning_label == "B"
    assert result.runner_up_label == "A"
    assert result.vote_margin == 2
    assert result.consensus_ratio == 0.5
    assert result.hypothetical_answer is None
    assert result.hypothetical_conservative_acceptance is False


def test_tie_status_precedes_winner_policy_acceptance():
    result, _summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B", "B", "C", "C", "A", "D"])
    )

    assert result.aggregate_status == V12BAggregateStatus.TIE
    assert result.tie is True
    assert result.winning_label == "B"
    assert result.runner_up_label == "C"
    assert result.vote_margin == 0
    assert result.base_v12b_agreement is None
    assert result.hypothetical_answer is None
    assert result.hypothetical_conservative_acceptance is False


def test_insufficient_valid_permutations_is_distinct_from_all_invalid():
    result, _summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie"), ["B", "B", "B", "B"]),
        choices=("Alpha", "Bravo", "Charlie"),
    )

    assert result.attempted_permutation_count == 4
    assert result.valid_permutation_count == 4
    assert result.aggregate_status == V12BAggregateStatus.INSUFFICIENT_VALID_PERMUTATIONS
    assert result.record_error_code == V12BErrorCode.INSUFFICIENT_VALID_PERMUTATIONS
    assert result.hypothetical_conservative_acceptance is False


def test_all_invalid_status_from_missing_selected_labels():
    responses = [json.dumps({"selected_option_text": "Bravo", "label_matches_option": True})] * 6

    result, _summary, _backend = _run_one(responses)

    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID
    assert result.record_error_code == V12BErrorCode.ALL_INVALID
    assert result.valid_permutation_count == 0
    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.MISSING_SELECTED_LABEL}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"selected_label": None, "selected_option_text": "Bravo", "label_matches_option": True},
        {"selected_label": "", "selected_option_text": "Bravo", "label_matches_option": True},
        {"selected_label": "   ", "selected_option_text": "Bravo", "label_matches_option": True},
    ],
)
def test_missing_null_or_empty_selected_label_remains_missing_selected_label(payload):
    result, _summary, _backend = _run_one([json.dumps(payload)] * 6)

    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID
    assert result.valid_permutation_count == 0
    assert result.hypothetical_answer is None
    assert result.hypothetical_conservative_acceptance is False
    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.MISSING_SELECTED_LABEL}


@pytest.mark.parametrize(
    "payload",
    [
        {"selected_label": 1, "selected_option_text": "Bravo", "label_matches_option": True},
        {"selected_label": ["B"], "selected_option_text": "Bravo", "label_matches_option": True},
        {"selected_label": "B", "label_matches_option": True},
        {"selected_label": "B", "selected_option_text": None, "label_matches_option": True},
        {"selected_label": "B", "selected_option_text": "", "label_matches_option": True},
        {"selected_label": "B", "selected_option_text": "   ", "label_matches_option": True},
        {"selected_label": "B", "selected_option_text": 123, "label_matches_option": True},
        {"selected_label": "B", "selected_option_text": "RAW_SECRET_MARKER"},
        {"selected_label": "B", "selected_option_text": "RAW_SECRET_MARKER", "label_matches_option": None},
        {"selected_label": "B", "selected_option_text": "RAW_SECRET_MARKER", "label_matches_option": "false"},
        {"selected_label": "B", "selected_option_text": "RAW_SECRET_MARKER", "label_matches_option": 1},
    ],
)
def test_invalid_structured_response_schema_fails_closed_before_mapping(payload):
    result, summary, _backend = _run_one([json.dumps(payload)] * 6)

    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID
    assert result.valid_permutation_count == 0
    assert result.vote_counts == {}
    assert result.hypothetical_answer is None
    assert result.hypothetical_conservative_acceptance is False
    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.INVALID_RESPONSE_SCHEMA}
    rendered = _json_blob(result, summary)
    assert "RAW_SECRET_MARKER" not in rendered
    json.dumps(result.as_dict(), sort_keys=True, allow_nan=False)
    json.dumps(summary.as_dict(), sort_keys=True, allow_nan=False)


def test_all_generation_failure_status_and_failed_summary_count():
    result, summary, _backend = _run_one([RuntimeError("private question Alpha")] * 6)

    assert result.aggregate_status == V12BAggregateStatus.GENERATION_FAILURE
    assert result.record_error_code == V12BErrorCode.GENERATION_ERROR
    assert result.generation_failure_count == 6
    assert result.valid_permutation_count == 0
    assert summary.failed_records == 1
    assert summary.succeeded_records == 0


def test_malformed_json_normalizes_to_parse_error():
    result, _summary, _backend = _run_one(["not json"] * 6)

    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID
    assert result.parse_failure_count == 6
    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.PARSE_ERROR}


def test_label_out_of_range_normalization():
    response = json.dumps(
        {"selected_label": "Z", "selected_option_text": "Zulu", "label_matches_option": True}
    )

    result, _summary, _backend = _run_one([response] * 6)

    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.LABEL_OUT_OF_RANGE}
    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID


def test_label_matches_option_false_normalizes_to_label_option_mismatch():
    sample = {"question": "Which option is correct?", "choices": ["Alpha", "Bravo", "Charlie", "Delta"]}
    responses = [
        _response_for_label(permutation, "B", label_matches=False)
        for permutation in build_option_permutations(sample, n=6)
    ]

    result, _summary, _backend = _run_one(responses)

    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.LABEL_OPTION_MISMATCH}
    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID


def test_label_text_conflict_normalization():
    choices = ("Alpha", "Bravo", "Charlie", "Delta")
    sample = {"question": "Which option is correct?", "choices": list(choices)}
    responses = []
    for permutation in build_option_permutations(sample, n=6):
        conflicting_text = next(
            choice["text"] for choice in permutation.permuted_choices if choice["original_label"] == "C"
        )
        responses.append(_response_for_label(permutation, "B", text=conflicting_text))

    result, _summary, _backend = _run_one(responses, choices=choices)

    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.LABEL_TEXT_CONFLICT}
    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID


def test_option_text_no_match_normalization():
    choices = ("Alpha", "Bravo", "Charlie", "Delta")
    sample = {"question": "Which option is correct?", "choices": list(choices)}
    responses = [
        _response_for_label(permutation, "B", text="not an option")
        for permutation in build_option_permutations(sample, n=6)
    ]

    result, _summary, _backend = _run_one(responses, choices=choices)

    assert {item.error_code for item in result.permutation_results} == {V12BErrorCode.OPTION_TEXT_NO_MATCH}
    assert result.aggregate_status == V12BAggregateStatus.ALL_INVALID


def test_duplicate_normalized_option_texts_remain_text_free_and_do_not_crash():
    choices = ("Same!", "same", "Other", "Last")
    result, _summary, _backend = _run_one(_responses_for_votes(choices, ["A"] * 6), choices=choices)

    assert result.aggregate_status == V12BAggregateStatus.VALID_UNIQUE_MAJORITY
    rendered = _json_blob(result)
    assert "Same!" not in rendered
    assert "same" not in rendered
    assert "Other" not in rendered
    assert "Last" not in rendered


def test_backend_exception_on_one_permutation_fails_closed_and_continues():
    choices = ("Alpha", "Bravo", "Charlie", "Delta")
    sample = {"question": "Which option is correct?", "choices": list(choices)}
    permutations = build_option_permutations(sample, n=6)
    responses = [RuntimeError("private Alpha")] + [
        _response_for_label(permutation, "B") for permutation in permutations[1:]
    ]

    result, _summary, backend = _run_one(responses, choices=choices)

    assert len(backend.calls) == 6
    assert result.generation_failure_count == 1
    assert result.valid_permutation_count == 5
    assert result.aggregate_status == V12BAggregateStatus.VALID_UNIQUE_MAJORITY
    assert result.permutation_results[0].exception_class_name == "RuntimeError"
    assert result.permutation_results[0].error_code == V12BErrorCode.GENERATION_ERROR


def test_unexpected_aggregation_exception_becomes_aggregate_error(monkeypatch):
    def raising_summary(*args, **kwargs):
        raise RuntimeError("private question Alpha")

    monkeypatch.setattr(runner, "summarize_permutation_votes", raising_summary)
    result, summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B"] * 6)
    )

    assert result.aggregate_status == V12BAggregateStatus.AGGREGATE_ERROR
    assert result.record_error_code == V12BErrorCode.AGGREGATE_ERROR
    assert summary.failed_records == 1
    rendered = _json_blob(result, summary)
    assert "private question Alpha" not in rendered


def test_privacy_excludes_question_choices_prompt_raw_response_and_extra_fields():
    question = "PRIVATE_QUESTION_MARKER"
    choices = ("SECRET_CHOICE_A", "SECRET_CHOICE_B", "SECRET_CHOICE_C", "SECRET_CHOICE_D")
    sample = {"question": question, "choices": list(choices)}
    responses = []
    for permutation in build_option_permutations(sample, n=6):
        responses.append(
            _response_for_label(
                permutation,
                "B",
                text="RAW_SECRET_MARKER",
                extra={
                    "confidence": 0.99,
                    "evidence": "EVIDENCE_SECRET_MARKER",
                    "reasoning": "REASON_SECRET_MARKER",
                    "expected_answer": "GROUND_TRUTH_SECRET",
                },
            )
        )
    backend = FakeBackend(responses)

    results, summary = run_v12b_for_selected(
        [
            _input(
                qid="privacy-qid",
                question=question,
                choices=choices,
                base_answer="A",
            )
        ],
        backend=backend,
    )

    rendered = _json_blob(results[0], summary)
    for forbidden in (
        question,
        "SECRET_CHOICE_A",
        "SECRET_CHOICE_B",
        "SECRET_CHOICE_C",
        "SECRET_CHOICE_D",
        "RAW_SECRET_MARKER",
        "EVIDENCE_SECRET_MARKER",
        "REASON_SECRET_MARKER",
        "GROUND_TRUTH_SECRET",
        "selected_option_text",
        "prompt",
        "raw_response",
        "confidence",
        "evidence",
        "reasoning",
        "expected_answer",
        "ground_truth",
    ):
        assert forbidden not in rendered
    json.dumps(results[0].as_dict(), allow_nan=False)
    json.dumps(summary.as_dict(), allow_nan=False)
    assert math.isfinite(results[0].elapsed_seconds)


def test_exception_message_never_appears_in_returned_diagnostics():
    marker = "PRIVATE QUESTION AND SECRET CHOICE TEXT"
    result, summary, _backend = _run_one([ValueError(marker)] * 6)

    rendered = _json_blob(result, summary)
    assert marker not in rendered
    assert "ValueError" in rendered


def test_duplicate_identities_preserve_private_ordinals_and_input_order():
    choices = ("Alpha", "Bravo", "Charlie", "Delta")
    inputs = [
        _input(qid="dup", input_index=7, choices=choices, base_answer="A", rank=3),
        _input(qid="dup", input_index=7, choices=choices, base_answer="A", rank=1),
        _input(qid="dup", input_index=7, choices=choices, base_answer="A", rank=2),
    ]
    responses = (
        _responses_for_votes(choices, ["B"] * 6)
        + _responses_for_votes(choices, ["C"] * 6)
        + _responses_for_votes(choices, ["D"] * 6)
    )
    backend = FakeBackend(responses)

    results, summary = run_v12b_for_selected(inputs, backend=backend)

    assert [result.record_ordinal for result in results] == [0, 1, 2]
    assert [result.qid for result in results] == ["dup", "dup", "dup"]
    assert [result.input_index for result in results] == [7, 7, 7]
    assert [result.router_selected_rank for result in results] == [3, 1, 2]
    assert [result.winning_label for result in results] == ["B", "C", "D"]
    assert summary.selected_qids == ("dup", "dup", "dup")
    assert [item.record_ordinal for item in summary.selected_items] == [0, 1, 2]
    assert summary.total_selected_records == 3
    assert summary.total_valid_permutations == 18


def test_empty_input_returns_zero_summary_without_backend_calls():
    backend = FakeBackend([])

    results, summary = run_v12b_for_selected([], backend=backend)

    assert results == ()
    assert backend.calls == []
    assert summary.total_selected_records == 0
    assert summary.attempted_records == 0
    assert summary.succeeded_records == 0
    assert summary.failed_records == 0
    assert summary.total_permutation_attempts == 0
    assert summary.aggregate_status_counts == {}
    assert summary.selected_items == ()


def test_repeated_run_is_deterministic_except_elapsed_time():
    choices = ("Alpha", "Bravo", "Charlie", "Delta")
    inputs = [_input(choices=choices)]

    first, first_summary = run_v12b_for_selected(inputs, backend=FakeBackend(_responses_for_votes(choices, ["B"] * 6)))
    second, second_summary = run_v12b_for_selected(inputs, backend=FakeBackend(_responses_for_votes(choices, ["B"] * 6)))

    first_dict = first[0].as_dict()
    second_dict = second[0].as_dict()
    first_dict.pop("elapsed_seconds")
    second_dict.pop("elapsed_seconds")
    assert first_dict == second_dict
    assert first_summary.as_dict() == second_summary.as_dict()


def test_inputs_and_caller_owned_collections_are_not_mutated():
    choices = ["Alpha", "Bravo", "Charlie", "Delta"]
    reasons = ["low_margin"]
    item = V12BRunInput(
        qid="immutable",
        input_index=0,
        question="Immutable?",
        choices=choices,
        canonical_labels=tuple(labels_for(len(choices))),
        base_answer="A",
        router_selected_rank=1,
        router_candidate_reasons=reasons,
    )
    before = item
    choices_before = list(choices)
    reasons_before = list(reasons)

    with pytest.raises(FrozenInstanceError):
        item.qid = "changed"
    run_v12b_for_selected([item], backend=FakeBackend(_responses_for_votes(tuple(choices), ["B"] * 6)))

    assert item == before
    assert choices == choices_before
    assert reasons == reasons_before
    assert item.choices == tuple(choices_before)
    assert item.router_candidate_reasons == tuple(reasons_before)


def test_json_compatible_public_dictionaries_for_valid_and_failure_results():
    valid_result, valid_summary, _backend = _run_one(
        _responses_for_votes(("Alpha", "Bravo", "Charlie", "Delta"), ["B"] * 6)
    )
    failure_result, failure_summary, _backend = _run_one([RuntimeError("secret")] * 6)

    json.dumps(valid_result.as_dict(), sort_keys=True, allow_nan=False)
    json.dumps(valid_summary.as_dict(), sort_keys=True, allow_nan=False)
    json.dumps(failure_result.as_dict(), sort_keys=True, allow_nan=False)
    json.dumps(failure_summary.as_dict(), sort_keys=True, allow_nan=False)
