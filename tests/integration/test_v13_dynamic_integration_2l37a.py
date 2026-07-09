"""Tests for Phase 2L.37A — V13 multi-layer integrated into the dynamic FASTMCQ system."""

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

from src.base.dynamic_base_predictor import predict_base_answers, BasePrediction
from src.layers.v13_dynamic_layer import select_v13_targets, run_v13_layer, V13LayerResult
from src.layers.v12b_dynamic_layer import V12BLayerResult
from src.selector.system_candidate_selector import select_system_overrides
from src.system.fastmcq_system import run_fastmcq_system, FastMCQSystemConfig

_PUBLIC = str(_ROOT / "public-test_1780368312.json")
# public_replay now reproduces the V13 79.7 artifact (promoted in 2L.38A).
_V12B = str(_ROOT / "output" / "pred_v13_multilayer_candidate_api30_from_v12b.csv")


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _final_infer():
    spec = importlib.util.spec_from_file_location("fi_v13", _ROOT / "scripts" / "tools" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


_NUMERIC = {"qid": "n1", "question": "2 + 2 bằng bao nhiêu?", "choices": ["3", "4", "5", "6"]}
_PROVERB = {"qid": "p1", "question": "Chọn câu tục ngữ đồng nghĩa với 'A'.",
            "choices": ["x", "y", "z", "w"]}
_MULTI = {"qid": "m1", "question": "Chọn phát biểu đúng về CSDL.",
          "choices": ["a", "b", "c", "d", "e"]}


def _base(samples):
    return predict_base_answers(samples, local_backend=_FakeLocalBackend(),
                                work_dir=None, resume=False)


class _FakeLocalBackend:
    def __init__(self):
        self.generate_calls = 0

    def predict_mcq(self, item, *, max_new_tokens=None):
        return "B" if "2 + 2" in str(item.get("question", "")) else "A"

    def generate_text(self, messages, *, max_new_tokens=None, temperature=0.0):
        self.generate_calls += 1
        text = "\n".join(m.get("content", "") for m in messages) if isinstance(messages, list) else str(messages)
        if "ANSWER CONTENT" in text:
            return json.dumps({"answer_content": "y", "answer_type": "term",
                               "numeric_value": None, "evidence": "fake", "confidence": 0.8})
        return json.dumps({"constraints": ["fake"],
                           "option_evaluations": [{"label": "A", "passes_constraints": [False],
                                                    "eliminated": True},
                                                   {"label": "B", "passes_constraints": [True],
                                                    "eliminated": False}],
                           "final_survivor_label": "B", "confidence": 0.8,
                           "contradiction_check": True})


# --- target selection (feature-based) ----------------------------------------

def test_programmatic_target_for_numeric():
    s = [_NUMERIC]
    t = select_v13_targets(s, _base(s), max_qids=None)[0]
    assert "programmatic_solver" in t.target_layers


def test_content_first_target_for_proverb_term():
    s = [_PROVERB]
    t = select_v13_targets(s, _base(s), max_qids=None)[0]
    assert "content_first" in t.target_layers


def test_least_to_most_target_for_multicondition():
    s = [_MULTI]
    t = select_v13_targets(s, _base(s), max_qids=None)[0]
    assert "least_to_most" in t.target_layers


def test_targets_feature_based_not_qid():
    src = (next(iter((_ROOT / "src").glob("**/v13_dynamic_layer.py")))).read_text()
    assert not re.search(r"\b(test_\d{4}|private_\w+)\b", src)


# --- local behavior ----------------------------------------------------------

def test_v13_local_model_layers_run(tmp_path):
    s = [_MULTI]
    targets = select_v13_targets(s, _base(s), max_qids=None)
    backend = _FakeLocalBackend()
    res = run_v13_layer(s, _base(s), targets, local_backend=backend,
                        work_dir=str(tmp_path / "v13"), resume=False)
    assert res and backend.generate_calls > 0
    assert any(r.layer in {"content_first", "least_to_most"} for r in res)


def test_v13_deterministic_programmatic_runs_locally(tmp_path):
    s = [_NUMERIC]
    targets = select_v13_targets(s, _base(s), max_qids=None)
    res = run_v13_layer(s, _base(s), targets, local_backend=_FakeLocalBackend(),
                        work_dir=str(tmp_path / "v13"), resume=False)
    prog = [r for r in res if r.layer == "programmatic_solver"]
    assert prog and prog[0].proposed_answer == "B"   # 2+2=4 -> option B
    assert prog[0].confidence == 1.0 and prog[0].reason == "deterministic_matches_current"


# --- system selector ---------------------------------------------------------

def _bp(qid, ans, source="dynamic_fallback", conf=None, risk="weak"):
    return BasePrediction(qid, ans, source, conf, "", risk, {})


def test_selector_accepts_v12b_valid_override():
    s = [{"qid": "q", "question": "?", "choices": ["a", "b", "c", "d"]}]
    base = [_bp("q", "A")]
    v12b = [V12BLayerResult("q", "C", True, "conservative", {"C": 5}, 6, None, {})]
    d = select_system_overrides(s, base, v12b, [])[0]
    assert d.accept and d.proposed_answer == "C" and "v12b" in d.source_layers


def test_selector_accepts_programmatic_unique():
    s = [{"qid": "q", "question": "?", "choices": ["a", "b", "c", "d"]}]
    base = [_bp("q", "A")]
    v13 = [V13LayerResult("q", "programmatic_solver", "C", "c", True, 1.0, "ok")]
    d = select_system_overrides(s, base, [], v13)[0]
    assert d.accept and d.proposed_answer == "C" and "programmatic_solver" in d.source_layers


def test_selector_accepts_content_plus_ltm_agreement():
    s = [{"qid": "q", "question": "?", "choices": ["a", "b", "c", "d"]}]
    base = [_bp("q", "A", source="formula_bank", conf=0.97, risk="deterministic_match")]
    v13 = [V13LayerResult("q", "content_first", "B", "b", True, 0.5, "ok"),
           V13LayerResult("q", "least_to_most", "B", "b", True, 0.8, "ok")]
    d = select_system_overrides(s, base, [], v13)[0]
    assert d.accept and d.proposed_answer == "B" and set(d.source_layers) == {"content_first", "least_to_most"}


def test_selector_rejects_single_weak_content_low_conf():
    # strong (non-weak) base + content_first alone with LOW confidence -> reject
    s = [{"qid": "q", "question": "?", "choices": ["a", "b", "c", "d"]}]
    base = [_bp("q", "A", source="formula_bank", conf=0.97, risk="deterministic_match")]
    v13 = [V13LayerResult("q", "content_first", "B", "b", True, 0.3, "ok")]
    d = select_system_overrides(s, base, [], v13)[0]
    assert not d.accept


def test_selector_rejects_invalid_label():
    s = [{"qid": "q", "question": "?", "choices": ["a", "b"]}]   # only A,B valid
    base = [_bp("q", "A")]
    v13 = [V13LayerResult("q", "programmatic_solver", "C", "c", True, 1.0, "ok")]
    d = select_system_overrides(s, base, [], v13)[0]
    assert not d.accept   # C invalid for a 2-choice sample


# --- system end-to-end -------------------------------------------------------

def test_dynamic_full_v13_disabled_matches_36b(tmp_path):
    s = [_NUMERIC, _MULTI]
    out = tmp_path / "pred.csv"
    rep = run_fastmcq_system(s, str(out), FastMCQSystemConfig(
        enable_v13=False, local_backend=_FakeLocalBackend(), work_dir=str(tmp_path / "w")))
    assert rep.v13_targets == 0 and rep.v13_overrides == 0 and rep.output_count == 2


def test_dynamic_full_v13_enabled_outputs_exact_qids(tmp_path):
    s = [_NUMERIC, _MULTI, _PROVERB]
    out = tmp_path / "pred.csv"
    rep = run_fastmcq_system(s, str(out), FastMCQSystemConfig(
        enable_v13=True, local_backend=_FakeLocalBackend(), work_dir=str(tmp_path / "w")))
    rows = [l.split(",")[0] for l in out.read_text().splitlines()[1:]]
    assert rows == ["n1", "m1", "p1"] and rep.v13_enabled and rep.output_count == 3


def test_cli_public_replay_still_v12b(tmp_path):
    out = tmp_path / "pred.csv"
    mod = _final_infer()
    mod.main(["--input", _PUBLIC, "--output", str(out), "--mode", "public_replay"])
    assert _md5(out) == _md5(_V12B) == "cb02fef569b31e7fb544abab46c0e282"


def test_cli_supports_v13_flags(tmp_path):
    s = tmp_path / "p.json"
    s.write_text(json.dumps([_NUMERIC]))
    out = tmp_path / "pred.csv"
    mod = _final_infer()
    rc = mod.main(["--input", str(s), "--output", str(out), "--mode", "dynamic_full",
                   "--enable-v13", "--v13-max-qids", "5", "--dry-run",
                   "--system-policy", "conservative", "--max-overrides", "10"])
    assert rc == 0


def test_no_hardcoding_in_new_modules():
    for name in ("v13_dynamic_layer", "system_candidate_selector"):
        src = (next(iter((_ROOT / "src").glob(f"**/{name}.py")))).read_text()
        assert not re.search(r"\btest_\d{4}\b", src), name
        assert "pred_v12b_permutation_candidate_api30" not in src, name
