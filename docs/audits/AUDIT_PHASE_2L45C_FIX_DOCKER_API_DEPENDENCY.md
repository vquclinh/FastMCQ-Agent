# Audit — Phase 2L.45C: Fix Docker API-Baked Runtime Dependency

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** dependency /
packaging fix (no commit, no real API)

## Root cause

The `:api-baked` Docker image correctly detected the baked key and selected
`production_full_system` (api: on), but failed during V12B API execution with:
```
RuntimeError: chat failed after 3 attempts: No module named 'httpx'
```
`src/api/openrouter_client.py::_http_chat` does `import httpx` **lazily** (line 200) and uses
`httpx.Client(...)` (line 208) as the only real-HTTP path — there is no stdlib fallback. `httpx`
was **not** in `requirements.txt`, so the Docker image (which `pip install -r requirements.txt`)
lacked it. The offline no-api path never imports `httpx`, so `:no-key` and all local tests (which
don't make real calls) were unaffected — the gap only surfaced on a real API run inside Docker.

## Files changed

- **`requirements.txt`** — added `httpx>=0.27` (with a comment explaining it is the runtime HTTP
  client for the OpenRouter/selective API path, imported lazily, only used with an API key).

No other files changed. **No core inference logic touched** — `openrouter_client.py` already
imported and used `httpx`; this phase only declares the dependency so it is installed in the
image.

## Dependency added

`httpx>=0.27` (local env has `httpx 0.28.1`; the image now installs `httpx 0.28.1`). Verified
present in both images:
- `:no-key` → `import httpx` → `0.28.1`
- `:api-baked-test` (dummy build) → `import httpx` → `0.28.1`

## Confirmations

- **No core inference behavior changed** — only `requirements.txt`; logic in `src/` untouched;
  model policy unchanged (audit PASS).
- **No secret committed** — `requirements.txt` contains no key (the only `OPENROUTER_API_KEY`
  text is the placeholder `-e OPENROUTER_API_KEY=...` in a comment). `.env` not staged/committed.
- **`Dockerfile.api` remains ignored / local-only**:
  - `git check-ignore -v Dockerfile.api` → `.gitignore:21:Dockerfile.api`
  - `git ls-files Dockerfile.api` → empty (not tracked); not shown by `git status`.
- **No API calls** — the dummy-key image was built only (not run); the no-key smoke is offline.
- **No unrelated containers/volumes touched; no prune.**

## Validation results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed**
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**
- `docker build -t vquclinh/fastmcq-agent:no-key .` → **built OK** (now installs `httpx`)

### No-key Docker smoke
```
docker run --rm -v "$PWD/docker_smoke_data:/data:ro" -v "$PWD/docker_smoke_output:/output" \
  vquclinh/fastmcq-agent:no-key
  [entrypoint] profile: production_full_system_noapi ; api: off
  [FASTMCQ] input_count=2 ... output_written path=/output/pred.csv ; status: PASS
  docker_smoke_output/pred.csv:
    qid,answer
    docker_smoke_001,B
    docker_smoke_002,A
```
- `/output/pred.csv` created; header exactly `qid,answer`; input qids preserved; no API call.

### validate_submission (correct flags)
```
.venv/bin/python scripts/validate_submission.py \
  --input docker_smoke_data/private_test.csv \
  --submission docker_smoke_output/pred.csv
  -> RESULT: PASS — submission is valid.
```

### api-baked dummy build (build-proof only; NOT run)
```
docker build -f Dockerfile.api --build-arg OPENROUTER_API_KEY=dummy_key_for_build_test \
  -t vquclinh/fastmcq-agent:api-baked-test .
  -> built OK (Docker's expected SecretsUsedInArgOrEnv advisory for ARG/ENV)
  -> httpx present in the image (0.28.1)
```
The dummy-key image was **not run** (would attempt a real call and fail) and was removed after
the build check. Smoke dirs were removed.

## Docker Hub state note

A pre-existing local `vquclinh/fastmcq-agent:api-baked` image (built before this fix) lacks
`httpx` and will still hit the `No module named 'httpx'` error. It must be **rebuilt** from the
updated `requirements.txt` (command below) before use/push. (It was left untouched this phase — no
unrelated image was removed.)

## Git status (this phase)

```
 M requirements.txt
?? docs/audits/AUDIT_PHASE_2L45C_FIX_DOCKER_API_DEPENDENCY.md
# Dockerfile.api present on disk but git-ignored (NOT shown by git status).
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E / 2L.45A–B changes.) Nothing committed.

## Exact next command — rebuild the real api-baked image with the real limited key

```bash
DOCKERHUB_USER="vquclinh"; IMAGE="$DOCKERHUB_USER/fastmcq-agent"

# Load the REAL limited-credit/disposable key into the shell only (never into a committed file):
set -a; source .env; set +a

# Rebuild api-baked (now includes httpx) and, if you accept the secret-in-image risk, push:
docker build \
  -f Dockerfile.api \
  --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -t "${IMAGE}:api-baked" .
# docker push "${IMAGE}:api-baked"      # disposable key only; revoke after the contest

# (Safe image, no secret — rebuild/push anytime:)
docker build -t "${IMAGE}:no-key" .
# docker push "${IMAGE}:no-key"
```

## Remaining risks

- `httpx` pulls in `httpcore`/`anyio`/`certfi`/`sniffio` transitively — the image grows slightly
  (~6 MB compressed observed), acceptable.
- The `:api-baked` image remains secret-bearing at the layer level; rebuild with a disposable key
  and never push to a public registry.
