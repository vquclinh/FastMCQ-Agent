"""AdaptiveAgentSolver — the core budget-aware multi-agent MCQA solver.

Composes the existing components into the pipeline from ``docs/ARCHITECTURE.md``:

    profile -> route -> budget -> (compress context) -> option scoring ->
    confidence -> selective fallback -> final valid label

This is the **Minimal Viable Agent v1** (ARCHITECTURE.md §14): deterministic
profiling/routing/compression + the `hf_option_score` backbone + margin-based
confidence + a simple alternate-mode/generation fallback. Advanced methods
(self-consistency, PAL-lite, debate, ToT-lite) are **gated off**; enabling one
raises ``NotImplementedError`` rather than silently doing nothing.

Heavy deps load lazily via the underlying HF solvers; importing this module does
not require torch/transformers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .confidence import assess_confidence
from .labels import index_to_label, is_valid_label
from .passage_compressor import compress_passage
from .question_profiler import profile_question
from .question_router import route_question
from .solver_base import BaseSolver

_FALLBACK = index_to_label(0)  # "A"


@dataclass
class AdaptiveConfig:
    primary_score_mode: str = "label_plus_choice"
    alternate_score_modes: list = field(default_factory=lambda: ["label_only", "choice_only"])
    enable_generation_fallback: bool = True
    enable_self_consistency: bool = False
    enable_pal_lite: bool = False
    enable_debate: bool = False
    enable_tot_lite: bool = False
    max_fallbacks_per_sample: int = 1
    high_margin: float = 0.30
    medium_margin: float = 0.10
    max_context_chars: int = 3000
    compress_long_context: bool = True
    log_agent_trace: bool = True
    allow_tier2_ambiguous: bool = False


# Advanced methods that are declared but NOT implemented in this phase.
_GATED_FLAGS = {
    "enable_self_consistency": "self-consistency",
    "enable_pal_lite": "PAL-lite",
    "enable_debate": "multi-agent debate",
    "enable_tot_lite": "ToT-lite",
}


class AdaptiveAgentSolver(BaseSolver):
    """Budget-aware adaptive solver over the option-scoring backbone."""

    def __init__(self, model_path: str, *, device: str = "auto",
                 trust_remote_code: bool = False, max_input_tokens: int = 4096,
                 max_new_tokens: int = 8, temperature: float = 0.0,
                 quantization: dict | None = None,
                 config: AdaptiveConfig | None = None, logger=None):
        self.cfg = config or AdaptiveConfig()
        self.logger = logger

        # Fail loudly if a not-yet-implemented advanced method is requested.
        for flag, name in _GATED_FLAGS.items():
            if getattr(self.cfg, flag):
                raise NotImplementedError(
                    f"{name} ({flag}) is configured on but is not implemented in "
                    "Phase 2F/G. Disable it; it is a gated hook for a later phase."
                )

        # Load the scoring backbone once; share its model with the generation
        # fallback so weights are not loaded twice. Sub-solvers do not log —
        # the adaptive solver owns the per-sample trace.
        from .hf_option_score_solver import HFOptionScoreSolver
        self.scorer = HFOptionScoreSolver(
            model_path, device=device, trust_remote_code=trust_remote_code,
            max_input_tokens=max_input_tokens, score_mode=self.cfg.primary_score_mode,
            quantization=quantization, save_raw=False, logger=None,
        )
        self.generate_fallback = None
        if self.cfg.enable_generation_fallback:
            from .hf_generate_solver import HFGenerateSolver
            self.generate_fallback = HFGenerateSolver(
                model_path, max_new_tokens=max_new_tokens, temperature=temperature,
                max_input_tokens=max_input_tokens, save_raw=False, logger=None,
                loaded=self.scorer._loaded,  # share loaded model/tokenizer
            )

    # -- main entry -----------------------------------------------------------
    def predict_one(self, sample: dict) -> str:
        start = time.perf_counter()
        trace = self._new_trace(sample)

        profile = profile_question(sample)
        decision = route_question(profile, allow_tier2_ambiguous=self.cfg.allow_tier2_ambiguous)
        trace.update(
            route=decision.route,
            budget_tier=decision.recommended_budget_tier,
            num_choices=profile.num_choices,
            question_length=profile.question_length,
            duplicate_choice_groups=profile.duplicate_choice_groups,
            profile_features=profile.to_dict(),
        )

        # --- Evidence / context build (long-context compression) -------------
        sample_for_model = sample
        if decision.route == "long_context" and self.cfg.compress_long_context:
            result = compress_passage(
                sample.get("question", ""), sample.get("choices", []),
                max_context_chars=self.cfg.max_context_chars,
            )
            trace["compressed_context_stats"] = result["stats"]
            if result["stats"]["was_compressed"]:
                sample_for_model = {**sample, "question": result["compressed_question"]}
                trace["compressed_context_used"] = True

        # --- Primary strategy: option scoring --------------------------------
        thresholds = {"high_margin": self.cfg.high_margin,
                      "medium_margin": self.cfg.medium_margin}
        primary = self.scorer.score_sample(sample_for_model,
                                           score_mode=self.cfg.primary_score_mode)
        best_label = primary.get("best_label")
        margin = primary.get("margin")
        trace.update(strategy=f"option_score:{self.cfg.primary_score_mode}",
                     score_mode=self.cfg.primary_score_mode,
                     best_label=best_label, second_label=primary.get("second_label"),
                     margin=margin)

        has_valid = best_label is not None and is_valid_label(best_label, sample)
        fallbacks_left = self.cfg.max_fallbacks_per_sample
        conf = assess_confidence(
            margin=margin, has_valid_label=has_valid,
            duplicate_choice_groups=profile.duplicate_choice_groups,
            thresholds=thresholds, allow_fallback=fallbacks_left > 0,
        )
        trace["confidence_level"] = conf.level
        final_label = best_label if has_valid else None

        # --- Selective fallback ----------------------------------------------
        if not (conf.should_accept and has_valid):
            final_label, margin = self._run_fallbacks(
                sample, sample_for_model, profile, conf, thresholds,
                current_label=final_label, current_margin=margin, trace=trace,
            )

        # --- Final safety net: always a valid label --------------------------
        if final_label is None or not is_valid_label(final_label, sample):
            if final_label is not None:
                trace["fallback_reason"] = (trace.get("fallback_reason") or "") + " -> postprocess_A"
            final_label = _FALLBACK

        trace["margin"] = margin
        trace["final_answer"] = final_label
        trace["elapsed_sec"] = round(time.perf_counter() - start, 4)
        self._emit(trace)
        return final_label

    # -- fallback ladder ------------------------------------------------------
    def _run_fallbacks(self, sample, sample_for_model, profile, conf, thresholds,
                       *, current_label, current_margin, trace):
        """Try up to ``max_fallbacks_per_sample`` cheaper-first fallbacks."""
        attempts = [("score", m) for m in self.cfg.alternate_score_modes]
        if self.generate_fallback is not None:
            attempts.append(("generate", None))

        trace["fallback_reason"] = conf.reason
        label, margin = current_label, current_margin

        for kind, mode in attempts[: self.cfg.max_fallbacks_per_sample]:
            trace["fallback_used"] = True
            if kind == "score":
                r = self.scorer.score_sample(sample_for_model, score_mode=mode)
                cand = r.get("best_label")
                cand_valid = cand is not None and is_valid_label(cand, sample)
                trace["strategy"] = f"fallback_option_score:{mode}"
                trace["score_mode"] = mode
                if cand_valid:
                    label, margin = cand, r.get("margin")
                    trace.update(best_label=cand, second_label=r.get("second_label"))
                    c2 = assess_confidence(
                        margin=margin, has_valid_label=True,
                        duplicate_choice_groups=profile.duplicate_choice_groups,
                        thresholds=thresholds, allow_fallback=False,
                    )
                    trace["confidence_level"] = c2.level
                    if c2.should_accept:
                        break
            else:  # generation
                trace["strategy"] = "fallback_generation"
                trace["score_mode"] = None
                try:
                    gen = self.generate_fallback.predict_one(sample_for_model)
                except Exception as exc:  # robustness: never crash a sample
                    trace["fallback_reason"] += f" | generation_error:{type(exc).__name__}"
                    gen = None
                if gen and is_valid_label(gen, sample):
                    label, margin = gen, None
                    break
        return label, margin

    # -- logging --------------------------------------------------------------
    def _new_trace(self, sample: dict) -> dict:
        return {
            "qid": sample.get("qid", ""),
            "solver": "adaptive_agent",
            "route": None,
            "profile_features": None,
            "num_choices": len(sample.get("choices", []) or []),
            "question_length": len(str(sample.get("question", "") or "")),
            "budget_tier": None,
            "strategy": None,
            "score_mode": None,
            "best_label": None,
            "second_label": None,
            "margin": None,
            "confidence_level": None,
            "fallback_used": False,
            "fallback_reason": None,
            "compressed_context_used": False,
            "compressed_context_stats": None,
            "duplicate_choice_groups": [],
            "elapsed_sec": None,
            "final_answer": None,
        }

    def _emit(self, trace: dict) -> None:
        if self.logger is not None and self.cfg.log_agent_trace:
            try:
                self.logger.record_event(trace)
            except Exception:
                pass  # logging must never break inference
