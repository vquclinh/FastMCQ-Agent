# Audit — Phase 2L.26A: Selective Multi-Candidate API Runner + Model-Policy Guard

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Implemented the controlled API execution layer for the answer factory: a competition
**model-policy guard**, five API candidate agents (builders/parsers), a guarded
OpenRouter wrapper, a dry-run-default selective runner, a v11 builder + reviewer, and
a repo policy scanner. **No API call was made; no inference run; no final prediction;
`outputs/pred.csv` and v10 untouched.** All API paths are gated by the model policy and
require an explicit human `--execute`.

## Files changed

**New (src)**
- `src/model_policy.py` — `is_allowed_llm_model`/`assert_allowed_llm_model`,
  `is_allowed_rerank_model`/`assert_allowed_rerank_model`.
- `src/api_candidate_agents.py` — builders + parsers for route_specialist, challenger,
  option_elimination, tool_hint, pairwise_judge.
- `src/selective_api_client.py` — guarded OpenRouter wrapper (asserts policy at
  construction AND every call; retries; strict JSON; usage).

**New (scripts)**
- `scripts/run_selective_multicandidate_api.py` — dry-run-default runner.
- `scripts/build_v11_from_api_candidates.py`, `scripts/review_v11_api_candidate.py`.
- `scripts/audit_model_policy.py` — runtime model-reference scanner.

**New (tests)**
- `tests/test_model_policy.py`, `tests/test_selective_api.py`.

**Modified**
- `src/answer_ranker.py` — added a gated multi-agent consensus override (≥3 independent
  sources agree + evidence + no contradicting deterministic proof; flagged for review).
- `scripts/run_production_pipeline.py` — enforces `assert_allowed_llm_model` /
  `assert_allowed_rerank_model` before building the base/reranker.
- `src/openrouter_client.py` — docstring slash removed (keeps the policy scanner clean).

## API agents implemented

route_specialist (route-aware, strict JSON with answer/confidence/rationale/evidence/
risk), challenger (tries to disprove v10; keeps v10 if it can't), option_elimination
(eliminates options explicitly + final answer), tool_hint (uses cards/hints/tool
candidates, no invented formulas), pairwise_judge (v10 vs alternatives; evidence over
confidence; `requires_manual_review`). All are builders/parsers only — no API here.

## Model allowlist

- **Allowed LLMs:** Qwen3.5 Series ≤ 9B (`qwen/qwen3.5-9b`, `qwen/qwen3.5-9b-20260310`)
  and explicitly-approved Gemma-4 aliases (`google/gemma-4-9b`, `gemma-4-9b`, `-it`).
- **Allowed rerank/embedding:** BGE-M3, Qwen-Rerank, local `models/qwen3-reranker-0.6b`.
- **Rejected examples (verified):** `gpt-4o`, `openai/gpt-4`, `claude-opus-4-8`,
  `anthropic/claude-3`, `gemini-1.5-pro`, `deepseek-chat`, `meta-llama/llama-3-70b`,
  `mistral-large`, and Qwen >9B (`qwen2.5-14b`, `qwen3.5-32b/72b`), `gemma-2-9b`.
  Rejected rerank: `openai/text-embedding-3`, arbitrary embedders.
- **Where enforced:** `selective_api_client` (construction + every call),
  `run_selective_multicandidate_api` (`--model` guard before anything), every agent
  call routes through the guarded client, and `run_production_pipeline` (base +
  reranker). Gemma is allowed only via the explicit alias list, not arbitrary "gemma".

## Dry-run behavior

`run_selective_multicandidate_api` is **dry-run by default**; `--dry-run` and
`--execute` are **mutually exclusive**. Without `--execute` it prints model, agents,
temperature grid, planned qids, calls/qid, **upper-bound call count**, and an estimated
cost, then exits with **no API call**. Verified: 120 qids × (4 agents × 2 temps + judge)
= 9 calls/qid → 1080 upper-bound calls, est. $2.16. Output dirs must be under
`scratch/` (refuses `outputs/`).

## Output artifacts (execute path; scratch only)

`api_candidates.jsonl` (appended per qid, crash-safe resume), `api_candidates.csv`,
`api_run_summary.json`, `api_run_summary.md`. Each candidate record: qid, agent, model,
temperature, answer, confidence, rationale, evidence, risk, parse_status, v10_answer,
agrees_with_v10, total_tokens, timestamp.

## v11 build / review pipeline

`build_v11_from_api_candidates` merges the offline factory pool with API candidates
(`api:<agent>` sources), ranks via `answer_ranker.select_answer`, and emits proposals
only where the selection differs from v10 (scratch only; never promotes to pred.csv;
refuses `outputs/`). `review_v11_api_candidate` summarizes risk/source breakdown and
emits a gate: `submit_candidate` (all deterministic, low-risk) /
`manual_review_required` (few, consensus + evidence) / `reject_candidate` (model/judge-
only or too many). Verified end-to-end with a synthetic 3-agent consensus →
`manual_review_required`.

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **446 passed** (was 424; +22).
- `scripts/audit_model_policy.py`: **PASS — only competition-allowed models referenced.**
- Coverage: allow/reject LLM + rerank; assert raises; prompt builders include labels +
  route instructions; parsers accept valid / reject invalid label / no-json; **runner
  dry-run makes no API call**; **runner rejects disallowed `--model`**; `--dry-run`/
  `--execute` mutually exclusive; refuses non-scratch output; **fake-execute writes
  JSONL + resume skips completed**; budget logic present; v11 builder refuses outputs
  path; ranker keeps v10 on a weak single API candidate and **overrides only on
  ≥3-source consensus with evidence**; policy scanner detects a disallowed model in a
  runtime file and ignores external-sheet columns; pairwise-judge/client reject
  disallowed models; no qid hardcoding.

## Confirmations

- **No API call during this coding phase** (dry-run + fakes only).
- **No final prediction generated**; `outputs/pred.csv` and
  `outputs/pred_v10_full_production_user_run.csv` untouched; all artifacts under `scratch/`.
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used as truth.
- **No disallowed model introduced** (scanner PASS); no fallback to GPT/Claude/Gemini/
  DeepSeek anywhere, including judging/parsing.
- `outputs/scratch` not deleted; nothing committed.

## Exact human-run commands (operator; API only with explicit --execute)

```bash
# 1) Dry run (no API): see the plan + upper-bound call count
.venv/bin/python scripts/run_selective_multicandidate_api.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --v10-log scratch/v10_full_production/run_v10_full_production_user_run.jsonl \
  --plan scratch/answer_factory_2l25/selective_api_plan.csv \
  --output-dir scratch/selective_multicandidate_2l26 \
  --model qwen/qwen3.5-9b-20260310 --max-qids 120

# 2) Execute first 20 qids (API)
.venv/bin/python scripts/run_selective_multicandidate_api.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --v10-log scratch/v10_full_production/run_v10_full_production_user_run.jsonl \
  --plan scratch/answer_factory_2l25/selective_api_plan.csv \
  --output-dir scratch/selective_multicandidate_2l26 \
  --model qwen/qwen3.5-9b-20260310 --max-qids 20 \
  --agents route_specialist,challenger,option_elimination,tool_hint --judge pairwise \
  --temperature-grid 0,0.2 --max-tokens 768 --budget-usd 2 --resume --execute

# 3) Execute full 120 qids (API) — same as above with --max-qids 120
# 4) Build v11 proposals (no API)
.venv/bin/python scripts/build_v11_from_api_candidates.py \
  --input public-test_1780368312.json \
  --base-pred outputs/pred_v10_full_production_user_run.csv \
  --api-candidates scratch/selective_multicandidate_2l26/api_candidates.jsonl \
  --output-dir scratch/selective_multicandidate_2l26
# 5) Review v11 candidate (no API)
.venv/bin/python scripts/review_v11_api_candidate.py \
  --proposals scratch/selective_multicandidate_2l26/v11_api_ranked_proposals.csv \
  --output-dir scratch/selective_multicandidate_2l26
```

## git status (new this phase)

```
?? src/model_policy.py, src/api_candidate_agents.py, src/selective_api_client.py
?? scripts/run_selective_multicandidate_api.py, build_v11_from_api_candidates.py,
   review_v11_api_candidate.py, audit_model_policy.py
?? tests/test_model_policy.py, tests/test_selective_api.py
?? docs/AUDIT_PHASE_2L26A_SELECTIVE_MULTICANDIDATE_API_RUNNER.md
 M src/answer_ranker.py, scripts/run_production_pipeline.py, src/openrouter_client.py
```
(Plus earlier uncommitted 2L.x files; `outputs/*`, `scratch/*` gitignored.)

## Next step

Operator runs the dry-run, reviews the plan, then executes the gated API pass (start
with 20 qids + a budget), builds v11 proposals, and reviews the safety gate. Only a
`submit_candidate` / reviewed `manual_review_required` result should lead to a v11 CSV
(into a NEW file, A/B vs v10). v10 remains the submission until then.

Do not commit until a result is accepted.
