# AUDIT 60 - OpenRouter to Local Qwen Migration

Date: 2026-07-09

## Summary

This task migrated active remote-provider/OpenRouter-backed inference paths to the baked local model:

- Model id: `Qwen/Qwen3-4B-Instruct-2507`
- Baked path: `/models/qwen3-4b-instruct-2507`
- Shared backend: `src/local_model/local_qwen_backend.py`

The accepted BTC no-argument path remains single-pass:

```text
docker run IMAGE
  -> Dockerfile CMD ["bash", "inference.sh"]
  -> inference.sh: python predict.py "$@"
  -> predict.py no-argument path
  -> QwenMCQPredictor facade
  -> LocalQwenBackend.predict_mcq()
  -> /code/submission.csv
  -> /code/submission_time.csv
```

The optional selective path remains explicit and is not the default:

```text
predict.py --legacy-dynamic-full
  -> scripts/tools/final_infer.py --profile local_selective_auto
  -> run_fastmcq_system()
  -> Dynamic Base
  -> local V12B
  -> local V13
  -> system selector
```

## Baseline And Safety

- Original branch: `main`
- Original HEAD: `87d5d71ff2f9d02b9f41c8df351a683f3b683662`
- Expected HEAD matched.
- Initial tracked worktree modifications: none.
- Initial untracked file already present: `docs/audits/AUDIT_59_system_reality_and_dependency_review.md`
- Safety branch created: `backup/before-local-backend-migration-87d5d71`
- Final HEAD: `87d5d71ff2f9d02b9f41c8df351a683f3b683662`
- No commit was created automatically.

## Pre-Migration OpenRouter Dependency Inventory

| Path | Role before migration | Consumer | Action |
|---|---|---|---|
| `src/api/openrouter_client.py` | HTTP transport, auth, retry/status handling | API solver/client tests and legacy scripts | Deleted |
| `src/api/selective_api_client.py` | selective remote model execution | V12B/V13 and API tests | Deleted |
| `src/api/openrouter_graph_solver.py` | remote graph solver | solver factory/tests | Deleted |
| `src/api/openrouter_prompts.py` | remote-provider prompt helpers | verifier/imports | Deleted; generic prompt helper used where needed |
| `src/api/model_policy.py` | allowed remote model policy | final inference/profile tests | Deleted |
| `src/api/api_candidate_agents.py` | reusable candidate prompt/parser logic under API package | calc/adaptive tests | Moved to `src/local_model/candidate_agents.py` |
| `requirements-openrouter.txt` | remote transport dependency file | docs/tests only | Deleted |
| `scripts/audit_model_policy.py`, `scripts/tools/audit_model_policy.py` | remote model-policy audit | docs/tests | Deleted |
| API profile names (`production_full_system`, `production_full_system_noapi`, `api50`, `api100`, `api200`) | remote execution profiles | `final_infer.py`, README, wrappers, tests | Replaced by local profiles |
| `--execute-api`, `--no-api`, `--base-execute-api`, `--no-base-api` | remote execution switches | final inference/docs/tests | Removed |
| `OPENROUTER_API_KEY` | provider key branch | `predict.py`, docs/tests | Removed from active material |
| `scripts/legacy/run/*api*.py` and V11 independent remote runners | remote orchestration | legacy tests | Deleted when transport-only or broken after transport deletion |

## Shared Local Backend Architecture

New file: `src/local_model/local_qwen_backend.py`

Main API:

- `LocalQwenBackend.load()`
- `LocalQwenBackend.generate_text(prompt_or_messages, max_new_tokens=..., temperature=0.0)`
- `LocalQwenBackend.predict_mcq(sample, max_new_tokens=...)`
- `parse_mcq_label(...)`
- `parse_json_object(...)`
- `get_local_qwen_backend(...)`
- `reset_local_qwen_backend_cache()` for tests

Evidence:

- The backend cache is `_BACKENDS: dict[tuple[str, str], LocalQwenBackend]`.
- `get_local_qwen_backend()` returns one backend per `(model_path, device)` inside a process.
- `load()` returns early when `_model` is already loaded.
- `AutoTokenizer.from_pretrained(..., local_files_only=True)` and `AutoModelForCausalLM.from_pretrained(..., local_files_only=True)` prevent runtime downloads.
- CUDA uses `torch.bfloat16`; CPU uses `torch.float32`.
- CUDA auto mode preserves `device_map="auto"`.
- Greedy default generation uses `do_sample=False`, `num_beams=1`.

Compatibility facade:

- `src/local_model/qwen_mcq_predictor.py` now wraps the shared backend.
- The BTC prompt and parser were moved into the shared backend and re-exported through the facade.
- `QwenMCQPredictor.predict_one()` delegates to `LocalQwenBackend.predict_mcq()`.

Proof tests:

- `tests/unit/test_local_qwen_backend.py::test_singleton_reuses_one_backend_per_model_path_device`
- `tests/unit/test_local_qwen_backend.py::test_qwen_predictor_facade_reuses_shared_backend`

## Dynamic Base Migration

File: `src/base/dynamic_base_predictor.py`

Current behavior:

1. For each sample, formula-bank deterministic solving is attempted first.
2. If no deterministic formula answer exists, `backend.predict_mcq()` is called.
3. Fallback is used only for no choices or local inference/parser failure.
4. Base still emits one `BasePrediction` for every input qid.
5. Provenance distinguishes `formula_bank:*`, `dynamic_local_qwen`, `dynamic_fallback_nochoices`, and `dynamic_fallback`.

Removed behavior:

- No OpenRouter client.
- No model policy.
- No API key branch.
- No `skipped_no_api`.
- No "always A" normal strategy; fallback is explicitly weak/failure provenance.

## V12B Migration

File: `src/layers/v12b_dynamic_layer.py`

Current local flow:

```text
select_v12b_targets()
  -> build_option_permutations()
  -> backend.generate_text() for each selected permutation
  -> parse_json_object()
  -> map_permuted_answer_to_original()
  -> summarize_permutation_votes()
  -> select_permutation_override()
```

Preserved:

- Feature/risk target selection.
- `max_qids` cap semantics.
- Conservative acceptance policy.
- Permutation mapping correctness.
- Per-permutation failure isolation.

Removed:

- Remote client/model-policy calls.
- `execute_api=False` skip path.
- `skipped_no_api`.

Failure handling:

- A failed permutation records `parse_status: local_error`.
- One failed permutation does not abort the whole item.

## V13 Migration

File: `src/layers/v13_dynamic_layer.py`

Current local flow:

```text
select_v13_targets()
  -> deterministic programmatic solver when applicable
  -> backend.generate_text() for content_first
  -> backend.generate_text() for least_to_most
  -> parse_json_object()
  -> layer result records
  -> system selector
```

Preserved:

- Programmatic solver remains model-free.
- Content-first and least-to-most reasoning remain separate layers.
- Per-layer provenance is retained in `V13LayerResult.layer` and metadata.
- One model layer failure does not erase another valid candidate.

Removed:

- Remote execution switch.
- API skip branch.
- `skipped_no_api`.

## Full Selective System Migration

File: `src/system/fastmcq_system.py`

`FastMCQSystemConfig` now carries:

- `model_path`
- `device`
- `max_new_tokens`
- `layer_max_new_tokens`
- `local_backend`

`run_fastmcq_system()` obtains one backend:

```text
backend = config.local_backend or get_local_qwen_backend(...)
```

The same `backend` object is passed to:

- `predict_base_answers(...)`
- `run_v12b_layer(...)`
- `run_v13_layer(...)`

This proves Base, V12B, and V13 share one model backend instance inside the process.

## One-Eighth Behavior

The `auto` budget remains in `scripts/tools/final_infer.py`:

```text
max(1, math.ceil(n_input / 8))
```

It applies only when:

- `v12b_max_qids = auto`
- `v13_max_qids = auto`

Semantics after migration:

- Base processes all `N` samples.
- V12B receives an independent maximum cap.
- V13 receives an independent maximum cap.
- The cap is a maximum, not an exact required count.
- Fixed local profiles (`public_local50`, `public_local100`, `private_local200`) are fixed caps, not 1/8.

## Config And Profile Migration

| Old name | New name/status |
|---|---|
| `production_full_system` | `local_selective_auto` |
| `production_full_system_noapi` | removed; same local behavior now always applies |
| `dynamic_noapi` | replaced by local selective profiles |
| `private_noapi` | `private_local` wrapper / local path |
| `public_api50` | `public_local50` |
| `public_api100` | `public_local100` |
| `private_api200` | `private_local200` |
| `public_layer_api50` | removed |

Current `configs/profiles/run_profiles.json` profiles:

- `local_selective_auto`
- `public_replay`
- `public_local50`
- `public_local100`
- `private_local200`

Current `configs/production/default.json`:

- Uses `model_path: /models/qwen3-4b-instruct-2507`.
- Clarifies that the 79.7 score is historical and not claimed for the migrated local implementation.
- Keeps historical frozen artifact references; those files are still absent and remain the known test-failure category.

## CLI Migration

| Old flag/command | Status |
|---|---|
| `predict.py --no-api` | removed |
| `predict.py --legacy-dynamic-full` | retained, now local selective |
| `final_infer.py --execute-api` | removed |
| `final_infer.py --no-api` | removed |
| `final_infer.py --base-execute-api` | removed |
| `final_infer.py --no-base-api` | removed |
| `final_infer.py --model` | replaced by `--model-path` |
| `final_infer.py --budget-usd` | removed |
| `scripts/run_full_system.sh <input> --no-api` | replaced by `scripts/run_full_system.sh <input>` |

## Deleted OpenRouter-Only Or Remote-Transport Files

Deleted tracked files include:

- `requirements-openrouter.txt`
- `src/api/__init__.py`
- `src/api/openrouter_client.py`
- `src/api/selective_api_client.py`
- `src/api/openrouter_graph_solver.py`
- `src/api/openrouter_prompts.py`
- `src/api/model_policy.py`
- `scripts/audit_model_policy.py`
- `scripts/tools/audit_model_policy.py`
- `scripts/legacy/run/run_adaptive_selective_api.py`
- `scripts/legacy/run/run_selective_multicandidate_api.py`
- `scripts/legacy/run/run_full_adaptive_submission.py`
- `scripts/legacy/run/run_full_v11_independent_submission.py`
- `scripts/legacy/run/run_production_pipeline.py`
- `scripts/legacy/run/run_v12b_option_permutation.py`
- `scripts/legacy/run/run_v13_multilayer_verifier.py`
- API/remote-only tests such as `tests/unit/test_openrouter_client.py`, `tests/unit/test_openrouter_graph_solver.py`, `tests/unit/test_model_policy.py`, and `tests/integration/test_selective_api.py`.

Reusable candidate-agent prompt/parser logic was not deleted; it was moved from:

```text
src/api/api_candidate_agents.py
```

to:

```text
src/local_model/candidate_agents.py
```

## Retained Components Outside BTC Default

| Component | Current status | Future-default relevance |
|---|---|---|
| Dynamic Base | Migrated and runnable with shared local backend | Candidate for future default integration |
| Formula-bank deterministic solvers | Offline deterministic | Useful before local model fallback |
| Question router/adaptive routing | Offline heuristic | Useful for selective targeting |
| V12B | Migrated and runnable with shared local backend | Candidate for future default integration |
| V13 programmatic | Offline deterministic | Useful for future default |
| V13 content-first | Migrated and runnable with shared local backend | Candidate for future default integration |
| V13 least-to-most | Migrated and runnable with shared local backend | Candidate for future default integration |
| Evidence stack | Offline/reusable | Useful but not BTC default |
| Selector/ranker/consistency | Offline/reusable | Useful but not BTC default |
| Historical frozen replay | Still references absent frozen artifacts | Historical only; not BTC default |
| Legacy candidate builders | Some remain for artifact analysis | Not BTC default |

## BTC Default Regression Evidence

Compared to accepted commit `d504296`:

```text
git diff d504296 -- Dockerfile inference.sh scripts/download_local_model.py src/utils/data_io.py src/utils/labels.py
```

Result:

- `Dockerfile`: comment-only wording changed from provider-specific wording to provider-neutral wording.
- `inference.sh`: comment-only wording removed stale `--no-api` example.
- `scripts/download_local_model.py`: unchanged.
- `src/utils/data_io.py`: unchanged.
- `src/utils/labels.py`: unchanged.

`predict.py` changed only in the optional `--legacy-dynamic-full` branch and argument surface:

- No-argument control flow remains the single-pass local predictor.
- Default `max_new_tokens` remains `64`.
- Default model path remains `/models/qwen3-4b-instruct-2507` via `LOCAL_MODEL_PATH` fallback.
- BTC prompt/parser behavior is preserved through `build_mcq_prompt()` and `parse_mcq_label()`.
- Output schemas remain `qid,answer` and `qid,answer,time`.

Production-critical regression tests:

```text
python -m pytest tests/integration/test_btc_submission_contract_2l47a.py tests/unit/test_data_io.py tests/unit/test_labels.py -q
33 passed in 0.15s
```

## Validation Results

Pre-migration full suite baseline:

```text
18 failed, 772 passed in 9.47s
```

Final validation:

```text
python -m compileall -q src scripts tests predict.py run.py
PASS
```

```text
find . -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
PASS
```

```text
python -m pytest tests/integration/test_btc_submission_contract_2l47a.py tests/unit/test_data_io.py tests/unit/test_labels.py -q
33 passed in 0.15s
```

Migrated local backend/selective tests:

```text
python -m pytest tests/unit/test_local_qwen_backend.py tests/unit/test_local_progress_resume_2l39c.py tests/integration/test_fastmcq_dynamic_system_2l36b.py tests/integration/test_v13_dynamic_integration_2l37a.py tests/integration/test_run_profiles_2l38c.py -q -k 'not public_replay and not auto_replay_only_with_flag_and_match'
48 passed, 5 deselected in 0.21s
```

Full suite:

```text
python -m pytest tests -q
16 failed, 565 passed in 11.84s
```

The 16 remaining failures are the known frozen-artifact/manifest class:

- missing `experiments/best_candidate_manifest.json`
- missing `output/pred_v13_multilayer_candidate_api30_from_v12b.csv`
- missing `output/pred_v10_full_production_user_run.csv`
- missing `output/pred_v11_independent_rerun1.csv`
- public replay tests that depend on the absent frozen public artifact

No remaining full-suite failure is caused by:

- OpenRouter imports
- API keys
- removed profiles
- renamed local-backend modules
- `requirements-openrouter.txt`
- deleted remote transport clients

The failure count changed from 18 to 16 because remote-provider-only tests and broken remote runners were removed or converted rather than retained as failing collection/import errors.

## Zero Active OpenRouter Verification

All required searches returned zero active matches:

```text
git grep -n -i 'openrouter' -- ':!docs/audits/**' ':!docs/FINAL_SYSTEM.md'
<no output>
```

```text
git grep -n 'OPENROUTER_API_KEY' -- ':!docs/audits/**' ':!docs/FINAL_SYSTEM.md'
<no output>
```

```text
git grep -n -E 'execute_api|base_execute_api|skipped_no_api|api_budget' -- src scripts configs tests README.md DOCKER_SUBMISSION.md requirements*.txt Dockerfile*
<no output>
```

```text
git grep -n -E 'SelectiveAPIClient|OpenRouterClient|OpenRouterGraphSolver|--no-api|--execute-api|api50|api100|api200|layer_api|requirements-openrouter|Dockerfile.api' -- src scripts configs tests README.md DOCKER_SUBMISSION.md requirements*.txt Dockerfile*
<no output>
```

```text
test ! -e requirements-openrouter.txt
PASS
```

## Documentation Updates

Updated:

- `README.md`
- `DOCKER_SUBMISSION.md`
- `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`
- `src/README.md`

Current runnable documentation now describes:

- Accepted/default BTC path: local Qwen3-4B single pass.
- Optional local selective path: Dynamic Base -> local V12B -> local V13 -> selector.
- No active instruction requiring provider keys, API budgets, API-named profiles, or `requirements-openrouter.txt`.

Historical score caveat:

- The old 79.7 result is not claimed for the migrated local implementation.
- It remains a historical frozen-artifact reference only.

## Added Files

- `src/local_model/local_qwen_backend.py`
- `src/local_model/candidate_agents.py`
- `tests/unit/test_local_qwen_backend.py`
- `tests/unit/test_local_progress_resume_2l39c.py`
- `scripts/run/run_local_auto.sh`
- `scripts/run/run_private_local.sh`
- `scripts/run/run_private_local200.sh`
- `scripts/run/run_public_local100.sh`
- `scripts/run/run_public_local50.sh`
- `docs/audits/AUDIT_60_openrouter_to_local_migration.md`

Pre-existing untracked file left untouched:

- `docs/audits/AUDIT_59_system_reality_and_dependency_review.md`

## Deleted Files

Deleted remote-provider-only or broken remote-runner files:

- `requirements-openrouter.txt`
- `scripts/audit_model_policy.py`
- `scripts/tools/audit_model_policy.py`
- `scripts/legacy/repair/repair_v11_independent_run.py`
- `scripts/legacy/run/run_adaptive_pilot.py`
- `scripts/legacy/run/run_adaptive_selective_api.py`
- `scripts/legacy/run/run_ambiguous_adjudicator_sample.py`
- `scripts/legacy/run/run_full_adaptive_submission.py`
- `scripts/legacy/run/run_full_v11_independent_submission.py`
- `scripts/legacy/run/run_law_admin_verifier_sample.py`
- `scripts/legacy/run/run_production_pipeline.py`
- `scripts/legacy/run/run_selective_multicandidate_api.py`
- `scripts/legacy/run/run_selective_self_consistency_sample.py`
- `scripts/legacy/run/run_short_knowledge_verifier_sample.py`
- `scripts/legacy/run/run_v12_delta_verifier.py`
- `scripts/legacy/run/run_v12b_option_permutation.py`
- `scripts/legacy/run/run_v13_multilayer_verifier.py`
- `scripts/run/run_dynamic_noapi.sh`
- `scripts/run/run_private_api200.sh`
- `scripts/run/run_private_noapi.sh`
- `scripts/run/run_public_api100.sh`
- `scripts/run/run_public_api50.sh`
- `scripts/run/run_public_layer_api50.sh`
- `src/api/__init__.py`
- `src/api/api_candidate_agents.py` (moved to `src/local_model/candidate_agents.py`)
- `src/api/model_policy.py`
- `src/api/openrouter_client.py`
- `src/api/openrouter_graph_solver.py`
- `src/api/openrouter_prompts.py`
- `src/api/selective_api_client.py`
- Remote-provider-only tests listed in final git status.

## Main Modified Files

Key modified files:

- `predict.py`
- `run.py`
- `scripts/tools/final_infer.py`
- `scripts/run_full_system.sh`
- `scripts/docker_entrypoint.sh`
- `scripts/docker_entrypoint_v11.sh`
- `src/base/dynamic_base_predictor.py`
- `src/base/solver_factory.py`
- `src/layers/v12b_dynamic_layer.py`
- `src/layers/v13_dynamic_layer.py`
- `src/local_model/qwen_mcq_predictor.py`
- `src/system/fastmcq_system.py`
- `configs/profiles/run_profiles.json`
- `configs/production/default.json`
- `configs/default.yaml`
- `configs/adaptive_reasoning.yaml`
- `configs/verifier_selective.yaml`
- `requirements.txt`
- current README/Docker docs
- local backend/selective tests

## Complete Changed/Deleted/Added File Inventory

Tracked `git diff --name-status` at audit time:

```text
M	.gitignore
M	DOCKER_SUBMISSION.md
M	Dockerfile
M	README.md
M	configs/adaptive_reasoning.yaml
M	configs/allowed_models.yaml
M	configs/default.yaml
M	configs/production/default.json
M	configs/profiles/run_profiles.json
M	configs/verifier_selective.yaml
M	docs/BTC_FINAL_COMPLIANCE_MATRIX.md
M	inference.sh
M	predict.py
D	requirements-openrouter.txt
M	requirements.txt
M	run.py
D	scripts/audit_model_policy.py
M	scripts/docker_entrypoint.sh
M	scripts/docker_entrypoint_v11.sh
M	scripts/legacy/analysis/analyze_v10_geography.py
M	scripts/legacy/analysis/analyze_v6_runtime.py
M	scripts/legacy/analysis/compare_neural_vs_lexical_chunks.py
M	scripts/legacy/audit/audit_first100_consensus_risks.py
M	scripts/legacy/benchmark/benchmark_neural_reranker_speed.py
M	scripts/legacy/misc/create_verifier_smoke_subset.py
M	scripts/legacy/misc/export_risk_review_pack.py
M	scripts/legacy/misc/select_adaptive_pilot_qids.py
M	scripts/legacy/repair/apply_clean_generalized_fixes_to_predictions.py
M	scripts/legacy/repair/apply_formula_bank_to_predictions.py
M	scripts/legacy/repair/apply_programmatic_assist_to_predictions.py
D	scripts/legacy/repair/repair_v11_independent_run.py
D	scripts/legacy/run/run_adaptive_pilot.py
D	scripts/legacy/run/run_adaptive_selective_api.py
D	scripts/legacy/run/run_ambiguous_adjudicator_sample.py
D	scripts/legacy/run/run_full_adaptive_submission.py
D	scripts/legacy/run/run_full_v11_independent_submission.py
D	scripts/legacy/run/run_law_admin_verifier_sample.py
M	scripts/legacy/run/run_llm_full.sh
M	scripts/legacy/run/run_llm_smoke.sh
M	scripts/legacy/run/run_local.sh
D	scripts/legacy/run/run_production_pipeline.py
D	scripts/legacy/run/run_selective_multicandidate_api.py
D	scripts/legacy/run/run_selective_self_consistency_sample.py
D	scripts/legacy/run/run_short_knowledge_verifier_sample.py
D	scripts/legacy/run/run_v12_delta_verifier.py
D	scripts/legacy/run/run_v12b_option_permutation.py
D	scripts/legacy/run/run_v13_multilayer_verifier.py
M	scripts/legacy/submission/cleanup_outputs_for_submission.py
D	scripts/run/run_dynamic_noapi.sh
D	scripts/run/run_private_api200.sh
D	scripts/run/run_private_noapi.sh
D	scripts/run/run_public_api100.sh
D	scripts/run/run_public_api50.sh
D	scripts/run/run_public_layer_api50.sh
M	scripts/run/run_public_replay.sh
M	scripts/run_full_system.sh
D	scripts/tools/audit_model_policy.py
M	scripts/tools/final_infer.py
M	src/README.md
D	src/api/__init__.py
D	src/api/api_candidate_agents.py
D	src/api/model_policy.py
D	src/api/openrouter_client.py
D	src/api/openrouter_graph_solver.py
D	src/api/openrouter_prompts.py
D	src/api/selective_api_client.py
M	src/base/dynamic_base_predictor.py
M	src/base/solver_factory.py
M	src/layers/mcq_permutation_debiaser.py
M	src/layers/v12b_dynamic_layer.py
M	src/layers/v13_dynamic_layer.py
M	src/layers/v13_layer_registry.py
M	src/local_model/qwen_mcq_predictor.py
M	src/selector/mcq_verifier.py
M	src/system/fastmcq_system.py
M	src/system/production_inference.py
M	src/system/production_prompts.py
M	src/utils/structured_answer.py
M	tests/integration/test_adaptive_branch_calibration.py
D	tests/integration/test_adaptive_orchestrator.py
M	tests/integration/test_btc_io_priority_2l44d.py
M	tests/integration/test_btc_noarg_2l32b.py
M	tests/integration/test_btc_short_2l31b.py
M	tests/integration/test_btc_submission_contract_2l47a.py
M	tests/integration/test_calc_first_2l28b.py
M	tests/integration/test_concept_solver.py
M	tests/integration/test_fastmcq_dynamic_system_2l36b.py
M	tests/integration/test_final_package_2l31a.py
M	tests/integration/test_formula_bank_solver.py
D	tests/integration/test_full_adaptive_submission_2l29b.py
M	tests/integration/test_full_system_output_contract_2l41a.py
D	tests/integration/test_independent_v11_2l30b.py
M	tests/integration/test_judge_and_adaptive.py
D	tests/integration/test_layer_only_api_profile_2l39d.py
M	tests/integration/test_model_compliance.py
M	tests/integration/test_pilot_gate.py
M	tests/integration/test_production_auto_budget_2l44e.py
M	tests/integration/test_production_layers.py
D	tests/integration/test_production_pipeline.py
D	tests/integration/test_production_timing.py
D	tests/integration/test_repair_v11_2l30c.py
M	tests/integration/test_run_profiles_2l38c.py
D	tests/integration/test_selective_api.py
D	tests/integration/test_sk_verifier_proposal.py
M	tests/integration/test_v11_hardening_2l30d.py
M	tests/integration/test_v12b_permutation_2l34b.py
M	tests/integration/test_v13_dynamic_integration_2l37a.py
M	tests/integration/test_v13_multilayer_2l35a.py
D	tests/legacy/test_v12_delta_2l34a.py
D	tests/unit/test_api_progress_resume_2l39c.py
M	tests/unit/test_mcq_permutation_debiaser_2l34c.py
M	tests/unit/test_mcq_verifier.py
D	tests/unit/test_model_policy.py
D	tests/unit/test_openrouter_client.py
D	tests/unit/test_openrouter_graph_solver.py
M	tests/unit/test_src_compatibility_imports_2l43f.py
```

Untracked files created or present:

```text
docs/audits/AUDIT_59_system_reality_and_dependency_review.md  # pre-existing before this task
docs/audits/AUDIT_60_openrouter_to_local_migration.md
scripts/run/run_local_auto.sh
scripts/run/run_private_local.sh
scripts/run/run_private_local200.sh
scripts/run/run_public_local100.sh
scripts/run/run_public_local50.sh
src/local_model/candidate_agents.py
src/local_model/local_qwen_backend.py
tests/unit/test_local_progress_resume_2l39c.py
tests/unit/test_local_qwen_backend.py
```

## Risks

- Real local selective inference was not run because model inference is forbidden for this task.
- Docker was not built or run.
- Historical frozen replay config still references absent artifact filenames; this is the unchanged known artifact state, not BTC default behavior.
- Some legacy artifact-analysis scripts still use historical candidate-file terminology, but they no longer call OpenRouter and are outside the BTC default path.

## Recommended Next Step

Run a manual GPU smoke test of the optional local selective path with a small synthetic input and fake/real local model environment only after the model is available, then decide separately whether any local selective layer should be promoted into the BTC default. Do not promote it in this migration.

## Rollback

Rollback branch:

```text
backup/before-local-backend-migration-87d5d71
```

To inspect rollback state without changing the current worktree:

```text
git show backup/before-local-backend-migration-87d5d71
```

No rollback was performed in this task.

## Required Explicit Statements

- No active repository runtime calls OpenRouter.
- No active config or profile requires an API key.
- No active test requires OpenRouter.
- `requirements-openrouter.txt` was removed.
- Dynamic Base uses the shared local model.
- V12B uses the shared local model.
- V13 content-first and least-to-most use the shared local model.
- The model is loaded once and reused through the process-wide backend cache.
- The accepted BTC no-argument path remains single-pass and unchanged in contract.
- V12B/V13 were not made the default in this task.
- The old 79.7 result was not claimed for the local implementation.
- No package was installed.
- No model was downloaded.
- No API or network request was made.
- No Docker image was built or pushed.
- No real inference was run.
- No test was skipped or xfailed to hide a failure.
- No commit was created automatically.

## Final Git Status

```text
## main...origin/main
M  .gitignore
M  DOCKER_SUBMISSION.md
M  Dockerfile
M  README.md
M  configs/adaptive_reasoning.yaml
M  configs/allowed_models.yaml
M  configs/default.yaml
M  configs/production/default.json
M  configs/profiles/run_profiles.json
M  configs/verifier_selective.yaml
M  docs/BTC_FINAL_COMPLIANCE_MATRIX.md
M  inference.sh
M  predict.py
D  requirements-openrouter.txt
M  requirements.txt
M  run.py
D  scripts/audit_model_policy.py
M  scripts/docker_entrypoint.sh
M  scripts/docker_entrypoint_v11.sh
M  scripts/legacy/misc/select_adaptive_pilot_qids.py
D  scripts/legacy/repair/repair_v11_independent_run.py
D  scripts/legacy/run/run_adaptive_pilot.py
D  scripts/legacy/run/run_adaptive_selective_api.py
D  scripts/legacy/run/run_full_adaptive_submission.py
D  scripts/legacy/run/run_full_v11_independent_submission.py
D  scripts/legacy/run/run_production_pipeline.py
D  scripts/legacy/run/run_selective_multicandidate_api.py
D  scripts/legacy/run/run_v12b_option_permutation.py
D  scripts/legacy/run/run_v13_multilayer_verifier.py
D  scripts/run/run_dynamic_noapi.sh
D  scripts/run/run_private_api200.sh
D  scripts/run/run_private_noapi.sh
D  scripts/run/run_public_api100.sh
D  scripts/run/run_public_api50.sh
D  scripts/run/run_public_layer_api50.sh
M  scripts/run_full_system.sh
D  scripts/tools/audit_model_policy.py
M  scripts/tools/final_infer.py
D  src/api/*
M  src/base/dynamic_base_predictor.py
M  src/base/solver_factory.py
M  src/layers/v12b_dynamic_layer.py
M  src/layers/v13_dynamic_layer.py
M  src/local_model/qwen_mcq_predictor.py
M  src/system/fastmcq_system.py
M  tests/*
?? docs/audits/AUDIT_59_system_reality_and_dependency_review.md
?? docs/audits/AUDIT_60_openrouter_to_local_migration.md
?? scripts/run/run_local_auto.sh
?? scripts/run/run_private_local.sh
?? scripts/run/run_private_local200.sh
?? scripts/run/run_public_local100.sh
?? scripts/run/run_public_local50.sh
?? src/local_model/candidate_agents.py
?? src/local_model/local_qwen_backend.py
?? tests/unit/test_local_progress_resume_2l39c.py
?? tests/unit/test_local_qwen_backend.py
```
