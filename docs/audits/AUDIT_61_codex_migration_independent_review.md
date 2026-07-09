# AUDIT 61 — Independent Adversarial Review of Audit 60 (OpenRouter → Local Qwen Migration)

Date: 2026-07-09
Reviewer: independent (adversarial, read-only). Audit 60 was treated as a set of claims, not as evidence.

## 0. Headline

**AUDIT 60 VERIFIED — SAFE TO CONTINUE (with caveats).**

The migration is technically correct, complete for tracked active code, behavior-preserving on the
BTC no-argument path, and uses one shared backend object. No critical or high defect was found in
the migrated code itself. The caveats are: (a) end-to-end wrapper/contract tests were weakened to
shape checks because the local path now needs a real model; (b) the shared-backend cache does not
normalize model paths; (c) the local selective path has never been run with the real model; and
(d) several tracked historical docs and ignored local files still carry OpenRouter material, which
Audit 60 disclosed but phrased more strongly than the evidence supports.

## 1. Repository state (verified)

- Branch: `main`, tracking `origin/main`.
- HEAD: `87d5d71ff2f9d02b9f41c8df351a683f3b683662` — matches the expected pre-migration baseline.
- Backup branch `backup/before-local-backend-migration-87d5d71` exists and points to the same
  commit `87d5d71` (the migration is uncommitted worktree state, so the backup equals HEAD; a
  simple `git restore`/`git clean` of the worktree would recover the pre-migration state).
- `git diff --name-status`: 116 tracked paths (matches the inventory printed in Audit 60 exactly).
- `git diff --stat`: 655 insertions, 9102 deletions.
- `git diff --check`: clean.
- Untracked files: exactly the 11 listed in Audit 60 (AUDIT_59/60, 5 `scripts/run/run_*local*.sh`,
  `src/local_model/candidate_agents.py`, `src/local_model/local_qwen_backend.py`,
  2 `tests/unit/test_local_*.py`). No unrelated changes appeared after Audit 60.
- Comparison method: `git show`/`git diff backup/... -- <path>` plus a temporary detached worktree
  (created, used for pre-migration test collection/execution, then removed with
  `git worktree remove`). The main worktree was never switched or modified.

## 2. Audit-60 claim matrix

| # | Audit-60 claim | Evidence inspected | Result | Caveat / problem |
|---|---|---|---|---|
| 1 | No active runtime calls OpenRouter | `git grep -i openrouter` + key/class/flag greps over all tracked files; plain `grep` over all 11 untracked files (git grep does not see untracked files — re-checked independently) | **VERIFIED** | `docs/FINAL_SYSTEM.md` (tracked, historical doc) still has 10 `openrouter` mentions; ignored `.env` still names `OPENROUTER_API_KEY`; ignored `Dockerfile.api` still has 3 mentions. None are runtime. |
| 2 | No active config/profile requires an API key | `configs/profiles/run_profiles.json` (5 profiles: `local_selective_auto`, `public_replay`, `public_local50/100`, `private_local200`), `configs/*.yaml`, `configs/production/default.json` | **VERIFIED** | `configs/adaptive_reasoning.yaml` was rewritten to local-only wording but its consumer (`adaptive_orchestrator`) is not wired into any current entrypoint. |
| 3 | Dynamic Base uses local Qwen | `src/base/dynamic_base_predictor.py:53-93` (`_local_answer` → `backend.predict_mcq`) | **VERIFIED** | |
| 4 | V12B uses local Qwen for every model-backed permutation | `src/layers/v12b_dynamic_layer.py:166-169` (`backend.generate_text` inside the permutation loop; no client) | **VERIFIED** | |
| 5 | V13 content-first uses local Qwen | `src/layers/v13_dynamic_layer.py:271-276` (`backend.generate_text` on the non-programmatic layer path) + fake-backend run confirming a `content_first` generate call | **VERIFIED** | |
| 6 | V13 least-to-most uses local Qwen | same code path; fake-backend run produced an LTM candidate | **VERIFIED** | |
| 7 | Programmatic V13 remains model-free | `v13_dynamic_layer.py:256-268`: `programmatic_solver` now hits **only** `_deterministic_programmatic` and `continue`s; the model branch is unreachable for it | **VERIFIED** | Semantic narrowing vs the old `execute_api=True` mode, where programmatic could also be model-backed. Matches the intended design; the `programmatic_solver` branch of `_interpret_model_json` is now dead code (cosmetic). |
| 8 | Base, V12B, V13 share exactly one backend object | `fastmcq_system.py:125-126` creates `backend` once and passes it to all three (`:141-143`, `:159-162`, `:172-175`); adversarial spy-backend run confirmed one object served all calls and `_BACKENDS` stayed empty | **VERIFIED** | |
| 9 | Model/tokenizer loads only once per process under normal execution | `local_qwen_backend.py:102-121` (`load()` early-returns when `_model` set); cache `_BACKENDS` keyed `(model_path, device)`; `predict.py` builds one predictor; system passes one backend | **VERIFIED (static/fake only)** | Cache key does not normalize paths (trailing slash / relative path / `..` → separate entries → second load possible). No thread lock in `load()` (concurrent first calls could double-load; nothing in the repo is multi-threaded today). Not observed with the real model. |
| 10 | BTC no-argument path remains single-pass | `git diff backup -- predict.py`: only the `--legacy-dynamic-full` branch and argument surface changed; the no-arg loop, input resolution, output writers untouched | **VERIFIED** | |
| 11 | BTC prompt/parser/generation defaults behaviorally compatible | line-by-line comparison of old `qwen_mcq_predictor.py` vs new backend (§9 below); 33/33 BTC contract tests pass | **VERIFIED** | One deliberate difference: `local_files_only=True` added (stricter offline; identical behavior when the baked path exists). |
| 12 | Input resolution unchanged | `predict.py` `_resolve_input` untouched in diff; `test_btc_io_priority_2l44d.py` passes | **VERIFIED** | |
| 13 | Output schemas/paths unchanged | `_resolve_out`, submission/time writers untouched; contract tests assert `qid,answer` and `qid,answer,time` | **VERIFIED** | |
| 14 | Per-sample failure isolation unchanged | `_coerce_label`/`_fallback_answer` untouched; `test_fallback_when_model_returns_nothing` passes | **VERIFIED** | Layer-level isolation actually **improved**: old V12B had no try/except around `client.chat` — one exception aborted the whole layer; new code records `local_error` per permutation (proven by fake-backend test). Audit 60 presents this as "preserved", which understates the change. |
| 15 | ceil(N/8) applies only to V12B and V13 | `final_infer.py:255-272` `_resolve_maxq` is the only auto resolver; called only for `--v12b-max-qids`/`--v13-max-qids`; Base takes all samples; checked N∈{0,1,7,8,9,450,463} → {1,1,1,1,2,57,58} | **VERIFIED** | Only other `/8`-ish hits are an unrelated bitsandbytes comment (`src/solvers/hf_common.py:160`) and doc comments. |
| 16 | All active OpenRouter requirements/flags/profiles/commands removed | flag greps (`--no-api`, `--execute-api`, `api50/100/200`, `budget_usd`, `skipped_no_api`) → zero in src/scripts/configs/tests/README/Docker files; `final_infer.py --help` accepts only local flags | **VERIFIED** | |
| 17 | Deleted scripts/tests were provider-transport-only or safely replaced | §6/§7 below | **PARTIALLY VERIFIED** | Deleted scripts were remote *workflows*, not pure transport; their reusable logic lives in src, but several complete research workflows (adaptive multi-agent, v11 independent, production pipeline w/ checkpointing) were removed, not migrated. Audit 60's own inventory says "Deleted" — accurate — but the summary phrase "transport-only or broken after transport deletion" undersells what the workflows contained. |
| 18 | No useful architecture removed accidentally | src survey: all layer/selector/solver/evidence modules remain; only `src/api/*` deleted; `api_candidate_agents.py` moved byte-comparably | **VERIFIED for src** | The deletions in scripts/ were deliberate, disclosed removals (see §7); "accidentally" does not apply, but replacement coverage is incomplete for a few workflows. |
| 19 | Local selective path runnable without an API key | `env -u OPENROUTER_API_KEY python scripts/tools/final_infer.py --profile local_selective_auto --dry-run` → PASS; full fake-backend `run_fastmcq_system` with `OPENROUTER_API_KEY` deleted and set → byte-identical outputs | **VERIFIED (dry-run/fake only)** | Real-model execution NOT TESTED IN REAL RUNTIME. |
| 20 | Full suite has no new non-artifact regression | pre suite (temp worktree): 18 failed / 772 passed; post suite: 16 failed / 565 passed; the 16 post-failures are a strict subset of the pre-failures (all frozen-artifact/public-replay class) | **VERIFIED** | See §5: passing count fell because 209 tests were removed with the deleted remote code, not because of hidden failures. |

## 3. Pre/post test counts (measured, not taken from Audit 60)

Commands: `python -m pytest --collect-only -q tests` and `python -m pytest tests -q`, run in this
worktree (post) and in a temporary detached worktree at the backup commit (pre).

| Metric | Before migration | After migration | Difference |
|---|---|---|---|
| Test files collected | 57 | 46 | −11 (13 collected files deleted, +2 new; `tests/legacy/test_v12_delta_2l34a.py` was never collected — see below) |
| Collected tests | 790 | 581 | −209 |
| Passed | 772 | 565 | −207 |
| Failed | 18 | 16 | −2 |
| Skipped | 0 | 0 | 0 |
| Deselected | 0 | 0 | 0 |
| Collection errors | 0 | 0 | 0 |

\* `tests/conftest.py` has `collect_ignore_glob = ["legacy/*"]` (pre-existing), so the deleted
`tests/legacy/test_v12_delta_2l34a.py` contributed **zero** collected tests in both states.

Exact per-file accounting of the −209 (sums check: −218 removed + 9 added = −209):

| File | pre → post | Why the tests disappeared |
|---|---|---|
| `tests/unit/test_openrouter_client.py` | 30→0 … 17→0 (file deleted) | HTTP transport/auth/payload only |
| `tests/unit/test_openrouter_graph_solver.py` | 30→0 (deleted) | tested the deleted remote graph solver (incl. its calc/evidence/verifier integration) |
| `tests/integration/test_adaptive_orchestrator.py` | 24→0 (deleted) | trace-only adaptive orchestrator via fake API client |
| `tests/unit/test_openrouter_client.py` | 17→0 (deleted) | transport only |
| `tests/integration/test_independent_v11_2l30b.py` | 15→0 (deleted) | tested deleted `run_full_v11_independent_submission.py` |
| `tests/integration/test_selective_api.py` | 14→0 (deleted) | selective API client/runner/ranker workflow |
| `tests/integration/test_production_pipeline.py` | 13→0 (deleted) | tested deleted `run_production_pipeline.py` |
| `tests/integration/test_repair_v11_2l30c.py` | 13→0 (deleted) | tested deleted `repair_v11_independent_run.py` |
| `tests/integration/test_v11_hardening_2l30d.py` | 14→3 (trimmed) | finalize/preflight/resume guards of the deleted v11 runner |
| `tests/integration/test_full_adaptive_submission_2l29b.py` | 10→0 (deleted) | tested deleted `run_full_adaptive_submission.py` |
| `tests/integration/test_sk_verifier_proposal.py` | 9→0 (deleted) | tested deleted `run_short_knowledge_verifier_sample.py` |
| `tests/unit/test_api_progress_resume_2l39c.py` | 9→0 (deleted) | replaced by `test_local_progress_resume_2l39c.py` (5 tests) |
| `tests/integration/test_judge_and_adaptive.py` | 11→3 (trimmed) | judge/adaptive API-runner tests; candidate-agent parser tests kept |
| `tests/integration/test_layer_only_api_profile_2l39d.py` | 8→0 (deleted) | tested the removed base-no-api/layer-api configuration axis |
| `tests/unit/test_model_policy.py` | 8→0 (deleted) | remote model allowlist policy + deleted audit script |
| `tests/integration/test_full_system_output_contract_2l41a.py` | 12→5 (trimmed) | end-to-end wrapper executions (needed the deterministic no-api mode) → shape checks |
| `tests/integration/test_production_timing.py` | 5→0 (deleted) | timing/entrypoint metadata of deleted production pipeline |
| `tests/integration/test_run_profiles_2l38c.py` | 17→12 (trimmed) | api50/noapi profile tests removed; local profile tests added |
| `tests/integration/test_pilot_gate.py` | 13→10 (trimmed) | pilot-runner (deleted script) tests |
| `tests/integration/test_production_layers.py` | 15→12 (trimmed) | atomic-write/checkpoint helpers of the deleted production pipeline |
| `tests/integration/test_adaptive_branch_calibration.py` | 11→9 (trimmed) | law_admin/ambiguous/self-consistency runner (deleted scripts) tests |
| `tests/integration/test_calc_first_2l28b.py` | 16→14 (trimmed) | API-runner upper-bound/route-agent tests; parser tests kept |
| `tests/integration/test_v12b_permutation_2l34b.py` | 9→7 (trimmed) | verifier-sample runner (deleted script) tests |
| `tests/unit/test_local_qwen_backend.py` | 0→4 (new) | backend singleton, prompt/parser contract, JSON parser, facade sharing |
| `tests/unit/test_local_progress_resume_2l39c.py` | 0→5 (new) | fake-backend base/V12B/V13 JSONL+resume, failure isolation, shared instance |

Failure-set comparison (measured): the 16 post-migration failures are the identical test ids of 16
of the 18 pre-migration failures (missing `output/pred_v11_independent_rerun1.csv`,
`experiments/best_candidate_manifest.json`, public frozen artifact, etc.). The two pre-failures
that no longer exist as failures (`test_btc_short_2l31b::test_v10_is_not_default`,
`test_final_package_2l31a::test_pred_csv_allowed_without_flag`) now pass in their updated form.
**No new failure class was introduced.** Audit 60's counts (790/772/18 → 581/565/16) reproduce
exactly.

## 4. Deleted-test review

| Deleted test | What it actually tested | Transport only? | Architecture logic protected? | Replacement | Verdict |
|---|---|---|---|---|---|
| `test_openrouter_client.py` | endpoint URL, auth headers, payload shape, reasoning flags, key resolution | Yes | None beyond transport | none needed | **Safely deleted** |
| `test_model_policy.py` | remote model allowlist (Qwen3.5≤9B/Gemma-4), repo audit script | Provider policy | Policy is meaningless with one fixed local model; `configs/allowed_models.yaml` now names Qwen3-4B and `test_model_compliance.py` remains | partial (compliance test) | **Safely deleted** |
| `test_openrouter_graph_solver.py` | the remote graph solver **plus** its integration of calc-override, evidence reranker, verifier gating, self-consistency, repair loop | No — mixed | The integration orchestration died with the solver; the underlying modules keep their own unit tests (`test_calculation_solver.py`, `test_evidence_reranker.py`, `test_mcq_verifier.py` all still pass) | module-level only | **Justified** (solver deleted) — but note the calc/evidence/verifier *integrated flow* now has no runnable host (see finding M2) |
| `test_adaptive_orchestrator.py` | trace-only adaptive orchestrator gates (never overrides, assist mode, SK verifier eligibility) with a fake client | No | `src/layers/adaptive_orchestrator.py` **still exists untouched** but lost all 24 of its tests | none | **Over-trimmed**: module kept, coverage dropped to zero (finding M3) |
| `test_selective_api.py` | prompt builders/parsers (moved to `candidate_agents`), client model-blocking, runner dry-run/resume, answer-ranker keep/override | Mixed | builders/parsers still covered via `test_calc_first_2l28b.py`/`test_judge_and_adaptive.py`; ranker logic still covered by `test_answer_factory.py` | partial | **Acceptable** |
| `test_layer_only_api_profile_2l39d.py` | base-no-api + layer-api split | Config axis removed | axis no longer exists | n/a | **Safely deleted** |
| `test_api_progress_resume_2l39c.py` | V13 empty-prompt guard, incremental JSONL, resume skip, progress logs | No | same behaviors, local | `test_local_progress_resume_2l39c.py` (9→5 tests; empty-prompt guard now covered by `build_messages` test; progress-log format test dropped) | **Replaced (slightly thinner)** |
| `test_independent_v11_2l30b.py`, `test_repair_v11_2l30c.py`, `test_full_adaptive_submission_2l29b.py`, `test_sk_verifier_proposal.py`, `test_production_pipeline.py`, `test_production_timing.py` | guardrails (ack flags, protected outputs, validation, repair fallback ladder, timing report, input detection) of the deleted legacy runner scripts | Workflow around remote execution | the runner scripts are gone, so the tests have no subject | intentionally removed with their scripts | **Consistent with the script deletions** (see §5 of scripts review) |
| `tests/legacy/test_v12_delta_2l34a.py` | v12-delta experiment (never collected — `collect_ignore_glob`) | — | — | — | **Zero-impact deletion** |

Trimmed-file detail worth flagging: `test_full_system_output_contract_2l41a.py` lost
`test_output_qids_match_input_exactly`, `test_successful_run_promotes_to_final_pred_csv`,
`test_failed_run_does_not_overwrite_existing_final`, `test_fail_on_quality_guard_blocks_promotion`
— these executed `scripts/run_full_system.sh` **end-to-end** (possible pre-migration because
no-api mode was deterministic without any model). Post-migration the wrapper needs the real model,
so they were replaced by text-shape checks. The qid-contract itself is still enforced in-process
(`test_dynamic_full_outputs_exactly_input_qids` with a fake backend, plus the hard
`REFUSING` guards in `fastmcq_system.py:199-204`), but wrapper-level promotion/quality-guard
behavior is now untested (finding M1).

## 5. Deleted-script review

All contents inspected via `git show backup/...:<path>`.

| Deleted script | Original behavior | Pure transport? | Unique non-provider logic? | Current replacement | Verdict |
|---|---|---|---|---|---|
| `run_production_pipeline.py` (334 ln) | base LLM (OpenRouter) + safe deterministic overrides + presets + checkpoint/skip-existing + input detection | No — workflow | policy logic lives in `src/system/production_policy.py` (kept); **atomic-write/checkpoint helpers were script-local and are gone** | `final_infer.py --profile local_selective_auto` (different pipeline; V12B/V13 have their own JSONL resume; base-solver checkpointing not replicated) | **Intentionally removed; partially replaced** |
| `run_full_v11_independent_submission.py` (556 ln) | independent v11 candidate generation + selection + validation + ack guards | No — workflow | selector logic lives in `src/selector/independent_answer_selector.py` (kept) | local selective system supersedes the architecture | **Intentionally removed; superseded** |
| `run_v12b_option_permutation.py` (157 ln) | CLI + prompting + model I/O around `mcq_permutation_debiaser` | Mostly | core logic always lived in src (kept) | `src/layers/v12b_dynamic_layer.py` (migrated, tested) | **Fully replaced** |
| `run_v13_multilayer_verifier.py` (155 ln) | CLI + model I/O around the three V13 src modules | Mostly | core in src (kept) | `src/layers/v13_dynamic_layer.py` (migrated, tested) | **Fully replaced** |
| `run_full_adaptive_submission.py` (219 ln), `run_adaptive_pilot.py` (75 ln), `run_adaptive_selective_api.py` (248 ln) | adaptive multi-agent selective workflow (cheap/rich agent routing, judge-on-conflict, variant build) | No — workflow | agent prompts/parsers moved to `src/local_model/candidate_agents.py` (byte-identical, verified by diff); the **multi-agent routing/judge orchestration has no local runner** | none | **Intentionally removed, NOT migrated** (disclosed in Audit 60's inventory; do not call it migrated) |
| `repair_v11_independent_run.py` (270 ln) | null/invalid-label repair ladder for v11 runs | No | fallback ladder logic was script-local | selective system coerces invalid labels inline (`fastmcq_system.py:148-152`) | **Intentionally removed; inline guard covers the contract** |
| `run_short_knowledge_verifier_sample.py`, `run_law_admin_verifier_sample.py`, `run_ambiguous_adjudicator_sample.py`, `run_selective_self_consistency_sample.py`, `run_v12_delta_verifier.py` | proposal-only verifier sampling experiments (OpenRouter `--execute` paths) | No — experiments | gate logic partially mirrored in `configs/adaptive_reasoning.yaml` blocks and `adaptive_orchestrator` (kept, untested) | none | **Intentionally removed research experiments** |
| `run_selective_multicandidate_api.py` (218 ln) | selective multi-candidate API runner w/ crash-safe resume | No — workflow | resume pattern re-exists in V12B/V13 JSONL resume | selective system | **Superseded** |
| `scripts/audit_model_policy.py`, `scripts/tools/audit_model_policy.py` | remote model-policy repo audit | Policy | n/a with fixed local model | n/a | **Safely deleted** |
| `scripts/run/run_*api*.sh`, `run_dynamic_noapi.sh`, `run_private_noapi.sh` | wrappers over removed profiles | Yes (profile plumbing) | none | `scripts/run/run_local_auto.sh`, `run_public_local50/100.sh`, `run_private_local.sh`, `run_private_local200.sh` (all `bash -n` clean; correct paths; correct profiles) | **Fully replaced** |

Conclusion: nothing was deleted *accidentally*; every deletion is either transport, a
transport-dependent workflow, or an experiment, and Audit 60's file inventory lists them all.
Three workflows (adaptive multi-agent, base-solver checkpointing, verifier sampling experiments)
were **removed without functional replacement** — acceptable as an explicit decision, and Audit 60's
"Retained Components" table does mark the surviving pieces as library-only, but the summary line
"transport-only or broken after transport deletion" is the weakest-worded claim in Audit 60.

## 6. Shared local backend analysis

`src/local_model/local_qwen_backend.py` (new, 183 lines):

- `get_local_qwen_backend()` resolves `model_path or $LOCAL_MODEL_PATH or DEFAULT_MODEL_PATH` and
  caches per `(resolved_path, device or "auto")` (`:165-177`). Verified singleton behavior for:
  default vs explicit default path, `device=None` vs `"auto"`, env-derived default — all same object.
- **Cache-key gaps found (adversarially confirmed)**: `"/models/qwen3-4b-instruct-2507/"`
  (trailing slash) and `"models/../models/qwen3-4b-instruct-2507"` produce *separate* cache
  entries → a second full model load if two call sites spell the path differently in one process.
  In the current code this cannot happen on any real path: `predict.py` builds exactly one
  predictor; `run_fastmcq_system` creates one backend and passes the same object to
  `predict_base_answers` (`fastmcq_system.py:141-143`), `run_v12b_layer` (`:159-162`) and
  `run_v13_layer` (`:172-175`); the layers use `local_backend or get_local_qwen_backend(...)` and
  always receive the injected object. Finding L1.
- `default_max_new_tokens` is not part of the cache key; the second caller's value is ignored.
  Harmless today because every call site passes `max_new_tokens` explicitly per call.
- `load()` (`:102-121`) guards on `_model is not None`; a failed model load leaves `_tokenizer`
  set but `_model` None, so a retry re-runs both loads — no corrupt cached state. There is **no
  lock**, so two threads calling `load()` concurrently could double-load; nothing in the repo is
  multi-threaded. Finding L2.
- Only `load()` calls `AutoTokenizer.from_pretrained`/`AutoModelForCausalLM.from_pretrained`
  (`git grep from_pretrained -- src scripts`: backend + the pre-existing `src/solvers/hf_*`
  research solvers only, unchanged from pre-migration). No module instantiates
  `LocalQwenBackend(` outside the backend itself and its unit test.
- Loading is lazy (`torch`/`transformers` imported inside `load()`) and offline
  (`local_files_only=True` on both loads — **stricter** than the pre-migration predictor, which
  omitted it).
- `QwenMCQPredictor` (`qwen_mcq_predictor.py:25-26`) resolves its backend through the same cache;
  verified `p._backend is get_local_qwen_backend()`.

Fake-backend proof run (temporary script, deleted after use): one spy backend served 9 base
`predict_mcq` calls + 12 layer `generate_text` calls across Base/V12B/V13; the real
`LocalQwenBackend.load` was patched to raise and never fired; `_BACKENDS` stayed empty; output CSV
contained exactly the 9 input qids in input order.

## 7. BTC prompt/parser compatibility (old `QwenMCQPredictor.predict_one` vs new backend chain)

Line-by-line comparison of `git show backup:src/local_model/qwen_mcq_predictor.py` vs
`local_qwen_backend.py` + the new facade:

| Aspect | Pre-migration | Post-migration | Compatible? |
|---|---|---|---|
| Prompt text | `build_mcq_prompt` (Vietnamese answer-only) | **byte-identical function**, moved | Yes |
| Labels | `labels_for(len(choices))`, `ABCD` fallback | identical | Yes |
| Chat template | `apply_chat_template(tokenize=False, add_generation_prompt=True)`, fallback to raw prompt on exception | `_render_prompt`: same call; fallback `"\n\n".join(contents)` ≡ raw prompt for the single user message | Yes |
| Tokenization | `tokenizer(text, return_tensors="pt").to(model.device)` | identical | Yes |
| Generation | `max_new_tokens=self.max_new_tokens, do_sample=False, num_beams=1, pad_token_id=eos` | `predict_one` passes `max_new_tokens` explicitly; `temperature=0.0` → `do_sample=False`; `num_beams=1`; `pad_token_id=eos` | Yes |
| Suffix extraction | `out[0][inputs["input_ids"].shape[1]:]` + `decode(skip_special_tokens=True)` | identical | Yes |
| Parser | `parse_label`: first `[A-K]` match in allowed set | `parse_mcq_label`: **identical regex/logic**; `parse_label` re-exported | Yes |
| Label coercion/fallback | in `predict.py` `_coerce_label` (unchanged) | unchanged | Yes |
| dtype/device | bfloat16 on CUDA / float32 CPU; `device_map="auto"` on CUDA-auto | identical | Yes |
| `from_pretrained` flags | `trust_remote_code=True` | `trust_remote_code=True, local_files_only=True` | **Difference (intentional, safer)**: pre-migration could in principle reach the network for a missing path; now it errors offline. Behavior identical when `/models/...` exists (the BTC case). |
| max_new_tokens default | 64 | 64 (predict.py arg + backend default) | Yes |
| Timing/output ordering | measured around `predict_one` per sample in `predict.py` (untouched) | unchanged | Yes |

Also re-verified Audit 60's `d504296` comparison: `Dockerfile`/`inference.sh` diffs are
comment-only; `scripts/download_local_model.py`, `src/utils/data_io.py`, `src/utils/labels.py`
unchanged. `python -m pytest tests/integration/test_btc_submission_contract_2l47a.py
tests/unit/test_data_io.py tests/unit/test_labels.py -q` → **33 passed** (matches Audit 60).

## 8. Dynamic Base review

Diff vs backup: `_api_answer` (JSON-prompt remote call) → `_local_answer`
(`backend.predict_mcq`, single-letter). All contract properties verified with fake backends:

- one `BasePrediction` per input qid, input order preserved (adversarial check);
- formula bank first, accepted only when `fb.selected_answer in labels` (`:79-82`), confidence
  passthrough — unchanged;
- local model only when the formula bank misses; fallback (`labels[0]`) only on
  no-choices/parse-failure/exception, always tagged `weak` in `risk_reason` — never a normal
  strategy;
- provenance: `formula_bank:<rule>`, `dynamic_local_qwen` (conf 0.6, same 0.6 the old
  `dynamic_api` used → downstream weak-source semantics preserved), `dynamic_fallback[_nochoices]`;
- per-item exception isolation confirmed (one raising item → its fallback; neighbors unaffected);
- duplicate-qid rejection lives in `run_fastmcq_system` (`:121-122`), unchanged;
- Base has no max-qids parameter at all — it cannot inherit the 1/8 cap.
- `work_dir`/`resume` parameters are accepted-but-unused — **identical to pre-migration**, so no
  resume regression (Base never had resume).

**Verdict: VERIFIED.**

## 9. V12B review

Diff vs backup shows exactly three semantic changes, all correct:

1. Client → `backend.generate_text` + shared `parse_json_object` (same JSON contract:
   `selected_label`, `selected_option_text`, `label_matches_option`, `confidence`). The system
   prompt string is unchanged.
2. `_WEAK_SOURCE_TOKENS`: `("…","api:","dynamic_api")` → `("…","dynamic_local_qwen")` —
   symmetric rename; local-model base answers are weak-source targets exactly as API answers were.
3. Per-permutation `try/except` added → `parse_status: "local_error"`, `failure_reason` recorded;
   pre-migration an exception aborted the entire layer. This is an improvement, verified by fake
   test (one injected failure → 1 `local_error` + 5 `ok` records, item still summarized).

Unchanged and re-verified: feature-based target scoring (weights identical), `max_qids` as slice
cap after sort (`targets[:max_qids]`), deterministic permutation build, map-back
(`map_permuted_answer_to_original` — module untouched except a docstring; adversarially exercised
for **every option position in every permutation** of a 4-choice sample: all mapped correctly;
label/text mismatch → `option_text_no_match`, not a vote), vote summary + conservative override
policy (`summarize_permutation_votes`/`select_permutation_override` untouched), JSONL resume keyed
`(qid, permutation_id)`. No API response field is referenced anywhere. V12B returns a
`V12BLayerResult` per target (never silently empty).

**Verdict: VERIFIED.**

## 10. V13 review

Diff vs backup: client → backend, `_interpret_api` → `_interpret_model_json` (rename only, same
body), `_WEAK_TOKENS` rename symmetric, per-call `try/except` added
(`local_error:<ExcType>` result). Prompts (`_prompt`), `build_messages` empty-prompt guard, JSONL
emit/resume, `V13LayerResult` fields — all unchanged.

- Programmatic solver: now always deterministic-only (`v13_dynamic_layer.py:256-268`) — model-free
  in every mode. (Pre-migration `execute_api=True` could also model-back it; that mode is gone by
  design. The `programmatic_solver` branch of `_interpret_model_json` is now dead code.)
- Content-first and least-to-most genuinely call `backend.generate_text` (fake-backend run shows
  distinct prompts and per-layer results).
- Branch isolation proven: injected content-first failure → `local_error:RuntimeError` recorded,
  least-to-most still produced its candidate.
- `parse_json_object` (fenced/embedded JSON tolerated) replaces `client.parse_json`; plain-text
  non-JSON output → `parse_error`/interpret-failure, same as before (the old client parser also
  required a JSON object).
- Confidence is still the model-reported value passed through (`parsed.get("confidence")`) — same
  scale, not fabricated.
- Candidate agents: `src/api/api_candidate_agents.py` → `src/local_model/candidate_agents.py` is a
  **pure move; `diff` shows docstring-only changes**. Consumers (`test_calc_first_2l28b.py`,
  `test_judge_and_adaptive.py`, compat-imports test) updated and passing.

**Verdict: VERIFIED.**

## 11. Selector / candidate schema compatibility

`src/selector/system_candidate_selector.py`, `answer_ranker.py`, `candidate_consistency.py`,
`confidence.py` are **byte-identical to pre-migration** (not in the diff). `mcq_verifier.py`
changed one import — `format_choices` now from `src/utils/prompting` — and the old
`openrouter_prompts.format_choices` was itself just a re-import of that same function, so this is
an indirection removal, not a behavior change.

The dataclasses the selector consumes (`V12BLayerResult.{qid,proposed_answer,accept,reason,
vote_counts,valid_votes}`, `V13LayerResult.{qid,layer,proposed_answer,accept,confidence,reason}`,
`BasePrediction.{qid,answer,source,confidence,risk_reason}`) kept every field name and type.
Fake-candidate proofs (temporary script):

- strong accepted V12B overrides ✔; non-accepted V12B does not ✔;
- agreeing content-first + least-to-most override ✔;
- invalid label (`"Z"`) is rejected by the selector's `is_valid_label` check and additionally by
  `fastmcq_system._label_valid` before writing ✔ — no silent never-promotable path found; a
  candidate that fails promotion always leaves the Base answer in place, and every qid is written;
- conflict case: with a **weak** Base answer, a `content_first` candidate at
  confidence ≥ `_STRONG_CONF` (= 0.6) is promoted even when least-to-most disagrees
  (`system_candidate_selector.py:86-87`). This is **pre-existing selector semantics, byte-identical
  to the backup** — not a migration change — but reviewers expecting "conflict always retains
  Base" should know the actual rule is conditional.

**Verdict: schema-compatible; no silent mismatch.**

## 12. One-eighth budget

Full-source search for `1/8`, `/8`, `ceil(`, `auto`, `max_qids`: the only resolver is
`final_infer.py:_resolve_maxq` (`:255-272`), `max(1, math.ceil(n_input/8))`, applied independently
to `--v12b-max-qids` and `--v13-max-qids` (both default `"auto"`); Base is uncapped by
construction. Measured: N=1→1, 7→1, 8→1, 9→2, 450→57, 463→58; N=0→1; `"all"`→None; ints pass
through. Fixed profiles `public_local50` (50), `public_local100` (100), `private_local200` (200)
set explicit ints, not `auto`. Target selectors sort by risk score and slice — they may return
fewer than the cap and are risk-ranked, not first-K. Other `/8` occurrences: a bitsandbytes
comment in `src/solvers/hf_common.py:160` and doc comments only.

**Verdict: VERIFIED.**

## 13. OpenRouter zero-dependency status (tracked vs untracked, made explicit)

- **Active tracked runtime (src/scripts/configs/tests/requirements/Dockerfile/README/
  DOCKER_SUBMISSION)**: zero matches for `openrouter` (case-insensitive), `OPENROUTER_API_KEY`,
  `api.openrouter.ai`, `OpenRouterClient|OpenRouterGraphSolver|SelectiveAPIClient|execute_api|
  base_execute_api|skipped_no_api|api_budget`. Independently re-run; also re-run with plain `grep`
  over the 11 untracked files (which `git grep` cannot see): zero matches, and no
  `httpx/requests/urllib/socket` usage in the new backend.
- **Historical tracked documentation**: `docs/FINAL_SYSTEM.md` still contains 10 `openrouter`
  mentions (plus `docs/audits/*` by design). Audit 60 excluded this file from its greps and
  disclosed the exclusion; strictly, "no active instruction requires a provider key" is true, but
  a tracked doc still describes the old system (finding M4).
- **Ignored local workspace state**: `.env` (git-ignored, `.gitignore:15`) still contains the key
  name `OPENROUTER_API_KEY` (value not inspected); `Dockerfile.api` (git-ignored, `.gitignore:21`)
  still contains 3 OpenRouter references. Both are excluded from Git and from the Docker build
  context (`.dockerignore` excludes `.env`/`.env.*`; `Dockerfile.api` is not the build file).
  Neither was deleted or modified in this review.
- Environment-key immunity proven dynamically: running the full fake-backend system with
  `OPENROUTER_API_KEY` set vs deleted produces byte-identical output.

**Verdict: COMPLETE FOR TRACKED ACTIVE CODE** (with the historical-doc and ignored-file caveats
above stated explicitly).

## 14. Requirements and Docker

- `requirements.txt`: removed only `httpx` (and the legacy comment block). Verified no active
  import of `httpx` or `dotenv` anywhere in `src/scripts/tests/predict.py/run.py` — the only
  remaining "httpx" strings are *negative assertions* in `test_calculation_solver.py:451` /
  `test_evidence_reranker.py:382` that forbid network imports. Local-Qwen deps present:
  `transformers`, `accelerate`, `safetensors`, `huggingface_hub`, `sentencepiece`, `PyYAML`,
  `pytest`; torch pinned in the Dockerfile (unchanged).
- `requirements-openrouter.txt` deleted; nothing references it.
- `Dockerfile`: comment-only change vs backup and vs accepted `d504296`. `COPY . /code` +
  unchanged `.dockerignore` still include all new files (`src/local_model/*`, `scripts/run/*`,
  configs); `.dockerignore` excludes only secrets/scratch/docs/artifacts, and excludes `.env`.
  Runtime remains offline (`local_files_only=True` added on both loads; no network import).
  No build performed (out of scope).
- `python -m compileall -q src scripts tests predict.py run.py` → PASS.
- `bash -n` over every existing `.sh` in the worktree → PASS (the six deleted tracked `.sh` paths
  fail `git ls-files`-driven checks only because the files no longer exist — expected for an
  uncommitted deletion).

## 15. Entrypoint / command verification

| Command | Exists | Parser OK | Profile/config exists | Imports clean | Key/network free | Documented accurately |
|---|---|---|---|---|---|---|
| Docker no-arg (`inference.sh` → `python predict.py`) | ✔ | ✔ | n/a | ✔ (contract tests stub `_build_predictor` and pass) | ✔ | ✔ |
| `python predict.py` | ✔ | `--help` OK; `--no-api` removed | n/a | ✔ | ✔ | ✔ |
| `python predict.py --legacy-dynamic-full` | ✔ | ✔ | delegates to `final_infer --profile local_selective_auto` (profile exists) | ✔ | ✔ (dry-run + fake-backend verified) | ✔ |
| `scripts/run_full_system.sh` | ✔ | `bash -n` OK | `local_selective_auto` | calls `scripts/final_infer.py` (shim exists) + `scripts/output_quality_report.py` (exists) | ✔ | ✔ (no `--no-api` remnants) |
| `scripts/final_infer.py` (shim) / `scripts/tools/final_infer.py` | ✔ | `--help` OK; modes `dynamic_full/public_replay/auto/frozen_csv/v10`; `v11_independent` removed cleanly (unknown mode now refuses) | 5 local profiles | ✔ | ✔ (`--dry-run` PASS with key env removed) | ✔ |
| `scripts/run/run_local_auto.sh`, `run_public_local50/100.sh`, `run_private_local.sh`, `run_private_local200.sh` | ✔ (untracked) | `bash -n` OK | profiles exist | ✔ | ✔ | usage comment in `run_local_auto.sh` says `scripts/run_local_auto.sh` instead of `scripts/run/run_local_auto.sh` (cosmetic, finding L4) |
| `python run.py` | ✔ | all `openrouter_*` flags removed; `--solver` choices `always_a/hf_generate/hf_option_score/adaptive_agent` | `configs/default.yaml` | ✔ | ✔ | ✔ (docstring says it is not the BTC entrypoint) |

Note on `run.py`: the removed `--calculation-solver/--evidence-reranker/--mcq-verifier/
--adaptive-reasoning` flags were all keys of `openrouter_config`, consumed **only** by the deleted
`openrouter_graph` solver — verified in the pre-migration `build_solver` signature. Their library
modules remain in src with their own tests; only the remote solver that orchestrated them is gone.

## 16. Functional equivalence matrix

| Pre-migration function/entrypoint | Old behavior | New replacement | Semantically equivalent? | Missing behavior |
|---|---|---|---|---|
| Dynamic Base (`_api_answer` via SelectiveAPIClient) | JSON one-letter answer from remote model | `_local_answer` via `backend.predict_mcq` | Yes (same gate order, provenance semantics, conf 0.6) | none |
| SelectiveAPIClient use in V12B | remote chat per permutation | `backend.generate_text` per permutation | Yes + better failure isolation | none |
| V12B permutation run (`run_v12b_option_permutation.py`) | CLI experiment wrapper | `v12b_dynamic_layer` in-system | Yes | standalone CLI gone (system path covers it) |
| V13 content-first / least-to-most | remote chat per layer | local generate per layer | Yes | none |
| Adaptive/graph solver (`openrouter_graph` + calc/evidence/verifier integration) | full remote solving pipeline with integrated calc-override, evidence rerank, verifier | **none** | **No — intentionally removed** | integrated calc/evidence/verifier inference flow has no runnable host |
| Candidate agents (`api_candidate_agents`) | prompt builders/parsers | `local_model/candidate_agents` | Yes (byte-identical code) | none |
| Full-system runner (`run_full_system.sh --no-api`) | deterministic offline full system | `run_full_system.sh` (local model) | Yes in structure | end-to-end run now needs the real model (no modelless mode) |
| Progress/resume | V12B/V13 JSONL resume (API) | same JSONL resume (local), tested | Yes | production-pipeline base checkpointing (`--skip-existing/--checkpoint-every`) not replicated |
| Production pipeline (`run_production_pipeline.py`) | base LLM + safe deterministic overrides + presets | selective system (different design) | **No — superseded, not ported** | preset system, atomic checkpoint writer |
| Timing | per-sample timing in `predict.py` (kept) + production timing report (script deleted) | `predict.py` timing unchanged | BTC timing: yes | production JSONL timing report gone with its script |
| Verifier samples (SK/law-admin/ambiguous/self-consistency) | proposal-only remote experiments | none | **No — intentionally removed** | those experiments |
| Repair workflow (`repair_v11_independent_run.py`) | post-hoc null-label repair | inline label coercion in `fastmcq_system` | Contract covered; workflow gone | standalone repair CLI |

## 17. Validation results (all executed in this review)

- `python -m compileall -q src scripts tests predict.py run.py` → PASS.
- `bash -n` on every existing shell script → PASS.
- Production-critical: `test_btc_submission_contract_2l47a.py + test_data_io.py + test_labels.py`
  → **33 passed**.
- Local backend/selective batch (`test_local_qwen_backend`, `test_local_progress_resume_2l39c`,
  `test_fastmcq_dynamic_system_2l36b`, `test_v13_dynamic_integration_2l37a`,
  `test_run_profiles_2l38c`) → **48 passed, 5 failed**, all 5 being the public-replay
  frozen-artifact tests (the exact set Audit 60 deselected with `-k`).
- Full suite post: **16 failed, 565 passed** — failure ids are a strict subset of the
  pre-migration 18; every failure opens a missing historical artifact
  (`output/pred_v11_independent_rerun1.csv`, `experiments/best_candidate_manifest.json`,
  frozen public CSV, `output/pred_v13_multilayer_candidate_api30_from_v12b.csv`,
  `output/pred_v10_full_production_user_run.csv`).
- Full suite pre (temp worktree at backup): **18 failed, 772 passed** — reproduces Audit 59/60.
- Temporary adversarial fake-backend checks (2 scripts under the session scratchpad, deleted after
  use): 41 checks total; all genuine checks pass. The only persistent findings are the two
  cache-path-normalization gaps (L1) — the other initial failures were bugs in the harness
  (double-counting spy) or pre-existing selector semantics (§11), re-verified green after
  correction.

## 18. Real-runtime limitations (unverified by anyone so far)

Neither Audit 60 nor this review loaded the real model, ran GPU inference, built Docker, or ran
the selective path end-to-end with real generation. Therefore the following remain **unverified**:
real prompt quality and JSON adherence of Qwen3-4B on the V12B/V13 structured prompts, actual
memory footprint of bfloat16 4B + 768-token layer generations, throughput/latency, absence of OOM,
and accuracy of the migrated selective path. Code-level compatibility does not prove
production-readiness. A GPU smoke test is required before any promotion decision.

## 19. Defects found, by severity

**Critical:** none.

**High:** none.

**Medium:**
- **M1** — End-to-end wrapper coverage lost: `test_full_system_output_contract_2l41a.py` (12→5)
  and `test_btc_noarg_2l32b.py` no longer *execute* `run_full_system.sh`/`final_infer` main paths
  (now `--dry-run`/shape checks), because the local path needs a real model. Promotion to
  `output/pred.csv`, failed-run non-overwrite, and quality-guard blocking are untested.
  Repair: add a fake-backend injection seam (env var or importable stub) usable from the wrapper,
  or a marked GPU smoke test.
- **M2** — The integrated calc-override/evidence-reranker/mcq-verifier inference flow (formerly
  hosted by `openrouter_graph`) has no runnable host; modules survive as libraries with unit
  tests. If that architecture is wanted for a future local default, it must be re-wired.
- **M3** — `src/layers/adaptive_orchestrator.py` retained but its entire test file (24 tests) was
  deleted; the module now has zero coverage and no entrypoint. Either delete it too or restore a
  local-client version of its tests.
- **M4** — Stale tracked doc: `docs/FINAL_SYSTEM.md` still describes the OpenRouter system
  (10 mentions). Audit 60 excluded it from greps rather than updating or flagging it for update.

**Low:**
- **L1** — `get_local_qwen_backend` cache key does not normalize `model_path` (trailing slash,
  relative segments → separate backend → potential second model load if call sites diverge).
  Suggest `str(Path(p).resolve())` normalization. Not reachable via current call paths.
- **L2** — `LocalQwenBackend.load()` has no lock; concurrent first calls could double-load.
  Single-threaded today.
- **L3** — Dead code: `_interpret_model_json`'s `programmatic_solver` branch is unreachable;
  `predict_base_answers(work_dir=, resume=)` accepted-but-unused (pre-existing);
  `run_v13_layers_if_enabled` in `v13_layer_registry.py` now reports `executed/applied: True` as
  static metadata without executing anything (misleading notes; no caller in the runtime path).
- **L4** — Cosmetic: usage comment in `scripts/run/run_local_auto.sh` cites the wrong path.

**Files that would need repair/restoration if the findings are addressed** (do NOT change in this
review): `docs/FINAL_SYSTEM.md` (M4), `tests/` wrapper-level fake-backend seam (M1),
`src/local_model/local_qwen_backend.py` (L1/L2), `src/layers/v13_layer_registry.py` +
`src/layers/adaptive_orchestrator.py` decision (M3/L3), `scripts/run/run_local_auto.sh` (L4).
Nothing needs rollback.

## 20. Is Audit 60 accurate?

**Accurate, with two overstatements and one understatement.** Every checkable factual claim
(file inventory, test counts, grep results, prompt/parser preservation, shared-backend design,
1/8 semantics, profile/CLI migration, d504296 comparison) reproduced exactly. Overstated:
(1) "Deleted when transport-only or broken after transport deletion" — several deletions were
complete research workflows containing non-transport logic (disclosed in the inventory but not in
that sentence); (2) the zero-OpenRouter section silently scopes out `docs/FINAL_SYSTEM.md` and the
ignored `.env`/`Dockerfile.api`, which still carry provider material. Understated: V12B/V13
failure isolation is an improvement, not mere preservation. Audit 60 did not fabricate results.

## 21. Required verdicts

- **A. BTC accepted single-pass preservation: SAFE** (prompt, parser, generation kwargs, I/O,
  timing all preserved; only intentional hardening `local_files_only=True`).
- **B. OpenRouter removal completeness: COMPLETE FOR TRACKED ACTIVE CODE** (historical
  `docs/FINAL_SYSTEM.md` and ignored `.env`/`Dockerfile.api` still carry provider material).
- **C. Dynamic Base local migration: VERIFIED.**
- **D. V12B local migration: VERIFIED.**
- **E. V13 local migration: VERIFIED.**
- **F. Shared one-model-load design: VERIFIED BY STATIC/FAKE TESTS** (never proven with the real
  model; cache-path normalization gap noted as L1).
- **G. Deleted scripts/tests safety: PARTIALLY JUSTIFIED** (all deletions deliberate and
  disclosed; adaptive-workflow/wrapper-level/orchestrator coverage removed without replacement —
  M1/M2/M3).
- **H. Ready to merge selective mode into default: REQUIRES REAL GPU SMOKE TEST FIRST** (no code
  blocker found, but the selective path has never generated a single real token; per instructions
  the selective-default merge was NOT performed here).

## 22. Recommendation

**Keep the migration.** Do not roll back. Before making the selective pipeline the default:
(1) run a real-model GPU smoke test of `final_infer.py --profile local_selective_auto` on a small
input; (2) address M1 (wrapper-level testability) and L1 (path normalization); (3) update or flag
`docs/FINAL_SYSTEM.md`; (4) decide the fate of `adaptive_orchestrator.py` (M3).

## 23. Required explicit statements

- No migration file was modified.
- No deleted file was restored.
- No source/test/config/script was changed (the only file created is this audit).
- No test was skipped or xfailed.
- No package was installed.
- No model was downloaded.
- No API or network request was made.
- No Docker image was built or pushed.
- No real model inference was run.
- No commit was created automatically.
- The temporary detached worktree at the backup commit was removed after use
  (`git worktree remove`); temporary fake-backend scripts lived in the session scratchpad and were
  deleted after execution. No repository cache or artifact was deleted.
- `.env` and `Dockerfile.api` were not deleted, modified, or value-inspected (key **names** only).

## 24. Final Git status (after this review)

Identical to the Audit-60 final status plus exactly one new untracked file:

```text
## main...origin/main   (HEAD 87d5d71)
 M  <the same 116 tracked modifications/deletions listed in Audit 60 §Complete Inventory>
?? docs/audits/AUDIT_59_system_reality_and_dependency_review.md
?? docs/audits/AUDIT_60_openrouter_to_local_migration.md
?? docs/audits/AUDIT_61_codex_migration_independent_review.md   <- created by this review
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
