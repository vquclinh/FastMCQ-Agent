"""Phase 2L.47A/2L.47B — official BTC submission contract (predict.py / inference.sh).

The FINAL path is OFFLINE local-model inference; tests stub the local backend so they never
download or load the real Qwen model and never call any external API. predict.py must write
/code/submission.csv (qid,answer) + /code/submission_time.csv (qid,answer,time) with REAL,
positive per-sample time, resolve the BTC JSON input, and preserve /output/pred.csv mirroring.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _predict():
    spec = importlib.util.spec_from_file_location("predict_btc", _ROOT / "predict.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class _FakePredictor:
    """Deterministic stand-in for the local Qwen model (no torch, no weights, no network)."""
    def __init__(self, *a, **k):
        pass

    def load(self):
        return self

    def predict_one(self, item):
        # 'B' when the question mentions "2 + 2", else None -> exercises the deterministic fallback.
        return "B" if "2 + 2" in str(item.get("question", "")) else None


def _stub_local(mod, monkeypatch):
    monkeypatch.setattr(mod, "_build_predictor", lambda args: _FakePredictor().load())


def _write_json(path, qids):
    samples = [{"qid": q, "question": "2 + 2 bằng bao nhiêu?", "choices": ["3", "4", "5", "6"]}
               for q in qids]
    path.write_text(json.dumps(samples, ensure_ascii=False))
    return path


def _read_rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


# --- predict.py writes both BTC files via the (stubbed) local model ----------

def test_predict_writes_submission_and_time(tmp_path, monkeypatch):
    mod = _predict(); _stub_local(mod, monkeypatch)
    inp = _write_json(tmp_path / "private_test.json", ["btc1", "btc2", "btc3"])
    sub = tmp_path / "submission.csv"
    subt = tmp_path / "submission_time.csv"
    rc = mod.main(["--input", str(inp), "--submission", str(sub), "--submission-time", str(subt)])
    assert rc == 0 and sub.exists() and subt.exists()

    srows, trows = _read_rows(sub), _read_rows(subt)
    assert srows[0] == ["qid", "answer"]
    assert trows[0] == ["qid", "answer", "time"]
    assert [r[0] for r in srows[1:]] == ["btc1", "btc2", "btc3"]
    assert [r[0] for r in trows[1:]] == ["btc1", "btc2", "btc3"]
    assert [r[1] for r in srows[1:]] == [r[1] for r in trows[1:]]
    for r in trows[1:]:
        assert float(r[2]) >= 0.0          # measured per sample, non-negative
    # model answered every "2 + 2" question with B
    assert all(r[1] == "B" for r in srows[1:])


def test_per_sample_time_measured_around_each_sample(tmp_path, monkeypatch):
    mod = _predict()

    class _Slow(_FakePredictor):
        def predict_one(self, item):
            import time as _t
            _t.sleep(0.01)
            return "A"
    monkeypatch.setattr(mod, "_build_predictor", lambda args: _Slow())
    inp = _write_json(tmp_path / "private_test.json", ["s1", "s2"])
    sub = tmp_path / "s.csv"; subt = tmp_path / "t.csv"
    assert mod.main(["--input", str(inp), "--submission", str(sub), "--submission-time", str(subt)]) == 0
    # each per-sample time reflects the ~10ms sleep (measured around predict_one, not an average)
    for r in _read_rows(subt)[1:]:
        assert float(r[2]) >= 0.008


def test_fallback_when_model_returns_nothing(tmp_path, monkeypatch):
    mod = _predict()
    monkeypatch.setattr(mod, "_build_predictor",
                        lambda args: type("P", (), {"load": lambda s: s,
                                                     "predict_one": lambda s, i: None})())
    inp = _write_json(tmp_path / "private_test.json", ["f1", "f2"])
    sub = tmp_path / "s.csv"; subt = tmp_path / "t.csv"
    assert mod.main(["--input", str(inp), "--submission", str(sub), "--submission-time", str(subt)]) == 0
    assert all(r[1] == "A" for r in _read_rows(sub)[1:])        # deterministic fallback label


def test_default_model_path(monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)
    from src.local_model.qwen_mcq_predictor import DEFAULT_MODEL_PATH
    assert DEFAULT_MODEL_PATH == "/models/qwen3-4b-instruct-2507"


def test_env_overrides_for_outputs(tmp_path, monkeypatch):
    mod = _predict(); _stub_local(mod, monkeypatch)
    inp = _write_json(tmp_path / "private_test.json", ["e1", "e2"])
    sub = tmp_path / "env_submission.csv"; subt = tmp_path / "env_time.csv"
    monkeypatch.setenv("SUBMISSION_FILE", str(sub))
    monkeypatch.setenv("SUBMISSION_TIME_FILE", str(subt))
    assert mod.main(["--input", str(inp)]) == 0
    assert _read_rows(sub)[0] == ["qid", "answer"]
    assert _read_rows(subt)[0] == ["qid", "answer", "time"]


def test_mirrors_legacy_output(tmp_path, monkeypatch):
    mod = _predict(); _stub_local(mod, monkeypatch)
    inp = _write_json(tmp_path / "private_test.json", ["m1", "m2"])
    sub = tmp_path / "s.csv"; subt = tmp_path / "t.csv"; legacy = tmp_path / "pred.csv"
    assert mod.main(["--input", str(inp), "--submission", str(sub),
                     "--submission-time", str(subt), "--output", str(legacy)]) == 0
    assert legacy.exists() and _read_rows(legacy)[0] == ["qid", "answer"]
    assert [r[0] for r in _read_rows(legacy)[1:]] == ["m1", "m2"]


def test_input_priority_code_first(monkeypatch):
    monkeypatch.delenv("INPUT_FILE", raising=False)
    mod = _predict()
    assert mod._resolve_input("x.json") == "x.json"
    monkeypatch.setenv("INPUT_FILE", "/env/in.json")
    assert mod._resolve_input(None) == "/env/in.json"
    assert mod._INPUT_CANDIDATES[0] == "/code/private_test.json"
    assert "/app/data/private_test.json" in mod._INPUT_CANDIDATES


def test_default_official_output_paths(monkeypatch):
    mod = _predict()
    monkeypatch.setattr(mod.Path, "is_dir", lambda self: str(self) == "/code")
    assert mod._resolve_out(None, None, "submission.csv") == "/code/submission.csv"
    assert mod._resolve_out(None, None, "submission_time.csv") == "/code/submission_time.csv"


# --- optional local selective wrapper shape ----------------------------------

def test_run_full_system_wrapper_is_local_only():
    sh = (_ROOT / "scripts" / "run_full_system.sh").read_text()
    assert "local_selective_auto" in sh
    assert "python" in sh and "final_infer.py" in sh
    r = subprocess.run(["bash", "-n", str(_ROOT / "scripts" / "run_full_system.sh")],
                       cwd=str(_ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- Dockerfile / inference.sh / download shape (offline local model) --------

def test_dockerfile_offline_local_model_shape():
    df = (_ROOT / "Dockerfile").read_text()
    assert "WORKDIR /code" in df
    assert "inference.sh" in df
    assert "COPY . /code" in df
    assert "nvidia/cuda:12.8" in df                       # CUDA 12.8+ base for BTC GPU
    assert "torch==2.7.1" in df and "https://download.pytorch.org/whl/cu128" in df
    assert "download_local_model.py" in df                # weights baked at build time
    assert "ARG SKIP_MODEL_DOWNLOAD=0" in df              # final builds download the real model
    assert "TRANSFORMERS_OFFLINE=1" in df and "HF_HUB_OFFLINE=1" in df   # offline runtime
    assert "LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507" in df
    assert 'CMD ["bash", "inference.sh"]' in df           # BTC template startup shape
    assert "ENTRYPOINT" not in df
    assert "external model provider" in df


def test_download_script_targets_qwen3_4b():
    src = (_ROOT / "scripts" / "download_local_model.py").read_text()
    assert "Qwen/Qwen3-4B-Instruct-2507" in src
    assert "/models/qwen3-4b-instruct-2507" in src
    assert "snapshot_download" in src


def test_inference_sh_calls_predict():
    sh = (_ROOT / "inference.sh").read_text()
    assert "predict.py" in sh
    r = subprocess.run(["bash", "-n", str(_ROOT / "inference.sh")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_predict_default_is_offline_local_not_api():
    src = (_ROOT / "predict.py").read_text()
    assert "qwen_mcq_predictor" in src or "local_model" in src
    # the default path must not run the optional selective pipeline.
    assert "--legacy-dynamic-full" in src
    import py_compile
    py_compile.compile(str(_ROOT / "predict.py"), doraise=True)


# --- secret / model-weight hygiene -------------------------------------------

def test_no_secret_or_weights_tracked():
    tracked = subprocess.run(["git", "ls-files"], cwd=str(_ROOT),
                             capture_output=True, text=True).stdout.splitlines()
    api_dockerfile = "Dockerfile." + "api"
    for bad in (".env", api_dockerfile, api_dockerfile + ".local"):
        assert bad not in [t.strip() for t in tracked], bad
    assert not any(t.startswith("models/") and t.endswith((".safetensors", ".bin", ".pt"))
                   for t in tracked), "model weights must not be tracked"


def test_required_root_submission_files_exist():
    for name in ("Dockerfile", "predict.py", "inference.sh", "README.md", "requirements.txt"):
        assert (_ROOT / name).exists(), name


def test_btc_2l47d_docs_document_manual_docker_checks():
    docs = "\n".join([
        (_ROOT / "README.md").read_text(),
        (_ROOT / "DOCKER_SUBMISSION.md").read_text(),
        (_ROOT / "docs" / "BTC_SUBMISSION_COMPLIANCE.md").read_text(),
    ])
    assert "docker build -t vquclinh/fastmcq-agent:latest ." in docs
    assert '-v "$PWD/btc_data:/app/data:ro"' in docs
    assert "/app/data/private_test.json" in docs
    assert '-e SUBMISSION_FILE=/code/btc_output/submission.csv' in docs
    assert '-e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv' in docs
    assert "docker run --rm --gpus all --network none" in docs
    assert "docker push vquclinh/fastmcq-agent:latest" in docs
    assert "no `--ipc=host`" in docs or "`--ipc=host` is NOT required" in docs
    assert "no `--shm-size`" in docs or "`--shm-size` is NOT required" in docs
    assert "no vLLM" in docs
    assert "CUDA 12.2" in docs and "CUDA 12.8+" in docs
    assert "BTC confirmed CUDA 12.8+" in docs
    assert "`uv`" in docs and "`--torch-backend=cu128`" in docs


def test_btc_2l47e_readme_repository_sections():
    text = (_ROOT / "README.md").read_text()
    for heading in ("## Pipeline Flow", "## Data Processing", "## Resource Initialization"):
        assert heading in text
    assert "Question/choice normalization" in text
    assert "/code/private_test.json" in text and "/app/data/private_test.json" in text
    assert "No vector database is used" in text
    assert "No external index is used" in text
    assert "No retrieval database is required" in text
    assert "submission.csv:" in text and "submission_time.csv:" in text


def test_requirements_are_exact_pinned_and_final_docker_uses_only_requirements_txt():
    req = (_ROOT / "requirements.txt").read_text()
    deps = []
    for raw in req.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        deps.append(line)
    assert deps, "requirements.txt should list direct dependencies"
    assert all("==" in d and ">=" not in d and "<=" not in d and "~=" not in d for d in deps), deps
    assert not any(d.startswith("torch") for d in deps), "torch is installed from Dockerfile cu128"

    df = (_ROOT / "Dockerfile").read_text()
    assert "python -m pip install -r requirements.txt" in df
    retired_req = "requirements-" + "open" + "router.txt"
    assert not (_ROOT / retired_req).exists()
    assert "torch==2.7.1" in df and "cu128" in df


def test_btc_submission_compliance_uses_correct_submission_time_env_name():
    text = (_ROOT / "docs" / "BTC_SUBMISSION_COMPLIANCE.md").read_text()
    assert "SUBMISSION_TIME_FILE" in text
    assert "SUBMISSION_TIME_FIL" not in text.replace("SUBMISSION_TIME_FILE", "")
