"""Solver interface.

A solver maps a normalised sample (``{qid, question, choices}``) to an answer
label (``"A"``, ``"B"``, ...). Future Phase 2 LLM solvers subclass
:class:`BaseSolver` and override :meth:`predict_one`; batching comes for free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSolver(ABC):
    """Abstract base class for all MCQ solvers."""

    @abstractmethod
    def predict_one(self, sample: dict) -> str:
        """Return the predicted answer label for a single sample."""
        raise NotImplementedError

    def predict_batch(self, samples: list[dict]) -> list[str]:
        """Predict labels for a batch of samples.

        The default implementation calls :meth:`predict_one` per sample. A
        Phase 2 solver that benefits from true batching (e.g. batched LLM
        calls) can override this.
        """
        return [self.predict_one(sample) for sample in samples]
