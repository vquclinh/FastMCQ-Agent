"""Tests for the selective multi-candidate API layer (Phase 2L.26A; no real API)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src import api_candidate_agents as agents  # noqa: E402
from src.answer_factory import build_candidate_pool  # noqa: E402
from src.answer_ranker import select_answer  # noqa: E402
from src.candidate_answer import AnswerCandidate  # noqa: E402
from src.selective_api_client import SelectiveAPIClient  # noqa: E402

_S = {"qid": "x", "question": "Tính 2+2?", "choices": ["3", "4", "5", "6"]}


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), _ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Res:
    def __init__(self, content):
        self.content = content
        self.usage = {"total_tokens": 10}


class _FakeRawClient:
    def __init__(self, content='{"answer":"B","confidence":0.9,"risk":"low"}'):
        self.content = content
        self.calls = 0

    def chat(self, messages, **kw):
        self.calls += 1
        return _Res(self.content)


# --- prompt builders + parsers ------------------------------------------------

def test_builders_include_labels_and_route_instructions():
    for route, marker in (("calculation", "TÍNH TOÁN"), ("law_admin", "KHÔNG từ chối"),
                          ("long_context", "NGỮ CẢNH")):
        msgs = agents.build_route_specialist(_S, route, evidence="ev")
        assert marker in msgs[0]["content"]
        assert "A. 3" in msgs[1]["content"] and '"answer"' in msgs[0]["content"]


def test_parser_accepts_valid_rejects_invalid():
    assert agents.parse_candidate('{"answer":"B","confidence":0.9}', _S)["answer"] == "B"
    assert agents.parse_candidate('{"answer":"Z"}', _S)["parse_status"] == "no_valid_label"
    assert agents.parse_candidate("not json", _S)["parse_status"] == "no_json"


def test_judge_parser():
    j = agents.parse_judge('{"winner_answer":"B","confidence":0.8,"requires_manual_review":false}', _S)
    assert j["winner_answer"] == "B" and j["requires_manual_review"] is False


# --- client guard -------------------------------------------------------------

def test_client_blocks_disallowed_model():
    for bad in ("gpt-4o", "claude-3", "gemini-1.5", "qwen/qwen3.5-32b"):
        try:
            SelectiveAPIClient(bad)
            assert False, f"should block {bad}"
        except ValueError:
            pass


def test_client_runs_with_fake_and_allowed_model():
    c = SelectiveAPIClient("qwen/qwen3.5-9b", client=_FakeRawClient())
    content, usage = c.chat([{"role": "user", "content": "hi"}])
    assert json.loads(content)["answer"] == "B" and c.total_calls == 1


# --- runner: dry-run, guards, fake execute, resume ---------------------------

def _tiny_inputs(d):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": "q1", "question": "Tính 2+2?", "choices": ["3", "4", "5"]},
                               {"qid": "q2", "question": "Thủ đô Pháp?", "choices": ["Paris", "Lyon"]}]))
    base = Path(d) / "v10.csv"
    base.write_text("qid,answer\nq1,A\nq2,A\n")
    plan = Path(d) / "plan.csv"
    plan.write_text("qid\nq1\nq2\n")
    return str(inp), str(base), str(plan)


def test_runner_dry_run_makes_no_api_call(capsys):
    mod = _load("run_selective_multicandidate_api.py")
    d = tempfile.mkdtemp()
    inp, base, plan = _tiny_inputs(d)
    rc = mod.main(["--input", inp, "--base-pred", base, "--plan", plan,
                   "--output-dir", "scratch/_t_dryrun", "--max-qids", "5"])
    out = capsys.readouterr().out
    assert rc == 0 and "DRY-RUN" in out and "upper-bound calls" in out


def test_runner_rejects_disallowed_model():
    mod = _load("run_selective_multicandidate_api.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--model", "gpt-4o"])
        assert False
    except ValueError:
        pass


def test_runner_dry_run_execute_mutually_exclusive():
    mod = _load("run_selective_multicandidate_api.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--dry-run", "--execute"])
        assert False
    except SystemExit as e:
        assert "mutually exclusive" in str(e)


def test_runner_refuses_non_scratch_output():
    mod = _load("run_selective_multicandidate_api.py")
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--plan", "z", "--output-dir", "output/foo"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


def test_runner_fake_execute_writes_jsonl_and_resume(monkeypatch):
    import src.selective_api_client as sac
    mod = _load("run_selective_multicandidate_api.py")
    d = tempfile.mkdtemp()
    inp, base, plan = _tiny_inputs(d)
    outdir = Path(d) / "scratch" / "out"      # under scratch/ token

    class _FakeSelective:
        def __init__(self, model, **kw):
            from src.model_policy import assert_allowed_llm_model
            assert_allowed_llm_model(model)   # keep the guard
            self.model = model; self.total_calls = 0; self.total_tokens = 0

        def chat(self, messages, **kw):
            self.total_calls += 1
            return '{"answer":"A","confidence":0.9,"risk":"low"}', {"total_tokens": 5}

    monkeypatch.setattr(sac, "SelectiveAPIClient", _FakeSelective)
    rc = mod.main(["--input", inp, "--base-pred", base, "--plan", plan,
                   "--output-dir", str(outdir), "--max-qids", "2",
                   "--agents", "route_specialist", "--judge", "none",
                   "--temperature-grid", "0", "--execute"])
    assert rc == 0
    jsonl = outdir / "api_candidates.jsonl"
    assert jsonl.exists()
    n_first = len([l for l in jsonl.read_text().splitlines() if l.strip()])
    assert n_first >= 1
    # resume: a second run with --resume should not duplicate completed (qid,agent,temp)
    rc2 = mod.main(["--input", inp, "--base-pred", base, "--plan", plan,
                    "--output-dir", str(outdir), "--max-qids", "2",
                    "--agents", "route_specialist", "--judge", "none",
                    "--temperature-grid", "0", "--execute", "--resume"])
    n_second = len([l for l in jsonl.read_text().splitlines() if l.strip()])
    assert rc2 == 0 and n_second == n_first   # resume skipped already-done work


# --- v11 builder + ranker -----------------------------------------------------

def test_v11_builder_refuses_outputs_path():
    mod = _load("build_v11_from_api_candidates.py")
    try:
        mod.main(["--input", "x", "--api-candidates", "y", "--output-dir", "output/foo"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


# A non-deterministic question (no tool fires) so only the API candidates populate.
_S_KNOW = {"qid": "k", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon", "Nice", "Huế"]}


def test_ranker_keeps_v10_when_single_api_candidate_weak():
    pool = build_candidate_pool(_S_KNOW, "A", {"route": "short_knowledge", "confidence": 0.5})
    pool.add(AnswerCandidate("k", "B", "api:route_specialist", confidence=0.8,
                             risk_level="medium", evidence_text="some"))
    ans, rec = select_answer(pool, _S_KNOW, "A")
    assert ans == "A" and rec["decision"] == "keep_base"


def test_ranker_overrides_on_multi_agent_consensus_with_evidence():
    pool = build_candidate_pool(_S_KNOW, "A", {"route": "short_knowledge", "confidence": 0.5})
    for ag in ("api:route_specialist", "api:challenger", "api:option_elimination"):
        # Real (non-placeholder) evidence so the consistency guard accepts it.
        pool.add(AnswerCandidate("k", "B", ag, confidence=0.8, risk_level="medium",
                                 evidence_text="Lyon là lựa chọn đúng theo lập luận chi tiết của tác nhân."))
    ans, rec = select_answer(pool, _S_KNOW, "A")
    assert ans == "B" and rec["decision"] == "override"
    assert rec["selected_source"] == "multi_agent_consensus" and rec["requires_manual_review"]


def test_no_qid_hardcoding_in_new_sources():
    import re as _re
    for rel in ("src/api_candidate_agents.py", "src/selective_api_client.py",
                "scripts/run_selective_multicandidate_api.py",
                "scripts/build_v11_from_api_candidates.py", "scripts/review_v11_api_candidate.py"):
        src = (_ROOT / rel).read_text()
        for pat in (r'qid\s*==', r'==\s*["\']test_0', r'test_0\d{3}'):
            assert not _re.search(pat, src), f"{pat} in {rel}"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
