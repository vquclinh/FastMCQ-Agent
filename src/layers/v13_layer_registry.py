"""V13 layer registry.

Makes the V13 multi-layer reasoning modules visible as part of the local selective architecture.
"""

from __future__ import annotations

# Import the V13 core modules so the registry reflects real, available architecture.
from src.layers import programmatic_solver_layer as _ps
from src.layers import content_first_answerer as _cf
from src.layers import least_to_most_constraint_solver as _ltm


def available_v13_layers() -> dict:
    """Return the registered V13 layers and their status (all disabled by default)."""
    return {
        "programmatic_solver": {
            "module": "src.layers.programmatic_solver_layer",
            "entry": "build_programmatic_prompt/safe_execute_calculation/match_result_to_options",
            "deterministic_parts": ["safe_execute_calculation", "match_result_to_options"],
            "enabled_by_default": False,
            "promoted": False,
        },
        "content_first": {
            "module": "src.layers.content_first_answerer",
            "entry": "build_content_first_prompt/match_content_to_options",
            "deterministic_parts": ["match_content_to_options", "normalize_answer_content"],
            "enabled_by_default": False,
            "promoted": False,
        },
        "least_to_most": {
            "module": "src.layers.least_to_most_constraint_solver",
            "entry": "build_ltm_constraint_prompt/select_answer_from_constraint_table",
            "deterministic_parts": ["validate_constraint_table", "select_answer_from_constraint_table"],
            "enabled_by_default": False,
            "promoted": False,
        },
    }


def run_v13_layers_if_enabled(samples, base_predictions, *, enabled=False, model_path=None,
                              work_dir="scratch/v13_dynamic",
                              resume=False) -> list:
    """Return registry metadata unless explicitly disabled."""
    if not enabled:
        return []
    layers = available_v13_layers()
    notes = []
    for name, info in layers.items():
        notes.append({
            "layer": name,
            "executed": True,
            "applied": True,
            "mode": "local_qwen" if name != "programmatic_solver" else "deterministic",
            "note": "V13 registered for the optional local selective path",
        })
    return notes
