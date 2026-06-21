"""Tests for generalized concept rules + clean-v8 / cleanup scripts (Phase 2L.17).

No network, no real model, no qid logic. Synthetic samples only.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.concept_solver import solve_concept_sample  # noqa: E402
from src.labels import labels_for  # noqa: E402


def _solve(q, choices):
    return solve_concept_sample({"question": q, "choices": choices}, labels_for(len(choices)))


def _load(name):
    path = _ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Rule 1: paging logical address ------------------------------------------

def test_paging_logical_address_generic():
    q = ("Trong kỹ thuật phân trang bộ nhớ, địa chỉ luận lý mà hệ điều hành cấp cho "
         "CPU có dạng nào?")
    choices = ["số page (p), số frame (f) và độ dời frame (t)",
               "số page (p) và kích thước page (s)",
               "số page (p) và độ dời page (d)",
               "số frame (f) và độ dời frame (t)"]
    r = _solve(q, choices)
    assert r.matched and r.answer == "C" and r.rule_id == "paging_logical_address"


def test_paging_rejects_frame_and_size_only_options():
    # If no option is page+offset (only frame / size variants), the rule declines.
    q = "Trong phân trang, địa chỉ luận lý có dạng nào?"
    choices = ["số frame (f) và độ dời frame (t)", "kích thước page (s)",
               "số frame và số page", "địa chỉ vật lý"]
    r = _solve(q, choices)
    assert not r.matched


def test_paging_declines_without_paging_or_logical_terms():
    r = _solve("Bộ nhớ ảo là gì?", ["A", "B", "C", "D"])
    assert not r.matched


# --- Rule 2: MC vs AVC --------------------------------------------------------

def test_mc_greater_than_avc_increases():
    q = ("Doanh nghiệp có chi phí biến đổi trung bình là 15 đô la và chi phí biên là "
         "20 đô la; nếu sản lượng tăng thêm một đơn vị thì chi phí biến đổi trung bình?")
    r = _solve(q, ["Sẽ giảm", "Sẽ tăng", "Không thay đổi", "Không thể xác định"])
    assert r.matched and r.answer == "B"


def test_mc_less_than_avc_decreases():
    q = ("Chi phí biến đổi trung bình là 25 đô la, chi phí biên là 10 đô la; khi sản "
         "lượng tăng thêm một đơn vị thì chi phí biến đổi trung bình sẽ thế nào?")
    r = _solve(q, ["Sẽ giảm", "Sẽ tăng", "Không đổi", "Không xác định"])
    assert r.matched and r.answer == "A"


def test_mc_equals_avc_unchanged():
    q = ("Chi phí biến đổi trung bình là 20 đô la và chi phí biên là 20 đô la; sản "
         "lượng tăng thêm một đơn vị thì chi phí biến đổi trung bình?")
    r = _solve(q, ["Sẽ giảm", "Sẽ tăng", "Không thay đổi", "Không thể xác định"])
    assert r.matched and r.answer == "C"


def test_mc_avc_declines_without_numbers():
    q = "Mối quan hệ giữa chi phí biên và chi phí biến đổi trung bình là gì?"
    r = _solve(q, ["MC cắt AVC tại điểm cực tiểu", "MC luôn lớn hơn AVC", "Khác", "Khác2"])
    assert not r.matched


def test_concept_result_has_no_qid_or_answer_table():
    import re as _re
    src = (_ROOT / "src" / "concept_solver.py").read_text()
    for pat in (r'qid\s*==', r'\[\s*["\']qid', r'==\s*["\']test_0', r'test_0\d{3}'):
        assert not _re.search(pat, src), f"qid/answer-table pattern {pat} in concept_solver.py"
    for bad in ("import requests", "import urllib", "eval(", "exec(", "openrouter"):
        assert bad not in src.lower()


# --- clean v8 script ----------------------------------------------------------

def test_clean_v8_refuses_protected_output():
    mod = _load("apply_clean_generalized_fixes_to_predictions.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y",
                  "--output", "outputs/pred.csv",          # protected
                  "--log-path", "outputs/z.jsonl", "--diff", "outputs/d.csv"])
        assert False, "should have refused protected output"
    except SystemExit as e:
        assert "REFUSING" in str(e) or e.code != 0


def test_clean_v8_no_external_sheet_or_api():
    src = (_ROOT / "scripts" / "apply_clean_generalized_fixes_to_predictions.py").read_text()
    # No actual API/client usage, no env access, no external answer sheet read.
    assert "first100_external" not in src and "OpenRouterClient" not in src
    assert "import" not in src or "openrouter_client" not in src
    assert ".env" not in src and "OPENROUTER_API_KEY" not in src


# --- cleanup script -----------------------------------------------------------

def test_cleanup_dry_run_deletes_nothing():
    mod = _load("cleanup_outputs_for_submission.py")
    # Create a temp diagnostic file under outputs/ matching a temp pattern.
    marker = mod.OUTPUTS / "zzz_tmp_candidates.csv"
    marker.write_text("qid\n")
    try:
        rc = mod.main(["--dry-run"])
        assert rc == 0 and marker.exists()      # dry-run must not delete
    finally:
        if marker.exists():
            marker.unlink()


def test_cleanup_keep_list_protects_final_outputs():
    mod = _load("cleanup_outputs_for_submission.py")
    for name in ("pred.csv", "pred_v7_programmatic_assist_from_v6b.csv",
                 "pred_v8_clean_generalized_from_v7.csv",
                 "run_v6b_qwen_rerank_calc_verifier_fast.jsonl"):
        assert name in mod.KEEP
    keep, delete = mod._classify()
    assert not (set(keep) & set(delete))         # disjoint
    assert all(n not in mod.KEEP for n in delete)  # never delete a protected name


def test_cleanup_only_targets_outputs_dir():
    mod = _load("cleanup_outputs_for_submission.py")
    src = (_ROOT / "scripts" / "cleanup_outputs_for_submission.py").read_text()
    assert 'OUTPUTS = Path("outputs")' in src
    assert "OUTPUTS.resolve() not in rp.parents" in src   # outside-outputs guard


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
