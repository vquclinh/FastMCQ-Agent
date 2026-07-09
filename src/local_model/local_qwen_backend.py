"""Shared local Qwen backend for all model-backed inference paths.

The backend owns the tokenizer/model pair and is cached per process so the BTC
single-pass predictor and the optional selective Base/V12B/V13 pipeline reuse one
loaded model instance. Heavy dependencies are imported lazily inside ``load()`` so
tests can inject a fake backend without importing torch/transformers.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.utils.labels import labels_for
from src.utils.logging import log

DEFAULT_MODEL_PATH = "/models/qwen3-4b-instruct-2507"


@runtime_checkable
class LocalQwenBackendProtocol(Protocol):
    model_path: str

    def load(self) -> "LocalQwenBackendProtocol":
        ...

    def generate_text(self, prompt_or_messages: str | list[dict[str, str]], *,
                      max_new_tokens: int | None = None,
                      temperature: float = 0.0) -> str:
        ...

    def predict_mcq(self, item: dict, *, max_new_tokens: int | None = None) -> str | None:
        ...


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


def parse_mcq_label(text: str, labels: list[str]) -> str | None:
    """Pull the first valid option label out of the model's output. Robust to extra text."""
    if not text:
        return None
    allowed = {lab.upper() for lab in labels}
    for m in re.finditer(r"[A-K]", text.upper()):
        if m.group(0) in allowed:
            return m.group(0)
    return None


def parse_json_object(content: str | None) -> dict[str, Any] | None:
    """Best-effort JSON object parser for local structured prompts."""
    if not content:
        return None
    txt = str(content).strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", txt).strip()
    try:
        obj = json.loads(txt)
        return obj if isinstance(obj, dict) else None
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None


class LocalQwenBackend:
    """Lazy, deterministic local generation backend shared across the process."""

    def __init__(self, model_path: str | None = None, *, device: str = "auto",
                 default_max_new_tokens: int = 64):
        self.model_path = str(model_path or os.environ.get("LOCAL_MODEL_PATH") or DEFAULT_MODEL_PATH)
        self.device = device
        self.default_max_new_tokens = int(default_max_new_tokens)
        self._model = None
        self._tokenizer = None
        self.name = Path(self.model_path).name or self.model_path
        self.load_count = 0

    def load(self) -> "LocalQwenBackend":
        """Load tokenizer/model once. Runtime never downloads; path must already exist."""
        if self._model is not None:
            return self
        import torch  # noqa: E402
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        device_map = "auto" if (self.device in (None, "auto") and torch.cuda.is_available()) else None
        log(f"[local_model] loading {self.model_path} (cuda={torch.cuda.is_available()}, dtype={dtype})")
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, trust_remote_code=True, local_files_only=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path, torch_dtype=dtype, device_map=device_map,
            trust_remote_code=True, local_files_only=True)
        if device_map is None and self.device not in (None, "auto"):
            self._model = self._model.to(self.device)
        self._model.eval()
        self.load_count += 1
        return self

    def _render_prompt(self, prompt_or_messages: str | list[dict[str, str]]) -> str:
        if isinstance(prompt_or_messages, str):
            return prompt_or_messages
        try:
            return self._tokenizer.apply_chat_template(
                prompt_or_messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            return "\n\n".join(str(m.get("content") or "") for m in prompt_or_messages)

    def generate_text(self, prompt_or_messages: str | list[dict[str, str]], *,
                      max_new_tokens: int | None = None,
                      temperature: float = 0.0) -> str:
        if self._model is None:
            self.load()
        import torch  # noqa: E402

        text = self._render_prompt(prompt_or_messages)
        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        do_sample = bool(temperature and temperature > 0.0)
        gen_kwargs = {
            **inputs,
            "max_new_tokens": int(max_new_tokens or self.default_max_new_tokens),
            "do_sample": do_sample,
            "num_beams": 1,
            "pad_token_id": self._tokenizer.eos_token_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = float(temperature)
        with torch.no_grad():
            out = self._model.generate(**gen_kwargs)
        gen = out[0][inputs["input_ids"].shape[1]:]
        return self._tokenizer.decode(gen, skip_special_tokens=True)

    def predict_mcq(self, item: dict, *, max_new_tokens: int | None = None) -> str | None:
        prompt, labels = build_mcq_prompt(item)
        messages = [{"role": "user", "content": prompt}]
        return parse_mcq_label(
            self.generate_text(messages, max_new_tokens=max_new_tokens),
            labels,
        )


_BACKENDS: dict[tuple[str, str], LocalQwenBackend] = {}


def get_local_qwen_backend(model_path: str | None = None, *, device: str = "auto",
                           default_max_new_tokens: int = 64) -> LocalQwenBackend:
    resolved = str(model_path or os.environ.get("LOCAL_MODEL_PATH") or DEFAULT_MODEL_PATH)
    key = (resolved, device or "auto")
    backend = _BACKENDS.get(key)
    if backend is None:
        backend = LocalQwenBackend(
            resolved, device=device or "auto", default_max_new_tokens=default_max_new_tokens)
        _BACKENDS[key] = backend
    return backend


def reset_local_qwen_backend_cache() -> None:
    """Test helper: clear the singleton cache without touching loaded model objects."""
    _BACKENDS.clear()
