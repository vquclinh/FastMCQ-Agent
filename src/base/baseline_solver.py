"""Baseline solvers.

These exist only to exercise the end-to-end pipeline (load -> solve -> validate
-> write) before any real inference lands in Phase 2. They are intentionally
trivial and deterministic.
"""

from __future__ import annotations

from src.utils.labels import index_to_label
from src.base.solver_base import BaseSolver


class AlwaysASolver(BaseSolver):
    """Predicts label ``"A"`` for every question.

    This is the format-check baseline: it produces a structurally valid
    submission without attempting to answer anything. Replace it with a real
    solver in Phase 2.
    """

    def predict_one(self, sample: dict) -> str:
        return index_to_label(0)
