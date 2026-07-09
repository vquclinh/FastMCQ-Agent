# AUDIT 59: system reality and dependency review

Date: 2026-07-09

Scope: read-only repository/system audit of current `main`, accepted BTC Docker default runtime,
optional/legacy architectures, tests, configs, artifacts, and unused/uncertain candidates.

This audit is based on executable source, Dockerfile/shell entrypoints, argparse defaults,
environment-variable branches, config loaders, imports/dynamic imports, shell/subprocess references,
tests, README commands, and Git history. Existing docs were compared against code and were not treated
as authority.

## 1. Git baseline and guardrails

Initial commands and evidence:

| Check | Result |
|---|---|
| `git status --short --branch` before audit | `## main...origin/main` |
| `git rev-parse HEAD` | `87d5d71ff2f9d02b9f41c8df351a683f3b683662` |
| Expected HEAD | matches exactly |
| `git log --oneline --decorate -15` | `87d5d71 (HEAD -> main, origin/main, origin/HEAD) remove obsolete experiment metadata`; previous commits include `dd21ed8`, `d504296` |
| `git show --no-patch --format=fuller 87d5d71...` | subject `remove obsolete experiment metadata`, authored/committed 2026-07-08 20:45:51 +0700 |
| `git show --no-patch --format=fuller d504296` | subject `BTC DockerHub default run`, authored/committed 2026-06-28 10:21:04 +0700 |
| `git branch --contains 25e25ee` | only `backup/before-tests-scripts-restore-6fa2168` |
| `git branch --contains 6fa2168` | only `backup/before-tests-scripts-restore-6fa2168` |

No unrelated tracked modifications existed before the audit. The worktree was clean for tracked and
untracked files before validation. Ignored local state already existed (`.env`, `.pytest_cache`,
`Dockerfile.api`, `models/`, generated `output/pred*.csv`, caches). Running allowed validation
created/updated ignored caches and ignored `scratch/` artifacts; these were not deleted.

## 2. Accepted BTC default: exact no-argument runtime graph

Organizer-facing command documented in `README.md:95-97`:

```bash
docker run --name fastmcq_btc_test --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent:latest
```

No arguments are passed after the image name. Docker therefore executes the image `CMD`, not a
post-image command override.

Literal call graph:

```text
docker run ... vquclinh/fastmcq-agent:latest
  -> Dockerfile:18 WORKDIR /code
  -> Dockerfile:54-56 ENV LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507,
     TRANSFORMERS_OFFLINE=1, HF_HUB_OFFLINE=1
  -> Dockerfile:61 CMD ["bash", "inference.sh"]
  -> inference.sh:4 set -euo pipefail
  -> inference.sh:5 python predict.py "$@"
  -> predict.py:138-154 parse args; --legacy-dynamic-full defaults False
  -> predict.py:156 _resolve_input(None)
       priority predict.py:40-45 after $INPUT_FILE: /code/private_test.json,
       /code/public_test.json, /app/data/*.json, /data/*.json, /data/*.csv
  -> predict.py:157-159 resolve /code/submission.csv and /code/submission_time.csv
  -> predict.py:176-179 offline branch: load_dataset(inp), _build_predictor(args)
  -> predict.py:102-108 QwenMCQPredictor(...).load()
  -> src/local_model/qwen_mcq_predictor.py:62-78 lazy torch/transformers load
  -> src/local_model/qwen_mcq_predictor.py:80-100 build prompt, generate, parse label
  -> predict.py:182-197 per-sample loop, fallback isolation, timing
  -> predict.py:199-209 write submission.csv and submission_time.csv
  -> predict.py:214-221 optional legacy mirror to --output/$OUTPUT_FILE and /output/pred.csv
```

BTC default conclusions:

- Model: `Qwen/Qwen3-4B-Instruct-2507`, downloaded at build time to `/models/qwen3-4b-instruct-2507`
  (`Dockerfile:45-48`, `scripts/download_local_model.py:19-20`).
- Generation defaults: `--max-new-tokens 64` (`predict.py:148`), device `auto`
  (`predict.py:149`), `torch.bfloat16` on CUDA else `float32` (`qwen_mcq_predictor.py:69`),
  `device_map="auto"` on CUDA (`qwen_mcq_predictor.py:70`), `do_sample=False`, `num_beams=1`,
  `pad_token_id=eos` (`qwen_mcq_predictor.py:95-97`), `trust_remote_code=True`
  (`qwen_mcq_predictor.py:72-74`).
- Input paths: `--input`, `$INPUT_FILE`, then `/code/private_test.json`, `/code/public_test.json`,
  `/app/data/private_test.json`, `/app/data/public_test.json`, `/data/private_test.json`,
  `/data/public_test.json`, `/data/private_test.csv`, `/data/public_test.csv`.
- Outputs: `/code/submission.csv` (`qid,answer`), `/code/submission_time.csv`
  (`qid,answer,time`), optional mirror to `/output/pred.csv`.
- Sample failure behavior: per-sample exceptions and invalid/empty model labels fall back to first
  valid label (`predict.py:85-99`, `predict.py:185-197`) and do not abort the run.
- V12B/V13: not executed in BTC default. The legacy branch is gated by
  `--legacy-dynamic-full` (`predict.py:168`).
- `ceil(N/8)` / "1/8": not used in BTC default.
- OpenRouter/API key: not used in BTC default. `--no-api` is a compatibility no-op
  (`predict.py:152-153`).
- Config files: no config file is loaded in BTC default. `predict.py` uses argparse/env defaults and
  imports only runtime modules.

## 3. Build-time dependency graph

Current `Dockerfile` graph:

```text
Dockerfile
  -> FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04 (Dockerfile:12)
  -> ENV DEBIAN_FRONTEND, PYTHONUNBUFFERED, PIP_NO_CACHE_DIR (Dockerfile:14-16)
  -> WORKDIR /code (Dockerfile:18)
  -> apt-get python3 python3-pip python3-dev git ca-certificates (Dockerfile:21-24)
  -> pip install --upgrade pip (Dockerfile:29)
  -> pip install --index-url https://download.pytorch.org/whl/cu128 torch==2.7.1 (Dockerfile:29-30)
  -> COPY requirements.txt . (Dockerfile:33)
  -> pip install -r requirements.txt (Dockerfile:34)
  -> COPY . /code (Dockerfile:38), filtered by .dockerignore
  -> chmod +x inference.sh (Dockerfile:40)
  -> ARG SKIP_MODEL_DOWNLOAD=0 (Dockerfile:44)
  -> if default: python scripts/download_local_model.py
       --model Qwen/Qwen3-4B-Instruct-2507
       --out /models/qwen3-4b-instruct-2507 (Dockerfile:45-48)
  -> ENV LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507,
     TRANSFORMERS_OFFLINE=1, HF_HUB_OFFLINE=1 (Dockerfile:54-56)
  -> CMD ["bash", "inference.sh"] (Dockerfile:61)
```

`.dockerignore` excludes secrets/local artifacts (`.env`, `.env.*`, keys), `scratch/`,
`experiments/`, `docs/`, virtualenvs, harness `data/` and `output/`, `.git/`, caches, notebooks,
logs/jsonl, local `models/`, model weight extensions, and local smoke dirs (`.dockerignore:1-63`).

Repository files required to rebuild the accepted image from source:

- `Dockerfile`, `.dockerignore`, `requirements.txt`
- `inference.sh`, `predict.py`
- `scripts/download_local_model.py`
- `src/__init__.py`, `src/local_model/__init__.py`, `src/local_model/qwen_mcq_predictor.py`
- `src/utils/__init__.py`, `src/utils/data_io.py`, `src/utils/labels.py`, `src/utils/logging.py`

Build also depends on external package/model networks at build time: Ubuntu apt repos, PyPI/default
index, PyTorch CUDA 12.8 wheel index, and Hugging Face Hub for `Qwen/Qwen3-4B-Instruct-2507`. This
audit did not build Docker or download the model.

## 4. README and Docker command verification

| README/DOCKER command or claim | File and line | Actual executable path | Current status | Evidence |
|---|---:|---|---|---|
| `docker pull vquclinh/fastmcq-agent:latest` | `README.md:81-83` | Docker Hub pull | Runnable but requires network; not run | External image operation |
| Linux BTC run with `-v "$PWD/private_test.json:/code/private_test.json:ro"` and no post-image args | `README.md:95-97` | Docker `CMD` -> `inference.sh` -> `predict.py` offline branch | Valid organizer command if image has baked model and host file exists | `Dockerfile:61`, `inference.sh:5`, `predict.py:168-179` |
| PowerShell BTC run | `README.md:107-109` | Same as above | Valid Windows equivalent if mount path works | Same evidence |
| `docker cp fastmcq_btc_test:/code/submission*.csv` | `README.md:124-125`, `134-135` | Copies files written by `predict.py` | Valid only when container was kept with `--name` and not removed | `predict.py:199-209` |
| Minimal run with `/path/to/private_test.json:/code/private_test.json:ro` | `README.md:153-155` | Same BTC default path | Valid, no post-image args | `Dockerfile:61` |
| `--network none` run | `README.md:169-171` | Same BTC default path | Valid after image is built with weights | Offline env `Dockerfile:54-56` |
| `docker build -t vquclinh/fastmcq-agent:latest .` | `README.md:180`, `DOCKER_SUBMISSION.md:25` | `Dockerfile` graph above | Valid but requires network/model download; not run | `Dockerfile:29-48` |
| `/app/data` compatibility run | `README.md:190-192`, `DOCKER_SUBMISSION.md:39-41` | `predict.py` input resolver uses `/app/data/*.json` | Runnable if mounted dir contains private/public JSON; with `--rm` output inside `/code` is not preserved unless host output override is used | `predict.py:40-45`, `predict.py:199-221` |
| `/data` -> `/output/pred.csv` legacy run | `README.md:198-201`, `DOCKER_SUBMISSION.md:116-118` | `predict.py` uses `/data/*.json/csv`, mirrors to `/output/pred.csv` | Runnable compatibility path if `/output` mounted writable | `predict.py:214-221` |
| `predict.py --legacy-dynamic-full` dev path | `README.md:332-334`, `README.md:387` | dynamic import of `scripts/tools/final_infer.py` | Exists; not BTC default | `predict.py:125-135` |
| `bash scripts/run_full_system.sh <test_file> --no-api` | `DOCKER_SUBMISSION.md:169` | wrapper -> `scripts/final_infer.py` -> `scripts/tools/final_infer.py` -> `run_fastmcq_system` | Exists and works in no-API tests; writes ignored scratch/output artifacts | `scripts/run_full_system.sh:58-61`; pytest created ignored `scratch/runs/...` |
| Validation: `.venv/bin/python -m compileall -q src scripts tests` | `README.md:417` | Python compileall | `python -m compileall -q src scripts tests` passed in current env; `.venv/bin/python` may not exist | Audit command result |
| Validation: `.venv/bin/python -m pytest -q` | `README.md:418` | pytest suite | Full suite fails: 772 passed, 18 failed due missing legacy/frozen artifacts | See section 12 |
| Validation: `.venv/bin/python scripts/audit_model_policy.py` | `README.md:419` | shim -> `scripts/tools/audit_model_policy.py` | Passed with system Python | Audit command result |
| DOCKER_SUBMISSION "Run - BTC default (no flags)" without mounted input | `DOCKER_SUBMISSION.md:30-32` | Docker `CMD` -> `predict.py`, input resolver | Stale/incomplete as a standalone runnable command: with no `/code` or compat input mounted it exits refusing missing input | `predict.py:48-63` |

## 5. Default matrix

| Context | Default entrypoint | Default mode/profile | Default model | V12B? | V13? | 1/8? | API/local |
|---|---|---|---|---:|---:|---:|---|
| Docker no-argument default | `CMD ["bash","inference.sh"]` | offline local `predict.py` branch | `/models/qwen3-4b-instruct-2507` | No | No | No | Local only |
| `inference.sh` default | `python predict.py "$@"` | whatever flags pass; no flags = offline | `$LOCAL_MODEL_PATH` or Qwen path | No unless `--legacy-dynamic-full` | No unless `--legacy-dynamic-full` | No unless legacy dynamic | Local default |
| `predict.py` no-argument default | `predict.py` | offline local model | `DEFAULT_MODEL_PATH` or `$LOCAL_MODEL_PATH` | No | No | No | Local only |
| `predict.py --legacy-dynamic-full` | dynamic import `scripts/tools/final_infer.py` | `production_full_system_noapi` without key/`--no-api`, else `production_full_system` | API profile model `qwen/qwen3.5-9b-20260310` when API on; no local Qwen | Yes if enabled | Yes if enabled | Yes, only for auto V12B/V13 max qids | API if key and not `--no-api`; otherwise offline fallback |
| Root `run.py` | `python run.py` | intended `configs/default.yaml` / `always_a` | none by default | No | No | No | Broken: `ModuleNotFoundError: src.data_io` |
| `scripts/final_infer.py` | shim to tools final infer | `dynamic_full` | profile/config model if API path | Yes default | Yes default | Yes for `--v12b-max-qids auto`, `--v13-max-qids auto` | No API by default unless `--execute-api`/profile |
| `scripts/tools/final_infer.py` | direct | `--mode dynamic_full` default | config model for API path | Yes default | Yes default | Yes for auto max qids | No API by default |
| `scripts/run_full_system.sh` | shell wrapper | key present -> `production_full_system`; absent/`--no-api` -> `production_full_system_noapi` | OpenRouter Qwen 3.5 when API on | Yes | Yes | Yes in production profiles | API only with key |
| `configs/production/default.json` | loaded by final_infer | metadata says `production_mode=dynamic_full`, `default_mode=frozen_csv` | `qwen/qwen3.5-9b-20260310` | metadata yes | metadata yes | via profiles/CLI, not this JSON formula | Optional API/dynamic metadata |
| `configs/default.yaml` | intended root `run.py` | `solver: always_a` | none by default | No | No | No | No API unless solver changed |
| `production_full_system` profile | final_infer profile | `dynamic_full`, `execute_api=true` | `qwen/qwen3.5-9b-20260310` | Yes | Yes | Yes (`auto`) | OpenRouter |
| `production_full_system_noapi` profile | final_infer profile | `dynamic_full`, `execute_api=false`, `base_execute_api=false` | none for model calls | Targets selected; V12B skipped no API | V13 deterministic programmatic may run; model layers skipped | Yes (`auto`) | Offline |
| `public_api50` | wrapper/profile | `dynamic_full`, API cap 50 | `qwen/qwen3.5-9b-20260310` | Yes max 50 | Yes max 50 | No, fixed 50 | OpenRouter |
| `public_api100` | wrapper/profile | `dynamic_full`, API cap 100 | same | Yes max 100 | Yes max 100 | No, fixed 100 | OpenRouter |
| `private_api200` | wrapper/profile | `dynamic_full`, API cap 200 | same | Yes max 200 | Yes max 200 | No, fixed 200 | OpenRouter |
| `public_layer_api50` | wrapper/profile | base no API, layer API | same for layer calls | Yes max 50 | Yes max 50 | No, fixed 50 | OpenRouter layer only |
| `dynamic_noapi`, `private_noapi` | wrappers/profiles | `dynamic_full`, no API | none for model calls | targets only/skipped | deterministic V13 possible | Default CLI auto if not set in profile | Offline |
| API/no-API shell wrappers | `scripts/run/*.sh` | named profiles | profile-specific | profile-specific | profile-specific | profile-specific | API wrappers require key; noapi wrappers do not |

Do not say "the default uses 1/8" without naming the context. The BTC Docker default does not use
1/8. The optional dynamic `final_infer.py` profiles use `auto = ceil(N/8)` only for V12B/V13
`max_qids` when those values are `"auto"`.

## 6. V12B/V13 and 1/8 forensic analysis

Implementation locations:

- V12B layer: `src/layers/v12b_dynamic_layer.py`
  - target selection: `select_v12b_targets` (`v12b_dynamic_layer.py:79-117`)
  - execution: `run_v12b_layer` (`v12b_dynamic_layer.py:131-198`)
  - API guard: returns skipped results when `execute_api=False` (`v12b_dynamic_layer.py:137-142`)
  - API model policy/client only under execute_api (`v12b_dynamic_layer.py:144-147`)
- V13 layer: `src/layers/v13_dynamic_layer.py`
  - target selection: `select_v13_targets` (`v13_dynamic_layer.py:71-113`)
  - deterministic no-API arithmetic path: `_deterministic_programmatic`
    (`v13_dynamic_layer.py:116-132`)
  - execution: `run_v13_layer` (`v13_dynamic_layer.py:225-297`)
  - API client only when `execute_api=True` (`v13_dynamic_layer.py:229-233`)
  - model layers skip in no-API mode except deterministic arithmetic (`v13_dynamic_layer.py:262-277`)
- Candidate merging/selection: `src/selector/system_candidate_selector.py:36-110`.
- Base answers every input item: `src/base/dynamic_base_predictor.py:75-113` loops all samples and
  produces formula-bank, API, or valid fallback answer; `base_prediction_is_valid` checks validity.
- System orchestration: `src/system/fastmcq_system.py:114-230`.
- Auto budget: `scripts/tools/final_infer.py:284-302`, specifically `max(1, math.ceil(n_input / 8))`
  at line 301 for `"auto"`.

Nature of 1/8:

- It is a maximum cap per selective layer, not an exact count. After resolving `auto`, target
  selectors return `targets[:max_qids]` (`v12b_dynamic_layer.py:116`,
  `v13_dynamic_layer.py:113`). If fewer eligible targets exist, fewer are used.
- V12B and V13 each receive their own cap (`scripts/tools/final_infer.py:312-314`).
- Target qids are selected by feature/risk ranking, not by hardcoded qid lists
  (`v12b_dynamic_layer.py:79-117`, `v13_dynamic_layer.py:71-113`).
- Output remains all input qids because base predictions cover all qids and final output is assembled
  over `samples` (`fastmcq_system.py:204-215`).

Separate graphs:

```text
BTC accepted default graph
Docker CMD -> inference.sh -> predict.py offline branch
  -> src.utils.data_io.load_dataset
  -> src.local_model.qwen_mcq_predictor.QwenMCQPredictor
  -> src.utils.labels validation
  -> submission.csv + submission_time.csv
No V12B, no V13, no selector, no OpenRouter, no 1/8.
```

```text
Optional selective Base -> V12B -> V13 -> selector graph
predict.py --legacy-dynamic-full
  -> scripts/tools/final_infer.py
  -> FastMCQSystemConfig(dynamic_full)
  -> src.system.fastmcq_system.run_fastmcq_system
  -> src.base.dynamic_base_predictor.predict_base_answers
  -> src.layers.v12b_dynamic_layer.select_v12b_targets/run_v12b_layer
  -> src.layers.v13_dynamic_layer.select_v13_targets/run_v13_layer
  -> src.selector.system_candidate_selector.select_system_overrides
  -> src.utils.data_io.write_predictions
```

Without an API key or with `--no-api`, this optional system still runs offline: base uses
formula-bank/fallback, V12B reports `skipped_no_api`, V13 skips model layers but can run deterministic
programmatic arithmetic. With an API key and execute/profile flags, it uses OpenRouter via
`SelectiveAPIClient` and `OpenRouterClient`.

## 7. Current root inventory

| Root item | Tracked? | Classification | Evidence/status |
|---|---:|---|---|
| `.agents/` | no | LOCAL_GENERATED_ARTIFACT / UNKNOWN_REQUIRES_OWNER_DECISION | Empty local directory |
| `.claude/` | no, ignored by global gitignore | SECRET_OR_LOCAL_CONFIG | Contains `settings.local.json`; not tracked |
| `.codex/` | no | LOCAL_GENERATED_ARTIFACT / UNKNOWN_REQUIRES_OWNER_DECISION | Empty local directory |
| `.dockerignore` | yes | BTC_BUILD_REQUIRED | Excludes secrets, docs, data/output/models/scratch/experiments from image context |
| `.env` | no, ignored | SECRET_OR_LOCAL_CONFIG | Exists; only key name observed: `OPENROUTER_API_KEY`; value not printed |
| `.git/` | internal | UNKNOWN_REQUIRES_OWNER_DECISION | VCS metadata; not audited as repo content |
| `.gitignore` | yes | BTC_BUILD_REQUIRED / SECRET_OR_LOCAL_CONFIG guard | Ignores `.env`, `Dockerfile.api`, `models/`, generated output, scratch |
| `.pytest_cache/` | ignored | LOCAL_GENERATED_ARTIFACT | Test cache |
| `assets/` | yes | DOCUMENTATION_ONLY | `assets/archi.png` used by `README.md:338` |
| `configs/` | yes | OPTIONAL_RESEARCH_RUNTIME / LEGACY_PHASE_WORKFLOW | Loaded by `final_infer.py`, root `run.py` intended config, legacy checks |
| `data/` | yes `.gitkeep` only | BTC_RUNTIME_REQUIRED mount placeholder / LOCAL_GENERATED_ARTIFACT | Docker excludes `data/`; runtime input is mounted |
| `Dockerfile` | yes | BTC_BUILD_REQUIRED | Accepted image build file |
| `Dockerfile.api` | no, ignored | OPTIONAL_RESEARCH_RUNTIME / SECRET_OR_LOCAL_CONFIG | Local-only dev image with `OPENROUTER_API_KEY` build arg; not committed |
| `DOCKER_SUBMISSION.md` | yes | DOCUMENTATION_ONLY | Docker run/build docs |
| `docs/` | yes | DOCUMENTATION_ONLY | Current docs/audits/PDFs; excluded from Docker |
| `inference.sh` | yes | BTC_RUNTIME_REQUIRED | Docker `CMD` target |
| `models/` | ignored except no tracked files | LOCAL_GENERATED_ARTIFACT | 5.4G local BGE/Qwen-reranker assets; Docker excludes host models |
| `output/` | yes `.gitkeep`, ignored local files | BTC_OUTPUT_CONTRACT / LOCAL_GENERATED_ARTIFACT | `output/pred.csv`, `output/pred_final.csv` ignored; BTC official outputs are `/code/*.csv` |
| `predict.py` | yes | BTC_RUNTIME_REQUIRED | Official BTC entrypoint |
| `public-test_1780368312.json` | yes | TEST_ONLY / dataset fixture | JSON list with 463 items; used by tests/docs |
| `README.md` | yes | DOCUMENTATION_ONLY | Organizer/user-facing docs |
| `requirements.txt` | yes | BTC_BUILD_REQUIRED | Installed by Dockerfile; pinned final deps |
| `requirements-llm.txt` | yes | OPTIONAL_RESEARCH_RUNTIME | Optional local HF solvers; not Docker default |
| `requirements-openrouter.txt` | yes | API_OR_OPENROUTER_ONLY | Optional OpenRouter deps; not Docker default |
| `run.py` | yes | LEGACY_PHASE_WORKFLOW / UNREFERENCED_CANDIDATE | Currently broken: `ModuleNotFoundError: src.data_io`; not BTC |
| `scripts/` | yes | BTC_BUILD_REQUIRED / CURRENT_MANUAL_UTILITY / LEGACY_PHASE_WORKFLOW | `download_local_model.py` build-required; many optional/legacy tools |
| `src/` | yes | BTC_RUNTIME_REQUIRED / OPTIONAL_RESEARCH_RUNTIME / REUSABLE_OFFLINE_ALGORITHM | See source inventory |
| `tests/` | yes | TEST_ONLY | 790 collected by default excluding `tests/legacy/*` |
| `__pycache__/` | ignored | LOCAL_GENERATED_ARTIFACT | Python bytecode cache |

## 8. Config and profile inventory

| Config/profile | Loader | Activation command | Main settings | BTC default? | Status |
|---|---|---|---|---:|---|
| `configs/default.yaml` | intended `run.py` via `load_config(args.config)` | `python run.py --config configs/default.yaml` | `solver: always_a`; HF/OpenRouter optional settings | No | Stale because `run.py` import path is broken |
| `configs/adaptive_reasoning.yaml` | intended overlay for root/OpenRouter solver | `--config configs/adaptive_reasoning.yaml` | adaptive reasoning trace-only defaults | No | Optional/legacy; no current BTC consumer |
| `configs/allowed_models.yaml` | `scripts/legacy/checks/check_model_compliance.py`; docs/tests | `python scripts/legacy/checks/check_model_compliance.py ...` | safe allowed/disallowed model patterns | No | Optional policy helper |
| `configs/verifier_selective.yaml` | intended root/OpenRouter overlay | `--config configs/verifier_selective.yaml` | MCQ verifier enabled with reduced trigger | No | Optional/legacy; no BTC consumer |
| `configs/production/default.json` | `scripts/tools/final_infer.py:_load_config` | default final_infer config | dynamic system metadata, frozen artifact paths, OpenRouter model | No | Loaded by optional dynamic/frozen modes; frozen paths missing |
| `production_full_system` | profiles JSON -> `_apply_profile` | `--profile production_full_system` or key-present `run_full_system.sh` | dynamic_full, API true, V12B/V13 auto, budget 20 | No | Optional API research; requires OpenRouter key |
| `production_full_system_noapi` | profiles JSON | `--profile production_full_system_noapi`, default without key in wrappers | dynamic_full, no API, V12B/V13 auto | No | Optional offline selective path |
| `public_replay` | profiles JSON | `--profile public_replay` | public_replay, no API | No | Broken without missing frozen public CSV |
| `dynamic_noapi` | profiles JSON | `scripts/run/run_dynamic_noapi.sh` | dynamic_full, no API, V12B/V13 true | No | Optional manual |
| `public_api50` | profiles JSON | `scripts/run/run_public_api50.sh` | API true, V12B/V13 max 50, budget 2.5 | No | Optional API |
| `public_layer_api50` | profiles JSON | `scripts/run/run_public_layer_api50.sh` | base no API, layer API max 50, budget 1.5 | No | Optional API |
| `public_api100` | profiles JSON | `scripts/run/run_public_api100.sh` | API true, max 100 | No | Optional API |
| `private_noapi` | profiles JSON | `scripts/run/run_private_noapi.sh` | dynamic_full, no API | No | Optional manual |
| `private_api200` | profiles JSON | `scripts/run/run_private_api200.sh` | API true, max 200 | No | Optional API |

Note: shell wrapper comments say `configs/run_profiles.json`; actual loader is
`configs/profiles/run_profiles.json` (`scripts/tools/final_infer.py:347-371`). Files exist and wrappers
call profiles by name.

## 9. Complete `src/` inventory and classification

Reachable root abbreviations: `BTC_DEFAULT_RUNTIME`, `BTC_BUILD`, `PREDICT_LEGACY_FLAG`,
`ROOT_RUN_PY`, `FINAL_INFER`, `OTHER_SCRIPT`, `TEST_ONLY`, `NO_REACHABLE_ROOT`.

| File | Main classes/functions | Imported by / calls | Reachable roots | Tests | Classification | Confidence |
|---|---|---|---|---|---|---|
| `src/__init__.py` | package version | package init | all imports | yes | USED_BTC_PRODUCTION package support | High |
| `src/api/__init__.py` | package init | package support | OTHER_SCRIPT/TEST_ONLY | yes | API_OR_OPENROUTER_ONLY | High |
| `src/api/api_candidate_agents.py` | candidate builders/parsers | legacy API runners, tests | OTHER_SCRIPT | yes | API_OR_OPENROUTER_ONLY | High |
| `src/api/model_policy.py` | allowed-model guards | dynamic base/V12B/V13/API scripts | PREDICT_LEGACY_FLAG, FINAL_INFER, OTHER_SCRIPT | yes | API_OR_OPENROUTER_ONLY | High |
| `src/api/openrouter_client.py` | `OpenRouterClient`, key/payload handling | selective API client, graph solver, legacy runners | OTHER_SCRIPT/ROOT_RUN_PY intended | yes | API_OR_OPENROUTER_ONLY | High |
| `src/api/openrouter_graph_solver.py` | `OpenRouterGraphSolver` | solver factory, tests | ROOT_RUN_PY intended, OTHER_SCRIPT | yes | API_OR_OPENROUTER_ONLY | Medium because root run.py broken |
| `src/api/openrouter_prompts.py` | OpenRouter prompt builders | graph solver, verifier | OTHER_SCRIPT | yes | API_OR_OPENROUTER_ONLY | High |
| `src/api/selective_api_client.py` | guarded selective client | V12B/V13/dynamic base/legacy scripts | PREDICT_LEGACY_FLAG, FINAL_INFER, OTHER_SCRIPT | yes | API_OR_OPENROUTER_ONLY | High |
| `src/base/__init__.py` | package init | package support | OPTIONAL | yes | TEST_SUPPORT/package support | High |
| `src/base/answer_factory.py` | candidate pool/offline factory | legacy scripts/tests | OTHER_SCRIPT | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/base/baseline_solver.py` | `AlwaysASolver` | solver factory/tests | ROOT_RUN_PY intended, OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | Medium |
| `src/base/dynamic_base_predictor.py` | `BasePrediction`, `predict_base_answers` | `fastmcq_system` | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/base/solver_base.py` | abstract solver base | HF/OpenRouter/baseline/adaptive | ROOT_RUN_PY intended, OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/base/solver_factory.py` | `build_solver` | legacy production pipeline, root run.py intended | OTHER_SCRIPT/ROOT_RUN_PY intended | yes | LEGACY_ORCHESTRATOR | Medium |
| `src/evidence/__init__.py` | package init | package support | OPTIONAL | yes | TEST_SUPPORT/package support | High |
| `src/evidence/evidence_pack.py` | evidence pack builders | answer factory/adaptive scripts | OTHER_SCRIPT | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/evidence/evidence_reranker.py` | lexical/neural rerankers | graph solver, option evidence, scripts | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/evidence_sufficiency.py` | sufficiency scoring | legacy audits/tests | OTHER_SCRIPT/TEST_ONLY | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/evidence_verifier_policy.py` | override gate | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/knowledge_cards.py` | cards/retrieval | evidence_pack/rag_lite | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/option_evidence.py` | option-aware evidence | production_inference, scripts | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/option_grounding.py` | option feature/claim match | candidate agents, solvers, tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/passage_compressor.py` | passage compression | graph/adaptive solvers/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/evidence/rag_lite.py` | card retrieval | answer factory/planner | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/formula_cards/__init__.py` | card constants | formula registry/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/layers/__init__.py` | package init | package support | OPTIONAL | yes | TEST_SUPPORT/package support | High |
| `src/layers/adaptive_accuracy_planner.py` | difficulty/planning | legacy plan scripts/tests | OTHER_SCRIPT | yes | LEGACY_ORCHESTRATOR | High |
| `src/layers/adaptive_agent_solver.py` | adaptive HF solver | solver factory/tests | ROOT_RUN_PY intended | yes | LEGACY_ORCHESTRATOR | Medium |
| `src/layers/adaptive_orchestrator.py` | adaptive trace/orchestrator | graph solver, legacy scripts/tests | OTHER_SCRIPT | yes | LEGACY_ORCHESTRATOR | High |
| `src/layers/adaptive_proposal_common.py` | shared legacy IO/guards | many legacy scripts | OTHER_SCRIPT | yes | TEST_SUPPORT/LEGACY_ORCHESTRATOR | High |
| `src/layers/adaptive_routing.py` | branch/risk routing | production/dynamic/legacy | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/layers/adaptive_types.py` | dataclasses | orchestrator/programmatic/cards | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/layers/content_first_answerer.py` | V13 content-first | V13 dynamic/legacy verifier | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/layers/least_to_most_constraint_solver.py` | V13 LTM | V13 dynamic/legacy verifier | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/layers/mcq_permutation_debiaser.py` | permutation maps/voting | V12B dynamic/legacy scripts | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/layers/programmatic_solver_layer.py` | V13 programmatic | V13 dynamic/legacy scripts | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/layers/question_profiler.py` | profile question | router/graph/adaptive/scripts | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/layers/question_router.py` | route question | dynamic base/planners/scripts | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/layers/v12b_dynamic_layer.py` | V12B target/run | `fastmcq_system` | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/layers/v13_dynamic_layer.py` | V13 target/run | `fastmcq_system` | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/layers/v13_layer_registry.py` | registry helper | tests/docs only | TEST_ONLY | yes | TEST_SUPPORT / LEGACY_ORCHESTRATOR | Medium |
| `src/local_model/__init__.py` | package init | package support | BTC_DEFAULT_RUNTIME | yes | USED_BTC_PRODUCTION | High |
| `src/local_model/qwen_mcq_predictor.py` | `QwenMCQPredictor`, prompt/parser | `predict.py` | BTC_DEFAULT_RUNTIME | yes | USED_BTC_PRODUCTION | High |
| `src/selector/__init__.py` | package init | package support | OPTIONAL | yes | TEST_SUPPORT/package support | High |
| `src/selector/answer_ranker.py` | candidate scoring/select | legacy builders | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/selector/candidate_answer.py` | candidate dataclasses | answer factory/tool solvers | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/selector/candidate_consistency.py` | consistency checks | answer ranker/API agents | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/selector/confidence.py` | confidence decision | adaptive solver/tests | ROOT_RUN_PY intended | yes | REUSABLE_OFFLINE_ALGORITHM | Medium |
| `src/selector/independent_answer_selector.py` | independent selection | legacy/tests | OTHER_SCRIPT/TEST_ONLY | yes | LEGACY_ORCHESTRATOR | Medium |
| `src/selector/mcq_verifier.py` | verifier messages/parser | graph solver/scripts/tests | OTHER_SCRIPT | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/selector/system_candidate_selector.py` | V12B/V13 override selector | `fastmcq_system` | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/solvers/__init__.py` | package init | package support | OPTIONAL | yes | TEST_SUPPORT/package support | High |
| `src/solvers/calculation_first_planner.py` | calc planning | adaptive planners/API agents | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/solvers/calculation_solver.py` | deterministic calc families | formula bank, graph, tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/solvers/concept_solver.py` | concept rules | formula bank/answer factory | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/solvers/formula_bank_solver.py` | formula bank | dynamic base/production/scripts | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/solvers/formula_registry.py` | formula registry | programmatic/adaptive | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/solvers/hf_common.py` | HF loading helpers | HF solvers | ROOT_RUN_PY intended | yes | OPTIONAL_RESEARCH_RUNTIME | Medium |
| `src/solvers/hf_generate_solver.py` | local HF generate solver | solver factory | ROOT_RUN_PY intended | yes | OPTIONAL_RESEARCH_RUNTIME | Medium |
| `src/solvers/hf_option_score_solver.py` | local HF scoring solver | solver factory | ROOT_RUN_PY intended | yes | OPTIONAL_RESEARCH_RUNTIME | Medium |
| `src/solvers/pot_lite.py` | safe arithmetic eval | candidate lab/tool solvers | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/solvers/programmatic_solver.py` | formula-card candidate | adaptive scripts | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/system/__init__.py` | package init | package support | OPTIONAL | yes | TEST_SUPPORT/package support | High |
| `src/system/fastmcq_system.py` | optional full-system orchestrator | final_infer legacy branch | FINAL_INFER/PREDICT_LEGACY_FLAG | yes | USED_OPTIONAL_SELECTIVE_SYSTEM | High |
| `src/system/production_inference.py` | old production one-sample path | legacy production pipeline | OTHER_SCRIPT | yes | LEGACY_ORCHESTRATOR | High |
| `src/system/production_policy.py` | branch policy | legacy scripts/tests | OTHER_SCRIPT | yes | LEGACY_ORCHESTRATOR | High |
| `src/system/production_prompts.py` | production prompts | production_inference | OTHER_SCRIPT | yes | LEGACY_ORCHESTRATOR | High |
| `src/tool_solvers/__init__.py` | candidate helper | tool solvers/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/cs_solver.py` | CS solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/finance_econ_solver.py` | finance/econ solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/geometry_solver.py` | geometry solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/physics_solver.py` | physics solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/probability_solver.py` | probability solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/safe_math_solver.py` | safe math solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/tool_solvers/stats_solver.py` | stats solver | answer factory/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/utils/__init__.py` | `log/load_config` re-export | package import | BTC_DEFAULT_RUNTIME and optional | yes | USED_BTC_PRODUCTION | High |
| `src/utils/data_io.py` | dataset/pred IO | `predict.py`, final_infer, scripts | BTC_DEFAULT_RUNTIME | yes | USED_BTC_PRODUCTION | High |
| `src/utils/labels.py` | label helpers | `predict.py`, qwen, many modules | BTC_DEFAULT_RUNTIME | yes | USED_BTC_PRODUCTION | High |
| `src/utils/logging.py` | `log`, `load_config` | qwen/OpenRouter/HF | BTC_DEFAULT_RUNTIME | yes | USED_BTC_PRODUCTION | High |
| `src/utils/output_parser.py` | parse answer label | HF/structured answer/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/utils/postprocess.py` | build predictions | tests/root run intended | ROOT_RUN_PY intended | yes | REUSABLE_OFFLINE_ALGORITHM | Medium |
| `src/utils/prompting.py` | prompt formatting | HF/OpenRouter/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |
| `src/utils/run_logger.py` | JSONL logger | legacy production pipeline | OTHER_SCRIPT | yes | LEGACY_ORCHESTRATOR | High |
| `src/utils/structured_answer.py` | structured answer parser | graph/verifier/tests | OTHER_SCRIPT | yes | REUSABLE_OFFLINE_ALGORITHM | High |

## 10. Complete `scripts/` inventory

| Script | Purpose | Called by | Calls | Required files/configs | BTC default? | Current status |
|---|---|---|---|---|---:|---|
| `scripts/download_local_model.py` | build-time HF snapshot download | `Dockerfile` | `huggingface_hub.snapshot_download` | network, model id, `/models/...` | Yes build | BTC_BUILD_REQUIRED |
| `scripts/audit_model_policy.py` | shim | README/tests | `scripts/tools/audit_model_policy.py` dynamic import | runtime src/scripts/configs | No | CURRENT_MANUAL_UTILITY |
| `scripts/tools/audit_model_policy.py` | model reference scanner | shim/tests/README | scans src/scripts/configs | none | No | CURRENT_MANUAL_UTILITY; passed |
| `scripts/final_infer.py` | shim | wrappers/predict legacy/tests | `scripts/tools/final_infer.py` dynamic import | configs/production, profiles | No | CURRENT_MANUAL_UTILITY |
| `scripts/tools/final_infer.py` | optional dynamic/full/frozen inference | predict legacy, wrappers, tests | `src.system.fastmcq_system`, legacy v11 dynamic import | `configs/production/default.json`, profiles; frozen modes need missing CSVs | No | OPTIONAL_RESEARCH_RUNTIME; dynamic works, frozen/public replay broken |
| `scripts/output_quality_report.py` | shim | `run_full_system.sh`, tests | tools report dynamic import | pred CSV | No | CURRENT_MANUAL_UTILITY |
| `scripts/tools/output_quality_report.py` | answer distribution report | wrapper/tests | reads predictions | pred CSV | No | CURRENT_MANUAL_UTILITY |
| `scripts/validate_submission.py` | shim | legacy shell/docs | tools validator dynamic import | dataset/submission CSV | No | CURRENT_MANUAL_UTILITY |
| `scripts/tools/validate_submission.py` | validates qid/answer CSV | shim/legacy docs | `src.utils.data_io`, labels | dataset and submission | No | CURRENT_MANUAL_UTILITY |
| `scripts/run_full_system.sh` | optional full dynamic runner | docs/tests/manual | `scripts/final_infer.py`, quality report | profiles, scratch/output | No | OPTIONAL_RESEARCH_RUNTIME; creates ignored artifacts |
| `scripts/docker_entrypoint.sh` | old production pipeline entrypoint | not Dockerfile | legacy `run_production_pipeline.py` | `/data`, `/output`, OpenRouter optional | No | LEGACY_PHASE_WORKFLOW |
| `scripts/docker_entrypoint_v11.sh` | dynamic full-system Docker entrypoint | not Dockerfile | `scripts/final_infer.py --profile` | profiles, API key optional | No | LEGACY_PHASE_WORKFLOW |
| `scripts/run/run_dynamic_noapi.sh` | dynamic no-API wrapper | tests/manual | `scripts/final_infer.py --profile dynamic_noapi` | profiles, input | No | OPTIONAL_RESEARCH_RUNTIME |
| `scripts/run/run_private_api200.sh` | private API wrapper | tests/manual | profile `private_api200` | OpenRouter key, input | No | API_OR_OPENROUTER_ONLY |
| `scripts/run/run_private_noapi.sh` | private no-API wrapper | tests/manual | profile `private_noapi` | input | No | OPTIONAL_RESEARCH_RUNTIME |
| `scripts/run/run_public_api100.sh` | public API wrapper | tests/manual | profile `public_api100` | OpenRouter key, input | No | API_OR_OPENROUTER_ONLY |
| `scripts/run/run_public_api50.sh` | public API wrapper | tests/manual | profile `public_api50` | OpenRouter key, input | No | API_OR_OPENROUTER_ONLY |
| `scripts/run/run_public_layer_api50.sh` | layer-only API wrapper | tests/manual | profile `public_layer_api50` | OpenRouter key, input | No | API_OR_OPENROUTER_ONLY |
| `scripts/run/run_public_replay.sh` | public frozen replay wrapper | tests/manual | profile `public_replay` | missing frozen CSV | No | BROKEN_LEGACY_ARTIFACT |
| `scripts/legacy/analysis/analyze_adaptive_branch_proposals.py` | read-only proposal analyzer | legacy/tests | adaptive proposal common | legacy scratch/output files | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/analyze_candidate_disagreements.py` | disagreement review | legacy/tests | formula/policy modules | output CSVs | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/analyze_pilot_failures.py` | pilot failure analysis | legacy/tests | answer factory/consistency | scratch pilot files | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/analyze_short_knowledge_verifier_proposals.py` | SK proposal analyzer | legacy | CSV inputs | output/risk CSVs | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/analyze_v10_geography.py` | V10 geography diagnostic | legacy | formula/policy | legacy output CSVs | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/analyze_v6_runtime.py` | v6 runtime log summary | legacy | JSONL reader | missing v6 logs | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/compare_neural_vs_lexical_chunks.py` | reranker comparison | legacy/tests | evidence_reranker | local models optional | No | OPTIONAL_RESEARCH_RUNTIME |
| `scripts/legacy/analysis/compare_v7_programmatic_assist_pseudo.py` | external pseudo comparison | legacy | CSV readers | missing scratch/output files | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/analysis/inspect_dataset.py` | dataset inspector | manual | data_io | input dataset | No | CURRENT_MANUAL_UTILITY |
| `scripts/legacy/analysis/inventory_calculation_families.py` | calc inventory | tests/manual | calculation solver | dataset/output | No | CURRENT_MANUAL_UTILITY |
| `scripts/legacy/analysis/profile_dataset.py` | dataset profile generator | docs historical | data_io | dataset | No | CURRENT_MANUAL_UTILITY |
| `scripts/legacy/audit/*` | legacy read-only audits | tests/legacy/manual | varied source modules | many missing output/scratch artifacts | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/benchmark/*` | runtime/reranker benchmarks | manual | reranker/log readers | local models/logs optional | No | OPTIONAL_RESEARCH_RUNTIME |
| `scripts/legacy/build/*` | legacy candidate/plan builders | tests/manual | V12/V13/answer factory modules | mostly scratch/output artifacts | No | LEGACY_PHASE_WORKFLOW; some tests fail when frozen inputs missing |
| `scripts/legacy/checks/check_llm_env.py` | local LLM env check | manual | importlib checks | optional local model | No | CURRENT_MANUAL_UTILITY |
| `scripts/legacy/checks/check_model_compliance.py` | model compliance helper | legacy shell | `configs/allowed_models.yaml` | config exists | No | CURRENT_MANUAL_UTILITY |
| `scripts/legacy/checks/check_neural_reranker_env.py` | reranker env check | manual | evidence_reranker | local models optional | No | CURRENT_MANUAL_UTILITY |
| `scripts/legacy/misc/*` | verifier subset/risk pack/pilot qid helpers | tests/manual | mcq verifier/common helpers | scratch/output artifacts | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/repair/*` | legacy repair/apply scripts | tests/manual | formula/assist/API common | output/scratch artifacts | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/review/review_v11_api_candidate.py` | v11 review gate | tests/manual | CSV readers | scratch dir | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/run/*` | legacy runners | tests/manual/runbooks | OpenRouter clients or dynamic imports | mostly OpenRouter key and/or scratch/output inputs | No | LEGACY_PHASE_WORKFLOW |
| `scripts/legacy/run/run_llm_full.sh` | local LLM full wrapper | manual | root `run.py` | broken via `run.py`; local model | No | BROKEN_LEGACY_RUNTIME |
| `scripts/legacy/run/run_llm_smoke.sh` | local LLM smoke wrapper | manual | root `run.py` | broken via `run.py`; local model | No | BROKEN_LEGACY_RUNTIME |
| `scripts/legacy/run/run_local.sh` | local wrapper | manual | root `run.py`, validator | broken via `run.py` | No | BROKEN_LEGACY_RUNTIME |
| `scripts/legacy/submission/*` | legacy submission variants/runbook/cleanup | tests/manual | answer factory/common helpers | missing v10/v11/v7 artifacts in defaults | No | LEGACY_PHASE_WORKFLOW |

All tracked shell files checked with `bash -n` for key wrappers: `inference.sh`,
`scripts/run_full_system.sh`, `scripts/docker_entrypoint.sh`, `scripts/docker_entrypoint_v11.sh`
passed.

## 11. Tests inventory and health

Collection:

- `tests/conftest.py:1-3` ignores `tests/legacy/*` by default.
- `python -m pytest --collect-only -q tests` collected 790 tests.
- `tests/legacy/test_v12_delta_2l34a.py` exists but is not collected by default.

Required targeted production-critical subset:

```text
python -m pytest tests/integration/test_btc_submission_contract_2l47a.py \
  tests/unit/test_data_io.py tests/unit/test_labels.py -q
33 passed in 0.35s
```

Full suite:

```text
python -m pytest tests -q
772 passed, 18 failed in 9.88s
```

Failure classification:

| Test file | Failures | Classification | Missing/stale dependency |
|---|---:|---|---|
| `tests/integration/test_btc_short_2l31b.py` | 3 | MISSING_FROZEN_OUTPUT / STALE_TEST | `output/pred_v13_multilayer_candidate_api30_from_v12b.csv`, `output/pred_v10_full_production_user_run.csv` |
| `tests/integration/test_fastmcq_dynamic_system_2l36b.py` | 3 | MISSING_FROZEN_OUTPUT / STALE_TEST | public replay expects missing frozen CSV |
| `tests/integration/test_final_package_2l31a.py` | 7 | MISSING_EXPERIMENT_ARTIFACT / MISSING_FROZEN_OUTPUT / STALE_TEST | `experiments/best_candidate_manifest.json`, V13/V10 frozen CSVs |
| `tests/integration/test_run_profiles_2l38c.py` | 1 | MISSING_FROZEN_OUTPUT / STALE_TEST | `public_replay` profile expects V13 frozen CSV |
| `tests/integration/test_v12b_permutation_2l34b.py` | 2 | MISSING_FROZEN_OUTPUT / STALE_TEST | `output/pred_v11_independent_rerun1.csv` |
| `tests/integration/test_v13_dynamic_integration_2l37a.py` | 1 | MISSING_FROZEN_OUTPUT / STALE_TEST | public replay expects missing frozen CSV |
| `tests/integration/test_v13_multilayer_2l35a.py` | 1 | MISSING_FROZEN_OUTPUT / STALE_TEST | `output/pred_v11_independent_rerun1.csv` |

Production-critical BTC status: the BTC contract/data/label subset passed. Full-suite failures are
not BTC default runtime failures; they are stale legacy/frozen-artifact tests.

Per-test-file classification:

| Test file | Behavior protected | Collected? | Status |
|---|---|---:|---|
| `tests/unit/test_data_io.py`, `tests/unit/test_labels.py` | BTC input/label helpers | Yes | Passed, production-critical |
| `tests/integration/test_btc_submission_contract_2l47a.py` | BTC `predict.py` contract | Yes | Passed, production-critical |
| all other `tests/unit/*.py` | reusable solvers/API/selector/evidence utilities | Yes | Passed |
| `tests/integration/test_fastmcq_dynamic_system_2l36b.py`, `test_v13_dynamic_integration_2l37a.py`, `test_production_auto_budget_2l44e.py`, `test_full_system_output_contract_2l41a.py`, `test_layer_only_api_profile_2l39d.py` | optional dynamic/V12B/V13 architecture | Yes | Mostly passed; failures only where public replay needs frozen CSV |
| `tests/integration/test_btc_noarg_2l32b.py`, `test_btc_io_priority_2l44d.py`, `test_btc_short_2l31b.py` | older `final_infer` noarg/short behavior | Yes | Mixed; failures are missing frozen CSV/V10 checks |
| `tests/integration/test_final_package_2l31a.py` | old frozen final package | Yes | Stale/broken due removed manifest and frozen outputs |
| `tests/integration/test_v12b_permutation_2l34b.py`, `test_v13_multilayer_2l35a.py` | legacy candidate builders | Yes | Stale where they read missing V11 frozen CSV |
| remaining integration files (`accuracy_engine`, `adaptive_*`, `answer_factory`, `calc_first`, `candidate_lab`, `concept_solver`, `formula_bank_solver`, `full_adaptive_submission`, `independent_v11`, `judge_and_adaptive`, `model_compliance`, `pilot_gate`, `production_layers`, `production_pipeline`, `production_timing`, `repair_v11`, `selective_api`, `sk_verifier_proposal`, `submission_variants`, `v11_hardening`) | optional/legacy reusable algorithms and script guards | Yes | Passed |
| `tests/legacy/test_v12_delta_2l34a.py` | legacy V12 delta | No | Not collected; references removed legacy config/artifacts |

No test was changed, skipped, or xfailed during this audit.

## 12. Dataset, artifact, and local state

| Path | Current state | Tracked/ignored | Consumers | BTC default? |
|---|---|---|---|---:|
| `public-test_1780368312.json` | exists, 463 JSON records | tracked | tests/docs | No |
| `data/` | only `.gitkeep` | tracked placeholder | runtime mount target in legacy; Docker excludes | No baked dependency |
| `output/` | tracked `.gitkeep`; ignored `pred.csv`, `pred_final.csv` local | mixed | legacy outputs/tests | BTC writes `/code/*`; mirror may write `/output/pred.csv` |
| `models/` | ignored local 5.4G BGE/Qwen-reranker assets | ignored | optional reranker checks | No; Docker excludes and downloads Qwen3-4B separately |
| `experiments/` | absent | removed since d504296 | stale legacy/test references | No |
| `scratch/` | initially absent; validation created ignored scratch files | ignored | optional dynamic/test outputs | No |
| frozen `output/pred_v*.csv` | absent | removed since d504296 | stale tests/configs/scripts | No |

Explicit confirmations:

- `experiments/` is absent.
- Frozen `output/pred_v*.csv` files are absent.
- `scratch/` was absent initially; allowed tests created ignored partial scratch outputs.
- Restored/current tests and scripts still point to absent frozen outputs and experiment manifest.

## 13. Requirements and environment

| File | Role | BTC default? | Notes |
|---|---|---:|---|
| `requirements.txt` | final Docker deps | Yes | Pins `transformers==5.12.1`, `accelerate==1.14.0`, `safetensors==0.8.0`, `huggingface_hub==1.21.0`, `sentencepiece==0.2.1`, `PyYAML==6.0.3`, `httpx==0.28.1`, `pytest==9.1.0`; torch installed in Dockerfile |
| `requirements-llm.txt` | optional local HF solvers | No | Not installed by Dockerfile |
| `requirements-openrouter.txt` | optional OpenRouter graph solver | No | Not installed by Dockerfile; `python-dotenv` optional |
| `Dockerfile` | final image | Yes | Does not copy `.env`; `.dockerignore` excludes secrets |
| `Dockerfile.api` | ignored local dev image | No | Contains `ARG OPENROUTER_API_KEY` and `ENV`; secret-bearing if built |
| `.env` | ignored local key file | No | Exists with `OPENROUTER_API_KEY`; value not printed |
| `.gitignore`/`.dockerignore` | safety filters | Yes | Exclude secrets/local artifacts/models/output/scratch |

BTC default does not require an API key. Optional selective API modes require `OPENROUTER_API_KEY`;
optional no-API dynamic modes do not.

## 14. Static reachability and unused-code levels

Levels used:

- Level 1: definitely reachable from BTC/build/default runtime.
- Level 2: optional/research reachable through executable/documented commands.
- Level 3: test-only.
- Level 4: documentation-only or historical.
- Level 5: apparently unreferenced, no executable/test/config/current-doc consumer found.
- Level 6: uncertain due dynamic loading/manual entrypoint ambiguity.

Level 1 closure:

- `Dockerfile`, `.dockerignore`, `requirements.txt`, `scripts/download_local_model.py`,
  `inference.sh`, `predict.py`, `src/local_model/qwen_mcq_predictor.py`, `src/utils/data_io.py`,
  `src/utils/labels.py`, `src/utils/logging.py`, package `__init__.py` files needed for imports.

Level 2 optional/research closure:

- `scripts/tools/final_infer.py`, `scripts/final_infer.py`, `scripts/run_full_system.sh`,
  `scripts/run/*.sh`, `configs/production/default.json`, `configs/profiles/run_profiles.json`,
  `src/system/fastmcq_system.py`, `src/base/dynamic_base_predictor.py`, `src/layers/v12b_dynamic_layer.py`,
  `src/layers/v13_dynamic_layer.py`, `src/selector/system_candidate_selector.py`,
  formula/route/evidence/selector/API modules used by that graph.

Level 3 test-only examples:

- `tests/*`, `src/layers/v13_layer_registry.py` in current checkout, package init support files in
  subpackages with no direct runtime logic.

Level 4 documentation/historical:

- most retained `docs/*`, `assets/archi.png`, old audit references, deleted-doc references in
  comments/audit docs.

Level 5 definitely-unused candidates:

- Count: 0 high-confidence candidates. No deletion recommendation is safe from this audit because
  many candidates are executable roots, legacy scripts, current docs assets, or dynamically referenced.

Level 6 uncertain / do-not-touch candidates:

Count: 9 groups.

1. `run.py`: broken, but still called by legacy shell wrappers; owner decision needed.
2. `scripts/docker_entrypoint.sh`: not used by current Dockerfile, but executable legacy entrypoint.
3. `scripts/docker_entrypoint_v11.sh`: not used by current Dockerfile, but executable legacy entrypoint.
4. `Dockerfile.api`: ignored local secret-bearing dev image; optional owner-maintained artifact.
5. `configs/adaptive_reasoning.yaml`: no BTC consumer, legacy overlay semantics.
6. `configs/verifier_selective.yaml`: no BTC consumer, legacy overlay semantics.
7. `requirements-llm.txt`: optional local solvers; no Docker use.
8. `requirements-openrouter.txt`: optional OpenRouter solver; no Docker use.
9. `scripts/legacy/**`: many files are test/manual runbook roots and dynamically import each other;
   they are not BTC default but not safe to declare unused solely by import count.

## 15. Missing-file and dangling-reference list

Static path scan found 91 distinct missing path-like references. This includes many intended output
destinations and legacy scratch/runbook paths; it is not equivalent to 91 production bugs.

Actionable/current stale missing inputs or docs/configs:

| Missing target | Live refs | Impact |
|---|---|---|
| `output/pred_v13_multilayer_candidate_api30_from_v12b.csv` | `configs/production/default.json`, `tests/integration/test_btc_short_2l31b.py`, `test_final_package_2l31a.py`, `test_run_profiles_2l38c.py`, `test_v13_dynamic_integration_2l37a.py` | Breaks public_replay/frozen legacy tests |
| `output/pred_v12b_permutation_candidate_api30.csv` | `configs/production/default.json` | Missing previous-best metadata artifact |
| `output/pred_v11_independent_rerun1.csv` | configs/tests/legacy V12/V13 builders | Breaks legacy candidate tests |
| `output/pred_v10_full_production_user_run.csv` | configs/tests/legacy scripts | Breaks V10/frozen tests |
| `output/pred_v8_clean_generalized_from_v7.csv` | configs/tests/legacy production pipeline protection list | Missing historical artifact |
| `experiments/best_candidate_manifest.json` | `scripts/legacy/audit/audit_production_candidate.py`, `test_final_package_2l31a.py` | Breaks legacy final-package audit/test |
| `experiments/leaderboard_log.csv` | `docs/DATASET_PROFILE.md`, legacy scripts | Documentation/runbook stale |
| `docs/ARCHITECTURE.md` | `configs/default.yaml`, `src/layers/adaptive_agent_solver.py`, `src/layers/question_router.py` comments | Stale comments only |
| `docs/METHOD.md` | `src/__init__.py`, audit docs | Stale comment/doc reference |
| `configs/production/noapi.json` | audit doc only | Historical |
| `configs/run_profiles.json` | wrapper comments | Stale comment; actual file is `configs/profiles/run_profiles.json` |

BTC default closure has zero missing-file references in current source.

## 16. Current HEAD vs accepted commit `d504296`

Commits since `d504296`:

- `dd21ed8 clean legacy configs and consolidate documentation`
- `87d5d71 remove obsolete experiment metadata`

Focused BTC closure diff:

```text
git diff d504296 -- Dockerfile inference.sh predict.py src/local_model src/utils scripts/download_local_model.py
# empty
```

Therefore no file on the accepted BTC build/runtime import closure was deleted, modified, or made
unreachable since `d504296`.

Broader diff summary from `d504296` to current HEAD:

- Documentation cleanup: deleted many old docs/audits/archive files; added `docs/FINAL_SYSTEM.md`,
  `AUDIT_53`, `AUDIT_54`; README now points to `docs/FINAL_SYSTEM.md`.
- Config cleanup: deleted `configs/production/noapi.json`; profiles adjusted.
- Artifact cleanup: deleted `experiments/*` and five frozen `output/pred_v*.csv` files.
- Test changes: `test_production_auto_budget_2l44e.py`, `test_run_profiles_2l38c.py` changed.
- Production runtime change: none in accepted Docker default closure.
- Possible impact requiring attention: legacy/frozen tests and public_replay/frozen modes now fail due
  deleted artifacts.

No `.dockerignore`, `.gitignore`, `Dockerfile.api`, public test, assets, data, or models tracked diff
was found against `d504296` for the checked paths.

## 17. Final conclusions: required questions

### Current submitted system

1. What exactly does BTC run? Docker `CMD ["bash","inference.sh"]`, then `python predict.py "$@"`,
   default offline local branch, with host input mounted at `/code/private_test.json`.
2. What model is used? `Qwen/Qwen3-4B-Instruct-2507`, baked at `/models/qwen3-4b-instruct-2507`.
3. Default generation parameters? `max_new_tokens=64`, `do_sample=False`, `num_beams=1`,
   `device=auto`, CUDA `bfloat16` else `float32`, `trust_remote_code=True`.
4. Input paths supported? `--input`, `$INPUT_FILE`, `/code/private_test.json`,
   `/code/public_test.json`, `/app/data/private_test.json`, `/app/data/public_test.json`,
   `/data/private_test.json`, `/data/public_test.json`, `/data/private_test.csv`,
   `/data/public_test.csv`.
5. Outputs written? `/code/submission.csv`, `/code/submission_time.csv`, optional `--output`,
   `$OUTPUT_FILE`, and `/output/pred.csv` mirror.
6. Sample failure behavior? Per-sample fallback to first valid label; model-load/input-load failure
   can abort before outputs.
7. Does BTC default execute V12B/V13? No.
8. Does BTC default use 1/8? No.
9. Does BTC default require OpenRouter? No.

### Optional research system

10. Does Base -> V12B -> V13 -> selector still exist? Yes, in `scripts/tools/final_infer.py` plus
    `src/system/fastmcq_system.py`, `src/base/dynamic_base_predictor.py`, `src/layers/v12b_dynamic_layer.py`,
    `src/layers/v13_dynamic_layer.py`, and `src/selector/system_candidate_selector.py`.
11. Exact command activating it? `python predict.py --legacy-dynamic-full --input <file>
    --submission <out> [--no-api]`, or `bash scripts/run_full_system.sh <test_file> --no-api`.
12. Does that command currently work from checkout? The no-API dynamic path works and was exercised by
    tests/wrappers; public_replay/frozen modes do not work without deleted frozen CSVs.
13. What without API key? `production_full_system_noapi`: base formula/fallback answers all qids;
    V12B targets are selected but skipped; V13 model layers are skipped, deterministic arithmetic may
    apply; no OpenRouter calls.
14. Which modules/scripts comprise it? See optional graph in section 6 and inventory sections 9-10.
15. Where is 1/8 applied? `scripts/tools/final_infer.py:284-302` resolving `"auto"` max qids for each
    V12B/V13 layer.

### Repository health

16. Are there live references to missing files? Yes: 91 distinct missing path-like refs in static scan;
    zero in BTC default closure; stale active failures center on 5 frozen output CSVs and 1 experiment
    manifest.
17. Does complete pytest suite pass? No: 772 passed, 18 failed.
18. Production-critical versus legacy/artifact failures? Production-critical subset passed; all full
    failures are legacy/frozen-artifact/stale-test related.
19. Which code is definitely used? Dockerfile/inference/predict/local_model/utils listed in Level 1.
20. Which code is optional/research-only? Dynamic full system, API clients, V12B/V13, selectors,
    legacy wrappers/profiles.
21. Which code is test-only? Tests and some registry/package support like `v13_layer_registry.py`.
22. Which code appears unused? No high-confidence Level-5 unused candidates.
23. Which files should not be touched because uncertain? The 9 groups listed in Level 6.
24. Is current repo safe to reproduce the accepted BTC run? Yes, for source-level accepted runtime:
    the accepted Docker build/runtime closure is unchanged from `d504296`. Real reproduction still
    requires building Docker and downloading the Qwen weights, which this audit did not do.

## 18. Validation restrictions and explicit statements

- No tracked repository file except this new audit was modified.
- No production, test, script, config, documentation, dataset, or tracked artifact file was modified.
- No file was deleted, moved, restored, or renamed.
- No test was changed, skipped, or xfailed.
- No config or README command was changed.
- No package was installed.
- No model was downloaded.
- No API or network request was made.
- No Docker image was built or pushed.
- No real model inference was run.
- No commit was created automatically.

Allowed validation did create/update ignored local generated files (`__pycache__`, `.pytest_cache`,
and `scratch/` outputs). They were not cleaned up because this audit is read-only and the task
explicitly says not to remove generated caches.

## 19. Recommended next action

Make an owner decision in a separate cleanup task: either update/remove the stale legacy/frozen tests
and public_replay/frozen artifact references, or intentionally restore the frozen artifacts and
manifest if those workflows must remain executable. Do not change the accepted BTC Docker default
closure unless a new BTC validation run is planned.

## 20. Final git status after audit

Actual `git status --short --branch` after creating this file:

```text
## main...origin/main
?? docs/audits/AUDIT_59_system_reality_and_dependency_review.md
```

Ignored generated state also exists (`.env`, `Dockerfile.api`, caches, `models/`, `output/pred*.csv`,
and `scratch/` from validation), but it is not part of tracked status.
