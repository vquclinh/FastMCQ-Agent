"""Tests for in-question evidence reranking (no network, no model, no qid).

Runnable with pytest, or standalone: ``python tests/test_evidence_reranker.py``.
Synthetic samples only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.evidence.evidence_reranker import (  # noqa: E402
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


# --- neural backend adapter (Phase 2L.6): all fail closed to lexical ---------

from src.evidence.evidence_reranker import build_neural_scorer  # noqa: E402


class _FakeNeuralScorer:
    """Deterministic fake: scores chunks by a keyword so ranking is predictable."""

    def __init__(self, keyword):
        self.keyword = keyword

    def score(self, query, chunks):
        return [1.0 if self.keyword in c.text else 0.0 for c in chunks]


def test_lexical_default_effective_method():
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2)
    assert r.matched and r.diagnostics["effective_method"] == "hybrid_lexical"
    assert r.diagnostics["requested_method"] == "hybrid_lexical"


def test_neural_missing_dependency_falls_back_lexical():
    # method=reranker but no model path / dep -> lexical, with a fallback reason.
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2,
                                   method="reranker", optional_reranker_model=None)
    assert r.matched and r.diagnostics["effective_method"] == "hybrid_lexical"
    assert r.diagnostics["neural_available"] is False
    assert "no_reranker_model_path" in (r.diagnostics["neural_fallback_reason"] or "")


def test_build_neural_scorer_reports_unavailable():
    for method in ("embedding", "reranker"):
        scorer, avail, reason = build_neural_scorer(method, None, None)
        assert scorer is None and avail is False and reason


def test_fake_neural_scorer_changes_ranking():
    # Inject a fake scorer that ranks the chunk containing "Nile/Cairo" top.
    s = _titled_sample()
    r = rerank_evidence_for_sample(s, max_chars=2500, top_k=1, candidate_top_k=12,
                                   method="reranker", neural_scorer=_FakeNeuralScorer("Cairo"))
    assert r.matched and r.diagnostics["effective_method"] == "reranker"
    assert r.diagnostics["neural_available"] is True
    assert "Cairo" in r.selected_text


def test_candidate_top_k_limits_stage1():
    s = _titled_sample()
    r = rerank_evidence_for_sample(s, max_chars=2500, top_k=2, candidate_top_k=1,
                                   method="reranker", neural_scorer=_FakeNeuralScorer("zzz"))
    # Only 1 candidate is fed to the neural stage.
    assert r.diagnostics["candidate_chunk_count"] == 1


def test_neural_no_fallback_returns_unmatched_on_error():
    class _Boom:
        def score(self, q, chunks):
            raise RuntimeError("boom")
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2,
                                   method="reranker", neural_scorer=_Boom(),
                                   neural_fallback_to_lexical=False)
    assert not r.matched and "neural_error" in (r.diagnostics.get("reason") or "")


def test_neural_error_falls_back_lexical_by_default():
    class _Boom:
        def score(self, q, chunks):
            raise RuntimeError("boom")
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2000, top_k=2,
                                   method="reranker", neural_scorer=_Boom())
    assert r.matched and r.diagnostics["effective_method"] == "hybrid_lexical"
    assert "neural_error" in (r.diagnostics["neural_fallback_reason"] or "")


# --- Phase 2L.10: transformers-native local backend selection (fakes only) ----

import json as _json2  # noqa: E402
import tempfile  # noqa: E402

import src.evidence.evidence_reranker as _er  # noqa: E402
from src.evidence.evidence_reranker import (  # noqa: E402
    _looks_like_bge_m3,
    _looks_like_qwen3_reranker,
)


def _make_model_dir(name, config):
    d = Path(tempfile.mkdtemp(prefix="model_")) / name
    d.mkdir(parents=True)
    (d / "config.json").write_text(_json2.dumps(config))
    return d


def test_looks_like_bge_m3_by_name_and_arch():
    by_name = _make_model_dir("bge-m3", {})
    by_arch = _make_model_dir("some-embed", {"architectures": ["XLMRobertaModel"]})
    not_bge = _make_model_dir("random-llm", {"architectures": ["LlamaForCausalLM"]})
    assert _looks_like_bge_m3(by_name) and _looks_like_bge_m3(by_arch)
    assert not _looks_like_bge_m3(not_bge)


def test_looks_like_qwen3_reranker_requires_name_and_arch():
    ok = _make_model_dir("qwen3-reranker-0.6b", {"architectures": ["Qwen3ForCausalLM"]})
    plain_qwen = _make_model_dir("qwen3.5-9b", {"architectures": ["Qwen3ForCausalLM"]})
    assert _looks_like_qwen3_reranker(ok)
    assert not _looks_like_qwen3_reranker(plain_qwen)  # no "reranker" in name


def test_build_selects_bge_m3_backend(monkeypatch):
    captured = {}

    class _FakeBge:
        def __init__(self, path):
            captured["path"] = str(path)

        def score(self, q, chunks):
            return [1.0] * len(chunks)

    monkeypatch.setattr(_er, "TransformersBgeM3EmbeddingScorer", _FakeBge)
    monkeypatch.setattr(_er, "_dep_available", lambda name: name in ("transformers", "torch"))
    path = _make_model_dir("bge-m3", {"architectures": ["XLMRobertaModel"]})
    scorer, ok, reason = _er.build_neural_scorer("embedding", path, None)
    assert ok and reason is None and isinstance(scorer, _FakeBge)
    assert captured["path"] == str(path)


def test_build_selects_qwen3_reranker_backend(monkeypatch):
    class _FakeQwen:
        def __init__(self, path):
            pass

        def score(self, q, chunks):
            return [0.5] * len(chunks)

    monkeypatch.setattr(_er, "TransformersQwen3RerankerScorer", _FakeQwen)
    monkeypatch.setattr(_er, "_dep_available", lambda name: name in ("transformers", "torch"))
    path = _make_model_dir("qwen3-reranker-0.6b", {"architectures": ["Qwen3ForCausalLM"]})
    scorer, ok, reason = _er.build_neural_scorer("reranker", None, path)
    assert ok and reason is None and isinstance(scorer, _FakeQwen)


def test_build_missing_path_fails_closed():
    s, ok, reason = _er.build_neural_scorer("embedding", "/nonexistent/model/dir", None)
    assert s is None and not ok and reason == "embedding_model_path_not_found"


def test_build_unsupported_path_fails_closed():
    bad = _make_model_dir("mystery-model", {"architectures": ["LlamaForCausalLM"]})
    s, ok, reason = _er.build_neural_scorer("embedding", bad, None)
    assert s is None and not ok and reason == "unsupported_embedding_model_path"


def test_build_bge_missing_transformers_fails_closed(monkeypatch):
    monkeypatch.setattr(_er, "_dep_available", lambda name: False)
    path = _make_model_dir("bge-m3", {"architectures": ["XLMRobertaModel"]})
    s, ok, reason = _er.build_neural_scorer("embedding", path, None)
    assert s is None and not ok and reason == "dependency_missing:transformers"


# --- Phase 2L.12: model cache + batched scoring + OOM retry (fakes only) ------

import types  # noqa: E402

from src.evidence.evidence_reranker import (  # noqa: E402
    TransformersQwen3RerankerScorer,
    _cached,
    clear_neural_model_cache,
    neural_model_cache_size,
)


class _CountingScorer:
    loads = 0

    def __init__(self, path):
        type(self).loads += 1
        self.path = str(path)

    def score(self, q, chunks):
        return [0.0] * len(chunks)


def test_model_cache_prevents_repeated_loads():
    clear_neural_model_cache()
    _CountingScorer.loads = 0
    s1, hit1, secs1 = _cached(_CountingScorer, ".")
    s2, hit2, secs2 = _cached(_CountingScorer, ".")
    assert _CountingScorer.loads == 1            # constructed once only
    assert hit1 is False and hit2 is True
    assert s1 is s2 and secs2 == 0.0
    clear_neural_model_cache()


def test_cache_key_includes_path_and_type():
    clear_neural_model_cache()
    _CountingScorer.loads = 0
    _cached(_CountingScorer, ".")
    _cached(_CountingScorer, "tests")            # different path -> new load
    assert _CountingScorer.loads == 2
    assert neural_model_cache_size() == 2
    clear_neural_model_cache()
    assert neural_model_cache_size() == 0


def test_cache_clear_helper_resets():
    clear_neural_model_cache()
    _cached(_CountingScorer, ".")
    assert neural_model_cache_size() == 1
    clear_neural_model_cache()
    assert neural_model_cache_size() == 0


def test_qwen_reranker_batched_oom_retry_shrinks_batch():
    # Exercise the real score() retry loop without loading weights.
    obj = TransformersQwen3RerankerScorer.__new__(TransformersQwen3RerankerScorer)
    obj._torch = types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda: None))
    obj.device = "cpu"
    obj.batch_size = 8
    calls = []

    def fake_score_prompts(prompts, bs):
        calls.append(bs)
        if bs > 2:
            raise RuntimeError("CUDA out of memory: tried to allocate ...")
        return [0.5] * len(prompts)

    obj._score_prompts = fake_score_prompts
    chunks = [types.SimpleNamespace(text=f"c{i}") for i in range(3)]
    scores = TransformersQwen3RerankerScorer.score(obj, "q", chunks)
    assert len(scores) == 3                      # one score per chunk
    assert calls == [8, 4, 2]                    # shrank 8 -> 4 -> 2 on OOM


def test_is_oom_detection():
    assert TransformersQwen3RerankerScorer._is_oom(RuntimeError("CUDA out of memory"))
    assert not TransformersQwen3RerankerScorer._is_oom(ValueError("bad input"))


def test_cached_load_error_propagates_and_fails_closed(monkeypatch):
    class _Boom:
        def __init__(self, path):
            raise RuntimeError("explode")
    # Route the bge path to _Boom; build_neural_scorer must fail closed (no raise).
    bad = _make_model_dir("bge-m3", {"architectures": ["XLMRobertaModel"]})
    monkeypatch.setattr(_er, "TransformersBgeM3EmbeddingScorer", _Boom)
    monkeypatch.setattr(_er, "_dep_available", lambda name: name in ("transformers", "torch"))
    clear_neural_model_cache()
    s, ok, reason = _er.build_neural_scorer("embedding", bad, None)
    assert s is None and not ok and reason.startswith("load_error:")


def test_rerank_sets_batch_size_and_records_timing():
    # Injected fake with a batch_size attribute -> rerank sets it + records diagnostics.
    class _BS:
        def __init__(self):
            self.batch_size = 1
        def score(self, q, chunks):
            return [1.0 if "Cairo" in c.text else 0.0 for c in chunks]
    fake = _BS()
    r = rerank_evidence_for_sample(_titled_sample(), max_chars=2500, top_k=1,
                                   candidate_top_k=12, method="reranker",
                                   neural_batch_size=4, neural_scorer=fake)
    assert r.matched and fake.batch_size == 4
    assert r.diagnostics["batch_size"] == 4
    assert r.diagnostics["pair_count"] >= 1
    assert r.diagnostics["score_seconds"] >= 0.0


def test_no_web_or_eval_in_source():
    import re as _re
    src = Path(__file__).resolve().parents[2].joinpath("src/evidence/evidence_reranker.py").read_text()
    # No network clients and no dynamic code execution.
    for bad in ("import requests", "import urllib", "import httpx", "import socket",
                "__import__", "hf_hub_download", "snapshot_download"):
        assert bad not in src, f"unexpected '{bad}' in evidence_reranker.py"
    # Bare eval(/exec( only — torch's `.eval()` (model eval mode) is allowed.
    for pat in (r"(?<![.\w])eval\(", r"(?<![.\w])exec\("):
        assert not _re.search(pat, src), f"unexpected dynamic execution '{pat}'"
    # Every model load must be local-only (no implicit download).
    for m in _re.finditer(r"\.from_pretrained\(", src):
        window = src[m.start(): m.start() + 200]
        assert "local_files_only=True" in window, "from_pretrained without local_files_only"
    # No qid is read for decisions.
    for pat in (r'\[\s*["\']qid', r'\.get\(\s*["\']qid'):
        assert not _re.search(pat, src)


class _StandaloneMonkeypatch:
    """Minimal monkeypatch shim so fixture-using tests run in standalone mode."""

    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value=None):
        obj, attr = (target, name) if value is not None else (None, None)
        if value is None:  # not used in this file's call style
            raise NotImplementedError
        self._undo.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, value)

    def undo(self):
        for obj, attr, old in reversed(self._undo):
            setattr(obj, attr, old)


if __name__ == "__main__":
    import inspect
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            mp = None
            try:
                if "monkeypatch" in inspect.signature(fn).parameters:
                    mp = _StandaloneMonkeypatch(); fn(mp)
                else:
                    fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {name}: {exc}")
            finally:
                if mp is not None:
                    mp.undo()
    raise SystemExit(1 if failures else 0)
