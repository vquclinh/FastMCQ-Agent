"""Tests for in-question evidence reranking (no network, no model, no qid).

Runnable with pytest, or standalone: ``python tests/test_evidence_reranker.py``.
Synthetic samples only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evidence_reranker import (  # noqa: E402
    chunk_context,
    extract_question_stem,
    rerank_evidence_for_sample,
)

# A multi-source structured context where the answer fact lives in source [2].
_RELEVANT = ("Nội dung: Sông Nile là con sông dài nhất châu Phi và chảy qua Ai Cập. "
             "Thành phố Cairo nằm bên bờ sông Nile và là thủ đô của Ai Cập.")
_NOISE1 = ("Nội dung: Bóng đá là môn thể thao phổ biến. Nhiều giải đấu lớn được tổ "
           "chức hàng năm với hàng triệu người hâm mộ trên khắp thế giới tham gia.")
_NOISE2 = ("Nội dung: Máy tính hiện đại sử dụng bộ vi xử lý. Lịch sử điện toán trải "
           "qua nhiều thế hệ phần cứng khác nhau trong nhiều thập kỷ phát triển.")


def _titled_sample():
    q = (f"Đoạn thông tin:\n[1] Tiêu đề: Thể thao\n{_NOISE1}\n"
         f"[2] Tiêu đề: Địa lý Ai Cập\n{_RELEVANT}\n"
         f"[3] Tiêu đề: Máy tính\n{_NOISE2}\n"
         "Câu hỏi: Thủ đô của Ai Cập nằm bên bờ sông nào?")
    return {"qid": "syn1", "question": q,
            "choices": ["Sông Nile", "Sông Amazon", "Sông Mê Kông", "Sông Hằng"]}


def test_parses_titled_multi_source():
    chunks = chunk_context(_titled_sample()["question"])
    assert len(chunks) >= 3
    assert any(c.source_title and "Ai Cập" in c.source_title for c in chunks)


def test_parses_doan_van_format():
    q = ("-- Đoạn văn 1 --\n" + _NOISE1 + "\n-- Đoạn văn 2 --\n" + _RELEVANT +
         "\nThủ đô Ai Cập nằm bên bờ sông nào?")
    chunks = chunk_context(q)
    assert len(chunks) >= 2 and any(c.kind.startswith("doan") for c in chunks)


def test_selects_relevant_chunk_over_generic_noise():
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2)
    assert r.matched
    assert "Nile" in r.selected_text and "Cairo" in r.selected_text
    # top-scoring chunk should be the Egypt-geography source.
    top = max(r.scores, key=lambda s: s["score"])
    assert top["source_title"] and "Ai Cập" in top["source_title"]


def test_includes_global_context_and_question_last():
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2500, top_k=3)
    assert "[NGỮ CẢNH TỔNG QUAN]" in r.selected_text
    assert "[BẰNG CHỨNG" in r.selected_text
    assert r.selected_text.rstrip().endswith("?")  # question stem placed last


def test_respects_max_chars():
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=900, top_k=4)
    assert r.matched and len(r.selected_text) <= 900 + 200  # global+stem overhead margin


def test_fallback_when_no_structured_context():
    # A short standalone question has no chunkable context -> matched False.
    r = rerank_evidence_for_sample(
        {"qid": "s", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon"]},
        max_chars=2000, top_k=3)
    assert not r.matched


def test_deterministic_output():
    a = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2)
    b = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2)
    assert a.selected_text == b.selected_text


def test_no_qid_effect():
    s1 = _titled_sample(); s2 = dict(s1, qid="test_0001")
    r1 = rerank_evidence_for_sample(s1, max_chars=2000, top_k=2)
    r2 = rerank_evidence_for_sample(s2, max_chars=2000, top_k=2)
    assert r1.selected_text == r2.selected_text


def test_optional_embedding_unavailable_falls_back_to_lexical():
    # method=embedding but no model -> uses hybrid_lexical (never downloads).
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2,
                                   method="embedding", optional_embedding_model=None)
    assert r.matched and r.method == "hybrid_lexical"


def test_never_empty_when_context_present():
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=3)
    assert r.matched and r.selected_text.strip()


def test_question_stem_extraction_vietnamese():
    stem = extract_question_stem(_titled_sample()["question"])
    assert "Thủ đô của Ai Cập" in stem and stem.endswith("?")


def test_no_web_or_eval_in_source():
    import re as _re
    src = Path(__file__).resolve().parent.parent.joinpath("src/evidence_reranker.py").read_text()
    # No network clients and no dynamic code execution.
    for bad in ("import requests", "import urllib", "import httpx", "import socket",
                "eval(", "exec(", "__import__"):
        assert bad not in src, f"unexpected '{bad}' in evidence_reranker.py"
    # No qid is read for decisions.
    for pat in (r'\[\s*["\']qid', r'\.get\(\s*["\']qid'):
        assert not _re.search(pat, src)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
