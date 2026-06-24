"""CLI-integration tests for the V12B permutation scripts (Phase 2L.34B, updated in 2L.34C).

Core permutation/mapping/voting logic is unit-tested in test_mcq_permutation_debiaser_2l34c.py.
These tests exercise the thin CLI wrappers: dry-run (no API), the selector wrapper + output
protection + CSV validation, and the plan ranking.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

_INPUT = str(_ROOT / "public-test_1780368312.json")
_V11 = str(_ROOT / "output" / "pred_v11_independent_rerun1.csv")


def _load(script):
    spec = importlib.util.spec_from_file_location(
        f"v12b_{script}", next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{script}.py")), _ROOT / "scripts" / f"{script}.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


# --- runner dry-run (no API) -------------------------------------------------

def test_verifier_dry_run_no_api(monkeypatch):
    import src.api.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in dry-run")))
    run = _load("run_v12b_option_permutation")
    d = tempfile.mkdtemp()
    sbq = {"q1": {"qid": "q1", "question": "x", "choices": ["a", "b", "c", "d"]}}
    summary = run.run(sbq, [{"qid": "q1"}], work_dir=d, model="qwen/qwen3.5-9b-20260310",
                      max_qids=10, permutations=6, budget_usd=0.5, execute=False, dry_run=True)
    assert summary["mode"] == "dry_run" and summary["model_calls_made"] == 0
    recs = [json.loads(l) for l in Path(summary["records"]).read_text().splitlines()]
    assert recs and all(r["parse_status"] == "dry_run" and r["valid"] is False for r in recs)


def test_verifier_builds_uses_core_module():
    run = _load("run_v12b_option_permutation")
    # The runner imports the core module functions (thin wrapper, no duplicated logic).
    src = (next(iter((_ROOT / "scripts" / "legacy").glob("**/run_v12b_option_permutation.py")))).read_text()
    assert "from src.layers.mcq_permutation_debiaser import" in src
    assert "def make_permutations" not in src and "def map_back" not in src


# --- selector wrapper + protection -------------------------------------------

def _rec(label, conf=0.8):
    return {"original_qid": "q1", "mapped_original_label": label, "parse_status": "ok",
            "label_option_match": True, "valid": True, "confidence": conf}


def test_selector_wrapper_accepts_4_of_6():
    sel = _load("build_v12b_permutation_candidate")
    recs = [_rec("B"), _rec("B"), _rec("B"), _rec("B"), _rec("A"), _rec("C")]
    new, dec = sel.decide_override("q1", "A", recs, policy="conservative")
    assert new == "B" and dec["verdict"] == "accept" and dec["best_votes"] == 4


def test_selector_wrapper_rejects_3_of_6():
    sel = _load("build_v12b_permutation_candidate")
    recs = [_rec("B"), _rec("B"), _rec("B"), _rec("A"), _rec("C"), _rec("D")]
    new, dec = sel.decide_override("q1", "A", recs, policy="conservative")
    assert new is None and dec["verdict"] == "reject"


def test_selector_validates_and_no_change_on_empty(tmp_path):
    sel = _load("build_v12b_permutation_candidate")
    recs = tmp_path / "recs.jsonl"; recs.write_text("")
    out = tmp_path / "pred_v12b_permutation_candidate.csv"
    rc = sel.main(["--input", _INPUT, "--current", _V11,
                   "--permutation-records", str(recs), "--output", str(out),
                   "--review-dir", str(tmp_path / "review")])
    assert rc == 0 and _md5(out) == _md5(_V11)


def test_selector_refuses_protected_outputs():
    sel = _load("build_v12b_permutation_candidate")
    for prot in ("output/pred_v11_independent_rerun1.csv", "output/pred.csv",
                 "output/pred_v10_full_production_user_run.csv",
                 "output/pred_v8_clean_generalized_from_v7.csv"):
        try:
            sel.main(["--input", _INPUT, "--current", _V11,
                      "--permutation-records", str(_ROOT / "nope.jsonl"), "--output", prot])
            assert False, prot
        except SystemExit as e:
            assert "protected" in str(e).lower()


# --- plan ranking ------------------------------------------------------------

def test_plan_ranks_manyoption_fallback_first():
    plan = _load("build_v12b_permutation_plan")
    samples = [
        {"qid": "q1", "question": "x", "choices": ["a", "b", "c", "d", "e", "f"]},
        {"qid": "q2", "question": "y", "choices": ["a", "b", "c", "d"]},
    ]
    current = {"q1": "A", "q2": "B"}
    decisions = {"q1": {"final_source": "direct_fallback", "route": "calc", "risk": "high"},
                 "q2": {"final_source": "consensus", "route": "calc", "risk": "low"}}
    out = plan.build_plan(samples, current, decisions=decisions)
    assert out[0]["qid"] == "q1" and out[0]["permutation_priority"] > out[1]["permutation_priority"]


# --- safety invariants -------------------------------------------------------

def test_frozen_v11_md5_stable():
    assert _md5(_V11) == "69f4e7c990e8c612e7bee53084d13b4d"


def test_production_default_is_v12b_frozen():
    cfg = json.loads((_ROOT / "configs" / "production" / "default.json").read_text())
    assert cfg["default_mode"] == "frozen_csv"
    assert cfg["current_best_csv"].endswith("pred_v13_multilayer_candidate_api30_from_v12b.csv")
