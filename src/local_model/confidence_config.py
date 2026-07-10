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


# Production scoring method (see AUDIT 68/69). The old canonical_answer_prefix
# setting is DEPRECATED/IGNORED: the scorer reads bare single-token label logits,
# never a space-prefixed continuation.
SCORING_METHOD = "next_token_logits_one_forward"


@dataclass(frozen=True)
class ChoiceScoringConfig:
    enabled: bool = True
    normalization: str = "softmax"
    batch_size: int = 8
    scoring_method: str = SCORING_METHOD


def _validate(block: dict) -> ChoiceScoringConfig:
    cfg = ChoiceScoringConfig(
        enabled=bool(block.get("enabled", True)),
        normalization=str(block.get("normalization", "softmax")),
        batch_size=block.get("batch_size", 8),
        scoring_method=SCORING_METHOD,   # fixed; not user-selectable in Phase 1
    )
    # `canonical_answer_prefix`, if present in an older config, is accepted but ignored.
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
    return _validate(_load_block(source, "choice_scoring"))


# --- Phase 2 shadow router config (opt-in; observational only) --------------
def _num_or_none(v):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("expected a number or null")
    return float(v)


def _validate_shadow(block: dict):
    from src.local_model.confidence_shadow_router import ShadowRouterConfig
    b = block or {}
    margin = b.get("provisional_margin_threshold", 10.0)
    if isinstance(margin, bool) or not isinstance(margin, (int, float)):
        raise ValueError("shadow_router.provisional_margin_threshold must be a number")
    entropy = _num_or_none(b.get("entropy_threshold", None))
    divisor = b.get("budget_divisor", 20)
    if isinstance(divisor, bool) or not isinstance(divisor, int) or divisor < 1:
        raise ValueError("shadow_router.budget_divisor must be an integer >= 1")
    override = b.get("max_targets_override", None)
    if override is not None and (isinstance(override, bool) or not isinstance(override, int)
                                 or override < 0):
        raise ValueError("shadow_router.max_targets_override must be a non-negative integer or null")
    sweeps = b.get("analysis_margin_thresholds",
                   [5.0, 7.5, 10.0, 12.5, 15.0, 20.0])
    if not isinstance(sweeps, (list, tuple)) or not all(
            (not isinstance(x, bool) and isinstance(x, (int, float))) for x in sweeps):
        raise ValueError("shadow_router.analysis_margin_thresholds must be a list of numbers")
    return ShadowRouterConfig(
        enabled=bool(b.get("enabled", False)),
        provisional_margin_threshold=float(margin),
        entropy_threshold=entropy,
        budget_divisor=int(divisor),
        max_targets_override=(int(override) if override is not None else None),
        include_scoring_invalid=bool(b.get("include_scoring_invalid", True)),
        include_parser_failure=bool(b.get("include_parser_failure", True)),
        include_formula_disagreement=bool(b.get("include_formula_disagreement", True)),
        analysis_margin_thresholds=tuple(float(x) for x in sweeps),
    )


def load_shadow_router_config(source=None):
    """Return a validated ShadowRouterConfig (opt-in; disabled by default)."""
    return _validate_shadow(_load_block(source, "shadow_router"))


# --- Phase 3A-1 confidence-routed V12B shadow config (opt-in; observational) ---
# The CLI flag (--confidence-v12b-shadow) is the ONLY execution opt-in; `enabled`
# here is a structural/default-disabled marker, NOT a second activation gate
# (mirrors the Phase 2 shadow_router convention). `min_valid_permutations`,
# `consensus_votes`, and `max_new_tokens` are deliberately NOT exposed in the first
# 3A-1 pass (AUDIT 85 L2 / AUDIT 87 §16/§17): the runner keeps its approved defaults.
@dataclass(frozen=True)
class V12BShadowConfig:
    enabled: bool = False
    observational_only: bool = True
    require_router_selected: bool = True
    permutation_count: int = 6


# Fields that must never be honored in Phase 3A-1 (present => fail closed).
_V12B_FORBIDDEN_FIELDS = (
    "answer_override", "merge", "merge_threshold", "balanced_policy",
    "self_reported_confidence", "v13", "selector",
    "min_valid_permutations", "consensus_votes", "max_new_tokens",
)


def _validate_v12b(block: dict) -> "V12BShadowConfig":
    b = block or {}
    present = tuple(f for f in _V12B_FORBIDDEN_FIELDS if f in b)
    if present:
        raise ValueError(
            f"confidence_v12b forbidden/unexposed fields in first 3A-1 pass: {list(present)}")
    if b.get("observational_only", True) is not True:
        raise ValueError("confidence_v12b.observational_only must be true")
    if b.get("require_router_selected", True) is not True:
        raise ValueError("confidence_v12b.require_router_selected must be true")
    perm = b.get("permutation_count", 6)
    if isinstance(perm, bool) or not isinstance(perm, int) or not (1 <= perm <= 6):
        raise ValueError("confidence_v12b.permutation_count must be an integer in 1..6")
    return V12BShadowConfig(
        enabled=bool(b.get("enabled", False)),
        observational_only=True,
        require_router_selected=True,
        permutation_count=int(perm),
    )


def load_v12b_config(source=None) -> "V12BShadowConfig":
    """Return a validated V12BShadowConfig (opt-in; disabled by default; observational)."""
    return _validate_v12b(_load_block(source, "confidence_v12b"))


# --- Phase 3B full confidence pipeline config (opt-in; answer-CHANGING) --------
# UNLIKE confidence_v12b/shadow_router above, this mode DOES change the official
# answer once activated. The CLI flag (--confidence-full-pipeline) is the ONLY
# execution opt-in; `enabled` here is a structural/default-disabled marker, NOT a
# second activation gate (mirrors the Phase 2/3A-1 convention). It reuses the
# `confidence_v12b` block's `permutation_count` for its internal V12B pass; V13 has
# no exposed tunables in this first pass (fixed runner default max_new_tokens).
@dataclass(frozen=True)
class FullPipelineConfig:
    enabled: bool = False
    require_router_selected: bool = True


# Fields that must never be honored in the first full-pipeline pass.
_FULL_PIPELINE_FORBIDDEN_FIELDS = (
    "answer_override", "merge", "merge_threshold", "balanced_policy",
    "self_reported_confidence", "min_valid_permutations", "consensus_votes",
    "max_new_tokens", "v13_max_new_tokens", "final_threshold", "api_key",
    "openrouter", "ground_truth", "calibration_threshold",
)


def _validate_full_pipeline(block: dict) -> "FullPipelineConfig":
    b = block or {}
    present = tuple(f for f in _FULL_PIPELINE_FORBIDDEN_FIELDS if f in b)
    if present:
        raise ValueError(
            f"confidence_full_pipeline forbidden/unexposed fields in first pass: {list(present)}")
    if b.get("require_router_selected", True) is not True:
        raise ValueError("confidence_full_pipeline.require_router_selected must be true")
    return FullPipelineConfig(
        enabled=bool(b.get("enabled", False)),
        require_router_selected=True,
    )


def load_full_pipeline_config(source=None) -> "FullPipelineConfig":
    """Return a validated FullPipelineConfig (opt-in; disabled by default). This
    pipeline DOES change official answers for router-selected records once
    activated via --confidence-full-pipeline; `enabled` here is a structural
    marker only, not a second activation gate."""
    return _validate_full_pipeline(_load_block(source, "confidence_full_pipeline"))


def _load_block(source, key) -> dict:
    """Shared block loader: dict / path / None -> the ``key`` sub-mapping (or {}).

    A dict ``source`` returns ``source[key]`` if present, else the dict itself
    (so a caller may pass either the whole config or the block directly)."""
    if isinstance(source, dict):
        return source.get(key, source)
    if source is None:
        path = Path(_DEFAULT_CONFIG_PATH)
        if not path.exists():
            return {}
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"confidence config not found: {path}")
    import yaml  # PyYAML is already a project dependency
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"confidence config {path} must be a mapping")
    return data.get(key, {})
