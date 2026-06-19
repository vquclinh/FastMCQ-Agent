# Method

This document describes the approach behind FastMCQ-Agent. It evolves with the
project; Phase 1 establishes the infrastructure, Phase 2 adds real inference.

## Phase 1 — Baseline infrastructure (current)

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

## Phase 2 — LLM solver *(planned)*

> Placeholder. To be filled in when real inference lands.

Plan: implement an LLM-backed solver subclassing `BaseSolver`, selected via
`configs/default.yaml` (`solver:`), with no changes to `run.py`'s pipeline.

- Model choice (local vs. API — note the competition constraints).
- Input formatting of question + enumerated choices.
- Mapping model output back to a single label, with the existing fallback.

## Prompt strategy *(planned)*

> Placeholder.

- Zero-shot vs. few-shot vs. chain-of-thought.
- Handling long context (some questions embed lengthy passages).
- Language considerations (the public test is in Vietnamese).

## Option scoring *(planned)*

> Placeholder.

- Direct label generation vs. per-option likelihood scoring.
- Calibration / tie-breaking across a variable number of options.

## Speed optimization *(planned)*

> Placeholder.

- Batching, quantization, caching, and the time budget per the rules.

## Ablation *(planned)*

> Placeholder.

- Compare prompt strategies, scoring methods, and model sizes on the public
  test; record accuracy vs. latency trade-offs.
