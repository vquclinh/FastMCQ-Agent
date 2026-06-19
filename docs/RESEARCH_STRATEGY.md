# Research Strategy

_Methodological strategy for FastMCQ-Agent. Written to be reusable, with light
editing, in the final method report. It states what is implemented today versus
what is planned, and the reasoning behind each choice._

## 1. Problem framing: Vietnamese multi-domain MCQA

The task is multiple-choice question answering over a **Vietnamese**, **multi-
domain** test set: 463 public questions spanning reading comprehension, general
knowledge, economics, and a large block of STEM/calculation items. Two
structural properties dominate the design:

- **Variable option counts (2–11).** About 29% of questions have more than four
  choices (a large 10-choice cluster). Any A–D assumption is wrong; labels must
  be sized per question.
- **Mixed length.** ~22% are long passage-based questions (up to ~8.7k chars),
  while most are short standalone questions. Prompt budgeting must protect both
  the passage signal and the answer choices.

The system reads `/data`, writes `/output/pred.csv` (`qid,answer`), and must be
robust and deterministic. There is no local ground truth, so model choices are
validated on the **leaderboard**.

## 2. Why simple generation is not enough

The most obvious approach — prompt the model and read the letter it generates —
is fragile in this setting:

- **Format drift.** Models add explanations, translate the label, or answer in a
  sentence; parsing must absorb many shapes and still sometimes fails.
- **Tokenizer noise.** A single generated letter carries little signal and is
  sensitive to decoding settings.
- **No calibrated comparison.** Generation gives one answer, not a comparison
  across options, so we cannot see how close the runner-up was.

Generation is implemented (`hf_generate`) and useful as a **baseline and
fallback**, but it is not the intended backbone.

## 3. Likelihood-based option scoring (the backbone)

The primary method scores each candidate answer as a **continuation** of the
prompt and picks the highest **length-normalised average log-probability**. This
turns MCQA into a direct comparison the model is actually good at, and it scales
cleanly to any number of options.

Three continuation styles are selectable (`--score-mode`):

| Mode | Continuation | Rationale |
|---|---|---|
| `label_only` | `" A"` | Cleanest signal *if* the tokenizer cooperates; brittle across tokenizers. |
| `label_plus_choice` *(default)* | `" A. <choice text>"` | Robust: binds the label to its content; survives tokenizer quirks. |
| `choice_only` | `" <choice text>"` | Pure content likelihood, label-free; useful contrast. |

We default to `label_plus_choice` for robustness, but **which mode wins is an
empirical question** to be settled on the leaderboard — hence all three are
first-class options, and the debug log records the score mode, per-label scores,
best/second-best labels, and the margin for later analysis.

## 4. CoT-style prompting for reasoning/calculation

Many STEM items need a short derivation. We allow the model to reason
*internally* but the **final emitted answer is always a single label** — the
prompt explicitly forbids explanations in the output, and the parser/scorer only
consume a label. This keeps the contract clean while not suppressing reasoning.

- **Implemented:** shape-aware prompting (`detect_question_shape`) that tells
  calculation questions they may compute internally but must output only the label.
- **Planned:** an optional light CoT variant for the generation path on hard
  items, measured against the no-CoT scorer before adoption.

## 5. Self-consistency for low-confidence cases

When the top-2 score margin is small, a single pass is least reliable. Self-
consistency (sample several reasoning paths, majority-vote the label) can rescue
these — but it multiplies cost.

- **Planned, selective:** trigger self-consistency *only* when the logged margin
  is below a threshold, so the expensive path is reserved for genuinely close
  calls. The margin is already recorded in the debug log to make this targeting
  possible.
- **Why not always-on:** under an unknown time budget, paying N× on every
  question is reckless; targeting keeps the cost bounded.

## 6. PAL-lite / Python-assisted calculation for numeric questions

The 10-choice numeric cluster is the most distinctive sub-population. A "Program-
Aided" approach — have the model emit a small calculation, execute it in a
sandbox, and match the result to the closest option — could lift accuracy there.

- **Status: planned, gated.** Only worth building if leaderboard data shows the
  numeric cluster is a weak spot. Risks (sandbox safety, parsing the model's
  code, latency) mean it is deferred until the simpler pipeline is measured.

## 7. RAG-inspired in-question passage compression for long context

Long passages can blow the prompt budget. Today we use a **head-tail
truncation** that preserves the passage opening and the trailing question while
never dropping the answer choices (`truncate_question`).

- **Implemented:** deterministic head-tail truncation, choices always intact.
- **Planned:** RAG-inspired *in-question* compression — split the passage into
  segments, score/retrieve the segments most relevant to the question (e.g. with
  BGE-m3 if approved), and keep those. This is "RAG over the provided passage,"
  not external retrieval — no outside corpus, consistent with the rules.

## 8. What is already implemented

- Dynamic labels (A..K), validity sized to each question.
- Vietnamese, shape-aware prompting; head-tail truncation that protects choices.
- `hf_generate` (parse a single label) and `hf_option_score` (3 score modes).
- Robust output parser; deterministic decoding by default.
- Per-sample debug logging (scores, best/second, margin, fallback reason) and a
  runtime benchmark.
- Model-compliance guardrail + LLM-environment checker.

## 9. What is planned

Phase names follow the canonical roadmap (`docs/ARCHITECTURE.md` §11):

- **Phase 2F** — lightweight, deterministic agent modules (profiler, router,
  passage compressor, confidence), no model needed. **(implemented, tested)**
- **Phase 2G** — AdaptiveAgentSolver v1 wiring those modules around the existing
  option-scoring backbone (Minimal Viable Agent v1; see `ARCHITECTURE.md` §14).
  **(implemented as `adaptive_agent`; advanced methods gated off; not yet run on a
  real model)**
- **Phase 2H** — first real local-model run + score-mode/prompt comparison,
  logged to the leaderboard.
- **Phase 2I** — speed work: batching, quantization, token/compute budgets.
- **Phase 2J** — selective self-consistency, PAL-lite for numerics, and other
  advanced reasoning — each adopted only if measured gains justify the cost.

## 10. What is intentionally avoided (runtime / deadline)

- Always-on self-consistency or large ensembles before knowing the time budget.
- Unapproved or oversized models (see `docs/MODEL_COMPLIANCE.md`).
- External retrieval / external APIs (out of scope and likely disallowed).
- Heavy refactors near the deadline; the baseline must always produce a valid
  submission.

## 11. How this supports "tư duy tối ưu & sáng tạo"

The strategy is explicitly **measure-then-optimise**: a robust, well-instrumented
backbone (option scoring with selectable modes and full score logging), with
creative-but-costly techniques (self-consistency, PAL, passage compression)
designed as **targeted, evidence-gated** add-ons rather than blanket
applications. This demonstrates optimisation thinking (cost-aware, leaderboard-
driven decisions) and creativity (problem-specific methods for the numeric and
long-context sub-populations) while keeping the system reproducible and within
budget.

## 12. Multi-agent architecture (FastMCQ-Agent++)

The strategy above is realised as a **budget-aware multi-agent pipeline**, fully
specified in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md):

`normalize → dynamic labels → profile → budget → route → specialist agent →
evidence build → option scoring → verify/confidence → selective fallback →
final answer`.

Key principles:
- **Cheap by default:** a deterministic profiler/router (no LLM call) sends most
  questions through a single option-scoring pass (Tier 0).
- **Specialists, not one prompt:** distinct handling for short-knowledge,
  long-context, calculation, law/admin, safety/ethics, and ambiguous routes.
- **Research mapped to lightweight modules:** CoT (internal, label-only),
  RAG (in-question passage selection), Lost-in-the-Middle (evidence placement),
  ReAct (module separation), Self-Consistency / PAL-lite / Self-Refine /
  debate-lite / ToT-lite as **rationed Tier-2 fallbacks** triggered by the
  confidence margin and the budget controller.
- **Evidence over complexity:** every advanced technique is adopted only if a
  leaderboard ablation shows a real gain at acceptable runtime; the default solver
  remains the safe baseline.
