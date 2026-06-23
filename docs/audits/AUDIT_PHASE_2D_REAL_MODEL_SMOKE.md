# Audit — Phase 2D: First Real Local Model Smoke Test + Public Run Preparation

**Date:** 2026-06-19
**Branch:** `main` @ `9b371dc`
**Scope:** Attempt the first real local-model smoke test and prepare the full
public run. **Outcome: real LLM inference is BLOCKED — no compliant local model
path and no torch/transformers are available.** All safe checks were run; nothing
was fabricated.

## 1. Files inspected

`README.md`, `run.py`, `configs/default.yaml`, `requirements-llm.txt`,
`scripts/check_llm_env.py`, `scripts/check_model_compliance.py`,
`scripts/run_llm_smoke.sh`, `scripts/run_llm_full.sh`,
`src/hf_generate_solver.py`, `src/hf_option_score_solver.py`,
`src/solver_factory.py`, `experiments/leaderboard_log.csv`,
`docs/MODEL_COMPLIANCE.md`, `docs/METHOD.md`, plus `git branch -vv` /
`git status` / `git log`. All expected Phase 2C.1 files are present on `main`.

## 2. Files modified

- **Created:** `docs/AUDIT_PHASE_2D_REAL_MODEL_SMOKE.md` (this file).
- **No code, config, or solver files were changed.** No leaderboard rows were
  added (no real run occurred — see §11).

## 3. Exact commands run

```bash
# Branch / reproducibility
git branch -vv ; git status --short ; git log --oneline --decorate -6
git rev-list --left-right --count origin/main...deployment      # -> "2  0"

# Task 2 — LLM environment
python3 scripts/check_llm_env.py

# Task 3 — compliance (no MODEL_PATH, so example checks only)
python3 scripts/check_model_compliance.py --model-name "Qwen3.5-7B"   # PASS
python3 scripts/check_model_compliance.py --model-name "DeepSeek-7B"  # FAIL

# Task 4 — baseline regression
python3 run.py --input public-test_1780368312.json --output outputs/pred.csv
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred.csv

# Task 8 — tests
python3 -m pytest -q                       # -> "No module named pytest"
python3 tests/test_*.py                    # standalone runners (all 7 suites)
```

`MODEL_PATH` was checked (`echo "${MODEL_PATH:-}"`) and is **empty**, so the
model-path variants of the env/compliance checks and the entire smoke test
(Task 5) were intentionally skipped.

## 4. Branch / reproducibility status

- **Current branch:** `main` @ `9b371dc add model compliance and LLM environment setup` (= `origin/main`/`origin/HEAD`). Working tree clean.
- **History:** `9b371dc` → `f1181ea Merge pull request #1 from vquclinh/deployment` → `137269d` (Phase 2B/C) → `ad1f477` (2A) → `8e63cee` (1/1.1) → `ce11a26` (initial).
- **`origin/main...deployment` = `2 0`:** `main` is **ahead of `deployment` by 2 commits** and `deployment` has nothing `main` lacks.
- **Conclusion:** the earlier blocker (*"all work on `deployment`, `main` empty"*) is **RESOLVED** — `main` now contains every phase including 2C.1 and is the up-to-date submission branch. `deployment` is now stale (2 commits behind); no merge was performed in this task (none required, and not instructed).

## 5. LLM environment check result

`scripts/check_llm_env.py` → **torch: NOT installed**, **transformers: NOT
installed**, **LLM-ready: NO**. CUDA/GPU not probed (deps absent). No model path
provided. Enable with `pip install -r requirements-llm.txt`.

## 6. Model compliance result

No real `MODEL_PATH` → **example checks only** (no actual model directory was
checked):

| Command | Verdict |
|---|---|
| `--model-name "Qwen3.5-7B"` | **PASS** |
| `--model-name "DeepSeek-7B"` | **FAIL** (disallowed family) |

The `--model-path "$MODEL_PATH" --strict` check from the task spec was **not**
run because `MODEL_PATH` is unset.

## 7. Was a real local model path available?

**No.** `MODEL_PATH` is unset and no model directory was provided by any other means.

## 8. Was real LLM inference run?

**No.** Phase 2D's smoke test is **blocked** on (a) a compliant local model path
and (b) the optional LLM dependencies (`requirements-llm.txt`). No `hf_generate`
or `hf_option_score` inference was executed. No fake outputs were produced.

## 9. Smoke test outputs / validation

**Not applicable** — no smoke test ran. No `outputs/pred_hf_*_smoke.csv` or
`outputs/run_hf_*_smoke.jsonl` were created.

## 10. Runtime benchmark

**Not applicable** — no debug logs from a real run exist.

## 11. Baseline regression & tests

- **Baseline:** `run.py` → 463 samples, solver `always_a`, 463 rows;
  `validate_submission.py` → **RESULT: PASS**. Baseline intact.
- **Tests:** `python -m pytest -q` → **"No module named pytest"** (declared in
  `requirements.txt`, not installed here). Standalone runners: **47/47 passed**
  (data_io 8, labels 6, model_compliance 9, output_parser 8, prompting 7,
  score_mode 5, solver_factory 4).

## 12. Experiment log updates

**None.** Per the task's honesty rule, no leaderboard rows were added because no
real model run occurred. The two pending rows from Phase 2B/C
(`hf_generate_zero_shot_v1`, `hf_option_score_v1`, both `local_model_path_pending`,
scores blank) remain the correct record of intent.

## 13. Full public run — prepared commands (NOT run)

Once a compliant local model is available and `requirements-llm.txt` is
installed, run (after `check_model_compliance.py --model-path "$MODEL_PATH" --strict`
returns PASS):

```bash
# Option-scoring (preferred backbone), default score mode
python3 run.py --solver hf_option_score --score-mode label_plus_choice \
  --model-path "$MODEL_PATH" \
  --input public-test_1780368312.json --output outputs/pred_llm.csv \
  --save-raw --log-path outputs/run_debug.jsonl
python3 scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_llm.csv
python3 scripts/benchmark_runtime.py --log-path outputs/run_debug.jsonl

# (Alternative backbone for comparison)
python3 run.py --solver hf_generate \
  --model-path "$MODEL_PATH" \
  --input public-test_1780368312.json --output outputs/pred_hf_generate.csv \
  --save-raw --log-path outputs/run_hf_generate.jsonl
python3 scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_hf_generate.csv
```

Helper scripts wrap the same flow: `bash scripts/run_llm_full.sh "$MODEL_PATH" label_plus_choice`.

## 14. Risks / caveats

- **Phase 2D is blocked** on a compliant local model + LLM deps; no accuracy or
  runtime evidence exists yet. Any competitive claim remains unproven.
- **`deployment` branch is now stale** (2 commits behind `main`). If anyone still
  treats `deployment` as the submission branch, it must be updated; otherwise
  standardise on `main`.
- **Compliance is name/path-based**, not weight-based — a real model still needs a
  `--strict` PASS *and* human confirmation of provenance before submission.
- **Exact scoring rubric / time budget / packaging** remain unconfirmed with BTC
  (carried over from the project overview).
- **pytest not installed** locally; standalone runners used (reported honestly).

## 15. Recommended next step

Unblock Phase 2D by providing a **compliant local model** (e.g. Qwen3.5 ≤ 9B) and
installing `requirements-llm.txt`, then:
1. `python3 scripts/check_llm_env.py --model-path "$MODEL_PATH" --load-tokenizer`
2. `python3 scripts/check_model_compliance.py --model-path "$MODEL_PATH" --strict`
3. `bash scripts/run_llm_smoke.sh "$MODEL_PATH" label_plus_choice` (+ `hf_generate`)
4. If smoke + runtime look good, run the full command in §13, validate, benchmark,
   and record the **first real leaderboard score** in `experiments/leaderboard_log.csv`.

In parallel (non-code): confirm the MCQA scoring rubric, time budget, and whether
the Docker image must bundle weights; and standardise the submission branch on `main`.
