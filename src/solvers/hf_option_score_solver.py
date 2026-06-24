"""Option-scoring MCQ solver.

Instead of trusting free-form generation, this solver scores every candidate
answer as a *continuation* of the prompt and picks the most likely one. This is
usually more stable than generation for multiple choice, and it naturally
handles any number of choices (2, 3, 4, 10, 11, ...).

Scoring method
--------------
The prompt ends with ``"Đáp án đúng là:"``. For each label we build a
continuation and compute the model's **average log-probability per continuation
token** (length-normalised, so longer options are not unfairly penalised). The
label with the highest average log-probability wins.

The continuation depends on ``score_mode``:
  * ``label_only``        -> ``" A"``                 (bare label token)
  * ``label_plus_choice`` -> ``" A. <choice text>"``  (default; most robust)
  * ``choice_only``       -> ``" <choice text>"``     (label-free)

``label_plus_choice`` is the default: bare-label scoring (``label_only``) is
brittle because tokenizers split " A" / "A" / "A." inconsistently and a lone
letter carries little signal, while ``choice_only`` ignores the label binding.
Which mode wins on the leaderboard is an empirical question — hence all three
are selectable (see docs/RESEARCH_STRATEGY.md).

Robustness: all tensor work is under ``torch.no_grad()``. If scoring raises for
any reason, we fall back to a generation solver (if one was provided) and then
to ``"A"``.
"""

from __future__ import annotations

import time

from src.solvers.hf_common import load_model
from src.utils.labels import index_to_label, labels_for
from src.utils.prompting import build_mcq_prompt, detect_question_shape
from src.base.solver_base import BaseSolver

_FALLBACK = index_to_label(0)  # "A"

SCORE_MODES = ("label_only", "label_plus_choice", "choice_only")
DEFAULT_SCORE_MODE = "label_plus_choice"


def _continuation(mode: str, label: str, choice: str) -> str:
    """Build the scored continuation string for a given score mode."""
    choice = str(choice).strip()
    if mode == "label_only":
        return f" {label}"
    if mode == "choice_only":
        return f" {choice}"
    # default: label_plus_choice
    return f" {label}. {choice}"


class HFOptionScoreSolver(BaseSolver):
    """Predict by scoring each candidate answer continuation."""

    def __init__(self, model_path: str, *, device: str = "auto",
                 trust_remote_code: bool = False, max_input_tokens: int = 4096,
                 score_mode: str = DEFAULT_SCORE_MODE, quantization: dict | None = None,
                 save_raw: bool = False, logger=None, loaded=None, generate_fallback=None):
        if score_mode not in SCORE_MODES:
            raise ValueError(
                f"unknown score_mode {score_mode!r}; choose one of {', '.join(SCORE_MODES)}"
            )
        self.max_input_tokens = max_input_tokens
        self.score_mode = score_mode
        self.save_raw = save_raw
        self.logger = logger
        self.generate_fallback = generate_fallback
        self._loaded = loaded or load_model(
            model_path, device=device, trust_remote_code=trust_remote_code,
            quantization=quantization,
        )

    @property
    def tokenizer(self):
        return self._loaded.tokenizer

    @property
    def model(self):
        return self._loaded.model

    def predict_one(self, sample: dict) -> str:
        start = time.perf_counter()
        choices = sample.get("choices", []) or []
        labels = labels_for(len(choices))
        shape = detect_question_shape(sample)

        if not labels:  # nothing to score
            self._log(sample, _FALLBACK, shape, 0, start, None, "no_choices")
            return _FALLBACK

        prompt = build_mcq_prompt(
            sample, mode="score", tokenizer=self.tokenizer,
            max_input_tokens=self.max_input_tokens,
        )

        try:
            scores = self._score_options(prompt, labels, choices, self.score_mode)
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            best_idx = ranked[0]
            label = labels[best_idx]
            detail = self._score_detail(labels, scores, ranked, self.score_mode)
            self._log(sample, label, shape, len(choices), start, detail, None)
            return label
        except Exception as exc:
            reason = f"scoring_error: {type(exc).__name__}: {exc}"
            # Fall back to generation if we were given a generate solver, else A.
            if self.generate_fallback is not None:
                try:
                    label = self.generate_fallback.predict_one(sample)
                    self._log(sample, label, shape, len(choices), start, None,
                              reason + " -> generate_fallback")
                    return label
                except Exception:
                    pass
            self._log(sample, _FALLBACK, shape, len(choices), start, None, reason)
            return _FALLBACK

    def _score_options(self, prompt: str, labels: list[str],
                       choices: list[str], score_mode: str | None = None) -> list[float]:
        """Return the average continuation log-prob for each label."""
        import torch

        mode = score_mode or self.score_mode
        # Encode the prompt once (with special tokens), reuse for every option.
        prompt_ids = self.tokenizer(prompt, return_tensors="pt")["input_ids"][0]
        prompt_len = prompt_ids.shape[0]
        device = self._loaded.device

        scores: list[float] = []
        with torch.no_grad():
            for label, choice in zip(labels, choices):
                continuation = _continuation(mode, label, choice)
                cont_ids = self.tokenizer.encode(continuation, add_special_tokens=False)
                if not cont_ids:
                    scores.append(float("-inf"))
                    continue
                cont_tensor = torch.tensor(cont_ids, dtype=prompt_ids.dtype)
                full_ids = torch.cat([prompt_ids, cont_tensor]).unsqueeze(0).to(device)

                logits = self.model(full_ids).logits  # [1, seq, vocab]
                # logits at position i predict token i+1; continuation tokens sit
                # at [prompt_len, full_len), so we read predictions from positions
                # [prompt_len-1, full_len-1).
                log_probs = torch.log_softmax(logits[0], dim=-1)
                total = 0.0
                for j, token_id in enumerate(cont_ids):
                    pos = prompt_len - 1 + j
                    total += log_probs[pos, token_id].item()
                scores.append(total / len(cont_ids))  # length-normalised
        return scores

    def _score_detail(self, labels, scores, ranked, score_mode: str | None = None) -> dict:
        """Structured scoring metadata for the debug log."""
        best_label = labels[ranked[0]]
        second_label = labels[ranked[1]] if len(ranked) > 1 else None
        best_score = scores[ranked[0]]
        second_score = scores[ranked[1]] if len(ranked) > 1 else None
        margin = (round(best_score - second_score, 4)
                  if second_score is not None else None)
        return {
            "score_mode": score_mode or self.score_mode,
            "labels": labels,
            "scores": {labels[i]: round(scores[i], 4) for i in range(len(labels))},
            "best_label": best_label,
            "second_label": second_label,
            "margin": margin,
        }

    def score_sample(self, sample: dict, score_mode: str | None = None) -> dict:
        """Score a sample and return rich metadata WITHOUT logging.

        Used by :class:`~src.adaptive_agent_solver.AdaptiveAgentSolver` so it can
        read scores/margin and choose its own fallback. ``predict_one`` is
        unaffected. On any error returns ``{"error": ...}`` with ``label=None``.

        To score a compressed long-context question, pass a ``sample`` whose
        ``question`` field is already compressed — prompt building reads it.
        """
        mode = score_mode or self.score_mode
        choices = sample.get("choices", []) or []
        labels = labels_for(len(choices))
        if not labels:
            return {"label": _FALLBACK, "labels": [], "scores": {},
                    "best_label": _FALLBACK, "second_label": None, "margin": None,
                    "score_mode": mode, "error": "no_choices"}
        prompt = build_mcq_prompt(
            sample, mode="score", tokenizer=self.tokenizer,
            max_input_tokens=self.max_input_tokens,
        )
        try:
            scores = self._score_options(prompt, labels, choices, mode)
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            detail = self._score_detail(labels, scores, ranked, mode)
            return {"label": labels[ranked[0]], "error": None, **detail}
        except Exception as exc:
            return {"label": None, "labels": labels, "scores": {},
                    "best_label": None, "second_label": None, "margin": None,
                    "score_mode": mode, "error": f"{type(exc).__name__}: {exc}"}

    def _log(self, sample, label, shape, num_choices, start, detail, reason):
        if self.logger is not None:
            self.logger.record(
                qid=sample.get("qid", ""), answer=label, solver="hf_option_score",
                shape=shape, num_choices=num_choices,
                elapsed_s=time.perf_counter() - start,
                option_scores=detail if self.save_raw else None,
                fallback_reason=reason,
            )
