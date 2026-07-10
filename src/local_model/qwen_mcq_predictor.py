"""Compatibility facade for the shared local Qwen backend."""

from __future__ import annotations

from pathlib import Path

from src.local_model.local_qwen_backend import (
    DEFAULT_MODEL_PATH,
    LocalQwenBackendProtocol,
    build_mcq_prompt,
    get_local_qwen_backend,
    parse_mcq_label,
)

parse_label = parse_mcq_label


class QwenMCQPredictor:
    """Deterministic single-model MCQ predictor. Call ``load()`` once, then ``predict_one``."""

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, *, device: str = "auto",
                 max_new_tokens: int = 64):
        self.model_path = str(model_path)
        self.device = device
        self.max_new_tokens = int(max_new_tokens)
        self._backend = get_local_qwen_backend(
            self.model_path, device=self.device, default_max_new_tokens=self.max_new_tokens)
        self.name = Path(self.model_path).name or self.model_path

    def load(self) -> "QwenMCQPredictor":
        """Load the tokenizer + model once through the process-wide backend."""
        self._backend.load()
        return self

    @property
    def backend(self) -> LocalQwenBackendProtocol:
        """Read-only access to the exact backend instance already used by
        ``predict_one`` and ``score_choices`` (Phase 3A-1 injection). Performs no
        model load, path resolution, cache lookup, or backend replacement — it just
        returns ``self._backend`` so callers never trigger a second model load."""
        return self._backend

    def predict_one(self, item: dict) -> str | None:
        """Return a single option label for ``item``; None if it could not be parsed."""
        return self._backend.predict_mcq(item, max_new_tokens=self.max_new_tokens)

    def score_choices(self, item: dict):
        """Phase 1 shadow scoring: per-choice uncertainty for ``item`` (observational,
        never changes the predicted answer). Delegates to the shared backend."""
        return self._backend.score_mcq_choices(item)
