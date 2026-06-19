"""Parse a single answer label out of free-form model output.

The model may answer in many shapes — ``"A"``, ``"A."``, ``"(A)"``,
``"Đáp án: A"``, ``"Câu trả lời là B"``, ``"The answer is C"``,
``"Answer: D"``, ``"Tôi chọn E"`` — possibly with extra commentary. We:

  1. try explicit "the answer is X" patterns first (most reliable), then
  2. fall back to the first *standalone* valid label in the text.

Only labels in ``valid_labels`` are ever returned, so a 4-choice question can
never yield ``"E"``. Letters embedded inside words (e.g. the "A" in "Animal")
are not mistaken for labels.
"""

from __future__ import annotations

import re
from typing import Optional

# Phrases that explicitly announce the answer, Vietnamese and English. The label
# is captured as a single A-Z letter; we validate it against valid_labels after.
_EXPLICIT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"đáp\s*án\s*(?:đúng)?\s*(?:là|:)?\s*[\(\[]?\s*([a-z])\b",
        r"câu\s*trả\s*lời\s*(?:đúng)?\s*(?:là|:)?\s*[\(\[]?\s*([a-z])\b",
        r"(?:tôi|mình|em)\s*chọn\s*[\(\[]?\s*([a-z])\b",
        r"chọn\s*(?:đáp\s*án)?\s*[\(\[]?\s*([a-z])\b",
        r"answer\s*(?:is|:)?\s*[\(\[]?\s*([a-z])\b",
        r"the\s*answer\s*is\s*[\(\[]?\s*([a-z])\b",
    )
]

# A standalone label: a single letter optionally wrapped in ()/[] and/or
# followed by . ) : — but bounded so it is not part of a larger word.
_STANDALONE_RE = re.compile(r"(?<![a-zA-Z])[\(\[]?\s*([a-zA-Z])\s*[\)\].:]?(?![a-zA-Z])")


def parse_answer_label(text: str, valid_labels: list[str]) -> Optional[str]:
    """Return the uppercase answer label found in ``text``, or ``None``.

    ``valid_labels`` is the list of labels valid for this question (e.g.
    ``["A", "B", "C", "D"]``); anything outside it is rejected.
    """
    if not text or not valid_labels:
        return None

    valid = {l.upper() for l in valid_labels}

    # 1) Explicit "answer is X" style phrases win.
    for pattern in _EXPLICIT_PATTERNS:
        match = pattern.search(text)
        if match:
            label = match.group(1).upper()
            if label in valid:
                return label

    # 2) Fall back to the first standalone valid label anywhere in the text.
    for match in _STANDALONE_RE.finditer(text):
        label = match.group(1).upper()
        if label in valid:
            return label

    return None
