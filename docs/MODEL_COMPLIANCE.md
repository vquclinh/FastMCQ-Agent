# Model Compliance

This document records which model families we believe we may use, how confident
we are, and what still needs confirmation from the organizer (BTC). The
machine-checkable version of this policy lives in
[`configs/allowed_models.yaml`](../configs/allowed_models.yaml) and is enforced
by [`scripts/check_model_compliance.py`](../scripts/check_model_compliance.py).

> **Status: provisional.** The exact allowed-model list has **not** been
> confirmed in writing for this task. Everything below is our *safe
> interpretation*; treat it as a guardrail, not as organizer authority.

## Candidate model families (as understood)

**Generation LLMs**
- **Qwen3.5 series, ≤ 9B parameters** (e.g. a 7B/9B instruct checkpoint).
- **Gemma-4 series** (size cap unconfirmed).

**Embedding / rerank**
- **BGE-m3** (embeddings / retrieval).
- **Qwen-Rerank** (reranking).

These are the families we will test first, subject to confirmation.

## Safe interpretation (what we will do by default)

- Use **only** the families listed above, and for Qwen3.5 keep it **≤ 9B**.
- Prefer **instruct/chat** checkpoints for the MCQA prompt.
- Run everything **locally**, `local_files_only=True`, no downloads at run time.
- Keep `trust_remote_code=False` unless a specific allowed model requires it,
  and document it if we turn it on.
- Run `check_model_compliance.py` before every leaderboard run; in the final
  pipeline, run it in `--strict` mode.

## Risky interpretation (what we will NOT assume)

- That "any open LLM" is allowed. We do **not** use Llama, Mistral/Mixtral,
  DeepSeek, Phi, Falcon, Yi, Baichuan, or any hosted API (GPT/Gemini/Claude)
  unless BTC explicitly confirms them. These are listed as
  `disallowed_families` in the config and produce a **FAIL**.
- That bigger is better: exceeding the Qwen3.5 ≤ 9B cap is treated as non-compliant.
- That a model "close" to an allowed name is fine — name similarity is a hint,
  not proof of provenance.

## Recommended models to test first

1. **Qwen3.5 ~7B instruct** — strong multilingual (incl. Vietnamese) coverage,
   fits a single modern GPU, clearly within the ≤ 9B cap. **Primary candidate.**
2. **Gemma-4 (small/instruct)** — second opinion / fallback, pending size
   confirmation.
3. **BGE-m3 / Qwen-Rerank** — only if we add retrieval or passage compression
   later (Phase 2G); not needed for the core MCQA solver.

## What still needs organizer confirmation

- [ ] **Exact allowed model names/versions** (not just families).
- [ ] **Whether "other LLMs" are truly allowed** or only the named families.
- [ ] **Whether the submitted Docker image must contain the model weights**, or
      weights are mounted/provided at run time.
- [ ] **Time budget and hardware** (GPU type/VRAM, CPU-only?, wall-clock limit)
      — this drives model size and whether multi-pass scoring is affordable.
- [ ] Whether embedding/rerank models are permitted in addition to the generation LLM.

Until these are answered, the safe interpretation above governs.

## Documenting model provenance (for the final submission)

For every model we actually run, record in `experiments/leaderboard_log.csv` and
the final method report:
- exact model name + version/revision and parameter count,
- where the weights came from (official source) and the license,
- checkpoint hash or directory listing if feasible,
- `trust_remote_code` setting used,
- the `check_model_compliance.py` verdict (ideally **PASS** in `--strict`).

## Why using an unapproved model is dangerous

- **Disqualification / invalid submission** if it violates the rules.
- **Wasted effort:** tuning around a model we cannot legally submit burns the
  limited time budget.
- **Reproducibility / licensing risk:** an unapproved or unclearly-licensed
  model can fail the organizer's verification step.

The cost of checking is tiny; the cost of being wrong is the whole submission.
When in doubt, **ask BTC and default to the safe list.**
