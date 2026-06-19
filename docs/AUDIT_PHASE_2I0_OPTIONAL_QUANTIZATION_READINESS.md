# Audit — Phase 2I.0: Optional 4-bit/8-bit Quantization Readiness

**Date:** 2026-06-19
**Branch:** `main` @ `487db5d`
**Scope:** Add **optional** bitsandbytes 4-bit/8-bit quantized loading so a
compliant 7B-class model can fit the 7.6 GB GPU, without changing default
behavior, requiring bitsandbytes, or breaking unquantized loading. **No model
downloaded; no real inference run** (`MODEL_PATH` empty). **Not committed.**

## 1. Repo guard result

- Branch: `main`. Working tree clean before this phase.
- Adaptive work **is committed** by the user as `487db5d "implement adaptive
  multi-agent MCQA solver"`; `src/adaptive_agent_solver.py` is tracked.
- Old Claude commits `4c2ac00` / `2dff905` are **absent** from history.
- Guard **passed** → proceeded.

## 2. Files inspected

`src/hf_common.py`, `src/hf_generate_solver.py`, `src/hf_option_score_solver.py`,
`src/adaptive_agent_solver.py`, `src/solver_factory.py`, `configs/default.yaml`,
`requirements-llm.txt`, `scripts/check_llm_env.py`, tests, `git status`.

## 3. Files created / modified

### Created
- `tests/test_quantization.py` — 11 tests (config builder error paths, no-op
  default, factory passthrough via monkeypatch); needs no real bnb/model.
- `docs/AUDIT_PHASE_2I0_OPTIONAL_QUANTIZATION_READINESS.md` — this audit.

### Modified
| Path | Change |
|---|---|
| `src/hf_common.py` | Added `bitsandbytes_available()`, `_resolve_compute_dtype()`, `_build_quantization_config()`, and a `quantization` param to `load_model()`. Quantized path uses `BitsAndBytesConfig` + `device_map="auto"` and skips `.to()`; unquantized path is byte-for-byte the old behavior. |
| `src/hf_generate_solver.py`, `src/hf_option_score_solver.py`, `src/adaptive_agent_solver.py` | Accept `quantization` and forward to `load_model` (adaptive forwards to its scorer; the generation fallback shares the loaded model, so no double load). |
| `src/solver_factory.py` | `build_solver(..., quantization=None)` threads the dict to all three HF solvers. |
| `run.py` | Resolve `hf.quantization` from config + new CLI `--quantization-mode` / `--quantization-compute-dtype`; pass to `build_solver`. Existing CLI unchanged. |
| `configs/default.yaml` | Added `hf.quantization` block (`mode: null` default → unchanged behavior). |
| `requirements-llm.txt` | Added **commented** optional `# bitsandbytes>=0.43`. |
| `scripts/check_llm_env.py` | Reports bitsandbytes availability/version (no import of the heavy CUDA extension). |

## 4. bitsandbytes: installed or only documented?

**Only documented.** `bitsandbytes` is **not installed** and was not installed in
this phase (it stays optional; baseline/tests do not need it). `check_llm_env.py`
reports `bitsandbytes : NOT installed (optional; only for 4bit/8bit quantization)`.

## 5. Quantization config added

```yaml
hf:
  quantization:
    mode: null            # null | "4bit" | "8bit"
    compute_dtype: null   # null | float16 | bfloat16 | float32
    double_quant: true
    quant_type: "nf4"
```
Default `mode: null` keeps the fp16/fp32 path and never imports bitsandbytes.

## 6. HF loading code path changed

`load_model()` now builds an optional `BitsAndBytesConfig`:
- **mode null** → unquantized; identical to before; bitsandbytes never imported.
- **"4bit"** → `load_in_4bit=True` with `bnb_4bit_quant_type`,
  `bnb_4bit_use_double_quant`, `bnb_4bit_compute_dtype`; loaded with
  `device_map="auto"`; no post-load `.to()`.
- **"8bit"** → `load_in_8bit=True`.
- **Clear failures (no silent fp16 fallback):** invalid mode → error; non-CUDA
  device → error; bitsandbytes missing → actionable error.

## 7. Solver construction changes

`hf_generate`, `hf_option_score`, and `adaptive_agent` all accept `quantization`
and pass it to `load_model`. The adaptive solver passes it only to its scorer; the
generation fallback reuses the already-loaded (possibly quantized) model — **no
double load**. Default solver remains `always_a` and ignores quantization.

## 8. Tests added/updated

`tests/test_quantization.py` (11 tests): bitsandbytes-availability bool; default
config is `None` (no bnb import); invalid mode → error; quant requires CUDA;
4bit/8bit without bnb → clear error; invalid compute_dtype → error; factory passes
quantization through to `hf_option_score` and `hf_generate`; `always_a` unaffected;
existing solver constructs with default (no) quantization. Dependency-requiring
checks skip gracefully if torch/transformers are absent; none require real
bitsandbytes or a model.

## 9. Validation commands and results

```bash
.venv/bin/python -m compileall -q src tests scripts     # OK
.venv/bin/python -m pytest -q                            # 95 passed
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_phase2i0_baseline.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_phase2i0_baseline.csv  # PASS
.venv/bin/python scripts/check_llm_env.py                # reports bitsandbytes NOT installed
```

- **compileall:** OK. **pytest:** **95 passed** (84 prior + 11 new).
- **Baseline:** 463 rows, solver `always_a`, **validate PASS** (unchanged).
- **Negative:** `--quantization-mode 4bit` without a model → clean
  `requires --model-path` error, **no output file**, no fabricated predictions.

## 10. Confirmations

- **No model downloaded** at any point; `local_files_only=True` preserved.
- **No real inference run** (`MODEL_PATH` empty).
- `.venv/`, `outputs/`, model dirs, and the HF cache remain git-ignored / outside the repo.

## 11. Remaining blocker for Phase 2H

Unchanged: **no compliant local model** (Qwen3.5 ≤ 9B / Gemma-4). With one
provided, a 7B now has a path to fit 7.6 GB via `--quantization-mode 4bit` (after
`pip install bitsandbytes`). A small/≤3B model could run unquantized.

## 12. Risks / caveats

- **Quantized path is unexercised end-to-end** — bitsandbytes isn't installed and
  no model is present, so the 4bit/8bit load was validated only at the
  config-builder and wiring level (error paths + passthrough). First real use
  should be a `--limit 1` smoke.
- **transformers 5.x** `BitsAndBytesConfig` / `device_map` API assumed stable;
  verify on first real quantized load.
- **bitsandbytes CUDA/Linux constraints** apply; the code errors clearly on
  non-CUDA or missing-package rather than guessing.

## 13. Recommended next step

User reviews and commits this phase. Then, to unblock Phase 2H: place a compliant
local model, `pip install bitsandbytes` (if using a 7B), and run a `--limit 1`
smoke with `--quantization-mode 4bit` before the full ablation.

## 14. Git status (uncommitted)

```
 M configs/default.yaml
 M requirements-llm.txt
 M run.py
 M scripts/check_llm_env.py
 M src/adaptive_agent_solver.py
 M src/hf_common.py
 M src/hf_generate_solver.py
 M src/hf_option_score_solver.py
 M src/solver_factory.py
?? tests/test_quantization.py
?? docs/AUDIT_PHASE_2I0_OPTIONAL_QUANTIZATION_READINESS.md
```

All changes **uncommitted**, left for the user to review and commit manually.
