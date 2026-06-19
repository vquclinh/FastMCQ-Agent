"""Per-sample debug logging for solver runs.

Writes one JSON object per sample to a JSONL file (default
``outputs/run_debug.jsonl``). This is **debug** output only — it never touches
``pred.csv``. Solvers append records via :meth:`RunLogger.record`; ``run.py``
also writes a final run-report line with overall timing and config.

The logger degrades gracefully: if the log path is unset, ``record`` is a no-op.
"""

from __future__ import annotations

import json
from pathlib import Path


class RunLogger:
    """Append-only JSONL logger for per-sample solver metadata."""

    def __init__(self, log_path: str | Path | None):
        self.log_path = Path(log_path) if log_path else None
        self._fh = None
        self.count = 0
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            # Truncate any previous run so the file reflects this run only.
            self._fh = self.log_path.open("w", encoding="utf-8")

    def record(self, *, qid: str, answer: str, solver: str, shape: str = "",
               num_choices: int = 0, elapsed_s: float = 0.0,
               raw_output=None, option_scores=None,
               fallback_reason: str | None = None) -> None:
        """Append one per-sample record. No-op if logging is disabled."""
        if self._fh is None:
            return
        record = {
            "qid": qid,
            "answer": answer,
            "solver": solver,
            "shape": shape,
            "num_choices": num_choices,
            "elapsed_s": round(elapsed_s, 4),
        }
        if raw_output is not None:
            record["raw_output"] = raw_output
        if option_scores is not None:
            record["option_scores"] = option_scores
        if fallback_reason is not None:
            record["fallback_reason"] = fallback_reason
        self._write(record)
        self.count += 1

    def record_event(self, record: dict) -> None:
        """Append an arbitrary per-sample record dict (no-op if disabled).

        Used by solvers (e.g. the adaptive agent) that emit a richer schema than
        :meth:`record`'s fixed fields. Writes the dict as-is.
        """
        if self._fh is None:
            return
        self._write(record)
        self.count += 1

    def record_summary(self, summary: dict) -> None:
        """Append a final summary record (tagged so it is easy to filter out)."""
        if self._fh is None:
            return
        self._write({"_summary": True, **summary})

    def _write(self, obj: dict) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
