"""Unit tests for the Phase 2 confidence-aware SHADOW router (observational only).

Deterministic, pure — no model, no torch, no ground truth. The router only records
which qids WOULD be selected; it never changes an answer or runs V12B/V13.
"""

from __future__ import annotations

import json
import math

import pytest

from src.local_model.confidence_shadow_router import (
    ShadowRouterConfig,
    ShadowRoutingInput,
    run_shadow_router,
    REASON_LOW_MARGIN,
    REASON_SCORING_INVALID,
    REASON_PARSER_FAILURE,
    REASON_HIGH_ENTROPY,
    REASON_FORMULA_DISAGREEMENT,
)
from src.local_model.confidence_config import load_shadow_router_config


def _cfg(**kw):
    base = dict(enabled=True, provisional_margin_threshold=10.0, budget_divisor=8,
                analysis_margin_thresholds=(5.0, 7.5, 10.0, 12.5, 15.0, 20.0))
    base.update(kw)
    return ShadowRouterConfig(**base)


def _inp(qid, idx, margin=None, valid=True, entropy=None, parser=None,
         formula=None, error=None):
    return ShadowRoutingInput(qid=qid, input_index=idx, generated_answer="A",
                              scoring_valid=valid, scoring_error=error, top1="A", top2="B",
                              logit_margin=margin, probability_margin=None,
                              normalized_entropy=entropy, scoring_method="next_token_logits_one_forward",
                              parser_failure=parser, formula_disagreement=formula)


# --- 21-item synthetic replay (margins from AUDIT 71; correctness only in comments) ---
def _synthetic_21():
    # margin, entropy (only low-margin items carry the AUDIT-71 entropy)
    named = [
        ("syn_020_sequence", 0.0, 0.50002295),   # wrong (comment only; never a runtime input)
        ("syn_008_speed", 4.25, 0.05333236),     # wrong
        ("syn_001_addition_3", 7.75, 0.00455163),# wrong
        ("syn_007_bat_ball", 9.0, 0.0),          # correct
        ("syn_021_pills", 12.0, 0.0),            # correct
        ("syn_004_fraction_4", 12.25, 0.0),      # correct
        ("syn_003_algebra_4", 13.75, 0.0),       # wrong
        ("syn_017_vn_spelling", 18.5, 0.0),      # wrong
    ]
    highs = [21.0, 22.0, 22.5, 23.0, 23.25, 23.5, 23.625, 23.75, 23.875, 24.0, 25.0, 27.0, 27.5]
    recs, i = [], 0
    for qid, m, e in named:
        recs.append(_inp(qid, i, margin=m, entropy=e)); i += 1
    for j, m in enumerate(highs):
        recs.append(_inp(f"syn_hi_{j:02d}", i, margin=m, entropy=0.0)); i += 1
    assert len(recs) == 21
    return recs


def test_synthetic_replay_selects_three_lowest_margins():
    recs = _synthetic_21()
    decisions, summary = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    assert summary.budget_cap == 3   # ceil(21/8)
    assert summary.selected_qids == ["syn_020_sequence", "syn_008_speed", "syn_001_addition_3"]
    # the margin-9.0 item is a candidate under threshold 10.0 but NOT selected (cap = 3)
    d7 = next(d for d in decisions if d.qid == "syn_007_bat_ball")
    assert d7.candidate is True and d7.selected is False and d7.selected_rank is None


def test_lower_threshold_selects_only_two():
    recs = _synthetic_21()
    _, summary = run_shadow_router(recs, _cfg(provisional_margin_threshold=7.5))
    assert summary.selected_qids == ["syn_020_sequence", "syn_008_speed"]


def test_all_margins_above_threshold_selects_zero():
    recs = _synthetic_21()
    _, summary = run_shadow_router(recs, _cfg(provisional_margin_threshold=-1.0))
    assert summary.candidate_count == 0 and summary.selected_count == 0


def test_never_backfills_with_non_candidates():
    recs = [_inp(f"q{i}", i, margin=99.0) for i in range(30)]   # none uncertain
    _, summary = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    assert summary.budget_cap == 4 and summary.selected_count == 0


# --- policy details ---------------------------------------------------------
def test_margin_threshold_inclusive():
    recs = [_inp("a", 0, margin=10.0), _inp("b", 1, margin=10.0001)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_qids == ["a"]                 # 10.0 <= 10.0 candidate; 10.0001 not


def test_lower_margin_ranks_first():
    recs = [_inp("hi", 0, margin=8.0), _inp("lo", 1, margin=2.0), _inp("mid", 2, margin=5.0)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_qids == ["lo", "mid", "hi"]


def test_scoring_invalid_ranks_high_when_enabled():
    recs = [_inp("num", 0, margin=1.0), _inp("inv", 1, valid=False, error="x")]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1,
                                        include_scoring_invalid=True))
    assert s.selected_qids == ["inv", "num"]        # explicit failure ranks above numerical
    inv = next(x for x in d if x.qid == "inv")
    assert REASON_SCORING_INVALID in inv.candidate_reasons and inv.risk_tier == 0


def test_scoring_invalid_not_selected_when_disabled():
    recs = [_inp("inv", 0, valid=False, error="x")]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0,
                                        include_scoring_invalid=False))
    assert s.candidate_count == 0
    assert d[0].candidate is False


def test_entropy_threshold_null_is_ignored():
    recs = [_inp("hi_ent", 0, margin=99.0, entropy=0.99)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, entropy_threshold=None))
    assert s.candidate_count == 0                   # entropy ignored when threshold is None


def test_entropy_threshold_when_configured():
    recs = [_inp("hi_ent", 0, margin=99.0, entropy=0.9)]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, entropy_threshold=0.5,
                                        budget_divisor=1))
    assert s.selected_qids == ["hi_ent"] and REASON_HIGH_ENTROPY in d[0].candidate_reasons


def test_parser_failure_used_only_when_provided():
    recs = [_inp("pf", 0, margin=99.0, parser=True), _inp("nf", 1, margin=99.0, parser=None)]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_qids == ["pf"]
    nf = next(x for x in d if x.qid == "nf")
    assert nf.candidate is False and REASON_PARSER_FAILURE not in nf.candidate_reasons


def test_formula_disagreement_used_only_when_provided():
    recs = [_inp("fd", 0, margin=99.0, formula=True), _inp("plain", 1, margin=99.0, formula=None)]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_qids == ["fd"]
    assert REASON_FORMULA_DISAGREEMENT in next(x for x in d if x.qid == "fd").candidate_reasons


def test_missing_optional_metadata_is_not_a_reason():
    recs = [_inp("q", 0, margin=99.0, parser=None, formula=None)]
    d, _ = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    assert d[0].candidate is False and d[0].candidate_reasons == []


@pytest.mark.parametrize("n,cap", [(1, 1), (7, 1), (8, 1), (9, 2), (21, 3), (30, 4)])
def test_budget_cap_formula(n, cap):
    recs = [_inp(f"q{i}", i, margin=0.0) for i in range(n)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=8))
    assert s.budget_cap == cap


def test_candidate_count_below_budget_still_limits_selection():
    """With divisor=20, budget_cap(30)=2, but only one record actually qualifies as a
    candidate -> selected_count must be 1, never backfilled to reach the cap."""
    recs = [_inp(f"q{i}", i, margin=99.0) for i in range(30)]   # none low-margin
    recs[5] = _inp("q5", 5, margin=0.0)                          # exactly one candidate
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=20))
    assert s.budget_cap == 2 and s.candidate_count == 1 and s.selected_count == 1


def test_max_targets_override():
    recs = [_inp(f"q{i}", i, margin=0.0) for i in range(30)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, max_targets_override=2))
    assert s.budget_cap == 2 and s.selected_count == 2


def test_deterministic_tie_break_by_input_order():
    recs = [_inp("b", 1, margin=5.0), _inp("a", 0, margin=5.0), _inp("c", 2, margin=5.0)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_qids == ["a", "b", "c"]       # equal margin -> input_index order


def test_decisions_in_stable_input_order():
    recs = [_inp("x", 0, margin=99.0), _inp("y", 1, margin=1.0), _inp("z", 2, margin=99.0)]
    d, _ = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    assert [x.qid for x in d] == ["x", "y", "z"]


def test_threshold_sweep_does_not_change_primary_decisions():
    recs = _synthetic_21()
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    assert s.selected_qids == ["syn_020_sequence", "syn_008_speed", "syn_001_addition_3"]
    sweep_at_10 = next(sw for sw in s.threshold_sweeps if sw["margin_threshold"] == 10.0)
    assert sweep_at_10["selected_qids"] == s.selected_qids   # sweep is consistent, not overriding
    # a lower sweep threshold selects fewer, but primary selection is unchanged
    sweep_at_5 = next(sw for sw in s.threshold_sweeps if sw["margin_threshold"] == 5.0)
    assert sweep_at_5["selected_qids"] == ["syn_020_sequence", "syn_008_speed"]
    assert s.selected_qids == ["syn_020_sequence", "syn_008_speed", "syn_001_addition_3"]


def test_probability_margin_is_not_the_ranking_signal():
    # 'a' has a WORSE (smaller) probability margin but a HIGHER logit margin than 'b';
    # ranking must follow the raw logit margin, not the probability margin.
    a = ShadowRoutingInput(qid="a", input_index=0, scoring_valid=True, logit_margin=9.0,
                           probability_margin=0.01)
    b = ShadowRoutingInput(qid="b", input_index=1, scoring_valid=True, logit_margin=1.0,
                           probability_margin=0.99)
    _, s = run_shadow_router([a, b], _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_qids == ["b", "a"]            # b has lower logit margin -> higher risk


def test_router_consumes_no_ground_truth_field():
    # Even if an 'expected'/'correct' key is smuggled onto the object, the router ignores it.
    inp = _inp("q", 0, margin=1.0)
    inp.expected_answer = "Z"; inp.correct = False   # noqa: attribute injection
    d, _ = run_shadow_router([inp], _cfg(provisional_margin_threshold=10.0))
    dd = d[0].as_dict()
    assert "expected_answer" not in dd and "correct" not in dd


# --- output safety ----------------------------------------------------------
def test_decision_and_summary_json_safe_no_text():
    recs = _synthetic_21()
    d, s = run_shadow_router(recs, _cfg())
    for dec in d:
        blob = json.dumps(dec.as_dict(), allow_nan=False)   # raises on NaN/Inf
        assert "question" not in dec.as_dict() and "choices" not in dec.as_dict()
        assert "prompt" not in dec.as_dict()
    json.dumps(s.as_dict(), allow_nan=False)


def test_nonfinite_margin_does_not_reach_json():
    recs = [ShadowRoutingInput(qid="q", input_index=0, scoring_valid=True,
                               logit_margin=float("inf"))]
    d, _ = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    # inf margin is not <= 10 so not a candidate; and as_dict scrubs non-finite to None
    assert d[0].as_dict()["logit_margin"] is None
    json.dumps(d[0].as_dict(), allow_nan=False)


# --- config loader ----------------------------------------------------------
def test_shadow_config_defaults_disabled():
    cfg = load_shadow_router_config({"shadow_router": {}})
    assert cfg.enabled is False and cfg.provisional_margin_threshold == 10.0 and cfg.budget_divisor == 20


def test_shadow_config_from_repo_yaml():
    cfg = load_shadow_router_config("configs/confidence_selective.yaml")
    assert cfg.enabled is False and cfg.entropy_threshold is None
    assert cfg.analysis_margin_thresholds == (5.0, 7.5, 10.0, 12.5, 15.0, 20.0)
    assert cfg.budget_divisor == 20   # effective runtime config; no hidden divisor=8 default remains


@pytest.mark.parametrize("n,cap", [(1, 1), (19, 1), (20, 1), (21, 2), (30, 2), (120, 6), (2000, 100)])
def test_budget_cap_formula_divisor_20(n, cap):
    """Direct proof of the divisor-20 budget formula, including the hard requirement
    that 2000 input records yield a maximum router budget of exactly 100 (not 250,
    which would be ceil(2000/8) under the old divisor). N=30 -> ceil(30/20)=2, which
    exceeds floor(30/20)=1 -- permitted because ceil(N/divisor) is the repository's
    existing, thoroughly-documented small-input minimum-selection behavior (AUDIT
    71/72/74/87/89/92-95): it guarantees at least 1 selected record whenever N>=1,
    without a separate max(1, ...) rule bolted on top. See AUDIT 96 for the full
    floor-vs-ceil rationale."""
    recs = [_inp(f"q{i}", i, margin=0.0) for i in range(n)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=20))
    assert s.budget_cap == cap
    assert s.selected_count <= s.budget_cap        # selected count never exceeds the budget
    assert s.selected_count <= s.candidate_count    # candidate count remains an upper bound too


def test_budget_cap_uses_default_divisor_when_unspecified():
    """The default ShadowRouterConfig() (no explicit budget_divisor) must use 20, not
    a hidden production default of 8, proving no authoritative location silently
    reverts to the old value."""
    recs = [_inp(f"q{i}", i, margin=0.0) for i in range(2000)]
    _, s = run_shadow_router(recs, ShadowRouterConfig(enabled=True, provisional_margin_threshold=10.0))
    assert s.budget_cap == 100


def test_2000_records_yield_exactly_100_not_250():
    """The task's explicit hard requirement, isolated as its own test: 2000 input
    records must yield a maximum router budget of exactly 100. 250 would be
    ceil(2000/8), proving the old divisor is not silently still in effect anywhere."""
    recs = [_inp(f"q{i}", i, margin=0.0) for i in range(2000)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=20))
    assert s.budget_cap == 100
    assert s.budget_cap != 250


@pytest.mark.parametrize("bad", [
    {"shadow_router": {"budget_divisor": 0}},
    {"shadow_router": {"max_targets_override": -1}},
    {"shadow_router": {"provisional_margin_threshold": "x"}},
    {"shadow_router": {"entropy_threshold": "x"}},
    {"shadow_router": {"analysis_margin_thresholds": [1, "a"]}},
])
def test_shadow_config_validation_errors(bad):
    with pytest.raises(ValueError):
        load_shadow_router_config(bad)


# --- duplicate-qid regression (AUDIT 73 F1/F2; fixed via per-record ordinal) ---
def test_duplicate_qid_keeps_each_records_own_reasons():
    recs = [
        _inp("dup", 0, margin=1.0),                     # low-margin candidate
        _inp("dup", 1, valid=False, error="x"),         # scoring-invalid candidate
        _inp("dup", 2, margin=99.0),                    # non-candidate
    ]
    d, _ = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    by_idx = {x.input_index: x for x in d}
    assert by_idx[0].candidate_reasons == [REASON_LOW_MARGIN]
    assert by_idx[1].candidate_reasons == [REASON_SCORING_INVALID]
    assert by_idx[2].candidate_reasons == [] and by_idx[2].candidate is False


def test_duplicate_qid_both_selected_get_distinct_ranks():
    recs = [_inp("dup", 0, margin=5.0), _inp("dup", 1, margin=1.0)]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    by_idx = {x.input_index: x for x in d}
    # lower margin (idx 1) ranks first; both selected with distinct ranks; no overwrite
    assert by_idx[1].selected_rank == 1 and by_idx[0].selected_rank == 2
    assert sorted(x.selected_rank for x in d if x.selected) == [1, 2]
    assert s.selected_count == 2                        # counts records, not unique qids
    assert s.selected_qids == ["dup", "dup"]            # risk-rank order, duplicates allowed
    assert s.selected_items == [
        {"qid": "dup", "input_index": 1, "selected_rank": 1},
        {"qid": "dup", "input_index": 0, "selected_rank": 2},
    ]


def test_duplicate_qid_one_selected_one_not():
    recs = [_inp("dup", 0, margin=1.0), _inp("dup", 1, margin=99.0), _inp("z", 2, margin=2.0)]
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, max_targets_override=1))
    by_idx = {x.input_index: x for x in d}
    assert by_idx[0].selected is True and by_idx[0].selected_rank == 1
    assert by_idx[1].selected is False and by_idx[1].selected_rank is None   # not overwritten
    assert by_idx[2].selected is False                 # cap 1


def test_duplicate_qid_summary_traceable():
    recs = [_inp("q", 0, margin=1.0), _inp("q", 1, margin=2.0), _inp("q", 2, margin=99.0)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_count == 2
    # each selected record uniquely identified by input_index despite identical qids
    assert [it["input_index"] for it in s.selected_items] == [0, 1]
    assert [it["selected_rank"] for it in s.selected_items] == [1, 2]


def test_duplicate_qid_in_threshold_sweeps_uses_input_indexes():
    recs = [_inp("q", 0, margin=1.0), _inp("q", 1, margin=6.0), _inp("q", 2, margin=99.0)]
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1,
                                        analysis_margin_thresholds=(5.0, 10.0)))
    sweep5 = next(sw for sw in s.threshold_sweeps if sw["margin_threshold"] == 5.0)
    sweep10 = next(sw for sw in s.threshold_sweeps if sw["margin_threshold"] == 10.0)
    # threshold 5 -> only idx0 (margin 1); threshold 10 -> idx0, idx1 (margins 1,6)
    assert sweep5["selected_input_indexes"] == [0]
    assert sweep10["selected_input_indexes"] == [0, 1]
    assert sweep10["selected_qids"] == ["q", "q"]       # duplicate qids preserved, traceable by index


def test_duplicate_input_index_and_qid_still_deterministic():
    recs = [_inp("q", 0, margin=1.0), _inp("q", 0, margin=5.0)]   # both qid AND input_index collide
    d, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=1))
    assert s.selected_count == 2 and sorted(x.selected_rank for x in d) == [1, 2]
    # the private ordinal keeps records distinct even with identical qid+index
    assert [it["selected_rank"] for it in s.selected_items] == [1, 2]


def test_duplicate_qid_repeated_run_determinism():
    import json
    recs = [_inp("dup", 0, margin=1.0), _inp("dup", 1, valid=False, error="x"),
            _inp("dup", 2, margin=99.0), _inp("z", 3, margin=2.0)]
    d1, s1 = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=2))
    d2, s2 = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0, budget_divisor=2))
    assert [x.as_dict() for x in d1] == [x.as_dict() for x in d2]
    assert json.dumps(s1.as_dict()) == json.dumps(s2.as_dict())


def test_synthetic_replay_unchanged_after_fix():
    recs = _synthetic_21()
    _, s = run_shadow_router(recs, _cfg(provisional_margin_threshold=10.0))
    assert s.budget_cap == 3
    assert s.selected_qids == ["syn_020_sequence", "syn_008_speed", "syn_001_addition_3"]
    assert [it["qid"] for it in s.selected_items] == s.selected_qids
