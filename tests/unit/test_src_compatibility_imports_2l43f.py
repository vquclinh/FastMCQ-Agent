"""Phase 2L.43F/2L.43G — src/ subpackage structure.

2L.43F moved real modules into subpackages; 2L.43G removed the flat compatibility shims.
This test now verifies the CLEAN structure: new subpackage imports work, the official
full-system import works, src.utils logging still works, and NO flat shim modules remain at
the src/ root (only approved root files).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Representative new subpackage paths (must all import).
_NEW_PATHS = [
    "src.system.fastmcq_system",
    "src.base.dynamic_base_predictor",
    "src.layers.v12b_dynamic_layer",
    "src.layers.v13_dynamic_layer",
    "src.layers.mcq_permutation_debiaser",
    "src.local_model.local_qwen_backend",
    "src.local_model.qwen_mcq_predictor",
    "src.local_model.candidate_agents",
    "src.selector.system_candidate_selector",
    "src.solvers.calculation_solver",
    "src.solvers.pot_lite",
    "src.evidence.evidence_reranker",
    "src.utils.data_io",
    "src.utils.labels",
]

# Files allowed to remain directly under src/ (everything else there would be shim clutter).
_ALLOWED_ROOT_FILES = {"__init__.py", "README.md"}


def test_new_subpackage_imports_work():
    for path in _NEW_PATHS:
        assert importlib.import_module(path) is not None, path


def test_official_full_system_import_works():
    from src.system.fastmcq_system import run_fastmcq_system, FastMCQSystemConfig  # noqa: F401
    assert callable(run_fastmcq_system)


def test_utils_logging_import_still_works():
    from src.utils import log, load_config            # package re-export
    from src.utils.logging import log as log2          # explicit path
    assert log is log2 and callable(load_config)


def test_no_flat_shim_files_remain_at_src_root():
    # Only approved root files may live directly under src/; all modules live in subpackages.
    stray = sorted(p.name for p in (_ROOT / "src").glob("*.py")
                   if p.name not in _ALLOWED_ROOT_FILES)
    assert stray == [], f"unexpected flat files at src/ root: {stray}"


def test_kept_subpackages_still_importable():
    # tool_solvers/ and formula_cards/ were intentionally not moved.
    from src.tool_solvers import cs_solver   # noqa: F401
    from src.formula_cards import CARDS       # noqa: F401
    assert CARDS is not None


def test_subpackages_present():
    for sub in ("system", "base", "layers", "local_model", "selector", "solvers", "evidence", "utils"):
        assert (_ROOT / "src" / sub / "__init__.py").exists(), sub
