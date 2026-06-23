"""Tests for Phase 2L.23 foundations + candidate lab (no API, no ground truth)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.evidence_verifier_policy import evaluate_override  # noqa: E402
from src.knowledge_cards import all_card_ids, retrieve_cards, score_card  # noqa: E402
from src.pot_lite import map_to_option, safe_eval_arithmetic  # noqa: E402


# --- PoT-lite -----------------------------------------------------------------

def test_pot_valid_arithmetic():
    assert safe_eval_arithmetic("2 + 3 * 4").value == 14.0
    assert safe_eval_arithmetic("(2 + 3) * 4").value == 20.0
    assert safe_eval_arithmetic("-5 + 2").value == -3.0


def test_pot_sqrt_log_pi():
    assert round(safe_eval_arithmetic("sqrt(100**2 + 150**2)").value, 2) == 180.28
    assert safe_eval_arithmetic("log10(1000)").value == 3.0
    assert round(safe_eval_arithmetic("pi").value, 4) == 3.1416
    assert round(safe_eval_arithmetic("2 * pi * 7").value, 2) == 43.98


def test_pot_rejects_unsafe_code():
    for bad in ("__import__('os')", "os.system('ls')", "[1,2,3][0]", "open('x')",
                "(lambda: 1)()", "abs(-3)", "x + 1", "1 if True else 2"):
        r = safe_eval_arithmetic(bad)
        assert r.ok is False and r.value is None, f"should reject: {bad}"


def test_pot_division_by_zero_rejected():
    assert safe_eval_arithmetic("1/0").ok is False


def test_pot_option_mapping():
    assert map_to_option(180.28, ["175", "180.28", "185"], ["A", "B", "C"]) == "B"


def test_pot_option_mapping_declines_ambiguous():
    # Two options nearly equidistant from the value -> decline.
    assert map_to_option(10.0, ["9.9", "10.1", "50"], ["A", "B", "C"]) is None


# --- knowledge cards ----------------------------------------------------------

def test_cards_loaded():
    ids = all_card_ids()
    # Phase 2L.25 expanded the card set; assert the core cards plus the grown count.
    assert "paging_logical_address" in ids and "cache_amat" in ids and len(ids) >= 10


def test_retrieve_cards_relevance():
    cards = retrieve_cards("Trong phân trang, địa chỉ luận lý có dạng nào?", top_k=3)
    assert cards and cards[0][0].id == "paging_logical_address"


def test_retrieve_cards_deterministic_and_no_answer():
    a = retrieve_cards("Định luật Ohm: V=IR, tính dòng điện?", top_k=2)
    b = retrieve_cards("Định luật Ohm: V=IR, tính dòng điện?", top_k=2)
    assert [c.id for c, _ in a] == [c.id for c, _ in b]      # deterministic
    # cards carry no answer selection — only statement/formula
    assert all(hasattr(c, "formula_or_rule") for c, _ in a)


def test_retrieve_cards_empty_for_irrelevant():
    # A question with no card-domain vocabulary retrieves nothing.
    assert retrieve_cards("Bạn thích màu sắc nào nhất trong các màu này?", top_k=3) == []


# --- evidence verifier policy -------------------------------------------------

def test_policy_rejects_internal_knowledge_only():
    d = evaluate_override({"evidence_kind": "internal_knowledge", "selected_answer": "B",
                           "current_answer": "A", "confidence": 0.99})
    assert d.allow is False


def test_policy_rejects_self_consistency_only():
    d = evaluate_override({"evidence_kind": "self_consistency", "selected_answer": "B",
                           "current_answer": "A", "confidence": 0.99})
    assert d.allow is False


def test_policy_accepts_deterministic_unique():
    d = evaluate_override({"evidence_kind": "deterministic_calculation", "unique_option": True,
                           "selected_answer": "B", "current_answer": "A", "reason": "computed"})
    assert d.allow is True


def test_policy_accepts_retrieved_card_high_conf():
    d = evaluate_override({"evidence_kind": "retrieved_card", "card_support": True,
                           "unique_option": True, "confidence": 0.95,
                           "selected_answer": "B", "current_answer": "A"})
    assert d.allow is True


def test_policy_rejects_unsupported_law_admin():
    d = evaluate_override({"evidence_kind": "law_admin_unsupported", "selected_answer": "B",
                           "current_answer": "A", "confidence": 0.99})
    assert d.allow is False


def test_policy_rejects_medium_high_risk_hint():
    d = evaluate_override({"evidence_kind": "deterministic_calculation", "unique_option": True,
                           "selected_answer": "B", "current_answer": "A", "risk_level": "high"})
    assert d.allow is False


def test_policy_rejects_no_change():
    d = evaluate_override({"evidence_kind": "deterministic_calculation", "unique_option": True,
                           "selected_answer": "A", "current_answer": "A"})
    assert d.allow is False


# --- scripts: source safety + recommender logic -------------------------------

def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_recommender_prefers_deterministic_over_drift():
    mod = _load("recommend_submission_candidate.py")
    d = tempfile.mkdtemp()
    review = Path(d) / "review.csv"
    review.write_text(
        "qid,question_preview,choices,branch,baseline_answer,candidate_answer,candidate_source,"
        "rule_id,change_type,risk_level,reason,matches_safe_deterministic_rule\n"
        "q1,Q,c,calc,D,B,pred_v9_formula_bank_from_v8_clean.csv,pyth,deterministic_rule,low,r,True\n"
        "q2,Q,c,sk,A,B,pred_production_user_run.csv,,production_model_drift,medium,r,False\n"
        "q3,Q,c,sk,A,C,pred_production_user_run.csv,,production_model_drift,medium,r,False\n"
        "q4,Q,c,sk,A,D,pred_production_user_run.csv,,production_model_drift,medium,r,False\n")
    out = Path(d) / "rec.md"
    rc = mod.main(["--review", str(review), "--output", str(out)])
    assert rc == 0
    text = out.read_text()
    assert "pred_v9_formula_bank_from_v8_clean.csv" in text and "Avoid the production rerun" in text


def test_no_qid_hardcoding_in_new_sources():
    import re as _re
    for rel in ("src/pot_lite.py", "src/knowledge_cards.py", "src/evidence_verifier_policy.py",
                "scripts/analyze_candidate_disagreements.py",
                "scripts/recommend_submission_candidate.py"):
        src = (_ROOT / rel).read_text()
        for pat in (r'qid\s*==', r'==\s*["\']test_0', r'test_0\d{3}'):
            assert not _re.search(pat, src), f"{pat} in {rel}"
        assert "first100_external" not in src


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
