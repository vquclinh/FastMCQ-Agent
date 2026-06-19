# Audit — Phase 2D.1: Local venv Setup + First Real LLM Smoke Test (attempt)

**Date:** 2026-06-19
**Branch:** `main` @ `9b371dc`
**Scope:** Build a local Python environment, install base + optional LLM
dependencies, and run the first real LLM smoke test **if** a compliant local
model is available.
**Outcome:** Environment is now **LLM-ready (with GPU)**, baseline + tests green.
The real LLM smoke test is **still blocked** — `MODEL_PATH` is empty. No LLM
inference was run; nothing was fabricated.

## 1. Files inspected

`requirements.txt`, `requirements-llm.txt`, `run.py`, `configs/default.yaml`,
`scripts/check_llm_env.py`, `scripts/check_model_compliance.py`,
`scripts/run_llm_smoke.sh`, `scripts/run_llm_full.sh`, `src/hf_common.py`,
`src/hf_generate_solver.py`, `src/hf_option_score_solver.py`,
`experiments/leaderboard_log.csv`, `docs/MODEL_COMPLIANCE.md`, plus `git status`.

## 2. Environment: created vs reused

- **`.venv` — CREATED** (did not previously exist), Python **3.14.5**.
  - Path: `/mnt/vquclinh/PROJECT-CMAKE/FASTMCQ-AGENT/FastMCQ-Agent/.venv`
  - Interpreter: `.venv/bin/python` → `Python 3.14.5`.
- **`.venv-llm` — NOT created / NOT needed.** torch ships a Python 3.14 wheel
  (`torch-2.12.1-cp314-cp314-manylinux_2_28_x86_64.whl`), so the single `.venv`
  works for both baseline/tests and LLM deps. (Also, no `python3.11/3.12/3.13`
  is installed on this machine, so an older-Python env was not an option anyway.)
- `.venv` is git-ignored.

## 3. Dependency installation result

| Step | Command | Result |
|---|---|---|
| Upgrade tooling | `pip install --upgrade pip setuptools wheel` | OK (pip 26.1.2) |
| Base deps | `pip install -r requirements.txt` | **OK** — PyYAML 6.0.3, pytest 9.1.0 |
| LLM deps | `pip install -r requirements-llm.txt` | **OK — exit code 0** |

**Note on the earlier delay:** the first LLM-install attempt appeared to hang and
was terminated (exit 144). Investigation showed it was **not** a Python 3.14
incompatibility — pip was downloading the **532 MB** `torch` cp314 wheel, and the
`| tail -25` buffering hid all progress. The retry (verbose, line-buffered)
confirmed a live download (observed the wheel growing to ~431/532 MB) and finished
cleanly. **No CUDA-specific wheel was hand-picked**; pip selected the default
`+cu130` build automatically.

## 4. Key package versions (in `.venv`)

```
torch          2.12.1  (reports 2.12.1+cu130)
transformers   5.12.1
accelerate     1.14.0
sentencepiece  0.2.1
safetensors    0.8.0
tokenizers     0.22.2
numpy          2.4.6
pytest         9.1.0
```

## 5. LLM environment check result

`.venv/bin/python scripts/check_llm_env.py`:

```
torch         : 2.12.1+cu130
CUDA available: True
  GPU[0]     : NVIDIA GeForce RTX 4060 Laptop GPU (7.6 GB VRAM)
transformers  : 5.12.1
model-path    : (not provided; pass --model-path to validate one)
LLM-ready (deps installed): YES
```

A CUDA GPU is available. **7.6 GB VRAM is modest** — a 7B model in fp16 (~14 GB)
will not fit; plan for 4-bit quantization or a smaller checkpoint (see §10).

## 6. Baseline regression result

`.venv/bin/python run.py …` → 463 samples, solver `always_a`, 463 rows.
`validate_submission.py` → **RESULT: PASS**. Baseline intact under Python 3.14 + the new deps.

## 7. Test result

`.venv/bin/python -m pytest -q` → **47 passed in ~0.14s** (pytest now installed in
the venv). All suites: data_io, labels, model_compliance, output_parser,
prompting, score_mode, solver_factory.

## 8. MODEL_PATH status

`echo "${MODEL_PATH:-}"` → **empty**. No compliant local model path is available.

## 9. Was real LLM inference run?

**No.** Per the constraints, with `MODEL_PATH` empty we did **not** run
`check_llm_env --load-tokenizer`, `check_model_compliance --model-path`, or any
`hf_generate` / `hf_option_score` smoke test. **No smoke outputs were created and
no leaderboard rows were added.**

**Exact blocker:** no `MODEL_PATH` pointing at a compliant local model directory.
Everything else (deps, GPU, baseline, tests) is ready.

## 10. Risks / caveats

- **Blocked on a model.** The environment is ready; only a compliant local model
  (e.g. Qwen3.5 ≤ 9B) is missing.
- **VRAM is tight (7.6 GB).** Expect to need 4-bit quantization (e.g.
  bitsandbytes) or a ≤ ~3B model to fit a generation/scoring run on GPU; otherwise
  CPU fallback will be slow. This may motivate Phase 2F (quantization) sooner.
- **transformers is 5.x (5.12.1).** The solvers were written against `>=4.40` and
  use stable `AutoTokenizer` / `AutoModelForCausalLM` / `model.generate` APIs, but
  the 5.x line has not been exercised end-to-end here — verify on the first real
  run; pin a known-good version if anything breaks.
- **`bitsandbytes` is not installed** — add it to `requirements-llm.txt` only if
  quantization is actually adopted (kept out for now to avoid unused heavy deps).
- **No internet model download** was performed at any point.

## 11. Recommended next step

Provide a compliant local model and set `MODEL_PATH`, then (in `.venv`):

```bash
.venv/bin/python scripts/check_llm_env.py --model-path "$MODEL_PATH" --load-tokenizer
.venv/bin/python scripts/check_model_compliance.py --model-path "$MODEL_PATH" --strict
# only if both pass:
.venv/bin/python run.py --solver hf_generate --model-path "$MODEL_PATH" \
  --input public-test_1780368312.json --output outputs/pred_hf_generate_smoke.csv \
  --limit 10 --save-raw --log-path outputs/run_hf_generate_smoke.jsonl
.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_hf_generate_smoke.csv
.venv/bin/python run.py --solver hf_option_score --score-mode label_plus_choice \
  --model-path "$MODEL_PATH" \
  --input public-test_1780368312.json --output outputs/pred_hf_option_score_smoke.csv \
  --limit 10 --save-raw --log-path outputs/run_hf_option_score_smoke.jsonl
.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_hf_option_score_smoke.csv
```

Given the 7.6 GB VRAM, pick a checkpoint that fits (or add 4-bit quantization)
before the full public run.
