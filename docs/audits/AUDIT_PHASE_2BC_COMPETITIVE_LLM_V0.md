# Audit — Phase 2B/C: Competitive Local LLM Solver v0

**Date:** 2026-06-19
**Scope:** A modular **local-LLM** inference framework (generation + option
scoring) behind the existing `BaseSolver` interface, with prompting, output
parsing, runtime logging, scripts, tests, and docs.
**Out of scope / not done (by constraint):** real LLM execution (no local model
or torch/transformers available here), model downloads, external APIs, secrets.
The default solver remains `always_a` and the I/O contract is unchanged.

## 1. Summary of files created / modified

### Created — source
| Path | Purpose |
|---|---|
| `src/prompting.py` | `format_choices`, `detect_question_shape`, `truncate_question` (head-tail), `build_mcq_prompt` (direct/score modes). Vietnamese, dynamic labels, choices never truncated. |
| `src/output_parser.py` | `parse_answer_label` — explicit-phrase patterns first, then standalone label; case-insensitive; rejects out-of-range labels; ignores letters inside words. |
| `src/hf_common.py` | Lazy torch/transformers loader; `local_files_only=True`; clear errors for missing deps/path; device + dtype resolution; safe pad token; eval mode. |
| `src/hf_generate_solver.py` | `HFGenerateSolver` — deterministic short generation, parse label, fallback to `A`, per-sample timing/logging. |
| `src/hf_option_score_solver.py` | `HFOptionScoreSolver` — length-normalised continuation log-prob scoring over `" A. <text>"`; `torch.no_grad()`; falls back to generation then `A`. |
| `src/solver_factory.py` | `build_solver(name, ...)` for `always_a` / `hf_generate` / `hf_option_score`; clear errors for unknown name / missing model path; shares one loaded model for the scorer's generation fallback. |
| `src/run_logger.py` | `RunLogger` — per-sample JSONL debug records + summary; no-op when disabled; never writes `pred.csv`. |
| `scripts/run_llm_smoke.sh` | 10-sample smoke test (`hf_option_score`) + validation. |
| `scripts/run_llm_full.sh` | Full run (`hf_option_score`) + validation + benchmark + upload/log reminder. |
| `scripts/benchmark_runtime.py` | Reads debug JSONL; total/avg/p50/p90/p95 + per-shape breakdown. |
| `tests/test_prompting.py` | Choice labels (2/4/10/11), all choices present, single-label instruction, score-prompt stem, long-question truncation keeps choices. |
| `tests/test_output_parser.py` | Common formats, rejection of invalid/out-of-range, case-insensitivity, no-word-letter pickups, explicit-beats-stray. |
| `tests/test_solver_factory.py` | Default → `AlwaysASolver`; unknown raises; `hf_*` without model path raises; bad path errors. HF deps optional (skips heavy paths). |
| `docs/AUDIT_PHASE_2BC_COMPETITIVE_LLM_V0.md` | This audit. |

### Modified
| Path | Change |
|---|---|
| `run.py` | New CLI (`--solver`, `--model-path`, `--max-new-tokens`, `--temperature`, `--max-input-tokens`, `--trust-remote-code`, `--device`, `--limit`, `--resume`, `--save-raw`, `--log-path`, `--config`, `--output`); CLI>config>default resolution; clean error exit (code 2) for config/dep failures; resume/limit; run summary. Default stays `always_a`. |
| `configs/default.yaml` | Added `hf:` section (model_path, solver, max_new_tokens, temperature, max_input_tokens, trust_remote_code, device, save_raw, log_path). Default `solver: always_a`. |
| `README.md` | Local-LLM solver section (smoke/full/validate/benchmark, flags, workflow), `hf_generate` vs `hf_option_score`, updated status/roadmap. |
| `docs/METHOD.md` | Phase 2B/C section (solver selection, dynamic labels, prompting, truncation, parsing, scoring, logging) + Phase 2D future work. |
| `experiments/leaderboard_log.csv` | Added `hf_generate_zero_shot_v1` and `hf_option_score_v1` rows (model `local_model_path_pending`, `local execution required`, score blank). |

No files deleted or moved. Dataset, sample submission, and PDF untouched.

## 2. Exact commands run

```bash
# Baseline regression (required)
python3 run.py --input public-test_1780368312.json --output outputs/pred.csv
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred.csv

# Tests (required)
python3 -m pytest -q                 # -> "No module named pytest" (not installed)
python3 tests/test_labels.py
python3 tests/test_data_io.py
python3 tests/test_prompting.py
python3 tests/test_output_parser.py
python3 tests/test_solver_factory.py

# Negative tests (no local model)
python3 run.py --solver hf_option_score --input public-test_1780368312.json --output outputs/nope.csv   # missing model path
python3 run.py --solver bogus          --input public-test_1780368312.json --output outputs/nope.csv   # unknown solver
python3 run.py --solver hf_generate --model-path /no/such/model --input public-test_1780368312.json --output outputs/nope.csv  # bad path

# Pipeline-feature checks
python3 run.py --input public-test_1780368312.json --output outputs/pred_limit.csv --limit 10
python3 run.py --input public-test_1780368312.json --output outputs/pred_resumed.csv --resume outputs/pred_limit.csv

# Lazy-import contract (no torch present)
python3 -c "import src.hf_common, src.hf_generate_solver, src.hf_option_score_solver, src.solver_factory"

# Docker baseline regression
docker build -t fastmcq-agent .
docker run --rm -v "$PWD/tmp_data:/data" -v "$PWD/tmp_output:/output" fastmcq-agent
```

## 3. Validation / test results

- **Baseline `run.py`:** 463 samples, solver `always_a`, 463 rows written.
- **`validate_submission.py`:** **RESULT: PASS**.
- **Docker baseline:** rebuilt and ran; auto-detected `/data/public-test.json`,
  wrote 463 rows, validation **PASS**. Baseline is intact.
- **`--limit 10`:** wrote 10 rows. **`--resume`:** skipped the 10 done qids, ran
  453, merged to 463 rows, validation **PASS**.
- **Tests:** `python -m pytest -q` → **"No module named pytest"** (declared in
  `requirements.txt`, not installed in this env). Standalone runners:
  **33/33 passed** — labels 6, data_io 8, prompting 7, output_parser 8,
  solver_factory 4.
- **Lazy imports:** all HF modules import without torch/transformers present.

## 4. Was the HF solver executed?

**No.** Real LLM inference was **not** run, because:

- No local model directory is available in this environment, and we must not
  download one (hard constraint).
- `torch` and `transformers` are not installed here.

The framework is wired and unit-tested up to the model boundary. Running it only
requires installing `torch`+`transformers` locally and pointing
`--model-path` at a local model:
`bash scripts/run_llm_smoke.sh /path/to/local/model`.

## 5. Negative test results (missing/invalid model path)

All produce a clear, single-line error and exit code **2** (no `pred.csv`
written):

| Command | Result |
|---|---|
| `--solver hf_option_score` (no `--model-path`) | `ERROR: solver 'hf_option_score' requires --model-path ... never downloads anything.` |
| `--solver bogus` | `ERROR: unknown solver 'bogus'; choose one of always_a, hf_generate, hf_option_score` |
| `--solver hf_generate --model-path /no/such/model` | `ERROR: model_path does not exist: /no/such/model ...` (when torch present) / clear dependency error otherwise |

`tests/test_solver_factory.py` asserts these error paths too.

## 6. Risks / caveats

- **Unexecuted on a real model.** The scoring math was reviewed (continuation
  token `j` at absolute index `prompt_len+j` is predicted by logits at
  `prompt_len-1+j`) and is correct, but end-to-end behaviour on a real model is
  unverified until a local model is available. Treat v0 numbers as TBD.
- **Option scoring scores `label + choice text`**, so a choice's intrinsic
  fluency influences its score (a known property of sequence scoring). This was
  chosen for robustness over bare-label-token scoring; revisit in Phase 2D if it
  biases results.
- **`torch`/`transformers` are NOT in `requirements.txt`** (kept the baseline /
  Docker image light per constraints). LLM runs require installing them locally.
- **Determinism** assumes `do_sample=False`; with `temperature>0` results vary.
- **Long-context truncation** keeps head+tail; a question whose answer hinges on
  the dropped middle could be missed. Budget is configurable via
  `--max-input-tokens`.
- **No public-test answers are encoded anywhere**; nothing overfits to the
  public set.

## 7. Git status

```
On branch deployment
 M README.md
 M configs/default.yaml
 M docs/METHOD.md
 M experiments/leaderboard_log.csv
 M run.py
?? scripts/benchmark_runtime.py
?? scripts/run_llm_full.sh
?? scripts/run_llm_smoke.sh
?? src/hf_common.py
?? src/hf_generate_solver.py
?? src/hf_option_score_solver.py
?? src/output_parser.py
?? src/prompting.py
?? src/run_logger.py
?? src/solver_factory.py
?? tests/test_output_parser.py
?? tests/test_prompting.py
?? tests/test_solver_factory.py
```

`outputs/run_debug.jsonl` and `outputs/pred*.csv` are git-ignored. Changes are
uncommitted, pending review.

## 8. Recommended next steps (Phase 2D)

1. **Run on a real local model** via the smoke script; compare `hf_generate` vs
   `hf_option_score` accuracy/latency and log both to the leaderboard CSV.
2. **Batching** of prompts and option continuations for throughput.
3. **Quantization** (8-bit/4-bit) to fit larger models in budget.
4. **Faster backend** (vLLM / llama.cpp) behind the same `BaseSolver`.
5. **Adaptive routing** by `question_shape` (e.g. scoring for short knowledge,
   special handling for calculation).
6. **Prompt ensemble / self-consistency** and **math verification** for the
   large 10-choice calculation bucket.
7. **Add `torch`/`transformers` to a separate optional requirements file** (e.g.
   `requirements-llm.txt`) so the baseline image stays light.
