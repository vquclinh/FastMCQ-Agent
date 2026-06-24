# `src/` — FASTMCQ module map

The package is intentionally **flat** (one directory, no sub-packages). A sub-package
reorg was attempted and reverted: a pre-existing `src/utils.py` (logging) collides with a
desired `src/utils/` package, and the modules use relative `from .utils import log`-style
imports that break on relocation. Renaming/merging `utils.py` + rewriting every relative
import is a large, error-prone change unsafe to land pre-submission, so `src/` stays flat
and is **documented** here instead. This file is the logical grouping; it does not move code.

## System / orchestrator (production entrypoint)

- `fastmcq_system.py` — **the dynamic full-system orchestrator**. `run_fastmcq_system(samples,
  output_csv, config)`: dynamic base predictor → V12B → V13 → unified selector, for any input
  qids. This is what `scripts/run_full_system.sh` and `scripts/final_infer.py` drive.
- `system_candidate_selector.py` — unified conservative selector that combines the V12B and V13
  layer proposals into final answers.
- `dynamic_base_predictor.py` — the dynamic base prediction pass over arbitrary inputs.

## Official layers (enabled by default in `dynamic_full`)

- `v12b_dynamic_layer.py` — V12B option-permutation debiaser (promoted at 78.83). Incremental
  JSONL records + resume by `(qid, permutation_id)`.
- `mcq_permutation_debiaser.py` — the permutation-debias core used by the V12B layer.
- `v13_dynamic_layer.py` — V13 multi-layer reasoning (promoted at 79.7): programmatic solver,
  content-first normalizer, least-to-most constraint table. Incremental JSONL + resume by
  `(qid, layer)`; builds validated non-empty message lists.
- `v13_layer_registry.py` — registry/dispatch of the V13 sub-layers.
- `content_first_answerer.py`, `least_to_most_constraint_solver.py`,
  `programmatic_solver_layer.py`, `programmatic_solver.py`, `pot_lite.py` — V13 reasoning
  sub-strategies (content-first, least-to-most, deterministic programmatic/arithmetic).

## Base solvers & answer assembly

- `baseline_solver.py`, `solver_base.py`, `solver_factory.py` — solver interface + factory.
- `calculation_solver.py`, `calculation_first_planner.py`, `formula_bank_solver.py`,
  `formula_registry.py`, `concept_solver.py` — domain solvers (arithmetic / formula / concept).
- `answer_factory.py`, `answer_ranker.py`, `independent_answer_selector.py`,
  `candidate_answer.py`, `candidate_consistency.py`, `structured_answer.py` — candidate
  generation, ranking, consistency, and final answer structuring.
- `mcq_verifier.py`, `evidence_verifier_policy.py` — answer verification policy.

## Adaptive routing / orchestration (research lineage)

- `adaptive_orchestrator.py`, `adaptive_routing.py`, `adaptive_agent_solver.py`,
  `adaptive_accuracy_planner.py`, `adaptive_proposal_common.py`, `adaptive_types.py`,
  `question_router.py`, `question_profiler.py` — adaptive branch selection / profiling.

## Retrieval & evidence

- `rag_lite.py`, `evidence_pack.py`, `evidence_reranker.py`, `evidence_sufficiency.py`,
  `option_evidence.py`, `option_grounding.py`, `passage_compressor.py`, `knowledge_cards.py` —
  lightweight retrieval, reranking, evidence sufficiency, and option grounding.

## API layer (allowed-model access)

- `selective_api_client.py` — selective API client; guards against empty prompts before the
  retry loop.
- `openrouter_client.py`, `openrouter_prompts.py`, `openrouter_graph_solver.py`,
  `api_candidate_agents.py` — OpenRouter access, prompt templates, graph solver, candidate
  agents.
- `model_policy.py` — competition model-allowlist enforcement (`is_allowed_llm_model`).

## Local HF inference

- `hf_common.py`, `hf_generate_solver.py`, `hf_option_score_solver.py` — local
  transformers-based generation / option-scoring solvers.

## Prompting & parsing

- `prompting.py`, `production_prompts.py`, `output_parser.py`, `confidence.py`,
  `labels.py` — prompt construction, output parsing, confidence, and the global label space.

## Production pipeline & post-processing (legacy lineage)

- `production_inference.py`, `production_policy.py`, `postprocess.py` — the older production
  pipeline path (driven by `scripts/legacy/run_production_pipeline.py`).

## I/O & utilities

- `data_io.py` — input loading (JSON + BTC CSV: `question|text|prompt|content`, A/B/C/D cols).
- `run_logger.py`, `utils.py` — logging (`log`), run records, misc helpers.
- `__init__.py` — package marker.
