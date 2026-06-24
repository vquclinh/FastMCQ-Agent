"""Tests for the deterministic passage compressor (no torch).

Runnable with pytest, or standalone: ``python tests/test_passage_compressor.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.passage_compressor import compress_passage  # noqa: E402


def test_short_input_passthrough():
    q = "Một câu hỏi ngắn?"
    out = compress_passage(q, ["a", "b"], max_context_chars=1000)
    assert out["compressed_question"] == q
    assert out["stats"]["was_compressed"] is False
    assert out["stats"]["method"] == "none"


def test_long_input_is_compressed_and_nonempty():
    body = " ".join(f"Câu số {i} nói về chủ đề {i}." for i in range(400))
    q = f"Tiêu đề: Chủ đề. Nội dung: {body} Theo đoạn văn, đáp án đúng là gì?"
    out = compress_passage(q, ["alpha", "beta"], max_context_chars=500)
    assert out["stats"]["was_compressed"] is True
    assert len(out["compressed_question"]) > 0
    assert len(out["compressed_question"]) <= len(q)


def test_final_question_preserved():
    body = " ".join(f"Thông tin {i}." for i in range(400))
    final_q = "Theo đoạn văn, thủ đô được nhắc đến là gì?"
    q = f"Nội dung: {body} {final_q}"
    out = compress_passage(q, ["Hà Nội", "Huế"], max_context_chars=600)
    # The trailing question should survive compression.
    assert "thủ đô" in out["compressed_question"]


def test_compressor_does_not_modify_choices():
    choices = ["a", "b", "c", "d"]
    snapshot = list(choices)
    q = "Nội dung: " + ("x " * 2000) + " Câu hỏi?"
    out = compress_passage(q, choices, max_context_chars=400)
    # choices list is untouched, and never appears injected into the question.
    assert choices == snapshot
    assert "compressed_question" in out
    assert "choices" not in out  # compressor only returns the question + stats


def test_relevant_evidence_selected():
    # One sentence mentions the query term "rồng"; it should be kept.
    filler = " ".join(f"Câu lấp đầy số {i}." for i in range(300))
    q = (f"Nội dung: {filler} Con rồng xuất hiện ở chương cuối. {filler} "
         "Theo đoạn văn, con vật nào xuất hiện ở chương cuối?")
    out = compress_passage(q, ["rồng", "hổ", "voi", "rắn"], max_context_chars=400)
    assert "rồng" in out["compressed_question"]


def test_stats_fields_present():
    q = "Nội dung: " + ("dữ liệu " * 500) + " Hỏi gì?"
    out = compress_passage(q, ["a", "b"], max_context_chars=400)
    for key in ("original_chars", "compressed_chars", "compression_ratio",
                "chunks_total", "chunks_kept", "kept_chunk_indices", "method",
                "was_compressed"):
        assert key in out["stats"]


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
