"""Local Hugging Face model loading utilities.

Everything heavy (``torch``, ``transformers``) is imported lazily inside
functions, so importing this module never requires those packages — the
non-LLM baseline and the test suite stay dependency-free.

Hard rules:
  * **Never downloads.** ``local_files_only=True`` is always set.
  * ``trust_remote_code`` defaults to ``False`` and must be opted into.
  * Clear, actionable errors for every common failure (missing torch, missing
    transformers, missing/invalid model path).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .utils import log


class HFDependencyError(RuntimeError):
    """Raised when torch/transformers are unavailable or a model path is bad."""


def _require_torch():
    try:
        import torch  # noqa: F401
        return torch
    except ImportError as exc:  # pragma: no cover - depends on env
        raise HFDependencyError(
            "PyTorch is not installed. Install it locally (e.g. `pip install torch`) "
            "to use the hf_* solvers. No download is performed by this tool."
        ) from exc


def _require_transformers():
    try:
        import transformers  # noqa: F401
        return transformers
    except ImportError as exc:  # pragma: no cover - depends on env
        raise HFDependencyError(
            "The `transformers` package is not installed. Install it locally "
            "(e.g. `pip install transformers`) to use the hf_* solvers."
        ) from exc


def validate_model_path(model_path: str | None) -> Path:
    """Validate that ``model_path`` is provided and exists locally."""
    if not model_path:
        raise HFDependencyError(
            "No --model-path / hf.model_path provided. The hf_* solvers require a "
            "path to a LOCAL model directory; nothing is downloaded automatically."
        )
    path = Path(model_path)
    if not path.exists():
        raise HFDependencyError(
            f"model_path does not exist: {path}. Point it at a local model directory."
        )
    return path


@dataclass
class LoadedModel:
    """A loaded tokenizer + model pair plus resolved device/dtype info."""

    tokenizer: object
    model: object
    device: str
    dtype: str


def resolve_device(device: str = "auto") -> str:
    """Resolve the compute device. ``"auto"`` picks CUDA if available, else CPU."""
    torch = _require_torch()
    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


def load_model(model_path: str | None, *, device: str = "auto",
               trust_remote_code: bool = False) -> LoadedModel:
    """Load a local causal-LM tokenizer + model for inference.

    Deterministic-friendly defaults: model in eval mode, no gradient tracking
    expected by callers. Chooses float16/bfloat16 on CUDA, float32 on CPU.
    """
    # Validate the path first (cheap, no heavy imports) so a bad path is reported
    # before we pay the cost of importing torch/transformers.
    path = validate_model_path(model_path)
    torch = _require_torch()
    transformers = _require_transformers()

    resolved_device = resolve_device(device)

    # Prefer bfloat16 on capable CUDA, else float16 on CUDA, else float32 on CPU.
    if resolved_device == "cuda":
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        dtype = torch.float32
    dtype_name = str(dtype).replace("torch.", "")

    log(f"loading model from {path} (device={resolved_device}, dtype={dtype_name}, "
        f"trust_remote_code={trust_remote_code})")

    tokenizer = transformers.AutoTokenizer.from_pretrained(
        str(path), local_files_only=True, trust_remote_code=trust_remote_code
    )
    model = transformers.AutoModelForCausalLM.from_pretrained(
        str(path),
        local_files_only=True,
        trust_remote_code=trust_remote_code,
        torch_dtype=dtype,
    )

    # Ensure a pad token exists so batching / scoring never crashes.
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is not None:
            tokenizer.pad_token = tokenizer.eos_token
            log("pad_token was missing; set pad_token = eos_token")
        else:  # last-resort: add a dedicated pad token
            tokenizer.add_special_tokens({"pad_token": "<|pad|>"})
            model.resize_token_embeddings(len(tokenizer))
            log("pad_token and eos_token missing; added a <|pad|> token")

    model.to(resolved_device)
    model.eval()
    return LoadedModel(tokenizer=tokenizer, model=model,
                       device=resolved_device, dtype=dtype_name)
