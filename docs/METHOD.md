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

A small factory (`src/base/solver_factory.py`) maps names to solvers:
`always_a` → `AlwaysASolver`, `hf_generate` → `HFGenerateSolver`,
`hf_option_score` → `HFOptionScoreSolver`. Unknown names and missing model paths
raise clear errors; `run.py` reports them cleanly (exit code 2) without a
traceback. Heavy deps (`torch`, `transformers`) are imported lazily, so the
baseline and the test suite never need them.

### Dynamic labels

Every solver returns a label sized to the sample's actual choice count
(`A`..`K` for an 11-choice question), via `src/utils/labels.py`. `postprocess.py` still
guarantees one valid label per qid, falling back to `A`.

### Prompt construction (`src/utils/prompting.py`)

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

### Output parsing (`src/utils/output_parser.py`)

`parse_answer_label` first matches explicit phrases (`Đáp án: A`,
`Câu trả lời là B`, `The answer is C`, `Answer: D`, `Tôi chọn E`, ...), then
falls back to the first standalone valid label. It is case-insensitive, never
returns a label outside the valid set, and avoids letters embedded in words.

### Option scoring (`src/solvers/hf_option_score_solver.py`)

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
`scripts/legacy/checks/check_model_compliance.py` (PASS/WARNING/FAIL, with `--strict`); the full
policy and open questions for the organizer are in `docs/MODEL_COMPLIANCE.md`.

The optional LLM dependencies live in `requirements-llm.txt` (kept out of the
baseline/Docker image). `scripts/legacy/checks/check_llm_env.py` reports torch/transformers
availability, CUDA, and GPU/VRAM, and can validate a local model path — all
without downloading anything.

### Runtime logging (`src/utils/run_logger.py`)

Per-sample JSONL debug records (qid, answer, solver, shape, #choices, elapsed,
optional raw output/scores, fallback reason) go to `--log-path`
(default `output/run_debug.jsonl`) — **never** to `pred.csv`. `run.py` appends a
summary record and prints totals; `scripts/legacy/benchmark/benchmark_runtime.py` reports
p50/p90/p95 and a per-shape breakdown.

## Future improvements (Phases 2I–2J)

These are **not** part of the Minimal Viable Agent v1 (Phases 2F–2G); they are
deferred and adopted only on leaderboard evidence (see `docs/ARCHITECTURE.md`
§14 for the explicit v1 exclusion list):

- **Batching** prompts/continuations for throughput (2I).
- **Quantization** (8-bit/4-bit) to fit larger models in the time/memory budget (2I).
- **Faster backends:** non-submission backend experiments for higher tokens/sec (2I).
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

## Final production architecture — the dynamic full system

The submitted system is the **dynamic full pipeline** (`final_infer.py --mode dynamic_full`, the
default), orchestrated by `src/system/fastmcq_system.py`. It runs over *any* input (public,
private, unseen, or larger sets) and writes a prediction for **exactly the input qids**.

```
load (/data) → base predictor → V12B layer → V13 layer → unified selector → write (/output/pred.csv) → validate
```

1. **Base predictor** (`src/base/dynamic_base_predictor.py`). Produces a valid baseline answer
   for **every** input qid. This guarantees full coverage regardless of how many qids the
   later layers revise.
2. **V12B — option-permutation debiaser** (`src/layers/v12b_dynamic_layer.py`,
   `mcq_permutation_debiaser.py`). For selected high-risk qids, it re-asks the model under
   several option permutations and keeps an answer only when it is stable across permutations —
   removing position bias. Promoted at public 78.83.
3. **V13 — multi-layer reasoning** (`src/layers/v13_dynamic_layer.py`, `v13_layer_registry.py`).
   Three sub-strategies: a deterministic **programmatic solver** (arithmetic/PoT-lite, runs even
   offline), a **content-first normalizer**, and a **least-to-most constraint table**. Promoted
   at public **79.7**.
4. **Unified selector** (`src/selector/system_candidate_selector.py`). Conservatively combines
   the base answer with the V12B/V13 proposals and writes **all** qids to `pred.csv`. A layer
   override is accepted only when it clears the conservative agreement bar; otherwise the base
   answer stands.

### Selective API budget — `auto = ceil(N / 8)`

The V12B/V13 layers are the only parts that may call the model. By default their per-layer cap is
`auto = ceil(input_count / 8)`, **minimum 1** (e.g. 3 → 1, 463 → 58, 2000 → 250), logged as
`auto(<cap>/<N>)`. This bounds API cost relative to the input size without any hardcoded number;
pass an integer to cap explicitly, or `all` to let the layers consider every qid. **The cap never
limits output coverage** — the base predictor + selector always emit all input qids. With no API
key the model-dependent layers report `skipped_no_api` (only the deterministic V13 programmatic
path still runs), and the system still writes a complete, valid `pred.csv`.

### Allowed-model policy

All model access goes through `src/api/model_policy.py` (`is_allowed_llm_model`), which enforces
the competition allowlist (a ≤9B open model, e.g. `qwen/qwen3.5-9b-20260310`). Profiles cannot
bypass it — a disallowed `--model` is rejected before any call. No GPT/Claude/Gemini/DeepSeek/
Llama or other disallowed models are referenced (`scripts/audit_model_policy.py` enforces this in
CI-style checks).

### Final offline submission (Phase 2L.47B)

The submitted system is **fully offline**: a single open-weight local model,
**`Qwen/Qwen3-4B-Instruct-2507`** (4.0B < 5B, Apache-2.0), run via Hugging Face Transformers. The
BTC private-test runtime is internet-isolated, so the final path uses **no OpenRouter, no external
API, and no web retrieval**.

The entry point is **`predict.py`** (run via **`inference.sh`**, the image default;
`CMD ["bash", "inference.sh"]`, `WORKDIR /code`). It:

1. Resolves the input (`--input`/`$INPUT_FILE` → `/code/private_test.json` → `/app/data/*.json`
   → `/data/*.json` → `/data/*.csv`).
2. Loads the local model **once** (`src/local_model/qwen_mcq_predictor.py`; greedy / answer-only).
3. For **each** question, builds a labeled-choice MCQ prompt, generates deterministically, parses
   the option label, and — on any failure — uses a deterministic fallback label so every qid is
   answered.
4. Writes **`/code/submission.csv`** (`qid,answer`) and **`/code/submission_time.csv`**
   (`qid,answer,time` — a **real per-sample** time measured around each inference); mirrors to
   `/output/pred.csv` for backward compatibility.

Model weights are downloaded at **Docker build time** (`scripts/download_local_model.py`) into
`/models/qwen3-4b-instruct-2507`; the container runs with `TRANSFORMERS_OFFLINE=1` /
`HF_HUB_OFFLINE=1`. No vector database is required, no indexing step is required, and only the
Qwen model is initialized during Docker build. GPU is used via `--gpus all`; `--ipc=host` is not
required, `--shm-size` is not required, and no vLLM is used. No secret is ever stored in GitHub.

BTC confirmed CUDA 12.8+ base images for the target GPU environment, so the final
GPU/local-Transformers image uses the clean official
`nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04` base and exact-pinned PyTorch `torch==2.7.1` from
the `cu128` wheel index. The original CUDA 12.2 template is historical context only. Because this
solution does not use vLLM, `--ipc=host`, `--shm-size`, `uv`, and `--torch-backend=cu128` are not
required.

The earlier dynamic API pipeline described above (base → V12B → V13 → selector, OpenRouter) is
retained only as a **dev-only** path (`predict.py --legacy-dynamic-full`) and is **not** used by
the offline submission.

This document describes the design and the public-leaderboard checkpoints that were actually
observed for the legacy dynamic system (V11 78.40 → V12B 78.83 → V13 79.7); it makes no unverified
private-set claims for the offline local model.
