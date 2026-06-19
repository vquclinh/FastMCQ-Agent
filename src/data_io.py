"""Input/output for datasets and predictions.

The competition input may be JSON (a list of objects) or CSV. CSV files come in
a few common shapes, so :func:`load_dataset` normalises everything into a list
of dicts with at least ``qid``, ``question`` and ``choices``.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

# CSV header variants we recognise as "this column holds choice text".
# Matches: A / B / ...,  option_a / option_b / ...,  choice_1 / choice1, etc.
_CHOICE_COLUMN_RE = re.compile(
    r"^(?:[a-z]|option[_\s]?[a-z0-9]+|choice[_\s]?[a-z0-9]+|opt[_\s]?[a-z0-9]+)$",
    re.IGNORECASE,
)

# Columns that are never choices.
_NON_CHOICE_COLUMNS = {"qid", "id", "question", "answer", "label", "choices"}


def load_dataset(path: str | Path) -> list[dict]:
    """Load and normalise a dataset from a JSON or CSV file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".json":
        rows = _load_json(path)
    elif suffix == ".csv":
        rows = _load_csv(path)
    else:
        raise ValueError(f"unsupported input extension {suffix!r} (expected .json or .csv)")

    return [_normalize(row, i) for i, row in enumerate(rows)]


def _load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        # Tolerate a wrapper like {"data": [...]} or {"questions": [...]}.
        for key in ("data", "questions", "items", "samples"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError("JSON object did not contain a recognised list of records")
    if not isinstance(data, list):
        raise ValueError("JSON input must be a list of objects")
    return data


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _normalize(row: dict, index: int) -> dict:
    """Normalise one raw record into ``{qid, question, choices}`` (plus extras)."""
    qid = row.get("qid") or row.get("id") or f"q_{index:04d}"
    question = row.get("question") or row.get("text") or ""
    choices = _extract_choices(row)
    return {"qid": str(qid), "question": str(question), "choices": choices}


def _extract_choices(row: dict) -> list[str]:
    """Pull the list of choice strings out of a raw record.

    Handles three CSV shapes plus the native JSON list:
      * choices already a list (JSON)
      * a single ``choices`` column holding JSON or a delimited string
      * separate columns (A,B,C,D / option_a,... / choice_1,...)
    """
    raw = row.get("choices")
    if isinstance(raw, list):
        return [str(c) for c in raw]

    if isinstance(raw, str) and raw.strip():
        return _parse_choices_string(raw)

    # Fall back to scanning columns that look like individual choices.
    choice_cols = sorted(
        (k for k in row if _is_choice_column(k)),
        key=_choice_sort_key,
    )
    values = [str(row[k]).strip() for k in choice_cols]
    return [v for v in values if v != ""]


def _parse_choices_string(raw: str) -> list[str]:
    raw = raw.strip()
    # Try JSON first (e.g. '["a", "b"]'), then fall back to common delimiters.
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(c) for c in parsed]
        except json.JSONDecodeError:
            pass
    for delimiter in ("|", ";", "\t"):
        if delimiter in raw:
            return [part.strip() for part in raw.split(delimiter) if part.strip()]
    return [raw]


def _is_choice_column(name: str) -> bool:
    if name is None or name.strip().lower() in _NON_CHOICE_COLUMNS:
        return False
    return bool(_CHOICE_COLUMN_RE.match(name.strip()))


def _choice_sort_key(name: str):
    """Sort choice columns so A<B<C and option_1<option_2<option_10."""
    name = name.strip().lower()
    # Numeric suffix sorts numerically; otherwise sort by the trailing letter.
    match = re.search(r"(\d+)$", name)
    if match:
        return (0, int(match.group(1)), name)
    letter = name[-1] if name else ""
    return (1, ord(letter) if letter else 0, name)


def write_predictions(predictions: list[dict], path: str | Path) -> None:
    """Write predictions to a ``qid,answer`` CSV, creating parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["qid", "answer"])
        for pred in predictions:
            writer.writerow([pred["qid"], pred["answer"]])


def read_predictions(path: str | Path) -> list[dict]:
    """Read a ``qid,answer`` CSV back into a list of dicts."""
    path = Path(path)
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))
