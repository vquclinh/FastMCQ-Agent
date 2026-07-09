"""Tests for Phase 2L.21 production accuracy layers (no API, no final predictions).

Covers route prompts, formula hints, option-aware evidence, JSON repair, the direct
inference path (fake client), and the runner's resume/checkpoint helpers.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from src.solvers.formula_bank_solver import detect_formula_hints  # noqa: E402
from src.evidence.option_evidence import build_option_aware_evidence_pack  # noqa: E402
from src.system.production_inference import predict_one_direct  # noqa: E402
from src.system.production_prompts import (answer_needs_repair, build_production_prompt,  # noqa: E402
                                    build_repair_prompt)


class _Res:
    def __init__(self, content):
        self.content = content


class _FakeClient:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        return _Res(self.contents[min(self.calls - 1, len(self.contents) - 1)])


# --- A: route prompts ---------------------------------------------------------

def test_route_prompt_selection_differs_by_route():
    q, ch = "Câu hỏi?", ["A", "B", "C", "D"]
    calc = build_production_prompt("calculation", q, ch)[0]["content"]
    lc = build_production_prompt("long_context", q, ch, evidence="bằng chứng X")[0]["content"]
    law = build_production_prompt("law_admin", q, ch)[0]["content"]
    assert "TÍNH TOÁN" in calc
    assert "NGỮ CẢNH" in lc or "BẰNG CHỨNG" in lc
    assert "KHÔNG từ chối" in law            # law_admin must not refuse
    # every route prompt enforces the JSON contract
    for route in ("calculation", "long_context", "short_knowledge", "ambiguous", "default"):
        assert '"answer"' in build_production_prompt(route, q, ch)[0]["content"]


def test_long_context_prompt_includes_evidence():
    msgs = build_production_prompt("long_context", "Q?", ["A", "B"], evidence="SÔNG NILE")
    assert "SÔNG NILE" in msgs[1]["content"]


def test_repair_prompt_and_needs_repair():
    assert answer_needs_repair(None, ["A", "B"]) is True
    assert answer_needs_repair("Z", ["A", "B"]) is True
    assert answer_needs_repair("b", ["A", "B"]) is False
    assert '"answer"' in build_repair_prompt("Q?", ["A", "B"])[0]["content"]


# --- B: formula hints (log-only unless safe) ---------------------------------

def test_hint_safe_for_deterministic_match():
    s = {"qid": "h1", "question": "Tính định thức của ma trận [[3, 8], [4, 6]].",
         "choices": ["-14", "14", "50", "-50"]}
    hints = detect_formula_hints(s)
    assert any(h["safe_to_override"] for h in hints)


def test_hint_log_only_for_risky_family():
    s = {"qid": "h2", "question": "Hai tụ điện mắc nối tiếp thì điện dung thay đổi thế nào?",
         "choices": ["Tăng", "Giảm", "Không đổi", "Khác"]}
    hints = detect_formula_hints(s)
    cap = [h for h in hints if h["detected_family"] == "capacitor_series_parallel"]
    assert cap and cap[0]["safe_to_override"] is False and cap[0]["risk_level"] == "high"


def test_hint_none_for_plain_question():
    s = {"qid": "h3", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon"]}
    assert detect_formula_hints(s) == []


# --- C: option-aware evidence (deterministic, no API) ------------------------

def _long_sample():
    body = " ".join(f"Câu nền {i} không liên quan." for i in range(30))
    q = (f"Đoạn thông tin:\n[1] Tiêu đề: Nền\nNội dung: {body}\n"
         f"[2] Tiêu đề: Địa lý\nNội dung: Thủ đô Cairo của Ai Cập nằm bên sông Nile.\n"
         f"Câu hỏi: Thủ đô Ai Cập nằm bên bờ sông nào?")
    return {"qid": "lc", "question": q, "choices": ["Sông Nile", "Sông Amazon", "Sông Mê Kông"]}


def test_option_evidence_pack_deterministic():
    a = build_option_aware_evidence_pack(_long_sample())
    b = build_option_aware_evidence_pack(_long_sample())
    assert a.matched and a.pack_text == b.pack_text          # deterministic
    assert a.evidence_pack_size > 0 and a.evidence_selected_by_option
    assert set(a.evidence_selected_by_option.keys()) == {"A", "B", "C"}


def test_option_evidence_declines_short_question():
    pack = build_option_aware_evidence_pack(
        {"qid": "s", "question": "Thủ đô Pháp?", "choices": ["Paris", "Lyon"]})
    assert pack.matched is False


# --- D: JSON repair retry via direct inference -------------------------------

def test_direct_inference_no_repair_when_valid():
    fc = _FakeClient(['{"answer": "B", "confidence": 0.9}'])
    ans, rec = predict_one_direct(fc, {"qid": "x", "question": "Q?", "choices": ["A", "B", "C"]})
    assert ans == "B" and rec["retry_count"] == 0 and rec["repair_status"] == "not_needed"
    assert fc.calls == 1


def test_direct_inference_repairs_invalid_once():
    fc = _FakeClient(["not json", '{"answer": "C", "confidence": 0.8}'])
    ans, rec = predict_one_direct(fc, {"qid": "x", "question": "Q?", "choices": ["A", "B", "C"]},
                                  json_repair_retry=True)
    assert ans == "C" and rec["retry_count"] == 1 and rec["repair_status"] == "repaired"
    assert fc.calls == 2        # exactly one repair retry, no multi-sampling


def test_direct_inference_fallback_when_repair_fails():
    fc = _FakeClient(["garbage", "still garbage"])
    ans, rec = predict_one_direct(fc, {"qid": "x", "question": "Q?", "choices": ["A", "B"]},
                                  json_repair_retry=True)
    assert ans in ("A", "B") and rec["repair_status"] == "repair_failed" and fc.calls == 2


# --- source safety ------------------------------------------------------------

def test_no_qid_hardcoding_or_sheet_in_new_sources():
    import re as _re
    for rel in ("src/system/production_prompts.py", "src/system/production_inference.py",
                "src/evidence/option_evidence.py"):
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
