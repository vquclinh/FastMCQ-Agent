# FastMCQ-Agent++: A Budget-Aware Multi-Agent Reasoning System for Vietnamese MCQA

_Design document. No accuracy is claimed before leaderboard runs._

> ## Two operating modes
>
> The project runs in **two complementary modes** (both implemented):
>
> - **Mode A — Round 1 (leaderboard / CSV upload):** the **`openrouter_graph`**
>   solver calls the **OpenRouter API** (default model `qwen/qwen3.5-9b`) with
>   structured-JSON output and a fast graph runner. This is **not** the offline
>   mode — it uses an external API by design, for speed of iteration in Round 1.
>   See `docs/OPENROUTER_ROUND1_STRATEGY.md`.
> - **Mode B — later Docker / local reproducibility:** the **offline, local-LLM**
>   solvers (`hf_option_score`, `adaptive_agent`) run a local quantized model with
>   **no external API**. This is the system described in detail below.
>
> The two modes **share** the same deterministic profiler, router, passage
> compressor, dynamic-label handling, validation, and `qid,answer` contract.
> "Offline / no external API" statements in this and the other design docs refer
> to **Mode B**; Mode A intentionally uses OpenRouter.

## 1. Executive summary (Mode B — offline local system)

FastMCQ-Agent++ (Mode B) is an **offline, local-LLM, multi-agent** inference system for
Vietnamese multiple-choice QA. It is deliberately **not** a single-prompt "ask
the LLM and read the letter" pipeline. Instead it:

- **profiles** each question with cheap, deterministic features (no LLM call),
- **routes** it to a specialized strategy,
- answers primarily by **likelihood-based option scoring** (the MCQA backbone),
- **verifies** the answer with a confidence check, and
- escalates to **selective, more expensive reasoning** only for low-confidence or
  high-value cases, under an explicit **compute budget**.

The design optimizes four things at once: **accuracy**, **inference time**,
**reproducibility**, and **model compliance** (Qwen3.5 ≤ 9B / Gemma-4 for
generation; BGE-m3 / Qwen-Rerank for embedding/rerank only if permitted). Every
expensive technique is gated behind a budget controller so the system stays fast
on a large private test set. The whole pipeline runs locally and offline and
always emits a valid `qid,answer` submission.

## 2. Why a multi-agent system is needed

A single fixed prompt is insufficient because the test set is heterogeneous and
the constraints are real:

- **Variable choice counts (2–11).** 318 questions have 4 choices but 134 have 10;
  a few have 2, 3, 5, or 11. Prompts and scoring must be choice-count agnostic.
- **Long-context questions (~100, 21.6%).** Passages up to ~8.7k chars need
  compression and careful evidence placement (lost-in-the-middle).
- **Calculation-heavy questions.** A large numeric/LaTeX cluster benefits from
  reasoning and (later) program-aided checking, which short factual questions do not.
- **Domain variation.** Reading, general knowledge, economics, law/admin, ethics —
  different framings help different domains.
- **No ground truth.** We cannot tune on labels; decisions must be robust and
  leaderboard-driven, not overfit.
- **Private test may differ from public test.** The system must generalize, not
  encode public-set quirks.
- **Speed matters.** Scoring a 10-choice question costs ~10 forward passes;
  applying expensive reasoning to all samples would blow the time budget.

A router + specialist + verifier design lets us spend compute where it pays and
stay cheap everywhere else.

## 3. System overview

```text
raw sample
   ↓
Input Normalizer Agent
   ↓
Dynamic Label Manager
   ↓
Question Profiler Agent
   ↓
Budget Controller
   ↓
Router Agent
   ↓
┌───────────────────────────────────────────────────────┐
│ Specialist Agents                                      │
│ - Knowledge Agent                                      │
│ - Reading / Long-Context Agent                         │
│ - Calculation Reasoning Agent                          │
│ - Law/Admin Agent                                      │
│ - Safety/Ethics Agent                                  │
│ - Ambiguity Agent                                      │
└───────────────────────────────────────────────────────┘
   ↓
Evidence / Context Builder
   ↓
Candidate Scoring Engine
   ↓
Verifier + Confidence Agent
   ↓
Selective Fallback Controller
   ↓
Final Answer Agent
   ↓
pred.csv
```

Most samples take the straight path (profile → route → score → verify → accept).
The fallback controller only diverts low-confidence/hard cases into more expensive
agents. "Agent" here means a focused module with one responsibility — not an
autonomous LLM loop — which keeps the system deterministic and debuggable.

## 4. Agent / module roles

### Input Normalizer Agent
- Reads JSON or CSV from `/data`; preserves `qid` exactly.
- Normalizes each record to `{qid, question, choices}`; absorbs schema variants
  (`A,B,C,D` / `option_*` / `choice_*` / single `choices` column).
- **Status:** implemented (`src/utils/data_io.py`).

### Dynamic Label Manager
- Builds `A, B, C, ...` labels sized to the actual choice count (2–11, extensible
  to 26); validates labels; prevents out-of-range labels.
- **Status:** implemented (`src/utils/labels.py`).

### Question Profiler Agent
- Computes cheap, deterministic features with **no LLM call**: question length,
  number of choices, long-context markers (`Đoạn thông tin`, `Nội dung:`,
  `Tiêu đề:`, `-- Đoạn văn`), numeric density, LaTeX/math symbols, legal/admin
  keywords, safety/ethics keywords, duplicate choices.
- **Status:** partially implemented (`detect_question_shape` in
  `src/utils/prompting.py`); full profiler planned (`src/layers/question_profiler.py`, 2F).

### Budget Controller
- Maps profile → a compute tier (0/1/2, see §8). Easy questions get the cheap
  route; expensive reasoning is reserved for low-confidence / high-risk cases.
- Tracks a global budget so a ~2000-sample private test finishes in time.
- **Status:** planned (logic to live in the adaptive solver, 2G).

### Router Agent
- Assigns one route: `short_knowledge`, `long_context`, `calculation`,
  `law_admin`, `safety_ethics`, `ambiguous`, `unknown`.
- **Deterministic heuristics first** (keywords, choice patterns, numeric density);
  optional LLM-assisted routing later. Router output informs, but is not trusted
  blindly — the verifier can override.
- **Status:** planned (`src/layers/question_router.py`, 2F).

### Knowledge Agent
- Short factual/commonsense questions. Primary: option scoring. Fallback:
  generation or an alternate score mode.

### Reading / Long-Context Agent
- Passage-based questions. Performs **RAG-inspired in-question passage selection**
  (over the provided passage only — never the internet). Preserves the title, the
  final question, and all choices; positions the most relevant evidence near the
  question to mitigate lost-in-the-middle.

### Calculation Reasoning Agent
- Math/physics/chemistry/economics numeric questions. Primary: a careful reasoning
  prompt + option scoring. Future: **PAL-lite** — extract the arithmetic, compute
  it in a **restricted sandbox**, match the closest option.

### Law/Admin Agent
- Legal/administrative/policy questions. Grounded, conservative prompt; avoids
  unsupported assumptions and invented statutes.

### Safety/Ethics Agent
- Safety/ethics/best-practice/refusal-style questions. Rule-aware prompt; avoids
  harmful or unsafe interpretations.

### Ambiguity Agent
- Low-confidence, duplicate-choice, or near-tie cases. May trigger an alternate
  score mode, generation, or **selective** self-consistency.

### Evidence / Context Builder
- Builds the final route-specific prompt context: compresses long context, keeps
  **all choices intact**, keeps the **final question visible**, and **logs what
  was kept/dropped** for debugging.
- **Status:** head-tail truncation implemented (`truncate_question`); evidence
  selection planned (`src/evidence/passage_compressor.py`, 2F).

### Candidate Scoring Engine
- The MCQA backbone. Scores each candidate continuation and picks the best
  length-normalised average log-prob. Modes: `label_only`, `label_plus_choice`
  (default), `choice_only`. Logs per-candidate scores and the top-2 margin; modes
  are directly comparable in ablations.
- **Status:** implemented (`src/solvers/hf_option_score_solver.py`).

### Generation Engine
- Fallback and comparison baseline. A robust parser extracts the label; parse
  failures are logged and trigger fallback.
- **Status:** implemented (`src/solvers/hf_generate_solver.py`, `src/utils/output_parser.py`).

### Verifier + Confidence Agent
- Checks: score margin, parse success, invalid label, duplicate choices, and
  route/strategy consistency. Decides **accept vs fallback**.
- **Status:** planned (`src/selector/confidence.py`, 2F).

### Selective Fallback Controller
- Escalation ladder: high-confidence → accept; low-confidence → alternate score
  mode → generation; calculation + budget → PAL-lite; very hard + budget →
  self-consistency / debate / ToT-lite. **Always** yields a valid label.
- **Status:** planned (2G/2J).

### Final Answer Agent
- Guarantees exactly one valid label per qid; writes only `qid,answer`; **never**
  writes reasoning into `pred.csv`.
- **Status:** implemented (`src/utils/postprocess.py`, `src/utils/data_io.py`).

## 5. Routing policy table

| Route | Detection signals | Primary strategy | Fallback strategy | Runtime cost | Expected benefit | Risks / caveats |
|---|---|---|---|---|---|---|
| `short_knowledge` | short text, no passage markers, low numeric density | `option_score_label_plus_choice` | alternate score mode → generation | Low (Tier 0) | Cheap, strong on facts | Subtle distractors; little context to exploit |
| `long_context` | passage markers, length above threshold | `context_grounded_option_score` (compressed evidence) | head-tail truncation → generation | Medium (Tier 1) | Fights lost-in-the-middle | Compression may drop the decisive sentence |
| `calculation` | LaTeX/math symbols, high numeric density, ≥10 numeric choices | `calculation_careful_option_score` | PAL-lite (later) → generation | Medium→High | Helps the large numeric cluster | Reasoning errors; PAL parsing/sandbox risk |
| `law_admin` | legal/admin keywords | grounded conservative `option_score` | alternate score mode | Low→Medium | Reduces invented-rule errors | Keyword routing is coarse |
| `safety_ethics` | safety/ethics keywords | rule-aware `option_score` | generation | Low | Safer interpretations | Small, noisy class |
| `ambiguous` | small top-2 margin, duplicate choices, tie | alternate score mode | selective self-consistency (budget) | High (Tier 2) | Rescues genuine near-ties | Expensive; cap the count |
| `unknown` | nothing matched | `option_score_label_plus_choice` (safe default) | generation | Low | Robust default | Misroute risk; verifier guards |

## 6. Strategy policy table

| Strategy | When to use | Research inspiration | Status | Runtime cost | Expected benefit | Stop condition |
|---|---|---|---|---|---|---|
| `option_score_label_plus_choice` | default backbone | likelihood scoring | **implemented** | Low (≈1 pass/choice) | Stable MCQA accuracy | — (always available) |
| `option_score_label_only` | ablation / tokenizer-clean models | likelihood scoring | **implemented** | Low | Sometimes cleaner signal | If it underperforms default on leaderboard |
| `option_score_choice_only` | ablation / label-free contrast | likelihood scoring | **implemented** | Low | Pure content likelihood | If it underperforms default |
| `direct_generation` | fallback, comparison baseline | instruction following | **implemented** | Low–Med | Cheap second opinion | On parse failure → fallback |
| `context_grounded_option_score` | long-context route | RAG (in-question) + Lost-in-the-Middle | planned (2F/2G) | Medium | Better passage QA | When evidence selection helps no further |
| `calculation_careful_option_score` | calculation route | CoT (internal) | planned (2G) | Medium | Better numeric reasoning | When margin is high |
| `low_confidence_self_consistency` | small margin, high value | Self-Consistency | planned (2J) | High (N×) | Rescues close calls | After K samples or budget exhausted |
| `pal_lite_math_helper` | numeric calculation, budget allows | PAL / PoT | planned (2J) | High | Exact arithmetic | If extraction/sandbox fails → fallback |
| `self_refine_verification` | borderline answers | Reflexion / Self-Refine | planned (2J) | Medium | One-shot revision, no looping | One refine pass max |
| `multi_agent_debate` | rare ambiguous high-value | Debate | planned (2J, optional) | Very High | Consensus on hard cases | Strict per-run cap |
| `tot_lite_deliberation` | rare very hard cases | Tree-of-Thought | planned (2J, optional) | Very High | Structured deliberation | Depth/branch cap |
| `got_style_future_reasoning` | research-only | Graph-of-Thought | future / maybe never | Very High | Speculative | Not for the deadline |

## 7. Research mapping

The system maps top-tier research ideas into **lightweight, gated** modules —
not full reimplementations. Runtime and reproducibility dominate every choice.

- **Chain-of-Thought →** internal reasoning prompt for the calculation route; the
  emitted output is still **only a label**.
- **Self-consistency →** a low-confidence fallback (small margin), not always-on.
- **PAL / Program-Aided LMs →** a future numeric helper that computes arithmetic
  in a restricted sandbox and matches the closest option.
- **RAG →** **in-question** passage selection/compression over the provided text;
  no external corpus, no internet.
- **Lost-in-the-Middle →** evidence positioning (relevant text near the question)
  and context compression instead of dumping the whole passage.
- **ReAct →** clean separation of reasoning vs. action modules (router, context
  builder, scorer, verifier, fallback controller) rather than one tangled loop.
- **Reflexion / Self-Refine →** logged error analysis and a single, selective
  answer revision — never uncontrolled looping.
- **Multi-agent debate →** a rare, capped consensus step for ambiguous high-value
  cases only.
- **Tree/Graph-of-Thought →** rare, depth-capped deliberation for very hard cases;
  GoT is research-only and may never ship.
- **Likelihood-based option scoring →** the MCQA **backbone**, used by default.

We explicitly use **lightweight versions**, do **not** blindly implement heavy
research systems, and gate everything expensive behind the budget controller.

## 8. Budget-aware decision policy

### Tier 0 — Cheap
- One option-scoring pass (`label_plus_choice`).
- For short/easy questions with a clear margin. The common case.

### Tier 1 — Moderate
- Route-specific prompt, context compression, and/or an alternate score mode.
- For long-context, calculation, law/admin, and mildly ambiguous questions.

### Tier 2 — Expensive
- Self-consistency, PAL-lite, debate-lite, or ToT-lite.
- Only for low-confidence or high-risk questions.

**Why Tier 2 must not run on all samples:** the private test may hold ~2000
questions, and many are 10-choice (≈10 scoring passes each). Multiplying every
sample by an N-sample self-consistency or a debate would make the run miss any
realistic time budget. Tier 2 is rationed to the minority of cases where it
changes the answer, keeping mean latency near Tier 0.

## 9. Confidence and fallback policy

- **Signal:** the option-scoring **top-2 margin** (best minus second-best average
  log-prob), plus parse success and structural checks.
- **High margin →** accept (Tier 0).
- **Medium margin →** verify route/strategy consistency; optionally an alternate
  score mode (Tier 1).
- **Low margin →** fallback ladder (alternate mode → generation → Tier 2 if budget
  and value justify).
- **Parse failure (generation) →** fallback to scoring or `A`.
- **Invalid label →** `postprocess.py` forces a valid label (final safety net).
- **Duplicate choices →** flag in the log; treat near-ties cautiously (the
  profiler already detects 6 such samples in the public set).
- **No ground truth →** all thresholds (margin cutoffs, self-consistency N, Tier 2
  budget) are **tuned against the leaderboard**, conservatively, not on local labels.

## 10. Ablation plan

Run each on the public set, validate, and log to `experiments/leaderboard_log.csv`:

1. `baseline_always_a`
2. `hf_generate`
3. `hf_option_score --score-mode label_only`
4. `hf_option_score --score-mode label_plus_choice`
5. `hf_option_score --score-mode choice_only`
6. `adaptive_agent` (routing, **no** expensive fallback)
7. `adaptive_agent` + context compression
8. `adaptive_agent` + selective self-consistency
9. `adaptive_agent` + PAL-lite (if implemented)

Each row logs: model, route policy, strategy, score mode, runtime, validation
status, leaderboard score. Adopt a technique only when it shows a real gain over
the simpler configuration at acceptable cost.

## 11. Implementation roadmap

### Phase 2F — Lightweight agent modules
- **Objective:** deterministic, no-LLM building blocks (profiler, router, passage
  compressor, confidence) with tests.
- **Files:** `src/layers/question_profiler.py`, `src/layers/question_router.py`,
  `src/evidence/passage_compressor.py`, `src/selector/confidence.py`, `tests/test_*`.
- **Validation:** `.venv/bin/python -m pytest -q`; baseline run + validate PASS.
- **Success:** modules covered by tests; no torch dependency; baseline unaffected.
- **Stop:** modules stable and tested.

### Phase 2G — AdaptiveAgentSolver v1
- **Objective:** wire profiler→router→scoring→verifier→fallback into one solver
  selectable as `adaptive_agent`; log route/strategy/confidence.
- **Files:** `src/layers/adaptive_agent_solver.py`, `src/base/solver_factory.py`,
  `configs/default.yaml`.
- **Validation:** run on a `--limit` slice (when a model exists) + validate;
  baseline still default.
- **Success:** produces valid `pred.csv`; default solver remains `always_a`.
- **Stop:** end-to-end path works on a small slice.

### Phase 2H — Real model ablation
- **Objective:** compare generation / scoring modes / adaptive agent on a real
  compliant model; upload; record scores.
- **Files:** `experiments/leaderboard_log.csv` (rows only).
- **Validation:** smoke → full run → validate → benchmark.
- **Success:** ≥3 logged leaderboard scores with runtimes.
- **Stop:** a clear backbone configuration emerges.

### Phase 2I — Runtime optimization
- **Objective:** batching, quantization (e.g. 4-bit for the 7.6 GB GPU), token
  budgets, route-based compute caps.
- **Files:** `src/solvers/hf_common.py`, `src/solvers/hf_option_score_solver.py`, config.
- **Validation:** `scripts/legacy/benchmark/benchmark_runtime.py`; full run within budget.
- **Success:** target latency met, accuracy retained.
- **Stop:** within budget, no regression.

### Phase 2J — Selective advanced reasoning
- **Objective:** add self-consistency, PAL-lite, debate-lite, ToT-lite — each
  gated by confidence and budget, only if 2H/2I justify.
- **Files:** new helpers + fallback controller.
- **Validation:** A/B vs the 2H backbone on the leaderboard.
- **Success:** measurable gain at acceptable cost.
- **Stop:** added complexity stops paying off.

### Phase 3 — Final packaging and report
- **Objective:** final (possibly model-bearing) Docker, method report,
  reproducibility instructions.
- **Files:** `Dockerfile`, report assembled from these docs.
- **Validation:** clean clone → build → run on mounted `/data` → validated `pred.csv`.
- **Success:** reproducible submission + polished report.
- **Stop:** a fresh environment reproduces the submission.

## 12. What NOT to implement yet

- No external APIs; no internet retrieval.
- No unapproved model families (see `docs/MODEL_COMPLIANCE.md`).
- No full self-consistency on every sample.
- No unrestricted Python execution for PAL (sandbox only, later).
- No overfitting to public-test answers; nothing hard-coded.
- No complex multi-agent debate before the simple ablations are in.

## 13. Immediate recommendation

1. Finish the local `.venv` / LLM dependency setup. **(Done in Phase 2D.1 — the
   env is LLM-ready with a CUDA GPU; note the modest 7.6 GB VRAM.)**
2. Implement **Phase 2F** lightweight modules (profiler, router, compressor,
   confidence) — pure Python, no model needed, fully testable now.
3. Once a compliant `MODEL_PATH` is available, run the **first real model
   ablation** (2H): generation vs scoring modes vs adaptive agent.
4. **Only after leaderboard evidence**, add expensive reasoning (2J).

## 14. Minimal Viable Agent v1

> **Status: implemented (Phases 2F–2G).** All five modules below exist with
> tests; `adaptive_agent` is selectable via `--solver adaptive_agent` (default
> stays `always_a`). Advanced methods remain gated off (enabling one raises
> `NotImplementedError`). It has **not** yet been run on a real model — that is
> Phase 2H and needs a compliant local `MODEL_PATH`.

To prevent over-engineering, the **first** implemented adaptive system
(`adaptive_agent` v1, Phases 2F–2G) is deliberately minimal. It consists of
**exactly these five modules**, and nothing more:

- `src/layers/question_profiler.py` — deterministic, cheap feature extraction (no LLM).
- `src/layers/question_router.py` — deterministic route assignment from the profile.
- `src/evidence/passage_compressor.py` — pure-Python, deterministic passage compression.
- `src/selector/confidence.py` — margin-based accept/fallback decisions.
- `src/layers/adaptive_agent_solver.py` — orchestrates the above and reuses the existing
  scoring backbone.

v1 **must** use:
- **deterministic profiling** (features only; no model call to classify),
- **deterministic routing** (heuristics over the profile),
- **pure-Python passage compression** (lexical, no embeddings),
- the existing **`hf_option_score`** solver as the scoring backbone,
- **margin-based confidence** (option-scoring top-2 margin),
- a **simple fallback** to an alternate score mode or generation.

The following are **explicitly NOT in v1** (deferred to Phase 2J, and only if
leaderboard evidence justifies them):

- ❌ PAL-lite / program-aided calculation
- ❌ multi-agent debate
- ❌ ToT-lite (Tree-of-Thought) deliberation
- ❌ GoT-style (Graph-of-Thought) reasoning
- ❌ unrestricted code execution
- ❌ external retrieval (internet or external corpus)
- ❌ always-on self-consistency

v1 keeps the default solver `always_a`; `adaptive_agent` is opt-in via `--solver`.

### Agent JSONL logging schema

Because there is **no local ground truth**, every `adaptive_agent` run must emit
a rich per-sample debug record (to `--log-path`, never to `pred.csv`) so behaviour
can be analysed and tuned against the leaderboard. Required fields:

```text
qid
route
profile_features
num_choices
question_length
budget_tier
strategy
score_mode
best_label
second_label
margin
fallback_used
fallback_reason
compressed_context_used
compressed_context_stats
duplicate_choice_groups
elapsed_sec
final_answer
```

This logging is the primary debugging instrument: with no labels, we reason about
*why* a route/strategy/fallback fired and correlate aggregate patterns (e.g. high
fallback rate on the calculation route) with leaderboard movement. It extends the
existing `run_logger` records (which already carry scores/margin/fallback) with
route, profile, budget tier, and compression stats.

### Passage compressor v1 policy

The v1 compressor is **pure Python and deterministic** — no embeddings, no model:

- split long text into chunks or sentences,
- extract query terms from the **final question and all choices**,
- score chunks by **lexical overlap / BM25-lite** style scoring,
- **preserve the title/head** if present,
- **preserve the tail / final question**,
- **place selected evidence near the final question** (mitigate lost-in-the-middle),
- **never drop or modify the choices**,
- **log what was kept/dropped** (`compressed_context_stats`).

It does **not** use BGE-m3 or Qwen-Rerank in v1. Neural rerank is a later option,
considered only if (a) it is confirmed allowed and (b) leaderboard evidence shows
the lexical compressor is the bottleneck.

### Confidence v1 policy

v1 confidence is margin-based and config-driven:

- use the **option-scoring top-2 margin** when available,
- **high margin → accept**,
- **medium margin →** try **one** alternate score mode if budget allows,
- **low margin →** try **generation** fallback if budget allows,
- **if all fails →** use the valid `postprocess` fallback (always a valid label),
- **duplicate choices →** logged (`duplicate_choice_groups`) and handled
  deterministically (e.g. prefer the first of tied labels),
- thresholds (high/medium/low margin cutoffs) are **config values**, not
  hard-coded constants,
- thresholds are **not claimed optimal** before leaderboard runs — they start
  conservative and are tuned with evidence.

This sequence front-loads the work that needs no model and defers cost until the
data justifies it — maximizing both progress under the deadline and the quality
of the final, evidence-backed system.
