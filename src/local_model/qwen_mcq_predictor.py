"""Local Qwen MCQ predictor (Phase 2L.47B) — offline, single open-weight model.

Loads ONE local Hugging Face Transformers model (default Qwen3-4B-Instruct-2507, 4.0B < 5B,
Apache-2.0) once, then answers each MCQ deterministically with an answer-only prompt and robust
label parsing. No internet, no external API. `torch`/`transformers` are imported lazily inside
``load()`` so this module can be imported (and unit-tested with a stub) without those heavy deps.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.utils.labels import labels_for
from src.utils.logging import log

DEFAULT_MODEL_PATH = "/models/qwen3-4b-instruct-2507"


def build_mcq_prompt(item: dict) -> tuple[str, list[str]]:
    """Return (prompt, labels). Answer-only instruction, labeled choices (Vietnamese)."""
    question = str(item.get("question") or item.get("text") or item.get("prompt") or "").strip()
    choices = list(item.get("choices") or [])
    labels = labels_for(len(choices)) if choices else list("ABCD")
    lines = [
        "Bạn là trợ lý trắc nghiệm. Đọc câu hỏi và các lựa chọn, rồi chỉ trả lời bằng ĐÚNG MỘT "
        "chữ cái nhãn của đáp án đúng (ví dụ: A). Không giải thích, không thêm chữ nào khác.",
        "",
        f"Câu hỏi: {question}",
    ]
    for lab, ch in zip(labels, choices):
        lines.append(f"{lab}. {ch}")
    lines.append("")
    lines.append("Đáp án (chỉ một chữ cái):")
    return "\n".join(lines), labels


def parse_label(text: str, labels: list[str]) -> str | None:
    """Pull the first valid option label out of the model's output. Robust to extra text."""
    if not text:
        return None
    allowed = {lab.upper() for lab in labels}
    # 1) An isolated label letter (e.g. "B", "Đáp án: B", "(C)").
    for m in re.finditer(r"[A-K]", text.upper()):
        if m.group(0) in allowed:
            return m.group(0)
    return None


class QwenMCQPredictor:
    """Deterministic single-model MCQ predictor. Call ``load()`` once, then ``predict_one``."""

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH, *, device: str = "auto",
                 max_new_tokens: int = 64):
        self.model_path = str(model_path)
        self.device = device
        self.max_new_tokens = int(max_new_tokens)
        self._model = None
        self._tokenizer = None
        self.name = Path(self.model_path).name or self.model_path

    def load(self) -> "QwenMCQPredictor":
        """Load the tokenizer + model once (lazy heavy imports; GPU when available)."""
        if self._model is not None:
            return self
        import torch  # noqa: E402  (lazy: only needed for real inference)
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        device_map = "auto" if (self.device in (None, "auto") and torch.cuda.is_available()) else None
        log(f"[local_model] loading {self.model_path} (cuda={torch.cuda.is_available()}, dtype={dtype})")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path, torch_dtype=dtype, device_map=device_map, trust_remote_code=True)
        if device_map is None and self.device not in (None, "auto"):
            self._model = self._model.to(self.device)
        self._model.eval()
        return self

    def predict_one(self, item: dict) -> str | None:
        """Return a single option label for ``item``; None if it could not be parsed."""
        if self._model is None:
            self.load()
        import torch  # noqa: E402

        prompt, labels = build_mcq_prompt(item)
        messages = [{"role": "user", "content": prompt}]
        try:
            text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            text = prompt  # tokenizer without a chat template
        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
                num_beams=1, pad_token_id=self._tokenizer.eos_token_id)
        gen = out[0][inputs["input_ids"].shape[1]:]
        decoded = self._tokenizer.decode(gen, skip_special_tokens=True)
        return parse_label(decoded, labels)
