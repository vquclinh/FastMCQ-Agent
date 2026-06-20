"""Solver registry / factory.

Maps a solver name to a constructed :class:`~src.solver_base.BaseSolver`.

Supported names:
  * ``always_a``        — :class:`AlwaysASolver` (Phase 1 baseline, no deps).
  * ``hf_generate``     — :class:`HFGenerateSolver` (local HF generation).
  * ``hf_option_score`` — :class:`HFOptionScoreSolver` (local HF option scoring).
  * ``adaptive_agent``  — :class:`AdaptiveAgentSolver` (budget-aware multi-agent).
  * ``openrouter_graph``— :class:`OpenRouterGraphSolver` (Round-1 OpenRouter API).

The ``hf_*`` / ``adaptive_agent`` / ``openrouter_graph`` solvers are imported
lazily so that ``always_a`` never pulls in torch/transformers/httpx. Unknown
names, missing ``model_path`` (hf_*), and missing ``OPENROUTER_API_KEY``
(openrouter_graph) raise clear errors.
"""

from __future__ import annotations

from .baseline_solver import AlwaysASolver
from .solver_base import BaseSolver

SOLVER_NAMES = ("always_a", "hf_generate", "hf_option_score", "adaptive_agent",
                "openrouter_graph")


def build_solver(name: str, *, model_path: str | None = None,
                 device: str = "auto", trust_remote_code: bool = False,
                 max_new_tokens: int = 8, temperature: float = 0.0,
                 max_input_tokens: int = 4096, score_mode: str = "label_plus_choice",
                 adaptive_config: dict | None = None, quantization: dict | None = None,
                 openrouter_config: dict | None = None,
                 save_raw: bool = False, logger=None) -> BaseSolver:
    """Construct a solver by name. See module docstring for supported names."""
    if name == "always_a":
        return AlwaysASolver()

    if name not in SOLVER_NAMES:
        raise ValueError(
            f"unknown solver {name!r}; choose one of {', '.join(SOLVER_NAMES)}"
        )

    # OpenRouter graph solver (Round 1): needs an API key, NOT a local model path.
    if name == "openrouter_graph":
        from .openrouter_client import api_key_available
        from .openrouter_graph_solver import OpenRouterConfig, OpenRouterGraphSolver
        if not api_key_available():
            raise ValueError(
                "solver 'openrouter_graph' requires OPENROUTER_API_KEY (env or a "
                "git-ignored .env). The key is never logged or committed; only "
                "OpenRouter is contacted."
            )
        cfg_kwargs = {k: v for k, v in (openrouter_config or {}).items()
                      if k in OpenRouterConfig.__dataclass_fields__}
        return OpenRouterGraphSolver(config=OpenRouterConfig(**cfg_kwargs), logger=logger)

    # From here on we know it is an hf_* solver and need a model path.
    if not model_path:
        raise ValueError(
            f"solver {name!r} requires --model-path (or hf.model_path in config); "
            "it runs a LOCAL model and never downloads anything."
        )

    if name == "hf_generate":
        from .hf_generate_solver import HFGenerateSolver
        return HFGenerateSolver(
            model_path, device=device, trust_remote_code=trust_remote_code,
            max_new_tokens=max_new_tokens, temperature=temperature,
            max_input_tokens=max_input_tokens, quantization=quantization,
            save_raw=save_raw, logger=logger,
        )

    if name == "adaptive_agent":
        from .adaptive_agent_solver import AdaptiveAgentSolver, AdaptiveConfig
        # Build the config from known keys only (ignore unrelated config noise).
        cfg_kwargs = {k: v for k, v in (adaptive_config or {}).items()
                      if k in AdaptiveConfig.__dataclass_fields__}
        return AdaptiveAgentSolver(
            model_path, device=device, trust_remote_code=trust_remote_code,
            max_input_tokens=max_input_tokens, max_new_tokens=max_new_tokens,
            temperature=temperature, quantization=quantization,
            config=AdaptiveConfig(**cfg_kwargs), logger=logger,
        )

    # hf_option_score: reuse the loaded model for a generation fallback so we do
    # not load weights twice.
    from .hf_generate_solver import HFGenerateSolver
    from .hf_option_score_solver import HFOptionScoreSolver
    scorer = HFOptionScoreSolver(
        model_path, device=device, trust_remote_code=trust_remote_code,
        max_input_tokens=max_input_tokens, score_mode=score_mode,
        quantization=quantization, save_raw=save_raw, logger=logger,
    )
    scorer.generate_fallback = HFGenerateSolver(
        model_path, max_new_tokens=max_new_tokens, temperature=temperature,
        max_input_tokens=max_input_tokens, save_raw=save_raw, logger=logger,
        loaded=scorer._loaded,  # share the already-loaded model/tokenizer
    )
    return scorer
