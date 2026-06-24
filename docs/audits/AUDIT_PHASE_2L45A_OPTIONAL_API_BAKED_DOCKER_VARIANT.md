# Audit — Phase 2L.45A: Optional API-Baked Docker Image Variant

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** Docker
packaging only (no commit, no real API)

Adds an optional `:api-baked` Docker variant alongside the safe `:no-key` default, for the two
Docker Hub tags `vquclinh/fastmcq-agent:no-key` and `vquclinh/fastmcq-agent:api-baked`. No
inference logic or model policy was touched.

## Files changed

- **`Dockerfile.api`** — NEW. Mirrors the normal `Dockerfile`; adds `ARG OPENROUTER_API_KEY` +
  `ENV OPENROUTER_API_KEY=${OPENROUTER_API_KEY}`; same entrypoint. No real key in the file.
- **`.dockerignore`** — added local Docker scratch dirs (`docker_output/`, `docker_smoke_data/`,
  `docker_smoke_output/`, `docker_smoke_output_api/`, `docker_pull_output_no_key/`,
  `docker_pull_output_api/`). `.env`, `scratch/`, `data/`, `output/pred.csv`, `.venv/`, `.git/`,
  `__pycache__/`, `*.pyc`, `*.log` were already excluded.
- **`DOCKER_SUBMISSION.md`** — documented both variants (build + run) under
  `vquclinh/fastmcq-agent`, with the `:api-baked` secret warning.

## Part A — current Dockerfile inspected (unchanged)

- `Dockerfile` is the safe no-key default image (`FROM python:3.11-slim`, installs
  `requirements.txt`, `COPY . .`, `ENTRYPOINT ["bash", "scripts/docker_entrypoint_v11.sh"]`).
  No key baked or required.
- `scripts/docker_entrypoint_v11.sh` detects `OPENROUTER_API_KEY`: present → `production_full_system`
  (API); absent → `production_full_system_noapi` (offline). Output stays `/output/pred.csv`.
- **No behavior changed** — the api-baked variant simply makes the key present in the container,
  which the existing entrypoint logic already handles.

## Part B — `Dockerfile.api` added

Build-time key injection only:
```dockerfile
ARG OPENROUTER_API_KEY
ENV OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
```
The real key is supplied via `--build-arg` at build time and is **never** written into the file
or copied from `.env`. If built without the arg, the ENV is empty and the image behaves exactly
like `:no-key` (offline fallback). Same entrypoint as the normal Dockerfile.

## Part C — `.dockerignore` updates

Confirmed the build context excludes secrets and scratch: `.env`, `.env.*`, `*.key`, `*.pem`,
`secrets/`, `**/api_key*`, `scratch/`, `data/`, `output/pred.csv`, `.venv/`, `.git/`,
`__pycache__/`, `*.pyc`, `*.log`, plus the new `docker_*` smoke/output dirs. No source/config
needed at inference time was excluded.

## Part D — documentation

`DOCKER_SUBMISSION.md` now documents:
- `:no-key` build/run (safe default; supply the key at run time with `-e OPENROUTER_API_KEY=...`).
- `:api-baked` build (`-f Dockerfile.api --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`
  after `set -a; source .env; set +a`) and run.
- A ⚠️ warning: the `:api-baked` image **contains a secret**; use a limited-credit/disposable
  key, revoke it after the contest, do not publish publicly, and prefer `:no-key`.

## Part E — validations / build results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed**
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**
- `docker build -t vquclinh/fastmcq-agent:no-key-test .` → **built OK**
- `docker build -f Dockerfile.api --build-arg OPENROUTER_API_KEY=dummy_key_for_build_test
  -t vquclinh/fastmcq-agent:api-baked-test .` → **built OK** (Docker emitted the expected
  `SecretsUsedInArgOrEnv` advisory for ARG/ENV — that is the intended, documented trade-off; the
  api-baked image was **not run** with the dummy key).

### No-key Docker smoke
```
docker run --rm -v "$PWD/docker_smoke_data:/data:ro" -v "$PWD/docker_smoke_output:/output" \
  vquclinh/fastmcq-agent:no-key-test
  [entrypoint] profile: production_full_system_noapi ; api: off
  [FASTMCQ] input_count=2 ... v12b_max_qids=auto(1/2) v13_max_qids=auto(1/2)
  [FASTMCQ] output_written path=/output/pred.csv ; status: PASS
  docker_smoke_output/pred.csv:
    qid,answer
    docker_smoke_001,B
    docker_smoke_002,A
```
- `/output/pred.csv` created; header exactly `qid,answer`; input qids preserved
  (`docker_smoke_001`, `docker_smoke_002`); **no API called** (no-api profile).

### Image-env verification (variant difference)
- `:no-key-test` `Config.Env` → **no `OPENROUTER_API_KEY`** (safe).
- `:api-baked-test` `Config.Env` → `OPENROUTER_API_KEY=dummy_key_for_build_test` (mechanism
  proven; only the dummy build-test key, never a real key).
- Test images and smoke dirs were removed after validation.

## Confirmations

- **No real key committed** — `Dockerfile.api`, `.dockerignore`, docs, and this audit contain no
  real key (only the placeholder `--build-arg` form and the `dummy_key_for_build_test` used for
  build validation). `.env` is gitignored and excluded by `.dockerignore`.
- **`.env` excluded from the image context** — listed in `.dockerignore`; never `COPY`'d.
- **No core inference code changed** — `src/` untouched.
- **No model policy changed** — audit PASS.
- **Docker `/data` → `/output/pred.csv` preserved** — no-key smoke wrote `/output/pred.csv`;
  entrypoint and input/output handling unchanged.
- **No unrelated containers/volumes touched**; no prune.
- **Not committed.**

## ⚠️ Security note on `:api-baked`

The `:api-baked` image embeds `OPENROUTER_API_KEY` in an image-layer ENV — anyone with the image
can read it (`docker inspect` / `docker history`). Use a limited-credit/disposable key, revoke
after the contest, and do not publish the image. Prefer `:no-key` + runtime `-e OPENROUTER_API_KEY`.

## Exact next build commands for the real images

```bash
# Safe no-key image
docker build -t vquclinh/fastmcq-agent:no-key .

# Optional api-baked image (load the key into the shell only; never into a committed file)
set -a; source .env; set +a
docker build \
  -f Dockerfile.api \
  --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -t vquclinh/fastmcq-agent:api-baked .
```
(Then `docker push vquclinh/fastmcq-agent:no-key` and, if accepted, `:api-baked`.)

## Git status (this phase)

```
 M .dockerignore
 M DOCKER_SUBMISSION.md
?? Dockerfile.api
?? docs/audits/AUDIT_PHASE_2L45A_OPTIONAL_API_BAKED_DOCKER_VARIANT.md
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E changes.) Nothing committed.

## Remaining risks

- `:api-baked` is inherently secret-bearing (documented). The build emits Docker's
  `SecretsUsedInArgOrEnv` advisory — expected for this convenience variant.
- For zero secret exposure, build only `:no-key` and pass the key at run time.
