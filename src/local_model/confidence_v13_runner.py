"""In-memory V13 runner for records left unresolved by V12B.

Clean adapter over the pure, deterministic V13 core modules (programmatic solver,
content-first answerer, least-to-most constraint solver) — NOT the legacy
``src.layers.v13_dynamic_layer.run_v13_layer`` orchestration, which unconditionally
creates a work directory and writes a legacy JSONL file before returning, and which
selects targets via legacy ``BasePrediction``-shaped risk scoring. This runner:

* injects the already-loaded backend (never loads/caches a second model);
* calls no external API;
* writes no intermediate files;
* accepts only the records explicitly handed to it (the caller decides what is
  "unresolved after V12B" — this module has no target-selection policy of its own
  beyond a small deterministic per-record layer choice, mirroring the pure feature
  classification the legacy layer also used, e.g. ``classify_programmatic_domain``);
* returns canonical labels and a closed set of failure codes only;
* fails closed per record: one record's exception never aborts the others, and the
  final answer/source decision is made entirely by the caller's selector (this
  runner never touches the official answer or any base prediction).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol

from src.layers import content_first_answerer as CF
from src.layers import least_to_most_constraint_solver as LTM
from src.layers import programmatic_solver_layer as PS
from src.local_model.local_qwen_backend import parse_json_object
from src.utils.labels import is_valid_label, labels_for

DEFAULT_MAX_NEW_TOKENS = 384

_CONTENT_HINTS = (
    "tục ngữ", "thành ngữ", "nghĩa", "định nghĩa", "là gì", "thuật ngữ",
    "khái niệm", "đồng nghĩa", "proverb", "definition", "term", "meaning",
)
_MULTI_COND_HINTS = (
    "đúng", "sai", "phát biểu", "chọn câu", "không đúng", "ngoại trừ",
    "statement", "which of the following", "true", "false", "except",
)

_LAYER_PROGRAMMATIC = "programmatic_solver"
_LAYER_CONTENT_FIRST = "content_first"
_LAYER_LEAST_TO_MOST = "least_to_most"
_LAYER_UNKNOWN = "unknown"


class V13BackendProtocol(Protocol):
    def generate_text(
        self,
        prompt_or_messages: str | list[dict[str, str]],
        *,
        max_new_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> str:
        ...


class V13ErrorCode(str, Enum):
    OK = "ok"
    EMPTY_PROMPT = "empty_prompt"
    GENERATION_ERROR = "generation_error"
    PARSE_ERROR = "parse_error"
    NO_MATCH = "no_match"
    INVALID_LABEL = "invalid_label"
    UNKNOWN_LAYER = "unknown_layer"
    RUNNER_ERROR = "runner_error"


@dataclass(frozen=True)
class V13RunInput:
    qid: str
    input_index: int
    question: str
    choices: tuple[str, ...]
    canonical_labels: tuple[str, ...]

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


@dataclass(frozen=True)
class V13RunResult:
    record_ordinal: int
    qid: str
    input_index: int
    layer: str
    attempted: bool
    valid: bool
    mapped_label: str | None
    error_code: V13ErrorCode
    exception_class_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "qid", str(self.qid))
        object.__setattr__(self, "input_index", int(self.input_index))
        object.__setattr__(self, "layer", str(self.layer))
        object.__setattr__(self, "attempted", bool(self.attempted))
        object.__setattr__(self, "valid", bool(self.valid))
        object.__setattr__(self, "mapped_label", _normalize_optional_label(self.mapped_label))
        if not isinstance(self.error_code, V13ErrorCode):
            object.__setattr__(self, "error_code", V13ErrorCode(str(self.error_code)))
        if self.exception_class_name is not None:
            object.__setattr__(self, "exception_class_name", str(self.exception_class_name))

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_ordinal": self.record_ordinal,
            "qid": self.qid,
            "input_index": self.input_index,
            "layer": self.layer,
            "attempted": self.attempted,
            "valid": self.valid,
            "mapped_label": self.mapped_label,
            "error_code": self.error_code.value,
            "exception_class_name": self.exception_class_name,
        }


@dataclass(frozen=True)
class V13RunSummary:
    total_unresolved_records: int
    attempted_records: int
    valid_records: int
    invalid_records: int
    layer_counts: Mapping[str, int]
    error_code_counts: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_unresolved_records": self.total_unresolved_records,
            "attempted_records": self.attempted_records,
            "valid_records": self.valid_records,
            "invalid_records": self.invalid_records,
            "layer_counts": dict(self.layer_counts),
            "error_code_counts": dict(self.error_code_counts),
        }


def run_v13_for_unresolved(
    inputs: Iterable[V13RunInput],
    *,
    backend: V13BackendProtocol,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> tuple[tuple[V13RunResult, ...], V13RunSummary]:
    """Run V13 on exactly the records the caller passes in, in order. Never selects
    its own targets beyond the per-record layer choice; never reads/writes files;
    never touches a base answer or the official output."""
    items = tuple(inputs)
    results = tuple(
        _run_one_record(item, record_ordinal=ordinal, backend=backend, max_new_tokens=max_new_tokens)
        for ordinal, item in enumerate(items)
    )
    return results, _build_summary(results)


def _sample_for_record(item: V13RunInput) -> dict[str, Any]:
    return {"qid": item.qid, "question": item.question, "choices": list(item.choices)}


def _choose_layer(sample: dict[str, Any]) -> str:
    """Deterministic, feature-based single-layer choice — pure text classification,
    no model call, no legacy risk-scoring/BasePrediction dependency."""
    domain = PS.classify_programmatic_domain(sample)
    if domain != "none":
        return _LAYER_PROGRAMMATIC
    question_lower = str(sample.get("question") or "").lower()
    if any(hint in question_lower for hint in _CONTENT_HINTS):
        return _LAYER_CONTENT_FIRST
    if any(hint in question_lower for hint in _MULTI_COND_HINTS):
        return _LAYER_LEAST_TO_MOST
    return _LAYER_CONTENT_FIRST  # safe default (mirrors the legacy layer's default)


def _build_prompt(layer: str, sample: dict[str, Any]) -> str:
    if layer == _LAYER_PROGRAMMATIC:
        return PS.build_programmatic_prompt(sample, PS.classify_programmatic_domain(sample))
    if layer == _LAYER_CONTENT_FIRST:
        return CF.build_content_first_prompt(sample, "")
    if layer == _LAYER_LEAST_TO_MOST:
        return LTM.build_ltm_constraint_prompt(sample, "")
    return ""


def _interpret(layer: str, sample: dict[str, Any], parsed: dict[str, Any]) -> tuple[str | None, bool]:
    if layer == _LAYER_PROGRAMMATIC:
        spec = PS.parse_calculation_spec(parsed)
        result = PS.match_result_to_options(PS.safe_execute_calculation(spec), sample)
        return result.mapped_label, bool(result.ok and result.mapped_label)
    if layer == _LAYER_CONTENT_FIRST:
        content_answer = CF.parse_content_answer(parsed)
        match = CF.match_content_to_options(content_answer, sample)
        return match.mapped_label, bool(match.ok and match.mapped_label)
    if layer == _LAYER_LEAST_TO_MOST:
        decision = LTM.parse_constraint_table(parsed)
        outcome = LTM.select_answer_from_constraint_table(decision, sample)
        return outcome.get("proposed_label"), bool(outcome.get("ok"))
    return None, False


def _run_one_record(
    item: V13RunInput,
    *,
    record_ordinal: int,
    backend: V13BackendProtocol,
    max_new_tokens: int,
) -> V13RunResult:
    layer = _LAYER_UNKNOWN
    try:
        sample = _sample_for_record(item)
        layer = _choose_layer(sample)
        prompt = (_build_prompt(layer, sample) or "").strip()
        if not prompt:
            return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                                attempted=False, valid=False, mapped_label=None,
                                error_code=V13ErrorCode.EMPTY_PROMPT)
        messages = [{"role": "user", "content": prompt}]
        try:
            content = backend.generate_text(messages, max_new_tokens=max_new_tokens, temperature=0.0)
        except Exception as exc:
            return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                                attempted=True, valid=False, mapped_label=None,
                                error_code=V13ErrorCode.GENERATION_ERROR,
                                exception_class_name=type(exc).__name__)
        parsed = parse_json_object(content)
        if not isinstance(parsed, dict):
            return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                                attempted=True, valid=False, mapped_label=None,
                                error_code=V13ErrorCode.PARSE_ERROR)
        label, ok = _interpret(layer, sample, parsed)
        if ok and label and is_valid_label(label, sample):
            return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                                attempted=True, valid=True, mapped_label=label,
                                error_code=V13ErrorCode.OK)
        if label and not is_valid_label(label, sample):
            return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                                attempted=True, valid=False, mapped_label=None,
                                error_code=V13ErrorCode.INVALID_LABEL)
        return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                            attempted=True, valid=False, mapped_label=None,
                            error_code=V13ErrorCode.NO_MATCH)
    except Exception as exc:                      # one record's failure never aborts the others
        return V13RunResult(record_ordinal, item.qid, item.input_index, layer,
                            attempted=True, valid=False, mapped_label=None,
                            error_code=V13ErrorCode.RUNNER_ERROR,
                            exception_class_name=type(exc).__name__)


def _build_summary(results: tuple[V13RunResult, ...]) -> V13RunSummary:
    layer_counts: dict[str, int] = {}
    error_counts: dict[str, int] = {}
    valid = 0
    attempted = 0
    for result in results:
        layer_counts[result.layer] = layer_counts.get(result.layer, 0) + 1
        error_counts[result.error_code.value] = error_counts.get(result.error_code.value, 0) + 1
        if result.attempted:
            attempted += 1
        if result.valid:
            valid += 1
    return V13RunSummary(
        total_unresolved_records=len(results),
        attempted_records=attempted,
        valid_records=valid,
        invalid_records=len(results) - valid,
        layer_counts=layer_counts,
        error_code_counts=error_counts,
    )


def _normalize_label(label: Any) -> str:
    return str(label).strip().upper()


def _normalize_optional_label(label: Any) -> str | None:
    if label is None:
        return None
    normalized = _normalize_label(label)
    return normalized or None
