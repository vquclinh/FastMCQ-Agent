# Audit — Phase 2L.47E: BTC GitHub Repository Requirement Compliance Check

**Date:** 2026-06-27  
**Scope:** BTC GitHub repository requirements: README, library management, source organization,
`predict.py` / `inference.sh`, output contract, and per-sample timing.  
**Status:** PASS for static repository contract; PARTIAL only for final Docker/GPU checks that must
be run manually later.

## Summary

Final repository direction remains unchanged: offline local GPU inference with
`Qwen/Qwen3-4B-Instruct-2507` via Hugging Face Transformers. The final path uses no OpenRouter, no
external API, no runtime internet, and no API key. Docker build/run/push and real Qwen inference
were not run in this phase.

Changes made:

- Added explicit README sections: `Pipeline Flow`, `Data Processing`, `Resource Initialization`.
- Added output format examples to `README.md` and `DOCKER_SUBMISSION.md`.
- Exact-pinned direct dependencies in `requirements.txt` using versions present in the existing
  validated `.venv`.
- Added repository-compliance tests for root files, README sections, exact-pinned requirements,
  Dockerfile dependency source, `/app/data` support, default `/code` outputs, and
  `SUBMISSION_TIME_FILE` typo prevention.

## BTC 2.1 — README.md

**Status: PASS.**

Evidence:

- Final-submission section exists: `README.md:35-59` states offline local model, image name,
  `Qwen/Qwen3-4B-Instruct-2507`, no API/no internet, model build-time initialization, and no
  vector database/index.
- `Pipeline Flow`: `README.md:124-154`.
  - Text diagram covers input resolver, question/choice normalization, prompt construction,
    offline Qwen3-4B inference, label parser/fallback, and output files.
  - `README.md:126-128` states `inference.sh` launches `predict.py`, model is loaded once, and
    per-item timing is measured inside the loop.
- `Data Processing`: `README.md:156-188`.
  - Accepted JSON list and normalized fields: `README.md:158-160`.
  - Input priority including `/code/private_test.json` and `/app/data/private_test.json`:
    `README.md:162-170`.
  - Dynamic labels and deterministic fallback without hardcoded qids/answers:
    `README.md:172-176`.
  - Output examples: `README.md:178-188`.
- `Resource Initialization`: `README.md:190-208`.
  - No vector database, no external index, no retrieval database: `README.md:192`.
  - Model path `/models/qwen3-4b-instruct-2507`: `README.md:195-197`.
  - Runtime env `LOCAL_MODEL_PATH`, `TRANSFORMERS_OFFLINE`, `HF_HUB_OFFLINE`:
    `README.md:199-205`.
  - Designed for `--network none`: `README.md:207-208`.
- Official input/output contract remains documented:
  - `/code/private_test.json`: `README.md:212-216`.
  - `/app/data/private_test.json`: `README.md:216`.
  - `/code/submission.csv` and `/code/submission_time.csv`: `README.md:220-225`.

Changes made:

- Added the three BTC-required README sections and text diagram.
- Added explicit output examples.
- Kept OpenRouter/API only as legacy/dev context, not as the final path.

Remaining manual checks:

- None for README content. Docker/GPU/manual validation remains outside this phase.

## BTC 2.2 — Library Management / requirements.txt

**Status: PASS for static repository check; PARTIAL for final Docker install because Docker build
was intentionally not run.**

Evidence:

- `requirements.txt:3-5` states torch is not listed there because it is exact-pinned in the
  Dockerfile from the CUDA 12.8 PyTorch wheel index.
- Direct dependencies are exact-pinned:
  - `transformers==5.12.1`
  - `accelerate==1.14.0`
  - `safetensors==0.8.0`
  - `huggingface_hub==1.21.0`
  - `sentencepiece==0.2.1`
  - `PyYAML==6.0.3`
  - `httpx==0.28.1` (legacy/dev-only path import support)
  - `pytest==9.1.0`
- Torch is exact-pinned in Dockerfile, not requirements:
  - `Dockerfile:30` installs `torch==2.7.1` from `https://download.pytorch.org/whl/cu128`.
- Final Dockerfile installs only `requirements.txt`:
  - `Dockerfile:33-34` copies and installs `requirements.txt`.
  - Static grep found no `requirements-openrouter.txt` reference in `Dockerfile`, README,
    DOCKER_SUBMISSION, METHOD, or BTC compliance docs.
- `requirements-openrouter.txt` remains a tracked legacy/dev file, but final docs and Dockerfile
  do not require it.
- Existing `.venv` dependency consistency:
  - `.venv/bin/python -m pip check` -> `No broken requirements found.`

Changes made:

- Replaced lower-bound direct dependencies with exact pins from the existing `.venv`.
- Added test coverage that every non-comment dependency line uses `==`, torch is absent from
  `requirements.txt`, and Dockerfile uses `requirements.txt` rather than
  `requirements-openrouter.txt`.

Remaining manual checks:

- User must run the final Docker build later to validate the pinned dependency installation in
  the CUDA image.

## BTC 2.3 — Source Organization / predict.py / inference.sh / Output Contract

**Status: PASS.**

Root files:

- Required root files exist: `Dockerfile`, `predict.py`, `inference.sh`, `README.md`,
  `requirements.txt`.
- Test coverage: `tests/integration/test_btc_submission_contract_2l47a.py:229-231`.

`predict.py` entrypoint:

- Root-level official entrypoint: `predict.py:1-15`.
- Official input support: `_INPUT_CANDIDATES` includes `/code/private_test.json` at
  `predict.py:40-41`.
- BTC sample compatibility: `/app/data/private_test.json` at `predict.py:42`.
- Input env/CLI override: `predict.py:48-56`.
- Default official outputs:
  - CLI help documents `/code/submission.csv` and `/code/submission_time.csv`:
    `predict.py:141-144`.
  - `_resolve_out` writes under `/code` by default when available: `predict.py:74-82`.
- Docker output env overrides:
  - `SUBMISSION_FILE`: `predict.py:157`.
  - `SUBMISSION_TIME_FILE`: `predict.py:158-159`.
- Local model is loaded once outside the per-item loop:
  - `_build_predictor` constructs and loads the predictor at `predict.py:102-108`.
  - Called once before the loop at `predict.py:178-180`.
- Per-sample timing proof:
  - Loop over samples starts at `predict.py:182`.
  - `t0 = time.time()` before `predictor.predict_one(item)`: `predict.py:184-186`.
  - `dt = time.time() - t0` after single-sample inference/fallback: `predict.py:194`.
  - Per-sample `dt` appended to `times`: `predict.py:196`.
  - `submission_time.csv` writes each `(qid, answer, dt)`: `predict.py:205-209`.
  - This is not total-time divided by N.
- Exact headers:
  - `submission.csv`: `predict.py:201-204` writes `["qid", "answer"]`.
  - `submission_time.csv`: `predict.py:205-209` writes `["qid", "answer", "time"]`.
- Answer coercion/fallback:
  - `_coerce_label`: `predict.py:91-99`.
  - `_fallback_answer`: `predict.py:85-88`.
- No OpenRouter/API final path:
  - Default path is the `else` branch at `predict.py:176-197`.
  - Legacy API-capable dynamic path only runs with explicit `--legacy-dynamic-full`:
    `predict.py:150-153`, `predict.py:168-175`.

`inference.sh`:

- Root file exists, shebang present: `inference.sh:1`.
- Strict mode: `inference.sh:4` uses `set -euo pipefail`.
- End-to-end call with argument forwarding: `inference.sh:5` runs `python predict.py "$@"`.
- No API key or OpenRouter requirement.

Tests:

- Headers, qids, env overrides, no API default path, and per-sample timing are covered in
  `tests/integration/test_btc_submission_contract_2l47a.py:67-133`.
- Per-sample timing test uses a sleeping stub and asserts every row records the per-item delay:
  `tests/integration/test_btc_submission_contract_2l47a.py:88-103`.
- Input priority and `/app/data/private_test.json` support:
  `tests/integration/test_btc_submission_contract_2l47a.py:147-154`.
- Default `/code` outputs:
  `tests/integration/test_btc_submission_contract_2l47a.py:157-161`.
- README repository sections:
  `tests/integration/test_btc_submission_contract_2l47a.py:253-262`.
- Requirements/Dockerfile dependency contract:
  `tests/integration/test_btc_submission_contract_2l47a.py:265-280`.
- `SUBMISSION_TIME_FILE` typo guard:
  `tests/integration/test_btc_submission_contract_2l47a.py:283-286`.

Changes made:

- Added tests for repository/source contracts.
- Added output examples to docs.
- No changes were needed in `predict.py` or `inference.sh`; they already satisfied the final
  source contract.

Remaining manual checks:

- User must run final Docker build and GPU/offline tests later.

## Static Check Results

Safe validation run with `.venv/bin/python`:

```text
.venv/bin/python -m compileall -q src scripts tests predict.py
-> PASS

.venv/bin/python -m pytest -q
-> 790 passed in 20.01s

.venv/bin/python scripts/audit_model_policy.py
-> RESULT: PASS — only competition-allowed models referenced.

.venv/bin/python -m pip check
-> No broken requirements found.
```

Required grep checks:

```text
grep -RIn "SUBMISSION_FILE\|SUBMISSION_TIME_FILE" predict.py inference.sh src tests README.md DOCKER_SUBMISSION.md docs/BTC_SUBMISSION_COMPLIANCE.md
-> confirms env support in predict.py, tests, README, DOCKER_SUBMISSION, BTC compliance docs.

grep -RInE "Pipeline Flow|Data Processing|Resource Initialization|Vector Database|Indexing|submission_time|/code/private_test.json|/app/data/private_test.json" README.md DOCKER_SUBMISSION.md docs/METHOD.md docs/BTC_SUBMISSION_COMPLIANCE.md
-> confirms README sections, official/compat inputs, and submission_time documentation.

grep -nE "requirements.txt|requirements-openrouter|torch==|cu128" Dockerfile requirements.txt README.md DOCKER_SUBMISSION.md docs/METHOD.md docs/BTC_SUBMISSION_COMPLIANCE.md
-> confirms Dockerfile installs requirements.txt, torch==2.7.1 from cu128, and no final-doc
   reference to requirements-openrouter.
```

## Secret / Model-Weight Tracking Proof

Commands run:

```text
git check-ignore -v .env
-> .gitignore:15:.env .env

git check-ignore -v Dockerfile.api
-> .gitignore:21:Dockerfile.api Dockerfile.api

git check-ignore -v models
-> .gitignore:25:models/ models

git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$|^models/)'
-> no output
```

Conclusion: `.env`, `Dockerfile.api`, and `models/` are ignored/untracked for final submission.

## Remaining Steps

1. User must run final Docker build manually:
   `docker build -t vquclinh/fastmcq-agent:latest .`
2. User must run GPU test manually with `--gpus all`.
3. User must run network-none test manually with `--network none`.
4. User must push `vquclinh/fastmcq-agent:latest`.
5. User must commit the final repo after successful validation.

No commit was made in this phase.
