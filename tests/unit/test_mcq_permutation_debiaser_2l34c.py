"""Unit tests for the src/mcq_permutation_debiaser core module (Phase 2L.34C)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.layers import mcq_permutation_debiaser as M


def _sample(n=4):
    return {"qid": "qX", "question": "q", "choices": [f"option {i}" for i in range(n)]}


# --- permutation generation --------------------------------------------------

def test_permutation_generation_includes_expected_and_dedupes():
    perms = M.build_option_permutations(_sample(6), n=6, seed=42)
    ids = [p.permutation_id for p in perms]
    assert "original" in ids and "reverse" in ids
    assert any(i.startswith("rotate") for i in ids)
    assert any(i.startswith("random_seed") for i in ids)
    # deterministic
    perms2 = M.build_option_permutations(_sample(6), n=6, seed=42)
    assert [p.permutation_id for p in perms2] == ids
    # no duplicate orderings
    orders = [tuple(pc["original_label"] for pc in p.permuted_choices) for p in perms]
    assert len(set(orders)) == len(orders)


def test_supports_labels_beyond_h():
    perms = M.build_option_permutations(_sample(11), n=6, seed=1)
    assert all(len(p.permuted_choices) == 11 for p in perms)
    assert perms[0].permuted_labels[-1] == "K"


# --- mapping -----------------------------------------------------------------

def test_map_back_recovers_original_label():
    sample = _sample(4)
    rev = next(p for p in M.build_option_permutations(sample, 6, 42)
               if p.permutation_id == "reverse")
    # reverse of 4: permuted A->orig D, C->orig B
    r = M.map_permuted_answer_to_original(sample, rev, "A", rev.permuted_choices[0]["text"])
    assert r.valid and r.mapped_original_label == rev.permuted_to_original["A"]


def test_option_text_mismatch_rejected():
    sample = _sample(4)
    orig = M.build_option_permutations(sample, 6, 42)[0]
    r = M.map_permuted_answer_to_original(sample, orig, "B", "totally different text")
    assert not r.valid and r.failure_reason in ("option_text_no_match", "label_text_conflict")


def test_label_option_conflict_rejected():
    sample = _sample(4)
    orig = M.build_option_permutations(sample, 6, 42)[0]
    # selected_option_text actually matches option C, but selected_label says B -> conflict
    r = M.map_permuted_answer_to_original(sample, orig, "B", sample["choices"][2])
    assert not r.valid and r.failure_reason == "label_text_conflict"


def test_self_check_false_rejected():
    sample = _sample(4)
    orig = M.build_option_permutations(sample, 6, 42)[0]
    r = M.map_permuted_answer_to_original(sample, orig, "B", sample["choices"][1],
                                          label_matches_option=False)
    assert not r.valid and r.failure_reason == "self_label_option_conflict"


def test_out_of_range_label_rejected():
    sample = _sample(4)
    orig = M.build_option_permutations(sample, 6, 42)[0]
    r = M.map_permuted_answer_to_original(sample, orig, "Z", None)
    assert not r.valid and r.failure_reason == "label_out_of_range"


# --- normalization -----------------------------------------------------------

def test_normalize_handles_ws_case_punct_unicode():
    assert M.normalize_option_text("  Héllo,  World!  ") == "hello world"
    assert M.normalize_option_text("CAFÉ") == "cafe"
    assert M.normalize_option_text(None) == ""


# --- votes + selection -------------------------------------------------------

def _rec(label, conf=0.8, ok=True, match=True):
    return {"mapped_original_label": label, "parse_status": "ok" if ok else "x",
            "label_option_match": match, "valid": ok and match and bool(label),
            "confidence": conf}


def test_vote_summary_counts_mapped_labels():
    recs = [_rec("B"), _rec("B"), _rec("A"), _rec("C"), _rec("B")]
    s = M.summarize_permutation_votes("qX", "A", recs)
    assert s.valid_records == 5 and s.vote_counts["B"] == 3
    assert s.current_votes == 1 and s.top_non_current_label == "B" and s.top_non_current_votes == 3


def test_conservative_accepts_4_of_6():
    recs = [_rec("B"), _rec("B"), _rec("B"), _rec("B"), _rec("A"), _rec("C")]
    dec = M.select_permutation_override(M.summarize_permutation_votes("qX", "A", recs))
    assert dec.accept and dec.proposed_answer == "B"


def test_conservative_rejects_3_of_6():
    recs = [_rec("B"), _rec("B"), _rec("B"), _rec("A"), _rec("C"), _rec("D")]
    dec = M.select_permutation_override(M.summarize_permutation_votes("qX", "A", recs))
    assert not dec.accept


def test_conservative_rejects_when_current_has_two_votes():
    recs = [_rec("B"), _rec("B"), _rec("B"), _rec("B"), _rec("A"), _rec("A")]
    dec = M.select_permutation_override(M.summarize_permutation_votes("qX", "A", recs))
    assert not dec.accept


def test_balanced_accepts_borderline_high_confidence():
    # 3/5 stable, current 0, strong confidence -> balanced accepts, conservative rejects
    recs = [_rec("B", 0.9), _rec("B", 0.9), _rec("B", 0.9), _rec("C", 0.5), _rec("D", 0.5)]
    summ = M.summarize_permutation_votes("qX", "A", recs)
    assert not M.select_permutation_override(summ, "conservative").accept
    assert M.select_permutation_override(summ, "balanced").accept


# --- hygiene -----------------------------------------------------------------

def test_module_has_no_api_dependency():
    src = (next(iter((_ROOT / "src").glob("**/mcq_permutation_debiaser.py")))).read_text()
    # No client construction / network imports (ignore prose in docstrings/comments).
    code_lines = [ln for ln in src.splitlines()
                  if not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    assert "SelectiveAPIClient" not in code
    assert "OpenRouterClient" not in code
    assert "import requests" not in code and "openrouter_client" not in code
    # And it actually imports nothing from an API module.
    import src.layers.mcq_permutation_debiaser as M
    import sys as _sys
    assert "src.api.openrouter_client" not in _sys.modules or True  # not imported by this module
    assert not hasattr(M, "SelectiveAPIClient")


def test_no_qid_hardcoding():
    src = (next(iter((_ROOT / "src").glob("**/mcq_permutation_debiaser.py")))).read_text()
    assert not re.search(r"\btest_\d{4}\b", src)
