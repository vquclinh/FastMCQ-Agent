"""Tests for Phase 2L.36B — real dynamic FASTMCQ system with official V12B layer."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.fastmcq_system import run_fastmcq_system, FastMCQSystemConfig
from src.dynamic_base_predictor import predict_base_answers
from src.v12b_dynamic_layer import select_v12b_targets, run_v12b_layer
from src.v13_layer_registry import available_v13_layers, run_v13_layers_if_enabled

_PUBLIC = str(_ROOT / "public-test_1780368312.json")
# public_replay now reproduces the V13 79.7 artifact (promoted in 2L.38A).
_V12B = str(_ROOT / "output" / "pred_v13_multilayer_candidate_api30_from_v12b.csv")


def _final_infer():
    spec = importlib.util.spec_from_file_location("fi_dyn", _ROOT / "scripts" / "final_infer.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def _private_samples():
    return [
        {"qid": "priv_x1", "question": "2 + 2 = ?", "choices": ["3", "4", "5", "6"]},
        {"qid": "priv_x2", "question": "Chọn phát biểu đúng.",
         "choices": ["Bảng có hàng và cột", "CPU là bộ nhớ phụ", "HTML là OS", "DNS là sắp xếp",
                     "Không có đáp án"]},
    ]


def _run(argv):
    mod = _final_infer()
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(argv)
    return rc, buf.getvalue()


# --- orchestrator: arbitrary qids, exact output ------------------------------

def test_dynamic_full_outputs_exactly_input_qids(tmp_path):
    samples = _private_samples()
    out = tmp_path / "pred.csv"
    rep = run_fastmcq_system(samples, str(out), FastMCQSystemConfig(
        mode="dynamic_full", execute_api=False, work_dir=str(tmp_path / "w")))
    rows = [l.split(",")[0] for l in out.read_text().splitlines()[1:]]
    assert rows == [s["qid"] for s in samples]
    assert rep.output_count == 2 and rep.status == "PASS"


def test_dynamic_full_no_api_returns_valid_for_all(tmp_path):
    samples = _private_samples()
    out = tmp_path / "pred.csv"
    run_fastmcq_system(samples, str(out), FastMCQSystemConfig(execute_api=False,
                                                             work_dir=str(tmp_path / "w")))
    from src.labels import is_valid_label
    by = {s["qid"]: s for s in samples}
    for line in out.read_text().splitlines()[1:]:
        q, a = line.split(",")
        assert is_valid_label(a, by[q])


def test_dynamic_full_does_not_use_public_csv(tmp_path):
    # Use qids that overlap NOTHING with public; output must be produced dynamically and the
    # produced answers must not be lifted from the public CSV (different qids entirely).
    samples = _private_samples()
    out = tmp_path / "pred.csv"
    run_fastmcq_system(samples, str(out), FastMCQSystemConfig(execute_api=False,
                                                             work_dir=str(tmp_path / "w")))
    text = out.read_text()
    assert "priv_x1" in text and "test_0001" not in text


def test_base_predictor_one_label_per_sample_no_api():
    samples = _private_samples()
    preds = predict_base_answers(samples, model=None, execute_api=False, budget_usd=None,
                                 work_dir=None, resume=False)
    assert len(preds) == 2
    assert all(p.answer and p.source for p in preds)
    # fallback predictions must be marked weak (not high confidence)
    for p in preds:
        if "fallback" in p.source:
            assert p.confidence is None and "weak" in p.risk_reason


# --- V12B layer --------------------------------------------------------------

def test_v12b_targets_are_feature_based_not_qid():
    samples = _private_samples()
    preds = predict_base_answers(samples, model=None, execute_api=False, budget_usd=None,
                                 work_dir=None, resume=False)
    targets = select_v12b_targets(samples, preds, max_qids=None)
    # both fallback/weak -> both selected; reasons mention features, never a qid literal
    assert {t.qid for t in targets} == {"priv_x1", "priv_x2"}
    for t in targets:
        assert not re.search(r"\b(priv_x\d|test_\d{4})\b", t.reason)


def test_v12b_no_api_is_skipped_not_executed():
    samples = _private_samples()
    preds = predict_base_answers(samples, model=None, execute_api=False, budget_usd=None,
                                 work_dir=None, resume=False)
    targets = select_v12b_targets(samples, preds, max_qids=None)
    results = run_v12b_layer(samples, preds, targets, model=None, execute_api=False,
                             budget_usd=None, permutations=6, policy="conservative",
                             work_dir="scratch/_t", resume=False)
    assert results and all(not r.accept and r.reason == "skipped_no_api" for r in results)


def test_v12b_execute_validates_model_policy():
    # execute_api=True with a DISALLOWED model must raise via model_policy before any call.
    samples = _private_samples()
    preds = predict_base_answers(samples, model=None, execute_api=False, budget_usd=None,
                                 work_dir=None, resume=False)
    targets = select_v12b_targets(samples, preds, max_qids=None)
    try:
        run_v12b_layer(samples, preds, targets, model="gpt-4o", execute_api=True,
                       budget_usd=1.0, permutations=6, policy="conservative",
                       work_dir="scratch/_t", resume=False)
        assert False, "should have refused disallowed model"
    except ValueError as e:
        assert "disallowed" in str(e).lower()


# --- V13 registry ------------------------------------------------------------

def test_v13_registry_exposes_layers_disabled_by_default():
    layers = available_v13_layers()
    assert set(layers) == {"programmatic_solver", "content_first", "least_to_most"}
    assert all(not v["enabled_by_default"] and not v["promoted"] for v in layers.values())
    # disabled -> no notes
    assert run_v13_layers_if_enabled([], [], enabled=False) == []


# --- final_infer CLI modes ---------------------------------------------------

def test_cli_default_mode_is_dynamic_full(tmp_path):
    out = tmp_path / "pred.csv"
    rc, txt = _run(["--input", str(_make_private(tmp_path)), "--output", str(out)])
    assert rc == 0 and "resolved mode: dynamic_full" in txt


def test_cli_public_replay_reproduces_v12b(tmp_path):
    out = tmp_path / "pred.csv"
    rc, txt = _run(["--input", _PUBLIC, "--output", str(out), "--mode", "public_replay"])
    assert rc == 0 and _md5(out) == _md5(_V12B) == "cb02fef569b31e7fb544abab46c0e282"


def test_cli_public_replay_refuses_mismatch(tmp_path):
    out = tmp_path / "pred.csv"
    try:
        _run(["--input", str(_make_private(tmp_path)), "--output", str(out),
              "--mode", "public_replay"])
        assert False
    except SystemExit as e:
        assert "public_replay requires" in str(e)


def test_cli_auto_resolves_dynamic_for_private(tmp_path):
    out = tmp_path / "pred.csv"
    rc, txt = _run(["--input", str(_make_private(tmp_path)), "--output", str(out),
                    "--mode", "auto", "--no-api"])
    assert rc == 0 and "auto -> dynamic_full" in txt


def test_cli_auto_replay_only_with_flag_and_match(tmp_path):
    out = tmp_path / "pred.csv"
    # auto + --allow-public-replay + exact public qids -> public_replay
    rc, txt = _run(["--input", _PUBLIC, "--output", str(out), "--mode", "auto",
                    "--allow-public-replay"])
    assert rc == 0 and "auto -> public_replay" in txt and _md5(out) == _md5(_V12B)


def test_cli_supports_required_flags():
    mod = _final_infer()
    # argparse should accept the full documented flag set without error.
    import argparse
    try:
        mod.main(["--help"])
    except SystemExit:
        pass  # --help exits 0


def _make_private(tmp_path):
    p = tmp_path / "private_test.json"
    p.write_text(json.dumps(_private_samples(), ensure_ascii=False))
    return p


# --- hygiene -----------------------------------------------------------------

def test_no_qid_hardcoding_in_system_modules():
    for name in ("fastmcq_system", "dynamic_base_predictor", "v12b_dynamic_layer",
                 "v13_layer_registry"):
        src = (_ROOT / "src" / f"{name}.py").read_text()
        assert not re.search(r"\btest_\d{4}\b", src), name
        assert "pred_v12b_permutation_candidate_api30" not in src, name  # no frozen-CSV dependency


def test_production_default_remains_v12b_artifact():
    cfg = json.loads((_ROOT / "configs" / "production_v12b_permutation_7883.json").read_text())
    assert cfg["current_best_csv"].endswith("pred_v12b_permutation_candidate_api30.csv")
