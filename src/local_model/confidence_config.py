"""Loader for the opt-in confidence-aware selective config (Phase 1 scope).

Phase 1 only needs the ``choice_scoring`` block. The loader has safe defaults
(so a missing file or key never breaks a run), type/value validation with clear
errors, and accepts a path, a dict, or None. It imports no torch/transformers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_DEFAULT_CONFIG_PATH = "configs/confidence_selective.yaml"
_SUPPORTED_NORMALIZATION = ("softmax",)


@dataclass(frozen=True)
class ChoiceScoringConfig:
    enabled: bool = True
    canonical_answer_prefix: str = " "
    normalization: str = "softmax"
    batch_size: int = 8


def _validate(block: dict) -> ChoiceScoringConfig:
    cfg = ChoiceScoringConfig(
        enabled=bool(block.get("enabled", True)),
        canonical_answer_prefix=block.get("canonical_answer_prefix", " "),
        normalization=str(block.get("normalization", "softmax")),
        batch_size=block.get("batch_size", 8),
    )
    if not isinstance(cfg.canonical_answer_prefix, str):
        raise ValueError("choice_scoring.canonical_answer_prefix must be a string")
    if cfg.normalization not in _SUPPORTED_NORMALIZATION:
        raise ValueError(
            f"choice_scoring.normalization={cfg.normalization!r} unsupported; "
            f"choose one of {_SUPPORTED_NORMALIZATION}")
    if not isinstance(cfg.batch_size, int) or isinstance(cfg.batch_size, bool) or cfg.batch_size < 1:
        raise ValueError("choice_scoring.batch_size must be an integer >= 1")
    return cfg


def load_choice_scoring_config(source=None) -> ChoiceScoringConfig:
    """Return a validated ChoiceScoringConfig.

    ``source`` may be a dict (already-parsed config), a path to a YAML file, or
    None. None loads the default config file if present, else safe defaults.
    """
    if isinstance(source, dict):
        return _validate(source.get("choice_scoring", source))

    if source is None:
        path = Path(_DEFAULT_CONFIG_PATH)
        if not path.exists():
            return ChoiceScoringConfig()
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"confidence config not found: {path}")

    import yaml  # PyYAML is already a project dependency
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"confidence config {path} must be a mapping")
    return _validate(data.get("choice_scoring", {}))
