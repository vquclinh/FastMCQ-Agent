"""Option-scoring MCQ solver.

Instead of trusting free-form generation, this solver scores every candidate
answer as a *continuation* of the prompt and picks the most likely one. This is
usually more stable than generation for multiple choice, and it naturally
handles any number of choices (2, 3, 4, 10, 11, ...).

Scoring method
--------------
The prompt ends with ``"Đáp án đúng là:"``. For each label we build a
continuation ``" A. <choice text>"`` and compute the model's **average
log-probability per continuation token** (length-normalised, so options with
longer text are not unfairly penalised). The label with the highest average
log-probability wins.

Why score the full ``" A. <text>"`` continuation rather than just the bare
label token? Single-label-token scoring is brittle: tokenizers split " A",
"A", "A." inconsistently, and a lone letter carries little signal. Scoring the
label *plus its answer text* is robust across tokenizers and is the method we
use here.

Robustness: all tensor work is under ``torch.no_grad()``. If scoring raises for
any reason, we fall back to a generation solver (if one was provided) and then
to ``"A"``.
"""

from __future__ import annotations

import time

from .hf_common import load_model
from .labels import index_to_label, labels_for
from .prompting import build_mcq_prompt, detect_question_shape
from .solver_base import BaseSolver

_FALLBACK = index_to_label(0)  # "A"


class HFOptionScoreSolver(BaseSolver):
    """Predict by scoring each candidate answer continuation."""

    def __init__(self, model_path: str, *, device: str = "auto",
                 trust_remote_code: bool = False, max_input_tokens: int = 4096,
                 save_raw: bool = False, logger=None, loaded=None,
                 generate_fallback=None):
        self.max_input_tokens = max_input_tokens
        self.save_raw = save_raw
        self.logger = logger
        self.generate_fallback = generate_fallback
        self._loaded = loaded or load_model(
            model_path, device=device, trust_remote_code=trust_remote_code
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
            scores = self._score_options(prompt, labels, choices)
            best_idx = max(range(len(scores)), key=lambda i: scores[i])
            label = labels[best_idx]
            score_map = {labels[i]: round(scores[i], 4) for i in range(len(labels))}
            self._log(sample, label, shape, len(choices), start, score_map, None)
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
                       choices: list[str]) -> list[float]:
        """Return the average continuation log-prob for each label."""
        import torch

        # Encode the prompt once (with special tokens), reuse for every option.
        prompt_ids = self.tokenizer(prompt, return_tensors="pt")["input_ids"][0]
        prompt_len = prompt_ids.shape[0]
        device = self._loaded.device

        scores: list[float] = []
        with torch.no_grad():
            for label, choice in zip(labels, choices):
                continuation = f" {label}. {str(choice).strip()}"
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

    def _log(self, sample, label, shape, num_choices, start, score_map, reason):
        if self.logger is not None:
            self.logger.record(
                qid=sample.get("qid", ""), answer=label, solver="hf_option_score",
                shape=shape, num_choices=num_choices,
                elapsed_s=time.perf_counter() - start,
                option_scores=score_map if self.save_raw else None,
                fallback_reason=reason,
            )
