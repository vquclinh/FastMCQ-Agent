# Method

This document describes the approach behind FastMCQ-Agent. It evolves with the
project; Phase 1 establishes the infrastructure, Phase 2 adds real inference.

## Phase 1 — Baseline infrastructure

The goal of Phase 1 is a **correct, reproducible pipeline** rather than accuracy.
We build the end-to-end path so that swapping in a real solver later is a
one-class change:

```
load (/data) → normalise → solve → postprocess → write (/output/pred.csv) → validate
```

Key design choices:

- **Data contract first.** `data_io.py` normalises JSON and several CSV shapes
  into `{qid, question, choices}`, so solvers never deal with raw formats.
- **Dynamic labels.** `labels.py` sizes labels (`A, B, C, ...`) to each
  question's choice count. The public test has 2–11 choices per question, so
  hard-coding A–D would be wrong.
- **Pluggable solver.** `BaseSolver` defines `predict_one` / `predict_batch`.
  The Phase 1 `AlwaysASolver` returns `A`; it is a format-check baseline, not a
  serious attempt at accuracy.
- **Safety net.** `postprocess.py` guarantees one valid answer per qid, falling
  back to `A` for anything invalid.
- **Determinism.** No randomness anywhere in Phase 1.

## Phase 2B/C — Local LLM solver (implemented)

Phase 2B/C adds a modular **local-LLM** inference framework behind the existing
`BaseSolver` interface. The default solver stays `always_a`; LLM solvers are
opt-in via `--solver` / config and require a **local** model path. Nothing is
downloaded, and no external API is used.

### Solver selection

A small factory (`src/solver_factory.py`) maps names to solvers:
`always_a` → `AlwaysASolver`, `hf_generate` → `HFGenerateSolver`,
`hf_option_score` → `HFOptionScoreSolver`. Unknown names and missing model paths
raise clear errors; `run.py` reports them cleanly (exit code 2) without a
traceback. Heavy deps (`torch`, `transformers`) are imported lazily, so the
baseline and the test suite never need them.

### Dynamic labels

Every solver returns a label sized to the sample's actual choice count
(`A`..`K` for an 11-choice question), via `src/labels.py`. `postprocess.py` still
guarantees one valid label per qid, falling back to `A`.

### Prompt construction (`src/prompting.py`)

Vietnamese prompts that enumerate **all** choices with dynamic labels and ask the
model to output exactly one label. `detect_question_shape` tags each sample as
`long_context`, `calculation`, or `short_knowledge` and tailors the instruction
(answer from the passage / allow internal calculation but print only the label /
choose the best answer). Two modes: `direct` (generation) and `score` (ends with
`"Đáp án đúng là:"`).

### Long-context truncation

`truncate_question` uses a **head-tail** strategy: it keeps the beginning of the
passage and the final question section, dropping the middle (`[...]`). Choices
are never truncated — the budget is computed so the instruction and full choice
block always survive. Token-accurate when a tokenizer is supplied, character-
based otherwise (so it is fully testable without heavy deps).

### Output parsing (`src/output_parser.py`)

`parse_answer_label` first matches explicit phrases (`Đáp án: A`,
`Câu trả lời là B`, `The answer is C`, `Answer: D`, `Tôi chọn E`, ...), then
falls back to the first standalone valid label. It is case-insensitive, never
returns a label outside the valid set, and avoids letters embedded in words.

### Option scoring (`src/hf_option_score_solver.py`)

For each label it scores the continuation `" A. <choice text>"` and computes the
**average log-probability per continuation token** (length-normalised so longer
options are not penalised). The best-scoring label wins. This is more stable than
trusting free-form generation and handles any choice count. Scoring full
`label + text` (rather than a lone label token) avoids tokenizer brittleness.
All tensor work is under `torch.no_grad()`; on failure it falls back to
generation, then `A`.

### Runtime logging (`src/run_logger.py`)

Per-sample JSONL debug records (qid, answer, solver, shape, #choices, elapsed,
optional raw output/scores, fallback reason) go to `--log-path`
(default `outputs/run_debug.jsonl`) — **never** to `pred.csv`. `run.py` appends a
summary record and prints totals; `scripts/benchmark_runtime.py` reports
p50/p90/p95 and a per-shape breakdown.

## Future improvements (Phase 2D+)

- **Batching** prompts/continuations for throughput.
- **Quantization** (8-bit/4-bit) to fit larger models in the time/memory budget.
- **Faster backends:** vLLM or llama.cpp for higher tokens/sec.
- **Adaptive routing:** pick generation vs. scoring (or a stronger model) by
  question shape.
- **Prompt ensembles / self-consistency** with majority vote over labels.
- **Math-specific verification** for calculation items (e.g. re-derive or
  sanity-check numeric answers).

## Ablation *(planned)*

- Compare prompt strategies, scoring methods, and model sizes on the public
  test; record accuracy vs. latency trade-offs in
  `experiments/leaderboard_log.csv`.
