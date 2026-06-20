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

## Operating modes

The system has two modes (both implemented). **Mode A (Round 1):** the
`openrouter_graph` solver uses the **OpenRouter API** (default `qwen/qwen3.5-9b`)
to generate the leaderboard CSV — see `docs/OPENROUTER_ROUND1_STRATEGY.md`.
**Mode B (later Docker/offline):** the local `hf_*` / `adaptive_agent` solvers
run a local model with **no external API**. The "local / no external API"
statements below describe **Mode B**.

## Phase 2B/C — Local LLM solver (implemented, Mode B)

Phase 2B/C adds a modular **local-LLM** inference framework behind the existing
`BaseSolver` interface. The default solver stays `always_a`; the local LLM
solvers are opt-in via `--solver` / config and require a **local** model path.
Nothing is downloaded, and no external API is used **in this (Mode B) path**.

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

For each label it scores a continuation and computes the **average log-probability
per continuation token** (length-normalised so longer options are not penalised).
The best-scoring label wins. This is more stable than trusting free-form
generation and handles any choice count. All tensor work is under
`torch.no_grad()`; on failure it falls back to generation, then `A`.

#### Option-scoring variants (`--score-mode` / `hf.score_mode`)

The scored continuation is selectable:

| Mode | Continuation | Notes |
|---|---|---|
| `label_only` | `" A"` | Cleanest when the tokenizer cooperates; brittle otherwise. |
| `label_plus_choice` *(default)* | `" A. <choice text>"` | Most robust; binds label to content. |
| `choice_only` | `" <choice text>"` | Label-free content likelihood. |

We default to `label_plus_choice`, but **the leaderboard score decides which
scoring mode is retained** — all three are first-class and the debug log records
the score mode, per-label scores, best/second-best labels, and the top-2 margin
so the choice can be made on evidence (see `docs/RESEARCH_STRATEGY.md`).

### Model compliance & LLM environment

LLM runs are gated by an explicit compliance policy. Allowed families (provisional)
are declared in `configs/allowed_models.yaml` and checked by
`scripts/check_model_compliance.py` (PASS/WARNING/FAIL, with `--strict`); the full
policy and open questions for the organizer are in `docs/MODEL_COMPLIANCE.md`.

The optional LLM dependencies live in `requirements-llm.txt` (kept out of the
baseline/Docker image). `scripts/check_llm_env.py` reports torch/transformers
availability, CUDA, and GPU/VRAM, and can validate a local model path — all
without downloading anything.

### Runtime logging (`src/run_logger.py`)

Per-sample JSONL debug records (qid, answer, solver, shape, #choices, elapsed,
optional raw output/scores, fallback reason) go to `--log-path`
(default `outputs/run_debug.jsonl`) — **never** to `pred.csv`. `run.py` appends a
summary record and prints totals; `scripts/benchmark_runtime.py` reports
p50/p90/p95 and a per-shape breakdown.

## Future improvements (Phases 2I–2J)

These are **not** part of the Minimal Viable Agent v1 (Phases 2F–2G); they are
deferred and adopted only on leaderboard evidence (see `docs/ARCHITECTURE.md`
§14 for the explicit v1 exclusion list):

- **Batching** prompts/continuations for throughput (2I).
- **Quantization** (8-bit/4-bit) to fit larger models in the time/memory budget (2I).
- **Faster backends:** vLLM or llama.cpp for higher tokens/sec (2I).
- **Adaptive routing:** pick strategy/score-mode by question shape (2F/2G core;
  extended routing later).
- **Prompt ensembles / self-consistency** with majority vote over labels (2J).
- **PAL-lite math verification** for calculation items (2J).

## Ablation *(planned)*

- Compare prompt strategies, scoring methods, and model sizes on the public
  test; record accuracy vs. latency trade-offs in
  `experiments/leaderboard_log.csv`.

## Adaptive multi-agent core *(implemented — Phase 2F/G)*

The core of the target architecture is now implemented as the **`adaptive_agent`**
solver (opt-in via `--solver adaptive_agent`; default stays `always_a`). It
composes five new modules — `question_profiler`, `question_router`,
`passage_compressor`, `confidence`, and `adaptive_agent_solver` — around the
existing `hf_option_score` backbone, with deterministic profiling/routing/
compression, margin-based confidence, and a simple alternate-score-mode →
generation fallback. Advanced methods (self-consistency, PAL-lite, debate,
ToT-lite) are **gated off**; enabling one raises `NotImplementedError` rather than
acting silently. Each sample emits a rich JSONL trace (route, profile, budget
tier, strategy, scores, margin, confidence, fallback, compression stats). **No
real LLM inference has been run** for this solver yet — it requires a compliant
local `MODEL_PATH` (Phase 2H).

## Target architecture — FastMCQ-Agent++ *(design)*

The planned end-state is a **budget-aware multi-agent** system (full design in
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md)): a sample is profiled with cheap
deterministic features, routed to a specialist strategy, answered by
likelihood-based option scoring, verified by a confidence check, and escalated to
**selective, more expensive reasoning only for low-confidence/high-value cases**
under an explicit compute budget (Tier 0 cheap → Tier 1 moderate → Tier 2
expensive). Research methods are mapped to **lightweight, gated** modules — CoT as
an internal reasoning prompt (label-only output), RAG as in-question passage
selection, self-consistency / PAL-lite / debate-lite / ToT-lite as rationed
fallbacks — never always-on. The default solver stays `always_a`; the adaptive
solver is opt-in and adopted only on leaderboard evidence.
