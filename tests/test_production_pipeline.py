"""Tests for the production pipeline runner, policy, and Docker detection (2L.20).

No network, no real model, no qid logic. Uses importlib to load the script module
and synthetic samples for the policy. The base-solver (API) path is never invoked.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.labels import labels_for  # noqa: E402
from src.production_policy import apply_safe_overrides, branch_of, decide  # noqa: E402


def _load_runner():
    path = _ROOT / "scripts" / "run_production_pipeline.py"
    spec = importlib.util.spec_from_file_location("rpp", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- preset expansion ---------------------------------------------------------

def test_preset_expands_to_stable_settings():
    m = _load_runner()
    opts = m.expand_preset("competition_qwen35_9b")
    assert opts["openrouter_model"] == "qwen/qwen3.5-9b"
    assert opts["openrouter_max_tokens"] == 512
    assert opts["evidence_reranker_method"] == "reranker"
    assert opts["evidence_reranker_model"] == "models/qwen3-reranker-0.6b"
    assert opts["formula_bank"] is True and opts["calculation_solver"] is True
    cfg = m._openrouter_config_from(opts)
    assert cfg["model"] == "qwen/qwen3.5-9b" and cfg["max_tokens"] == 512
    assert cfg["evidence_reranker_enabled"] is True


def test_unknown_preset_rejected():
    m = _load_runner()
    try:
        m.expand_preset("nope")
        assert False
    except SystemExit:
        pass


# --- no dependency on previous prediction files -------------------------------

def test_runner_does_not_read_prediction_files():
    src = (_ROOT / "scripts" / "run_production_pipeline.py").read_text()
    # The runner reads ONLY --input via load_dataset; it must not read prior preds.
    assert "load_dataset" in src
    assert "read_predictions" not in src        # never reads an existing prediction CSV
    # v7/v8/v9 names may appear ONLY in the protected-overwrite guard set.
    import re as _re
    for name in ("pred_v7", "pred_v8", "pred_v9"):
        for m in _re.finditer(name, src):
            ctx = src[max(0, m.start() - 60): m.start()]
            assert "_PROTECTED_LOCAL" in src and "/" in ctx or "outputs/" in ctx, \
                f"{name} referenced outside the protected set"


def test_runner_refuses_protected_output():
    m = _load_runner()
    try:
        m.main(["--input", "x.json", "--output", "outputs/pred.csv", "--preset",
                "competition_qwen35_9b"])
        assert False, "should refuse protected output"
    except SystemExit as e:
        assert "REFUSING" in str(e)


# --- Docker / entrypoint input detection --------------------------------------

def test_detect_input_priority_private_before_public():
    m = _load_runner()
    d = Path(tempfile.mkdtemp())
    (d / "public_test.csv").write_text("qid,question\n")
    assert m.detect_input_file(d).endswith("public_test.csv")
    (d / "private_test.csv").write_text("qid,question\n")
    assert m.detect_input_file(d).endswith("private_test.csv")   # private wins


def test_detect_input_none_when_empty():
    m = _load_runner()
    d = Path(tempfile.mkdtemp())
    assert m.detect_input_file(d) is None


def test_detect_input_generic_fallback():
    m = _load_runner()
    d = Path(tempfile.mkdtemp())
    (d / "weird_name.json").write_text("[]")
    assert m.detect_input_file(d).endswith("weird_name.json")


# --- safe override policy -----------------------------------------------------

def test_policy_overrides_with_safe_deterministic_rule():
    # A determinant question: deterministic answer overrides a wrong base answer.
    s = {"qid": "x", "question": "Tính định thức của ma trận [[3, 8], [4, 6]].",
         "choices": ["-14", "14", "50", "-50"]}
    labels = labels_for(4)
    final, rec = decide(s, "B", labels)        # base wrongly says B
    assert final == "A" and rec["override_applied"] is True
    assert rec["rule_id"].endswith("determinant_2x2") or "determinant" in rec["rule_id"]


def test_policy_keeps_base_when_no_rule():
    s = {"qid": "y", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon", "Nice", "Huế"]}
    final, rec = decide(s, "A", labels_for(4))
    assert final == "A" and rec["override_applied"] is False


def test_policy_keeps_base_when_rule_agrees():
    s = {"qid": "z", "question": "Tính định thức của ma trận [[3, 8], [4, 6]].",
         "choices": ["-14", "14", "50", "-50"]}
    final, rec = decide(s, "A", labels_for(4))   # base already correct (A)
    assert final == "A" and rec["override_applied"] is False


def test_apply_safe_overrides_batch():
    samples = [
        {"qid": "a", "question": "Tính định thức của ma trận [[2, 0], [0, 2]].",
         "choices": ["0", "2", "4", "-4"]},
        {"qid": "b", "question": "Thủ đô nước Pháp?", "choices": ["Paris", "Lyon"]},
    ]
    base = {"a": "A", "b": "A"}     # 'a' wrong (det=4 -> C), 'b' kept
    finals, recs = apply_safe_overrides(samples, base, labels_for)
    assert finals["a"] == "C" and finals["b"] == "A"
    assert sum(r["override_applied"] for r in recs) == 1


def test_branch_of_is_deterministic():
    s = {"qid": "q", "question": "Đoạn thông tin: ... Câu hỏi: ?" + "x" * 1600,
         "choices": ["A", "B"]}
    assert branch_of(s) == branch_of(s) and branch_of(s) in (
        "calculation", "long_context", "short_knowledge", "law_admin", "ambiguous", "formula_bank")


# --- source safety ------------------------------------------------------------

def test_no_qid_hardcoding_or_api_in_new_sources():
    import re as _re
    for rel in ("scripts/run_production_pipeline.py", "src/production_policy.py",
                "scripts/audit_hidden_generalization_readiness.py"):
        src = (_ROOT / rel).read_text()
        for pat in (r'qid\s*==', r'==\s*qid', r'==\s*["\']test_0', r'test_0\d{3}'):
            assert not _re.search(pat, src), f"{pat} in {rel}"
        assert "first100_external" not in src
        # production runner legitimately builds the OpenRouter solver; it must not
        # bake a key or read .env directly.
        assert "OPENROUTER_API_KEY" not in src and ".env" not in src


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
