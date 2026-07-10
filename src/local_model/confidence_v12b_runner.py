"""In-memory V12B permutation runner for explicitly selected records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import perf_counter
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from src.layers.mcq_permutation_debiaser import (
    OptionPermutation,
    build_option_permutations,
    map_permuted_answer_to_original,
    select_permutation_override,
    summarize_permutation_votes,
)
from src.local_model.local_qwen_backend import parse_json_object
from src.utils.labels import labels_for


DEFAULT_MIN_VALID_PERMUTATIONS = 5
DEFAULT_CONSENSUS_VOTES = 4
DEFAULT_PERMUTATION_COUNT = 6
DEFAULT_MAX_NEW_TOKENS = 192


class V12BBackendProtocol(Protocol):
    def generate_text(
        self,
        prompt_or_messages: str | list[dict[str, str]],
        *,
        max_new_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> str:
        ...


class V12BErrorCode(str, Enum):
    OK = "ok"
    GENERATION_ERROR = "generation_error"
    PARSE_ERROR = "parse_error"
    MISSING_SELECTED_LABEL = "missing_selected_label"
    INVALID_RESPONSE_SCHEMA = "invalid_response_schema"
    LABEL_OUT_OF_RANGE = "label_out_of_range"
    LABEL_OPTION_MISMATCH = "label_option_mismatch"
    LABEL_TEXT_CONFLICT = "label_text_conflict"
    OPTION_TEXT_NO_MATCH = "option_text_no_match"
    INSUFFICIENT_VALID_PERMUTATIONS = "insufficient_valid_permutations"
    TIE = "tie"
    ALL_INVALID = "all_invalid"
    AGGREGATE_ERROR = "aggregate_error"


class V12BAggregateStatus(str, Enum):
    AGGREGATE_ERROR = "aggregate_error"
    GENERATION_FAILURE = "generation_failure"
    ALL_INVALID = "all_invalid"
    INSUFFICIENT_VALID_PERMUTATIONS = "insufficient_valid_permutations"
    TIE = "tie"
    VALID_UNIQUE_MAJORITY = "valid_unique_majority"
    VALID_WEAK_CONSENSUS = "valid_weak_consensus"


@dataclass(frozen=True)
class V12BRunInput:
    qid: str
    input_index: int
    question: str
    choices: tuple[str, ...]
    canonical_labels: tuple[str, ...]
    base_answer: str | None
    router_selected_rank: int | None = None
    router_candidate_reasons: tuple[str, ...] = ()
    base_top1: str | None = None
    base_top2: str | None = None
    base_logit_margin: float | None = None
    base_normalized_entropy: float | None = None

    def __post_init__(self) -> None:
        choices = tuple(str(choice) for choice in self.choices)
        labels = tuple(_normalize_label(label) for label in self.canonical_labels if str(label).strip())
        if not labels:
            labels = tuple(labels_for(len(choices)))
        object.__setattr__(self, "qid", str(self.qid))
        object.__setattr__(self, "input_index", int(self.input_index))
        object.__setattr__(self, "question", str(self.question))
        object.__setattr__(self, "choices", choices)
        object.__setattr__(self, "canonical_labels", labels)
        object.__setattr__(self, "base_answer", _normalize_optional_label(self.base_answer))
        object.__setattr__(
            self,
            "router_candidate_reasons",
            tuple(str(reason) for reason in self.router_candidate_reasons),
        )
        object.__setattr__(self, "base_top1", _normalize_optional_label(self.base_top1))
        object.__setattr__(self, "base_top2", _normalize_optional_label(self.base_top2))


@dataclass(frozen=True)
class V12BPermutationResult:
    permutation_ordinal: int
    permutation_id: str
    permuted_to_original: Mapping[str, str]
    mapped_original_label: str | None
    parse_status: str
    valid: bool
    label_option_match: bool
    error_code: V12BErrorCode
    exception_class_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "permuted_to_original",
            MappingProxyType({str(k): str(v) for k, v in self.permuted_to_original.items()}),
        )
        object.__setattr__(self, "mapped_original_label", _normalize_optional_label(self.mapped_original_label))
        object.__setattr__(self, "parse_status", str(self.parse_status))
        object.__setattr__(self, "valid", bool(self.valid))
        object.__setattr__(self, "label_option_match", bool(self.label_option_match))
        if not isinstance(self.error_code, V12BErrorCode):
            object.__setattr__(self, "error_code", V12BErrorCode(str(self.error_code)))
        if self.exception_class_name is not None:
            object.__setattr__(self, "exception_class_name", str(self.exception_class_name))

    def as_dict(self) -> dict[str, Any]:
        return {
            "permutation_ordinal": self.permutation_ordinal,
            "permutation_id": self.permutation_id,
            "permuted_to_original": dict(self.permuted_to_original),
            "mapped_original_label": self.mapped_original_label,
            "parse_status": self.parse_status,
            "valid": self.valid,
            "label_option_match": self.label_option_match,
            "error_code": self.error_code.value,
            "exception_class_name": self.exception_class_name,
        }


@dataclass(frozen=True)
class V12BAggregateResult:
    record_ordinal: int
    qid: str
    input_index: int
    router_selected_rank: int | None
    attempted_permutation_count: int
    valid_permutation_count: int
    parse_failure_count: int
    generation_failure_count: int
    vote_counts: Mapping[str, int]
    winning_label: str | None
    winning_votes: int
    runner_up_label: str | None
    runner_up_votes: int
    vote_margin: int
    consensus_ratio: float
    unique_answer_count: int
    tie: bool
    aggregate_status: V12BAggregateStatus
    base_v12b_agreement: bool | None
    hypothetical_answer: str | None
    hypothetical_conservative_acceptance: bool
    record_error_code: V12BErrorCode
    permutation_results: tuple[V12BPermutationResult, ...] = field(default_factory=tuple)
    official_answer_source: str = "base"
    elapsed_seconds: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "qid", str(self.qid))
        object.__setattr__(self, "input_index", int(self.input_index))
        object.__setattr__(self, "vote_counts", MappingProxyType({str(k): int(v) for k, v in self.vote_counts.items()}))
        object.__setattr__(self, "winning_label", _normalize_optional_label(self.winning_label))
        object.__setattr__(self, "runner_up_label", _normalize_optional_label(self.runner_up_label))
        object.__setattr__(self, "hypothetical_answer", _normalize_optional_label(self.hypothetical_answer))
        object.__setattr__(self, "official_answer_source", "base")
        object.__setattr__(self, "elapsed_seconds", float(self.elapsed_seconds))
        if not isinstance(self.aggregate_status, V12BAggregateStatus):
            object.__setattr__(self, "aggregate_status", V12BAggregateStatus(str(self.aggregate_status)))
        if not isinstance(self.record_error_code, V12BErrorCode):
            object.__setattr__(self, "record_error_code", V12BErrorCode(str(self.record_error_code)))
        object.__setattr__(self, "permutation_results", tuple(self.permutation_results))

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_ordinal": self.record_ordinal,
            "qid": self.qid,
            "input_index": self.input_index,
            "router_selected_rank": self.router_selected_rank,
            "attempted_permutation_count": self.attempted_permutation_count,
            "valid_permutation_count": self.valid_permutation_count,
            "parse_failure_count": self.parse_failure_count,
            "generation_failure_count": self.generation_failure_count,
            "vote_counts": dict(self.vote_counts),
            "winning_label": self.winning_label,
            "winning_votes": self.winning_votes,
            "runner_up_label": self.runner_up_label,
            "runner_up_votes": self.runner_up_votes,
            "vote_margin": self.vote_margin,
            "consensus_ratio": self.consensus_ratio,
            "unique_answer_count": self.unique_answer_count,
            "tie": self.tie,
            "aggregate_status": self.aggregate_status.value,
            "base_v12b_agreement": self.base_v12b_agreement,
            "hypothetical_answer": self.hypothetical_answer,
            "hypothetical_conservative_acceptance": self.hypothetical_conservative_acceptance,
            "official_answer_source": self.official_answer_source,
            "elapsed_seconds": self.elapsed_seconds,
            "record_error_code": self.record_error_code.value,
            "permutation_results": [result.as_dict() for result in self.permutation_results],
        }


@dataclass(frozen=True)
class V12BSelectedItem:
    record_ordinal: int
    qid: str
    input_index: int
    router_selected_rank: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_ordinal": self.record_ordinal,
            "qid": self.qid,
            "input_index": self.input_index,
            "router_selected_rank": self.router_selected_rank,
        }


@dataclass(frozen=True)
class V12BRunSummary:
    total_selected_records: int
    attempted_records: int
    succeeded_records: int
    failed_records: int
    total_permutation_attempts: int
    total_valid_permutations: int
    parse_failure_total: int
    generation_failure_total: int
    aggregate_status_counts: Mapping[str, int]
    base_v12b_disagreement_count: int
    selected_qids: tuple[str, ...]
    selected_items: tuple[V12BSelectedItem, ...]
    observational_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "aggregate_status_counts",
            MappingProxyType({str(k): int(v) for k, v in self.aggregate_status_counts.items()}),
        )
        object.__setattr__(self, "selected_qids", tuple(str(qid) for qid in self.selected_qids))
        object.__setattr__(self, "selected_items", tuple(self.selected_items))
        object.__setattr__(self, "observational_only", True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_selected_records": self.total_selected_records,
            "attempted_records": self.attempted_records,
            "succeeded_records": self.succeeded_records,
            "failed_records": self.failed_records,
            "total_permutation_attempts": self.total_permutation_attempts,
            "total_valid_permutations": self.total_valid_permutations,
            "parse_failure_total": self.parse_failure_total,
            "generation_failure_total": self.generation_failure_total,
            "aggregate_status_counts": dict(self.aggregate_status_counts),
            "base_v12b_disagreement_count": self.base_v12b_disagreement_count,
            "selected_qids": list(self.selected_qids),
            "selected_items": [item.as_dict() for item in self.selected_items],
            "observational_only": self.observational_only,
        }


def run_v12b_for_selected(
    inputs: Iterable[V12BRunInput],
    *,
    backend: V12BBackendProtocol,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    permutation_count: int = DEFAULT_PERMUTATION_COUNT,
    min_valid_permutations: int = DEFAULT_MIN_VALID_PERMUTATIONS,
    consensus_votes: int = DEFAULT_CONSENSUS_VOTES,
) -> tuple[tuple[V12BAggregateResult, ...], V12BRunSummary]:
    selected_inputs = tuple(inputs)
    results = tuple(
        _run_one_record(
            item,
            record_ordinal=record_ordinal,
            backend=backend,
            max_new_tokens=max_new_tokens,
            permutation_count=permutation_count,
            min_valid_permutations=min_valid_permutations,
            consensus_votes=consensus_votes,
        )
        for record_ordinal, item in enumerate(selected_inputs)
    )
    return results, _build_summary(selected_inputs, results)


def _run_one_record(
    item: V12BRunInput,
    *,
    record_ordinal: int,
    backend: V12BBackendProtocol,
    max_new_tokens: int,
    permutation_count: int,
    min_valid_permutations: int,
    consensus_votes: int,
) -> V12BAggregateResult:
    started = perf_counter()
    permutation_results: tuple[V12BPermutationResult, ...] = ()
    try:
        sample = _sample_for_permutation_core(item)
        permutations = tuple(build_option_permutations(sample, n=permutation_count))
        permutation_results = tuple(
            _run_one_permutation(
                sample,
                permutation,
                permutation_ordinal=permutation_ordinal,
                backend=backend,
                max_new_tokens=max_new_tokens,
            )
            for permutation_ordinal, permutation in enumerate(permutations)
        )
        return _aggregate_record(
            item,
            record_ordinal=record_ordinal,
            permutation_results=permutation_results,
            min_valid_permutations=min_valid_permutations,
            consensus_votes=consensus_votes,
            elapsed_seconds=perf_counter() - started,
        )
    except Exception:
        return _aggregate_error_record(
            item,
            record_ordinal=record_ordinal,
            permutation_results=permutation_results,
            elapsed_seconds=perf_counter() - started,
        )


def _run_one_permutation(
    sample: dict[str, Any],
    permutation: OptionPermutation,
    *,
    permutation_ordinal: int,
    backend: V12BBackendProtocol,
    max_new_tokens: int,
) -> V12BPermutationResult:
    mapping = dict(permutation.permuted_to_original)
    try:
        response = backend.generate_text(
            _build_prompt(sample["question"], permutation),
            max_new_tokens=max_new_tokens,
            temperature=0.0,
        )
    except Exception as exc:
        return V12BPermutationResult(
            permutation_ordinal=permutation_ordinal,
            permutation_id=permutation.permutation_id,
            permuted_to_original=mapping,
            mapped_original_label=None,
            parse_status=V12BErrorCode.GENERATION_ERROR.value,
            valid=False,
            label_option_match=False,
            error_code=V12BErrorCode.GENERATION_ERROR,
            exception_class_name=type(exc).__name__,
        )

    parsed = parse_json_object(response)
    if not isinstance(parsed, dict):
        return V12BPermutationResult(
            permutation_ordinal=permutation_ordinal,
            permutation_id=permutation.permutation_id,
            permuted_to_original=mapping,
            mapped_original_label=None,
            parse_status=V12BErrorCode.PARSE_ERROR.value,
            valid=False,
            label_option_match=False,
            error_code=V12BErrorCode.PARSE_ERROR,
        )

    selected_label = parsed.get("selected_label")
    if selected_label is None:
        return _invalid_structured_response_result(
            permutation,
            permutation_ordinal=permutation_ordinal,
            mapping=mapping,
            error_code=V12BErrorCode.MISSING_SELECTED_LABEL,
        )
    if not isinstance(selected_label, str):
        return _invalid_structured_response_result(
            permutation,
            permutation_ordinal=permutation_ordinal,
            mapping=mapping,
            error_code=V12BErrorCode.INVALID_RESPONSE_SCHEMA,
        )
    selected_label = selected_label.strip()
    if not selected_label:
        return _invalid_structured_response_result(
            permutation,
            permutation_ordinal=permutation_ordinal,
            mapping=mapping,
            error_code=V12BErrorCode.MISSING_SELECTED_LABEL,
        )

    selected_option_text = parsed.get("selected_option_text")
    if not isinstance(selected_option_text, str) or not selected_option_text.strip():
        return _invalid_structured_response_result(
            permutation,
            permutation_ordinal=permutation_ordinal,
            mapping=mapping,
            error_code=V12BErrorCode.INVALID_RESPONSE_SCHEMA,
        )

    label_matches_option = parsed.get("label_matches_option")
    if type(label_matches_option) is not bool:
        return _invalid_structured_response_result(
            permutation,
            permutation_ordinal=permutation_ordinal,
            mapping=mapping,
            error_code=V12BErrorCode.INVALID_RESPONSE_SCHEMA,
        )

    mapped = map_permuted_answer_to_original(
        sample,
        permutation,
        selected_label,
        selected_option_text,
        label_matches_option,
    )
    return V12BPermutationResult(
        permutation_ordinal=permutation_ordinal,
        permutation_id=permutation.permutation_id,
        permuted_to_original=mapping,
        mapped_original_label=mapped.mapped_original_label,
        parse_status=mapped.parse_status,
        valid=mapped.valid,
        label_option_match=mapped.label_option_match,
        error_code=_normalize_mapping_error(mapped.failure_reason),
    )


def _invalid_structured_response_result(
    permutation: OptionPermutation,
    *,
    permutation_ordinal: int,
    mapping: Mapping[str, str],
    error_code: V12BErrorCode,
) -> V12BPermutationResult:
    return V12BPermutationResult(
        permutation_ordinal=permutation_ordinal,
        permutation_id=permutation.permutation_id,
        permuted_to_original=mapping,
        mapped_original_label=None,
        parse_status=V12BErrorCode.OK.value,
        valid=False,
        label_option_match=False,
        error_code=error_code,
    )


def _aggregate_record(
    item: V12BRunInput,
    *,
    record_ordinal: int,
    permutation_results: tuple[V12BPermutationResult, ...],
    min_valid_permutations: int,
    consensus_votes: int,
    elapsed_seconds: float,
) -> V12BAggregateResult:
    vote_records = [_vote_record(result) for result in permutation_results]
    summary = summarize_permutation_votes(item.qid, item.base_answer, vote_records)
    vote_counts = _ordered_vote_counts(summary.vote_counts, item.canonical_labels)
    attempted = len(permutation_results)
    valid = int(summary.valid_records)
    parse_failures = sum(1 for result in permutation_results if result.error_code == V12BErrorCode.PARSE_ERROR)
    generation_failures = sum(
        1 for result in permutation_results if result.error_code == V12BErrorCode.GENERATION_ERROR
    )
    winner, winner_votes, runner_up, runner_up_votes, tie = _vote_leaders(vote_counts, item.canonical_labels)
    status = _aggregate_status(
        attempted=attempted,
        valid=valid,
        generation_failures=generation_failures,
        tie=tie,
        winner_votes=winner_votes,
        min_valid_permutations=min_valid_permutations,
        consensus_votes=consensus_votes,
    )
    can_consider_override = status in (
        V12BAggregateStatus.VALID_UNIQUE_MAJORITY,
        V12BAggregateStatus.VALID_WEAK_CONSENSUS,
    )
    decision = select_permutation_override(summary, policy="conservative") if can_consider_override else None
    accepted = bool(decision and decision.accept)
    hypothetical_answer = decision.proposed_answer if accepted else None
    agreement = (winner == item.base_answer) if winner and not tie else None

    return V12BAggregateResult(
        record_ordinal=record_ordinal,
        qid=item.qid,
        input_index=item.input_index,
        router_selected_rank=item.router_selected_rank,
        attempted_permutation_count=attempted,
        valid_permutation_count=valid,
        parse_failure_count=parse_failures,
        generation_failure_count=generation_failures,
        vote_counts=vote_counts,
        winning_label=winner,
        winning_votes=winner_votes,
        runner_up_label=runner_up,
        runner_up_votes=runner_up_votes,
        vote_margin=winner_votes - runner_up_votes,
        consensus_ratio=(winner_votes / valid) if valid > 0 else 0.0,
        unique_answer_count=len(vote_counts),
        tie=tie,
        aggregate_status=status,
        base_v12b_agreement=agreement,
        hypothetical_answer=hypothetical_answer,
        hypothetical_conservative_acceptance=accepted,
        record_error_code=_record_error_code(status),
        permutation_results=permutation_results,
        elapsed_seconds=elapsed_seconds,
    )


def _aggregate_error_record(
    item: V12BRunInput,
    *,
    record_ordinal: int,
    permutation_results: tuple[V12BPermutationResult, ...],
    elapsed_seconds: float,
) -> V12BAggregateResult:
    parse_failures = sum(1 for result in permutation_results if result.error_code == V12BErrorCode.PARSE_ERROR)
    generation_failures = sum(
        1 for result in permutation_results if result.error_code == V12BErrorCode.GENERATION_ERROR
    )
    return V12BAggregateResult(
        record_ordinal=record_ordinal,
        qid=item.qid,
        input_index=item.input_index,
        router_selected_rank=item.router_selected_rank,
        attempted_permutation_count=len(permutation_results),
        valid_permutation_count=sum(1 for result in permutation_results if result.valid),
        parse_failure_count=parse_failures,
        generation_failure_count=generation_failures,
        vote_counts={},
        winning_label=None,
        winning_votes=0,
        runner_up_label=None,
        runner_up_votes=0,
        vote_margin=0,
        consensus_ratio=0.0,
        unique_answer_count=0,
        tie=False,
        aggregate_status=V12BAggregateStatus.AGGREGATE_ERROR,
        base_v12b_agreement=None,
        hypothetical_answer=None,
        hypothetical_conservative_acceptance=False,
        record_error_code=V12BErrorCode.AGGREGATE_ERROR,
        permutation_results=permutation_results,
        elapsed_seconds=elapsed_seconds,
    )


def _build_summary(
    selected_inputs: tuple[V12BRunInput, ...],
    results: tuple[V12BAggregateResult, ...],
) -> V12BRunSummary:
    status_counts: dict[str, int] = {}
    for result in results:
        status_counts[result.aggregate_status.value] = status_counts.get(result.aggregate_status.value, 0) + 1
    failed_statuses = {V12BAggregateStatus.AGGREGATE_ERROR, V12BAggregateStatus.GENERATION_FAILURE}
    failed = sum(1 for result in results if result.aggregate_status in failed_statuses)
    selected_items = tuple(
        V12BSelectedItem(
            record_ordinal=index,
            qid=item.qid,
            input_index=item.input_index,
            router_selected_rank=item.router_selected_rank,
        )
        for index, item in enumerate(selected_inputs)
    )
    return V12BRunSummary(
        total_selected_records=len(selected_inputs),
        attempted_records=len(selected_inputs),
        succeeded_records=len(selected_inputs) - failed,
        failed_records=failed,
        total_permutation_attempts=sum(result.attempted_permutation_count for result in results),
        total_valid_permutations=sum(result.valid_permutation_count for result in results),
        parse_failure_total=sum(result.parse_failure_count for result in results),
        generation_failure_total=sum(result.generation_failure_count for result in results),
        aggregate_status_counts=status_counts,
        base_v12b_disagreement_count=sum(1 for result in results if result.base_v12b_agreement is False),
        selected_qids=tuple(item.qid for item in selected_inputs),
        selected_items=selected_items,
    )


def _sample_for_permutation_core(item: V12BRunInput) -> dict[str, Any]:
    return {
        "qid": item.qid,
        "question": item.question,
        "choices": list(item.choices),
    }


def _build_prompt(question: str, permutation: OptionPermutation) -> list[dict[str, str]]:
    option_lines = [f"{choice['label']}. {choice['text']}" for choice in permutation.permuted_choices]
    user = "\n".join(
        [
            "Question:",
            str(question),
            "",
            "Options:",
            *option_lines,
            "",
            "Return JSON only with keys selected_label, selected_option_text, label_matches_option.",
        ]
    )
    return [
        {"role": "system", "content": "Select one listed option and return one JSON object."},
        {"role": "user", "content": user},
    ]


def _vote_record(result: V12BPermutationResult) -> dict[str, Any]:
    return {
        "parse_status": result.parse_status,
        "mapped_original_label": result.mapped_original_label,
        "label_option_match": result.label_option_match,
        "valid": result.valid,
        "failure_reason": "" if result.error_code == V12BErrorCode.OK else result.error_code.value,
    }


def _aggregate_status(
    *,
    attempted: int,
    valid: int,
    generation_failures: int,
    tie: bool,
    winner_votes: int,
    min_valid_permutations: int,
    consensus_votes: int,
) -> V12BAggregateStatus:
    if attempted > 0 and generation_failures == attempted:
        return V12BAggregateStatus.GENERATION_FAILURE
    if valid == 0:
        return V12BAggregateStatus.ALL_INVALID
    if valid < min_valid_permutations:
        return V12BAggregateStatus.INSUFFICIENT_VALID_PERMUTATIONS
    if tie:
        return V12BAggregateStatus.TIE
    if winner_votes >= consensus_votes:
        return V12BAggregateStatus.VALID_UNIQUE_MAJORITY
    return V12BAggregateStatus.VALID_WEAK_CONSENSUS


def _record_error_code(status: V12BAggregateStatus) -> V12BErrorCode:
    return {
        V12BAggregateStatus.AGGREGATE_ERROR: V12BErrorCode.AGGREGATE_ERROR,
        V12BAggregateStatus.GENERATION_FAILURE: V12BErrorCode.GENERATION_ERROR,
        V12BAggregateStatus.ALL_INVALID: V12BErrorCode.ALL_INVALID,
        V12BAggregateStatus.INSUFFICIENT_VALID_PERMUTATIONS: V12BErrorCode.INSUFFICIENT_VALID_PERMUTATIONS,
        V12BAggregateStatus.TIE: V12BErrorCode.TIE,
        V12BAggregateStatus.VALID_UNIQUE_MAJORITY: V12BErrorCode.OK,
        V12BAggregateStatus.VALID_WEAK_CONSENSUS: V12BErrorCode.OK,
    }[status]


def _normalize_mapping_error(raw_reason: str | None) -> V12BErrorCode:
    if not raw_reason:
        return V12BErrorCode.OK
    return {
        "label_out_of_range": V12BErrorCode.LABEL_OUT_OF_RANGE,
        "self_label_option_conflict": V12BErrorCode.LABEL_OPTION_MISMATCH,
        "label_text_conflict": V12BErrorCode.LABEL_TEXT_CONFLICT,
        "option_text_no_match": V12BErrorCode.OPTION_TEXT_NO_MATCH,
        "no_mapped_label": V12BErrorCode.MISSING_SELECTED_LABEL,
        "parse_error": V12BErrorCode.PARSE_ERROR,
        "local_error": V12BErrorCode.GENERATION_ERROR,
    }.get(str(raw_reason), V12BErrorCode.AGGREGATE_ERROR)


def _ordered_vote_counts(vote_counts: Mapping[str, int], labels: tuple[str, ...]) -> dict[str, int]:
    order = _label_order(labels)
    return {
        label: int(votes)
        for label, votes in sorted(
            vote_counts.items(),
            key=lambda item: (order.get(str(item[0]), len(order)), str(item[0])),
        )
    }


def _vote_leaders(
    vote_counts: Mapping[str, int],
    labels: tuple[str, ...],
) -> tuple[str | None, int, str | None, int, bool]:
    if not vote_counts:
        return None, 0, None, 0, False
    order = _label_order(labels)
    ranked = sorted(
        vote_counts.items(),
        key=lambda item: (-int(item[1]), order.get(str(item[0]), len(order)), str(item[0])),
    )
    winner, winner_votes = ranked[0][0], int(ranked[0][1])
    runner_up, runner_up_votes = (ranked[1][0], int(ranked[1][1])) if len(ranked) > 1 else (None, 0)
    tie = bool(runner_up is not None and runner_up_votes == winner_votes)
    return str(winner), winner_votes, str(runner_up) if runner_up is not None else None, runner_up_votes, tie


def _label_order(labels: tuple[str, ...]) -> dict[str, int]:
    return {label: index for index, label in enumerate(labels)}


def _normalize_label(label: Any) -> str:
    return str(label).strip().upper()


def _normalize_optional_label(label: Any) -> str | None:
    if label is None:
        return None
    normalized = _normalize_label(label)
    return normalized or None
