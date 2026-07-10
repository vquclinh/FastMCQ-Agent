"""Unit: Phase 3A-1 confidence_v12b config validation (opt-in, observational).

Proves defaults, structural invariants, the 1..6 permutation bound, and fail-closed
rejection of forbidden/unexposed fields. No torch/GPU/network.
"""

from __future__ import annotations

import pytest

from src.local_model.confidence_config import (
    V12BShadowConfig,
    load_v12b_config,
)


def test_defaults_disabled_marker():
    cfg = load_v12b_config({})
    assert isinstance(cfg, V12BShadowConfig)
    assert cfg.enabled is False                 # structural marker, default disabled
    assert cfg.observational_only is True
    assert cfg.require_router_selected is True
    assert cfg.permutation_count == 6


def test_absent_block_uses_safe_defaults():
    # a whole-config dict without the block => empty block => defaults
    cfg = load_v12b_config({"choice_scoring": {"enabled": True}})
    assert cfg.enabled is False and cfg.permutation_count == 6


def test_enabled_marker_parsed_but_is_not_execution_gate():
    cfg = load_v12b_config({"enabled": True, "permutation_count": 3})
    assert cfg.enabled is True and cfg.permutation_count == 3


@pytest.mark.parametrize("perm", [0, 7, -1, 2.5, True, "6"])
def test_permutation_count_out_of_range_fails_closed(perm):
    with pytest.raises(ValueError):
        load_v12b_config({"permutation_count": perm})


@pytest.mark.parametrize("perm", [1, 2, 3, 4, 5, 6])
def test_permutation_count_in_range_ok(perm):
    assert load_v12b_config({"permutation_count": perm}).permutation_count == perm


def test_observational_only_must_be_true():
    with pytest.raises(ValueError):
        load_v12b_config({"observational_only": False})


def test_require_router_selected_must_be_true():
    with pytest.raises(ValueError):
        load_v12b_config({"require_router_selected": False})


@pytest.mark.parametrize("field", [
    "answer_override", "merge", "merge_threshold", "balanced_policy",
    "self_reported_confidence", "v13", "selector",
    "min_valid_permutations", "consensus_votes", "max_new_tokens",
])
def test_forbidden_or_unexposed_fields_reject(field):
    with pytest.raises(ValueError):
        load_v12b_config({field: 1})


def test_unknown_field_is_tolerated_forward_compat():
    # an unknown, non-forbidden key must not disable the block (loader is tolerant)
    cfg = load_v12b_config({"some_future_marker": "x"})
    assert cfg.permutation_count == 6
