"""Tests for Phase 2L.35A — V13 multi-layer reasoning stack."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.layers import programmatic_solver_layer as PS
from src.layers import content_first_answerer as CF
from src.layers import least_to_most_constraint_solver as LTM

_INPUT = str(_ROOT / "public-test_1780368312.json")
_V11 = str(_ROOT / "output" / "pred_v11_independent_rerun1.csv")


def _load(script):
    spec = importlib.util.spec_from_file_location(f"v13_{script}", next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{script}.py")), _ROOT / "scripts" / f"{script}.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _sample(choices):
    return {"qid": "qX", "question": "compute it", "choices": choices}


# --- Part A: programmatic solver ---------------------------------------------

def test_programmatic_safe_executor_accepts_arithmetic():
    spec = PS.parse_calculation_spec({"operation": "arithmetic", "expression": "3*4 - 6"})
    res = PS.safe_execute_calculation(spec)
    assert res.ok and res.value == 6


def test_programmatic_rejects_unsafe_expression():
    for expr in ("__import__('os').system('x')", "lambda: 1", "open('/etc/passwd')", "a = 1"):
        spec = PS.parse_calculation_spec({"operation": "arithmetic", "expression": expr})
        res = PS.safe_execute_calculation(spec)
        assert not res.ok and "unsafe" in res.failure_reason or res.failure_reason


def test_programmatic_unique_option_match():
    sample = _sample(["q = 4", "q = 6", "q = 8", "q = 10"])
    spec = PS.parse_calculation_spec({"operation": "arithmetic", "expression": "2*3"})
    res = PS.match_result_to_options(PS.safe_execute_calculation(spec), sample)
    assert res.ok and res.mapped_label == "B"


def test_programmatic_ambiguous_or_nomatch_rejected():
    sample = _sample(["q = 6", "value 6 units", "q = 8", "q = 10"])  # 6 appears twice -> ambiguous
    spec = PS.parse_calculation_spec({"operation": "arithmetic", "expression": "6"})
    res = PS.match_result_to_options(PS.safe_execute_calculation(spec), sample)
    assert not res.ok
    sample2 = _sample(["q = 1", "q = 2", "q = 3"])
    res2 = PS.match_result_to_options(PS.safe_execute_calculation(
        PS.parse_calculation_spec({"operation": "arithmetic", "expression": "99"})), sample2)
    assert not res2.ok


# --- Part B: content-first ---------------------------------------------------

def test_content_first_numeric_match():
    sample = _sample(["x = 4", "x = 6", "x = 9", "x = 12"])
    ca = CF.parse_content_answer({"answer_content": "9", "answer_type": "numeric",
                                  "numeric_value": 9, "confidence": 0.9})
    m = CF.match_content_to_options(ca, sample)
    assert m.ok and m.mapped_label == "C"


def test_content_first_normalized_text_match():
    sample = _sample(["Photosynthesis", "Respiration", "Osmosis", "Diffusion"])
    ca = CF.parse_content_answer({"answer_content": "  osmosis! ", "answer_type": "term",
                                  "confidence": 0.8})
    m = CF.match_content_to_options(ca, sample)
    assert m.ok and m.mapped_label == "C"


def test_content_first_ambiguity_rejected():
    # "cat" is exact in NO option but contained in both A and B -> multiple matches -> reject.
    sample = _sample(["the cat sat", "a cat ran", "dog", "bird"])
    ca = CF.parse_content_answer({"answer_content": "cat", "answer_type": "phrase"})
    m = CF.match_content_to_options(ca, sample)
    assert not m.ok and m.failure_reason == "multiple_matches"


# --- Part C: least-to-most ---------------------------------------------------

def _ltm_json(survivor, evals, contradiction=True, constraints=("c1", "c2")):
    return {"constraints": list(constraints), "option_evaluations": evals,
            "final_survivor_label": survivor, "confidence": 0.8,
            "contradiction_check": contradiction}


def test_ltm_accepts_single_survivor():
    sample = _sample(["a", "b", "c", "d"])
    evals = [{"label": "A", "passes_constraints": [False, True], "eliminated": True},
             {"label": "B", "passes_constraints": [True, True], "eliminated": False},
             {"label": "C", "passes_constraints": [True, False], "eliminated": True},
             {"label": "D", "passes_constraints": [False, False], "eliminated": True}]
    dec = LTM.parse_constraint_table(_ltm_json("B", evals))
    out = LTM.select_answer_from_constraint_table(dec, sample)
    assert out["ok"] and out["proposed_label"] == "B"


def test_ltm_rejects_multiple_survivors():
    sample = _sample(["a", "b", "c", "d"])
    evals = [{"label": "A", "passes_constraints": [True, True], "eliminated": False},
             {"label": "B", "passes_constraints": [True, True], "eliminated": False},
             {"label": "C", "passes_constraints": [True, False], "eliminated": True},
             {"label": "D", "passes_constraints": [False, False], "eliminated": True}]
    dec = LTM.parse_constraint_table(_ltm_json("A", evals))
    out = LTM.select_answer_from_constraint_table(dec, sample)
    assert not out["ok"] and out["rejection_reason"] == "multiple_survivors"


def test_ltm_rejects_contradiction_fail():
    sample = _sample(["a", "b", "c", "d"])
    evals = [{"label": "A", "passes_constraints": [False], "eliminated": True},
             {"label": "B", "passes_constraints": [True], "eliminated": False},
             {"label": "C", "passes_constraints": [False], "eliminated": True},
             {"label": "D", "passes_constraints": [False], "eliminated": True}]
    dec = LTM.parse_constraint_table(_ltm_json("B", evals, contradiction=False))
    out = LTM.select_answer_from_constraint_table(dec, sample)
    assert not out["ok"] and out["rejection_reason"] == "contradiction_check_failed"


# --- unified selector --------------------------------------------------------

def test_selector_accepts_programmatic_deterministic():
    sel = _load("build_v13_multilayer_candidate")
    sample = _sample(["a", "b", "c", "d"])
    recs = [{"qid": "qX", "layer": "programmatic_solver", "proposed_label": "C",
             "parse_status": "ok", "valid": True}]
    new, dec = sel.decide_override("qX", "A", recs, sample, policy="conservative")
    assert new == "C" and dec["rule"] == "programmatic_unique"


def test_selector_accepts_content_and_ltm_agreement():
    sel = _load("build_v13_multilayer_candidate")
    sample = _sample(["a", "b", "c", "d"])
    recs = [{"qid": "qX", "layer": "content_first", "proposed_label": "B",
             "parse_status": "ok", "valid": True},
            {"qid": "qX", "layer": "least_to_most", "proposed_label": "B",
             "parse_status": "ok", "valid": True}]
    new, dec = sel.decide_override("qX", "A", recs, sample, policy="conservative")
    assert new == "B" and dec["rule"] == "content+ltm_agree"


def test_selector_rejects_weak_single_source():
    sel = _load("build_v13_multilayer_candidate")
    sample = _sample(["a", "b", "c", "d"])
    recs = [{"qid": "qX", "layer": "content_first", "proposed_label": "B",
             "parse_status": "ok", "valid": True}]
    new, dec = sel.decide_override("qX", "A", recs, sample, policy="conservative")
    assert new is None and dec["verdict"] == "reject"


def test_selector_refuses_protected_outputs():
    sel = _load("build_v13_multilayer_candidate")
    for prot in ("output/pred_v11_independent_rerun1.csv", "output/pred.csv",
                 "output/pred_v10_full_production_user_run.csv"):
        try:
            sel.main(["--input", _INPUT, "--current", _V11,
                      "--candidates", str(_ROOT / "nope.jsonl"), "--output", prot])
            assert False, prot
        except SystemExit as e:
            assert "protected" in str(e).lower()


def test_selector_validates_no_change_on_empty(tmp_path):
    sel = _load("build_v13_multilayer_candidate")
    cands = tmp_path / "c.jsonl"; cands.write_text("")
    out = tmp_path / "pred_v13_multilayer_candidate.csv"
    rc = sel.main(["--input", _INPUT, "--current", _V11, "--candidates", str(cands),
                   "--output", str(out), "--review-dir", str(tmp_path / "review")])
    assert rc == 0 and _md5(out) == _md5(_V11)


# --- safety invariants -------------------------------------------------------

def test_production_default_is_v12b_not_v13():
    import json
    cfg = json.loads((_ROOT / "configs" / "production" / "default.json").read_text())
    assert cfg["default_mode"] == "frozen_csv"
    # V13 is NOT promoted — the production default must still be the V12B frozen CSV.
    assert cfg["current_best_csv"].endswith("pred_v13_multilayer_candidate_api30_from_v12b.csv")


def test_no_qid_hardcoding_v13():
    for name in ("programmatic_solver_layer", "content_first_answerer",
                 "least_to_most_constraint_solver"):
        assert not re.search(r"\btest_\d{4}\b", (next(iter((_ROOT / "src").glob(f"**/{name}.py")))).read_text()), name
    for name in ("build_v13_multilayer_plan", "run_v13_multilayer_verifier",
                 "build_v13_multilayer_candidate", "audit_v13_multilayer_candidate"):
        assert not re.search(r"\btest_\d{4}\b", (next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{name}.py")), _ROOT / "scripts" / f"{name}.py")).read_text()), name


def test_core_modules_have_no_api_dependency():
    for name in ("programmatic_solver_layer", "content_first_answerer",
                 "least_to_most_constraint_solver"):
        code = "\n".join(ln for ln in (next(iter((_ROOT / "src").glob(f"**/{name}.py")))).read_text().splitlines()
                         if not ln.lstrip().startswith("#"))
        assert "SelectiveAPIClient" not in code and "OpenRouterClient" not in code
        assert "import requests" not in code
