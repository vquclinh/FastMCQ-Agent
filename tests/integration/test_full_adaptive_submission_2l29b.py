"""Tests for Phase 2L.29B: one-command full adaptive submission runner."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "") + "_t",
                                                  next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{name}")), _ROOT / "scripts" / name))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def _fixture(d, n=2):
    inp = Path(d) / "in.json"
    inp.write_text(json.dumps([{"qid": f"q{i}", "question": "Q?", "choices": ["A", "B"]}
                               for i in range(1, n + 1)]))
    base = Path(d) / "v10.csv"
    base.write_text("qid,answer\n" + "\n".join(f"q{i},A" for i in range(1, n + 1)) + "\n")
    plan = Path(d) / "plan.csv"
    plan.write_text("qid,route,recommended_layer,priority_score\n"
                    + "\n".join(f"q{i},calculation,cheap_api,2.0" for i in range(1, n + 1)) + "\n")
    return str(inp), str(base), str(plan)


def _base_args(d, inp, base, plan, **over):
    a = {"--input": inp, "--base-pred": base, "--plan": plan,
         "--work-dir": f"{d}/scratch/wd", "--output": f"{d}/output/sub.csv",
         "--mode": "cheap", "--model": "qwen/qwen3.5-9b-20260310"}
    a.update(over)
    out = []
    for k, v in a.items():
        out += [k] if v is None else [k, str(v)]
    return out


# --- dry-run ------------------------------------------------------------------

def test_dry_run_no_api_no_outputs(monkeypatch):
    import src.api.selective_api_client as sac
    monkeypatch.setattr(sac, "SelectiveAPIClient",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no API in dry-run")))
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    rc = mod.main(_base_args(d, inp, base, plan) + ["--dry-run"])
    assert rc == 0
    assert not Path(f"{d}/output/sub.csv").exists()


# --- guards -------------------------------------------------------------------

def test_execute_requires_ack():
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    try:
        mod.main(_base_args(d, inp, base, plan) + ["--execute"])
        assert False
    except SystemExit as e:
        assert "i-understand" in str(e).lower()


def test_protected_output_name_rejected():
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    try:
        mod.main(_base_args(d, inp, base, plan, **{"--output": "output/pred.csv"}) + ["--dry-run"])
        assert False
    except SystemExit as e:
        assert "protected" in str(e).lower()


def test_disallowed_model_rejected():
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    try:
        mod.main(_base_args(d, inp, base, plan, **{"--model": "gpt-4o"}) + ["--dry-run"])
        assert False
    except ValueError:
        pass


def test_output_must_be_under_outputs():
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    try:
        mod.main(_base_args(d, inp, base, plan, **{"--output": f"{d}/scratch/sub.csv"}) + ["--dry-run"])
        assert False
    except SystemExit as e:
        assert "output/" in str(e)


def test_work_dir_must_be_under_scratch():
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    try:
        mod.main(_base_args(d, inp, base, plan, **{"--work-dir": f"{d}/output/wd"}) + ["--dry-run"])
        assert False
    except SystemExit as e:
        assert "scratch/" in str(e)


def test_mutually_exclusive():
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    try:
        mod.main(_base_args(d, inp, base, plan) + ["--dry-run", "--execute"])
        assert False
    except SystemExit as e:
        assert "mutually exclusive" in str(e)


# --- order of operations (fakes) ---------------------------------------------

def test_execute_calls_generation_then_build_in_order(monkeypatch):
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)
    calls = []

    class _FakeAdaptive:
        def main(self, argv):
            calls.append("adaptive")
            # write the candidates file the wrapper expects
            wd = argv[argv.index("--output-dir") + 1]
            Path(wd).mkdir(parents=True, exist_ok=True)
            (Path(wd) / "adaptive_api_candidates.jsonl").write_text(
                json.dumps({"qid": "q1", "agent": "calculation_solver", "answer": "A",
                            "parse_status": "ok", "evidence": "x"}) + "\n")
            return 0

    class _FakeVariant:
        def main(self, argv):
            calls.append("variant")
            out = argv[argv.index("--output") + 1]
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader()
                w.writerow({"qid": "q1", "answer": "A"}); w.writerow({"qid": "q2", "answer": "A"})
            return 0

    def _fake_loader(name):
        return _FakeAdaptive() if "adaptive" in name else _FakeVariant()
    monkeypatch.setattr(mod, "_load_script", _fake_loader)

    rc = mod.main(_base_args(d, inp, base, plan) + ["--execute", "--i-understand-this-writes-outputs"])
    assert rc == 0
    assert calls == ["adaptive", "variant"]            # generation BEFORE build
    pred = {r["qid"]: r["answer"] for r in csv.DictReader(open(f"{d}/output/sub.csv"))}
    assert set(pred) == {"q1", "q2"}                   # validated full output


def test_execute_validates_output_qid_set(monkeypatch):
    mod = _load("run_full_adaptive_submission.py")
    d = tempfile.mkdtemp(); inp, base, plan = _fixture(d)

    class _FakeAdaptive:
        def main(self, argv):
            wd = argv[argv.index("--output-dir") + 1]
            Path(wd).mkdir(parents=True, exist_ok=True)
            (Path(wd) / "adaptive_api_candidates.jsonl").write_text("")
            return 0

    class _FakeVariant:
        def main(self, argv):
            out = argv[argv.index("--output") + 1]
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", newline="") as fh:   # writes only q1 -> qid set mismatch
                w = csv.DictWriter(fh, fieldnames=["qid", "answer"]); w.writeheader()
                w.writerow({"qid": "q1", "answer": "A"})
            return 0
    monkeypatch.setattr(mod, "_load_script",
                        lambda n: _FakeAdaptive() if "adaptive" in n else _FakeVariant())
    try:
        mod.main(_base_args(d, inp, base, plan) + ["--execute", "--i-understand-this-writes-outputs"])
        assert False
    except SystemExit as e:
        assert "row-count" in str(e).lower() or "qid set" in str(e).lower()


def test_no_qid_hardcoding():
    src = (next(iter((_ROOT / "scripts" / "legacy").glob("**/run_full_adaptive_submission.py")))).read_text()
    assert not re.search(r"\btest_\d{4}\b", src)
