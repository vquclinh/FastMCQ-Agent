#!/usr/bin/env python
"""Compatibility shim (Phase 2L.43D): delegates to scripts/tools/output_quality_report.py.
Re-exports all names so path-loading tests / imports / CLI keep working."""
import importlib.util, sys
from pathlib import Path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
_spec = importlib.util.spec_from_file_location("scripts.tools.output_quality_report",
        Path(__file__).resolve().parent / "tools" / "output_quality_report.py")
_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})
if __name__ == "__main__":
    raise SystemExit(_mod.main())
