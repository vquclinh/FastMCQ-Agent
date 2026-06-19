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

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from .utils import log

QUANTIZATION_MODES = ("4bit", "8bit")


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


def bitsandbytes_available() -> bool:
    """True if the optional ``bitsandbytes`` package is importable (no import)."""
    try:
        return importlib.util.find_spec("bitsandbytes") is not None
    except (ImportError, ValueError):  # pragma: no cover - env dependent
        return False


def _resolve_compute_dtype(name, torch, resolved_device):
    """Map a compute-dtype name to a torch dtype (None => sensible default)."""
    if name:
        mapping = {"float16": torch.float16, "bfloat16": torch.bfloat16,
                   "float32": torch.float32}
        if name not in mapping:
            raise HFDependencyError(
                f"unknown quantization.compute_dtype {name!r}; "
                "choose float16 | bfloat16 | float32"
            )
        return mapping[name]
    # Default: match the non-quantized choice (bf16 on capable CUDA, else fp16).
    if resolved_device == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


def _build_quantization_config(quantization, torch, transformers, resolved_device):
    """Return a ``BitsAndBytesConfig`` (or ``None`` for no quantization).

    Raises clearly for an invalid mode, missing bitsandbytes, or non-CUDA device.
    Never silently falls back to fp16 when quantization is explicitly requested.
    """
    if not quantization:
        return None
    mode = quantization.get("mode")
    if not mode:
        return None  # mode null => unquantized (current behavior preserved)
    if mode not in QUANTIZATION_MODES:
        raise HFDependencyError(
            f"unknown quantization mode {mode!r}; choose one of "
            f"{', '.join(QUANTIZATION_MODES)} (or null for fp16/fp32)."
        )
    if resolved_device != "cuda":
        raise HFDependencyError(
            f"quantization mode {mode!r} requires a CUDA GPU, but device resolved "
            f"to {resolved_device!r}. Use a CUDA device or set quantization.mode=null."
        )
    if not bitsandbytes_available():
        raise HFDependencyError(
            f"quantization mode {mode!r} requires the optional `bitsandbytes` "
            "package, which is not installed. Install it (see requirements-llm.txt: "
            "`pip install bitsandbytes`) or set quantization.mode=null. "
            "It is intentionally not required for the baseline or tests."
        )

    if mode == "8bit":
        return transformers.BitsAndBytesConfig(load_in_8bit=True)

    # 4bit
    compute_dtype = _resolve_compute_dtype(
        quantization.get("compute_dtype"), torch, resolved_device)
    return transformers.BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=quantization.get("quant_type", "nf4"),
        bnb_4bit_use_double_quant=bool(quantization.get("double_quant", True)),
        bnb_4bit_compute_dtype=compute_dtype,
    )


def load_model(model_path: str | None, *, device: str = "auto",
               trust_remote_code: bool = False, quantization: dict | None = None) -> LoadedModel:
    """Load a local causal-LM tokenizer + model for inference.

    Deterministic-friendly defaults: model in eval mode, no gradient tracking
    expected by callers. Chooses float16/bfloat16 on CUDA, float32 on CPU.

    ``quantization`` (optional dict ``{mode, compute_dtype, double_quant,
    quant_type}``) enables 4-bit/8-bit loading via bitsandbytes. When ``mode`` is
    falsy the original fp16/fp32 path is used **unchanged** and bitsandbytes is
    never imported.
    """
    # Validate the path first (cheap, no heavy imports) so a bad path is reported
    # before we pay the cost of importing torch/transformers.
    path = validate_model_path(model_path)
    torch = _require_torch()
    transformers = _require_transformers()

    resolved_device = resolve_device(device)
    quant_config = _build_quantization_config(
        quantization, torch, transformers, resolved_device)

    tokenizer = transformers.AutoTokenizer.from_pretrained(
        str(path), local_files_only=True, trust_remote_code=trust_remote_code
    )

    if quant_config is not None:
        # Quantized models must be placed on the GPU at load time via device_map;
        # they cannot be moved with .to() afterwards.
        mode = quantization["mode"]
        log(f"loading model from {path} (device={resolved_device}, "
            f"quantization={mode}, trust_remote_code={trust_remote_code})")
        model = transformers.AutoModelForCausalLM.from_pretrained(
            str(path),
            local_files_only=True,
            trust_remote_code=trust_remote_code,
            quantization_config=quant_config,
            device_map="auto",
        )
        dtype_name = f"{mode}-bnb"
    else:
        # Prefer bfloat16 on capable CUDA, else float16 on CUDA, else float32 CPU.
        if resolved_device == "cuda":
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        else:
            dtype = torch.float32
        dtype_name = str(dtype).replace("torch.", "")
        log(f"loading model from {path} (device={resolved_device}, dtype={dtype_name}, "
            f"trust_remote_code={trust_remote_code})")
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

    # Quantized models are already placed via device_map; do not move them.
    if quant_config is None:
        model.to(resolved_device)
    model.eval()
    return LoadedModel(tokenizer=tokenizer, model=model,
                       device=resolved_device, dtype=dtype_name)
