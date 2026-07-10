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
from src.local_model.choice_scoring import ChoiceScoreResult, compute_choice_scores

DEFAULT_MODEL_PATH = "/models/qwen3-4b-instruct-2507"


def _encode_ids(tokenizer, text: str) -> list[int]:
    """Tokenize ``text`` to a plain list of token ids (tokenizer-agnostic)."""
    if hasattr(tokenizer, "encode"):
        ids = tokenizer.encode(text)
    else:
        ids = tokenizer(text)["input_ids"]
    return list(ids)


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


# --- Answer-label parsing -------------------------------------------------
# Conservative, deterministic MCQ label extraction. It NEVER scans arbitrary
# prose for the first A–K letter (that turned "The answer is clearly option B."
# into "A" and "Grace Hopper" into "G"). Precedence: structured JSON answer
# field > exact bare label > explicit answer marker > a single isolated final
# label. Ambiguous or answer-free text returns None so the caller applies its
# own deterministic fallback (the parser never silently picks "A").

# A whole-output bare label, optionally wrapped: "B", "b", "B.", "(B)", "[B]".
# Brace wrapping is intentionally excluded so "{...}" is treated as JSON, not a label.
_BARE_LABEL_RE = re.compile(r"^\s*[\(\[]?\s*([A-Za-z])\s*[\)\]\.:,]?\s*$")

# Explicit answer markers (Vietnamese + English), longest/most specific first so
# the alternation prefers them. A separator (space/colon/dot/dash/open bracket)
# must sit between the marker and the label, so "optionB" or "answer cannot"
# never yield a label; the label must not be embedded in a larger word.
_MARKER_LABEL_RE = re.compile(
    r"(?:the\s+answer\s+is(?:\s+clearly)?(?:\s+option)?"
    r"|final\s+answer"
    r"|đáp\s*án(?:\s+đúng)?(?:\s+là)?"
    r"|lựa\s*chọn(?:\s+đúng)?(?:\s+là)?"
    r"|tôi\s+chọn"
    r"|chọn\s+đáp\s+án"
    r"|chọn"
    r"|answer"
    r"|choice"
    r"|option)"
    r"[\s:.\-]+[\(\[]?\s*"        # required separator, optional open bracket
    r"([A-Za-z])(?![A-Za-z])",   # the label, not inside a larger word
    re.IGNORECASE)

# A single letter standing alone as a token (not inside a word).
_ISOLATED_LABEL_RE = re.compile(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])")

# "... B or C" / "... B/C" style ambiguity immediately after a marker label.
_OR_AFTER_RE = re.compile(r"^\s*(?:or|hoặc|/|,)\s*[A-Za-z](?![A-Za-z])", re.IGNORECASE)

_ANSWER_KEYS = ("answer", "label", "choice")


def _allowed_labels(labels) -> set[str]:
    return {str(lab).strip().upper() for lab in (labels or []) if str(lab).strip()}


def _bare_label(text, allowed) -> str | None:
    if not text:
        return None
    m = _BARE_LABEL_RE.match(str(text))
    if not m:
        return None
    lab = m.group(1).upper()
    return lab if lab in allowed else None


def _marker_label(text, allowed) -> str | None:
    """Return the label of the LAST explicit answer marker (a final answer
    overrides earlier exploratory mentions); None if none is unambiguous."""
    if not text:
        return None
    found = None
    for m in _MARKER_LABEL_RE.finditer(str(text)):
        lab = m.group(1).upper()
        if lab not in allowed:
            continue
        if _OR_AFTER_RE.match(str(text)[m.end():]):   # "answer: B or C" -> ambiguous
            continue
        found = lab
    return found


def _isolated_final_label(text, allowed) -> str | None:
    """Accept a single isolated label only when exactly one distinct allowed
    label appears as a standalone token AND it is the final meaningful token."""
    if not text:
        return None
    hits = [g.upper() for g in _ISOLATED_LABEL_RE.findall(str(text)) if g.upper() in allowed]
    distinct = set(hits)
    if len(distinct) != 1:
        return None
    lab = next(iter(distinct))
    tokens = str(text).split()
    if not tokens:
        return None
    last = tokens[-1].strip("()[]{}.,:;\"'").upper()
    return lab if last == lab else None


def _json_label(text, allowed) -> str | None:
    """Resolve an explicit answer/label/choice field of a JSON object to one
    allowed label. Reuses the shared parse_json_object; rejects prose values."""
    obj = parse_json_object(text)
    if not isinstance(obj, dict):
        return None
    lowered = {str(k).lower(): v for k, v in obj.items()}
    for key in _ANSWER_KEYS:
        if key in lowered:
            val = lowered[key]
            if isinstance(val, str):
                lab = _bare_label(val, allowed) or _marker_label(val, allowed)
                if lab:
                    return lab
    return None


def parse_mcq_label(text: str, labels: list[str]) -> str | None:
    """Extract exactly one allowed option label from model output, or None.

    Conservative precedence (never a blind first-letter scan, never a silent 'A'):
      1. a structured JSON answer/label/choice field;
      2. an exact bare label (optionally wrapped: 'B', 'b', '(B)', 'B.');
      3. an explicit answer marker + label (Vietnamese/English; last marker wins);
      4. a single isolated final label, only when unambiguous.
    Ambiguous or answer-free text returns None so the caller applies its own
    deterministic fallback.
    """
    if not text:
        return None
    allowed = _allowed_labels(labels)
    if not allowed:
        return None
    s = str(text).strip()

    # 1) structured JSON answer field.
    lab = _json_label(s, allowed)
    if lab:
        return lab
    # A whole-output JSON object with no safe answer field must not be prose-scanned.
    if s.startswith("{") or s.startswith("```"):
        return None

    # 2) exact bare label.
    lab = _bare_label(s, allowed)
    if lab:
        return lab

    # 3) explicit answer marker.
    lab = _marker_label(s, allowed)
    if lab:
        return lab

    # 4) single isolated final label (conservative).
    return _isolated_final_label(s, allowed)


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

    # --- Per-choice uncertainty scoring (Phase 1: observational shadow only) ---
    SCORING_METHOD = "next_token_logits_one_forward"

    def _generation_prefix(self, item: dict) -> str:
        """The EXACT rendered generation prefix (chat template + add_generation_prompt).

        Shared by generation and scoring so they can never diverge: ``generate_text``
        renders the same messages the same way, and greedy generation samples its first
        answer token from the next-token position after this prefix."""
        prompt, _labels = build_mcq_prompt(item)
        return self._render_prompt([{"role": "user", "content": prompt}])

    # Back-compat alias (older name); same exact prefix.
    _scoring_prompt = _generation_prefix

    def _bare_label_token_id(self, tokenizer, label: str) -> int | None:
        """Token id of the BARE label (e.g. "B"), or None if it is not exactly one
        token. Special tokens are excluded so no BOS is prepended."""
        try:
            ids = list(tokenizer.encode(label, add_special_tokens=False))
        except TypeError:                                  # fake/older tokenizers without the kwarg
            ids = list(tokenizer.encode(label))
        return int(ids[0]) if len(ids) == 1 else None

    def _default_next_token_logits_fn(self, prompt_ids, token_ids) -> list[float]:
        """Raw next-token logits for ``token_ids`` from ONE model forward over
        ``prompt_ids`` (torch imported lazily). Reads the same next-token position
        greedy generation samples its first token from."""
        import torch  # noqa: E402
        if self._model is None:
            self.load()
        ids = torch.tensor([list(prompt_ids)], device=self._model.device)
        with torch.no_grad():
            logits = self._model(ids).logits            # [1, seq, vocab]
        row = logits[0, -1].float()                     # next-token position
        return [float(row[int(t)]) for t in token_ids]

    def score_mcq_choices(self, item: dict, *, logits_fn=None) -> ChoiceScoreResult:
        """Per-choice uncertainty from ONE model forward over the exact generation
        prefix: read the raw next-token logits of the BARE single-token labels
        (A, B, ...), softmax over only those labels, and report top-1/top-2 with the
        raw-logit margin, probability margin, and normalized entropy.

        Observational only — it changes no answer, route, or official output, and it
        fails closed to an explicit invalid result (never fabricates a label). It scores
        bare labels (matching the token greedy generation emits), NOT a space-prefixed
        continuation, and performs exactly one forward per item regardless of #labels."""
        method = self.SCORING_METHOD
        choices = list(item.get("choices") or [])
        labels = labels_for(len(choices)) if choices else []
        if not labels:
            return compute_choice_scores({}, labels, scoring_method=method, error="no_choices")
        if len(labels) < 2:
            return compute_choice_scores({}, labels, scoring_method=method,
                                         error="need_at_least_two_labels")
        try:
            if self._tokenizer is None:
                self.load()
            tok = self._tokenizer
            prompt_ids = _encode_ids(tok, self._generation_prefix(item))
            if not prompt_ids:
                return compute_choice_scores({}, labels, scoring_method=method, error="empty_prompt")
            token_by_label: dict[str, int] = {}
            for lab in labels:
                tid = self._bare_label_token_id(tok, lab)
                if tid is None:
                    return compute_choice_scores({}, labels, scoring_method=method,
                                                 error=f"label_not_single_token:{lab}")
                token_by_label[lab] = tid
            if len(set(token_by_label.values())) != len(token_by_label):
                return compute_choice_scores({}, labels, scoring_method=method,
                                             error="duplicate_label_token_ids")
            fn = logits_fn or self._default_next_token_logits_fn
            token_ids = [token_by_label[lab] for lab in labels]
            logit_vals = fn(prompt_ids, token_ids)        # exactly ONE forward per item
            if logit_vals is None or len(logit_vals) != len(labels):
                return compute_choice_scores({}, labels, scoring_method=method,
                                             error="logits_shape_invalid")
            scores = {lab: float(v) for lab, v in zip(labels, logit_vals)}
            return compute_choice_scores(scores, labels, scoring_method=method)
        except Exception as exc:                          # fail closed — telemetry must never crash a run
            return compute_choice_scores({}, labels, scoring_method=method,
                                         error=f"{type(exc).__name__}: {exc}")


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
