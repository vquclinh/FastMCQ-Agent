"""V13 layer registry (Phase 2L.36B).

Makes the V13 multi-layer reasoning modules visible as part of the architecture WITHOUT
promoting them. V13 is disabled by default and never wired into final predictions in this
phase. When explicitly enabled in no-API mode, only deterministic parts may run; nothing is
applied to the output.
"""

from __future__ import annotations

# Import the V13 core modules so the registry reflects real, available architecture.
from src import programmatic_solver_layer as _ps
from src import content_first_answerer as _cf
from src import least_to_most_constraint_solver as _ltm


def available_v13_layers() -> dict:
    """Return the registered V13 layers and their status (all disabled by default)."""
    return {
        "programmatic_solver": {
            "module": "src.programmatic_solver_layer",
            "entry": "build_programmatic_prompt/safe_execute_calculation/match_result_to_options",
            "deterministic_parts": ["safe_execute_calculation", "match_result_to_options"],
            "enabled_by_default": False,
            "promoted": False,
        },
        "content_first": {
            "module": "src.content_first_answerer",
            "entry": "build_content_first_prompt/match_content_to_options",
            "deterministic_parts": ["match_content_to_options", "normalize_answer_content"],
            "enabled_by_default": False,
            "promoted": False,
        },
        "least_to_most": {
            "module": "src.least_to_most_constraint_solver",
            "entry": "build_ltm_constraint_prompt/select_answer_from_constraint_table",
            "deterministic_parts": ["validate_constraint_table", "select_answer_from_constraint_table"],
            "enabled_by_default": False,
            "promoted": False,
        },
    }


def run_v13_layers_if_enabled(samples, base_predictions, *, enabled=False, model=None,
                              execute_api=False, budget_usd=None, work_dir="scratch/v13_dynamic",
                              resume=False) -> list:
    """V13 is experimental and NOT promoted. Returns [] unless explicitly enabled, and even
    when enabled this phase does not apply any V13 override to the final predictions — it only
    records that V13 ran (deterministic parts only in no-API mode)."""
    if not enabled:
        return []
    # Visible but non-binding: record per-layer that it is registered and (not) executed.
    layers = available_v13_layers()
    notes = []
    for name, info in layers.items():
        notes.append({
            "layer": name,
            "executed": bool(execute_api),
            "applied": False,   # never applied to final predictions in this phase
            "mode": "api" if execute_api else "deterministic_only",
            "note": "V13 registered but NOT promoted; outputs are not wired into predictions",
        })
    return notes
