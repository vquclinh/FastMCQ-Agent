"""Answer-label helpers.

Choices are labelled A, B, C, ... according to their position. The number of
choices is *not* fixed at 4 — the public test contains questions with anywhere
from 2 to 11 options, so every helper here works for an arbitrary count.
"""

from __future__ import annotations

import string

# A, B, C, ... Z gives us up to 26 labels, which is far more than any realistic
# MCQ needs. We deliberately keep this simple rather than supporting AA, AB, ...
_ALPHABET = string.ascii_uppercase


def index_to_label(index: int) -> str:
    """Convert a 0-based choice index to a label: 0 -> 'A', 1 -> 'B', ..."""
    if not 0 <= index < len(_ALPHABET):
        raise ValueError(f"index {index} out of supported range 0..{len(_ALPHABET) - 1}")
    return _ALPHABET[index]


def label_to_index(label: str) -> int:
    """Convert a label to a 0-based index: 'A' -> 0, 'b' -> 1, ..."""
    if not isinstance(label, str) or len(label.strip()) != 1:
        raise ValueError(f"label must be a single character, got {label!r}")
    upper = label.strip().upper()
    if upper not in _ALPHABET:
        raise ValueError(f"label {label!r} is not a valid A-Z label")
    return _ALPHABET.index(upper)


def labels_for(num_choices: int) -> list[str]:
    """Return the list of valid labels for a question with ``num_choices`` choices."""
    if num_choices < 0 or num_choices > len(_ALPHABET):
        raise ValueError(f"num_choices {num_choices} out of supported range 0..{len(_ALPHABET)}")
    return list(_ALPHABET[:num_choices])


def is_valid_label(label: str, sample: dict) -> bool:
    """Return True if ``label`` is a valid answer for ``sample``.

    Validity depends on the number of choices in the sample: 'E' is valid for a
    5-choice question but not for a 4-choice one.
    """
    choices = sample.get("choices") or []
    try:
        index = label_to_index(label)
    except ValueError:
        return False
    return 0 <= index < len(choices)
