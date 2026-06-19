"""Generation-based MCQ solver.

Builds a Vietnamese prompt, generates a short deterministic continuation, and
parses a single answer label out of it. Falls back to ``"A"`` if parsing fails.

Heavy deps are loaded lazily via :mod:`src.hf_common`, so importing this module
does not require torch/transformers.
"""

from __future__ import annotations

import time

from .hf_common import load_model
from .labels import index_to_label, labels_for
from .output_parser import parse_answer_label
from .prompting import build_mcq_prompt, detect_question_shape
from .solver_base import BaseSolver

_FALLBACK = index_to_label(0)  # "A"


class HFGenerateSolver(BaseSolver):
    """Predict by generating a short answer and parsing its label."""

    def __init__(self, model_path: str, *, device: str = "auto",
                 trust_remote_code: bool = False, max_new_tokens: int = 8,
                 temperature: float = 0.0, max_input_tokens: int = 4096,
                 quantization: dict | None = None,
                 save_raw: bool = False, logger=None, loaded=None):
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.max_input_tokens = max_input_tokens
        self.save_raw = save_raw
        self.logger = logger
        # Allow a pre-loaded model to be injected (e.g. reused as a fallback).
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
        label, _raw, _reason = self._predict_with_meta(sample)
        return label

    def _predict_with_meta(self, sample: dict):
        """Return (label, raw_text, fallback_reason|None) and log if enabled."""
        import torch

        start = time.perf_counter()
        choices = sample.get("choices", []) or []
        valid_labels = labels_for(len(choices))
        shape = detect_question_shape(sample)
        prompt = build_mcq_prompt(
            sample, mode="direct", tokenizer=self.tokenizer,
            max_input_tokens=self.max_input_tokens,
        )

        raw_text = ""
        fallback_reason = None
        try:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self._loaded.device)
            gen_kwargs = {
                "max_new_tokens": self.max_new_tokens,
                "do_sample": False,  # deterministic by default
                "pad_token_id": self.tokenizer.pad_token_id,
            }
            # Only pass temperature when actually sampling, to avoid warnings.
            if self.temperature and self.temperature > 0:
                gen_kwargs.update(do_sample=True, temperature=self.temperature)

            with torch.no_grad():
                output_ids = self.model.generate(**inputs, **gen_kwargs)
            # Decode only the newly generated tokens, not the prompt.
            new_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            raw_text = self.tokenizer.decode(new_ids, skip_special_tokens=True)

            label = parse_answer_label(raw_text, valid_labels)
            if label is None:
                label = _FALLBACK
                fallback_reason = "unparseable_output"
        except Exception as exc:  # robustness: never let one sample kill the run
            label = _FALLBACK
            fallback_reason = f"generation_error: {type(exc).__name__}: {exc}"

        if self.logger is not None:
            self.logger.record(
                qid=sample.get("qid", ""), answer=label, solver="hf_generate",
                shape=shape, num_choices=len(choices),
                elapsed_s=time.perf_counter() - start,
                raw_output=raw_text if self.save_raw else None,
                fallback_reason=fallback_reason,
            )
        return label, raw_text, fallback_reason
