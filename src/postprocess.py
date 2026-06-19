"""Prediction post-processing.

Guarantees the submission is well-formed regardless of what a solver returns:
every qid appears exactly once and carries a valid label, with ``"A"`` as the
safe fallback for anything invalid or missing.
"""

from __future__ import annotations

from .labels import index_to_label, is_valid_label

_FALLBACK = index_to_label(0)  # "A"


def build_predictions(samples: list[dict], labels: list[str]) -> list[dict]:
    """Pair samples with predicted labels into validated ``{qid, answer}`` dicts.

    Any label that is invalid for its sample (wrong type, out of range, or
    missing) is replaced with the fallback. Each sample yields exactly one row.
    """
    if len(samples) != len(labels):
        raise ValueError(f"got {len(labels)} labels for {len(samples)} samples")

    predictions = []
    for sample, label in zip(samples, labels):
        answer = label if is_valid_label(label, sample) else _FALLBACK
        predictions.append({"qid": sample["qid"], "answer": answer})

    return _dedupe(predictions)


def _dedupe(predictions: list[dict]) -> list[dict]:
    """Keep the first answer per qid so each appears exactly once."""
    seen = set()
    deduped = []
    for pred in predictions:
        if pred["qid"] in seen:
            continue
        seen.add(pred["qid"])
        deduped.append(pred)
    return deduped
