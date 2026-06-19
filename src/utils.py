"""Small shared helpers: logging and config loading.

Kept intentionally tiny — no framework, just a couple of functions the rest of
the project reuses.
"""

from __future__ import annotations

import sys
from pathlib import Path


def log(message: str) -> None:
    """Print a timestamp-free, prefixed log line to stderr.

    We use stderr so that anything writing CSV/JSON to stdout stays clean.
    """
    print(f"[fastmcq] {message}", file=sys.stderr, flush=True)


def load_config(path: str | Path) -> dict:
    """Load a YAML config file, returning an empty dict if it does not exist.

    PyYAML is an optional convenience; if it is unavailable we fall back to an
    empty config rather than crashing, since Phase 1 does not depend on it.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import yaml  # imported lazily so the core run does not require it
    except ImportError:
        log(f"PyYAML not installed; ignoring config at {path}")
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}
