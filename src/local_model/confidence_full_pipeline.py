"""Phase 3B full confidence-routed pipeline: Base -> V12B -> V13 -> deterministic
conservative selector.

UNLIKE the observational V12B shadow (``confidence_v12b_artifacts.py``), this module
DOES change the final answer for router-selected records. It never uses model
self-reported confidence, chain-of-thought, organizer ground truth, or an external
API. It never invokes V13/selector/legacy code beyond the two approved in-memory
runners it composes (``confidence_v12b_runner`` and ``confidence_v13_runner``), both
of which receive the SAME injected backend instance (no second model load).

Identity contract (mirrors AUDIT 87 §10, extended to V13): the authoritative
per-record identity is ``source_record_ordinal`` = ``enumerate(samples)`` index,
which equals the router decision-list position. Records are paired with V12B/V13
results by list position only, never by qid/input_index. A router-selected record
that fails the V12B input-validation boundary (``confidence_v12b_artifacts``'s
closed validation codes) is not sent to V13 either -- the same boundary that
protects V12B protects V13 -- and stays on the Base answer.

Selector policy (conservative; ties/ambiguity always fall back to Base):
  1. not router-selected                                   -> base
  2. selected + invalid at the V12B boundary                -> base
  3. selected + valid + V12B ``valid_unique_majority`` with
     a valid canonical hypothetical answer                  -> v12b
  4. selected + valid + V12B anything else (all_invalid,
     insufficient_valid_permutations, tie, weak_consensus,
     generation_failure, aggregate_error, ...)               -> V13 attempted
  5a. V13 returns one valid canonical label                  -> v13
  5b. V13 fails / malformed / invalid label / exception       -> base_fallback
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.local_model.confidence_v12b_artifacts import VALIDATION_OK, build_selected_entries
from src.local_model.confidence_v12b_runner import run_v12b_for_selected
from src.local_model.confidence_v13_runner import V13RunInput, run_v13_for_unresolved
from src.utils.labels import is_valid_label, labels_for

FINAL_SOURCE_BASE = "base"
FINAL_SOURCE_V12B = "v12b"
FINAL_SOURCE_V13 = "v13"
FINAL_SOURCE_BASE_FALLBACK = "base_fallback"

_ACCEPT_V12B_STATUS = "valid_unique_majority"


@dataclass(frozen=True)
class FullPipelineRecord:
    source_record_ordinal: int
    qid: str
    input_index: int
    base_answer: str | None
    router_selected: bool
    v12b_status: str | None
    v12b_hypothetical_answer: str | None
    v13_attempted: bool
    v13_status: str | None
    v13_answer: str | None
    final_answer: str
    final_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_record_ordinal": self.source_record_ordinal,
            "qid": self.qid,
            "input_index": self.input_index,
            "base_answer": self.base_answer,
            "router_selected": self.router_selected,
            "v12b_status": self.v12b_status,
            "v12b_hypothetical_answer": self.v12b_hypothetical_answer,
            "v13_attempted": self.v13_attempted,
            "v13_status": self.v13_status,
            "v13_answer": self.v13_answer,
            "final_answer": self.final_answer,
            "final_source": self.final_source,
        }


@dataclass(frozen=True)
class FullPipelineSummary:
    total_input_records: int
    total_router_selected: int
    total_router_selected_valid: int
    total_router_selected_invalid: int
    total_v12b_accepted: int
    total_v13_attempted: int
    total_v13_accepted: int
    total_base_fallback: int
    total_base: int
    final_source_counts: Mapping[str, int]
    v12b_aggregate_status_counts: Mapping[str, int]
    v13_error_code_counts: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_input_records": self.total_input_records,
            "total_router_selected": self.total_router_selected,
            "total_router_selected_valid": self.total_router_selected_valid,
            "total_router_selected_invalid": self.total_router_selected_invalid,
            "total_v12b_accepted": self.total_v12b_accepted,
            "total_v13_attempted": self.total_v13_attempted,
            "total_v13_accepted": self.total_v13_accepted,
            "total_base_fallback": self.total_base_fallback,
            "total_base": self.total_base,
            "final_source_counts": dict(self.final_source_counts),
            "v12b_aggregate_status_counts": dict(self.v12b_aggregate_status_counts),
            "v13_error_code_counts": dict(self.v13_error_code_counts),
            "note": ("full pipeline: official answer changes ONLY for router-selected, "
                     "V12B-input-valid records; ties/failures/malformed output always fall "
                     "back to Base; no self-reported confidence, no organizer ground truth, "
                     "no external API"),
        }


def _deterministic_fallback_label(sample: dict[str, Any]) -> str:
    """The same deterministic per-sample fallback predict.py itself uses
    (`_fallback_answer`): the first canonical label, or "A" if choices are
    somehow absent. Used only when even the Base answer is not canonical."""
    choices = sample.get("choices") or []
    return labels_for(len(choices))[0] if choices else "A"


def _v13_input_from_sample(sample: dict[str, Any], decision: Any) -> V13RunInput:
    choices = tuple(str(choice) for choice in sample.get("choices") or [])
    return V13RunInput(
        qid=str(sample.get("qid")),
        input_index=int(decision.input_index),
        question=str(sample.get("question")),
        choices=choices,
        canonical_labels=tuple(labels_for(len(choices))),
    )


def run_full_pipeline(
    *,
    samples,
    decisions,
    backend,
    v12b_config,
    v13_max_new_tokens: int | None = None,
) -> tuple[list[FullPipelineRecord], FullPipelineSummary]:
    """Base rows are the caller's responsibility (already generated); this function
    only decides, per router-selected record, whether V12B or V13 should override the
    Base answer, and returns one record per input sample in input order."""
    samples = list(samples)
    decisions = list(decisions)
    if len(decisions) != len(samples):
        raise AssertionError(
            "full pipeline: decision count does not match sample count "
            f"({len(decisions)} != {len(samples)})")
    selected, valid = build_selected_entries(samples, decisions)

    v12b_results, _v12b_run_summary = run_v12b_for_selected(
        [entry["v12b_input"] for entry in valid],
        backend=backend,
        permutation_count=int(v12b_config.permutation_count),
    )
    if len(v12b_results) != len(valid):
        raise AssertionError(
            "full pipeline: v12b result count does not match valid selected-input count")

    v12b_by_ordinal: dict[int, tuple[dict, Any]] = {
        entry["source_record_ordinal"]: (entry, aggregate)
        for entry, aggregate in zip(valid, v12b_results)
    }

    v12b_accepted_ordinals: set[int] = set()
    needs_v13: list[dict[str, Any]] = []   # ordered; carries source metadata for positional pairing
    for ordinal, (entry, aggregate) in v12b_by_ordinal.items():
        hypothetical = aggregate.hypothetical_answer
        accepted = (
            aggregate.aggregate_status.value == _ACCEPT_V12B_STATUS
            and hypothetical is not None
            and is_valid_label(hypothetical, entry["sample"])
        )
        if accepted:
            v12b_accepted_ordinals.add(ordinal)
        else:
            needs_v13.append({
                "source_record_ordinal": ordinal,
                "sample": entry["sample"],
                "decision": entry["decision"],
            })

    v13_kwargs = {} if v13_max_new_tokens is None else {"max_new_tokens": int(v13_max_new_tokens)}
    v13_results, v13_summary = run_v13_for_unresolved(
        [_v13_input_from_sample(entry["sample"], entry["decision"]) for entry in needs_v13],
        backend=backend,
        **v13_kwargs,
    )
    if len(v13_results) != len(needs_v13):
        raise AssertionError(
            "full pipeline: v13 result count does not match unresolved-input count")
    v13_by_ordinal = {
        entry["source_record_ordinal"]: result for entry, result in zip(needs_v13, v13_results)
    }

    records: list[FullPipelineRecord] = []
    final_source_counts: dict[str, int] = {}
    v12b_status_counts: dict[str, int] = {}
    for ordinal, _sample in enumerate(samples):
        decision = decisions[ordinal]
        base_answer = decision.generated_answer
        router_selected = bool(getattr(decision, "selected", False))
        v12b_status = v12b_hypothetical = v13_status = v13_answer = None
        v13_attempted = False
        final_answer, final_source = base_answer, FINAL_SOURCE_BASE

        if ordinal in v12b_by_ordinal:
            _entry, aggregate = v12b_by_ordinal[ordinal]
            v12b_status = aggregate.aggregate_status.value
            v12b_hypothetical = aggregate.hypothetical_answer
            v12b_status_counts[v12b_status] = v12b_status_counts.get(v12b_status, 0) + 1
            if ordinal in v12b_accepted_ordinals:
                final_answer, final_source = v12b_hypothetical, FINAL_SOURCE_V12B
            elif ordinal in v13_by_ordinal:
                v13_attempted = True
                v13_result = v13_by_ordinal[ordinal]
                v13_status = v13_result.error_code.value
                if v13_result.valid and v13_result.mapped_label:
                    v13_answer = v13_result.mapped_label
                    final_answer, final_source = v13_answer, FINAL_SOURCE_V13
                else:
                    final_answer, final_source = base_answer, FINAL_SOURCE_BASE_FALLBACK
        # else: not selected, or selected-but-invalid at the V12B boundary -> stays Base.

        # Defense-in-depth: enforce "every final answer is canonical" INSIDE the
        # selector itself (not only via a caller-side safety net). V12B/V13 answers
        # are already validated above before being assigned; this only fires if
        # `base_answer` itself is ever missing/invalid (e.g. a malformed decision
        # object from a future caller), in which case even "Base" is not safe to
        # trust and a deterministic canonical fallback is used instead.
        if not (isinstance(final_answer, str) and is_valid_label(final_answer, _sample)):
            final_answer = _deterministic_fallback_label(_sample)
            final_source = FINAL_SOURCE_BASE_FALLBACK

        final_source_counts[final_source] = final_source_counts.get(final_source, 0) + 1
        records.append(FullPipelineRecord(
            source_record_ordinal=ordinal, qid=str(decision.qid), input_index=int(decision.input_index),
            base_answer=base_answer, router_selected=router_selected,
            v12b_status=v12b_status, v12b_hypothetical_answer=v12b_hypothetical,
            v13_attempted=v13_attempted, v13_status=v13_status, v13_answer=v13_answer,
            final_answer=final_answer, final_source=final_source,
        ))

    summary = FullPipelineSummary(
        total_input_records=len(samples),
        total_router_selected=len(selected),
        total_router_selected_valid=len(valid),
        total_router_selected_invalid=len(selected) - len(valid),
        total_v12b_accepted=len(v12b_accepted_ordinals),
        total_v13_attempted=sum(1 for record in records if record.v13_attempted),
        total_v13_accepted=final_source_counts.get(FINAL_SOURCE_V13, 0),
        total_base_fallback=final_source_counts.get(FINAL_SOURCE_BASE_FALLBACK, 0),
        total_base=final_source_counts.get(FINAL_SOURCE_BASE, 0),
        final_source_counts=final_source_counts,
        v12b_aggregate_status_counts=v12b_status_counts,
        v13_error_code_counts=dict(v13_summary.error_code_counts),
    )
    return records, summary
