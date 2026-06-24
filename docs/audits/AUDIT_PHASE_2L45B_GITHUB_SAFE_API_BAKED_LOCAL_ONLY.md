# Audit — Phase 2L.45B: Make API-Baked Docker Variant Local-Only and GitHub-Safe

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** Docker
packaging / repo-hygiene only (no commit, no real API)

Ensures GitHub ships only the normal safe Docker path; the optional `api-baked` variant stays a
local-only, git-ignored convenience. No inference logic or model policy touched.

## What changed from 2L.45A

- **`.gitignore`** — added `Dockerfile.api` and `Dockerfile.api.local` (local-only, never
  committed). `Dockerfile.api` is now ignored (was previously `?? Dockerfile.api`).
- **`DOCKER_SUBMISSION.md`** — the "two image variants" / `:api-baked` build section was
  **removed** from the committed docs. The committed doc now presents **only** the safe
  `vquclinh/fastmcq-agent:no-key` build/run, plus runtime key injection
  (`docker run -e OPENROUTER_API_KEY=...`). A short note states the secret-bearing `:api-baked`
  image is **local-only and not part of the GitHub repo** (its Dockerfile is git-ignored).
- `Dockerfile.api` itself (from 2L.45A) is **kept on disk** so the user can still build the
  api-baked image locally — it is just no longer shown by git.

## Dockerfile.api: ignored / local-only

- `git ls-files Dockerfile.api` → empty (not tracked).
- `git status --short` → does **not** list `Dockerfile.api` (ignored).
- `git check-ignore -v Dockerfile.api` → `.gitignore:21:Dockerfile.api`.
- File still present on disk → local build ability preserved.

## Committed Docker path is GitHub-safe

The committed Docker surface is exactly:
```
Dockerfile
scripts/docker_entrypoint_v11.sh
DOCKER_SUBMISSION.md
README.md
```
`DOCKER_SUBMISSION.md` / `README.md` present only the normal safe image (`:no-key`) and runtime
env-var support; no API-baked build instructions, no secrets. (The historical 2L.45A audit under
`docs/audits/` still describes the api-baked build for the record — audits carry no real key and
are excluded from the staged-secret scan.)

## `.gitignore` / `.dockerignore` status

- `.gitignore`: `.env`, `.env.*` (keep `!.env.example`), **`Dockerfile.api`**,
  **`Dockerfile.api.local`**, `models/`, `.hf-cache/`, etc.
- `.dockerignore`: `.env`, `.env.*`, `*.key`, `*.pem`, `secrets/`, `**/api_key*`, `scratch/`,
  `data/`, `output/pred.csv`, `.venv/`, `.git/`, `__pycache__/`, `*.pyc`, `*.log`, plus the
  `docker_*` smoke/output dirs (from 2L.45A).

## Secret-safety proofs (no secret printed)

- `git check-ignore -v .env` → `.gitignore:15:.env` (ignored).
- `git check-ignore -v Dockerfile.api` → `.gitignore:21:Dockerfile.api` (ignored).
- `git add -A` then `git diff --cached --name-only | grep -E '(^\.env$|Dockerfile\.api$|…)'`
  → **no matches** (no `.env`, `Dockerfile.api`, scratch/data/runtime outputs staged).
- `git diff --cached -- . ':!docs/audits/*' | grep -Ei 'sk-or-|OPENROUTER_API_KEY=.{20,}|…'`
  → **no matches** (no key-like value staged).
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$)'` → **no output**
  (none tracked).
- The index was reset (`git reset`) after the checks — nothing left staged; **not committed**.
- Local `Dockerfile.api` real-key scan (`grep -nE 'sk-or-|OPENROUTER_API_KEY=[^$]…'`) → only the
  `ARG OPENROUTER_API_KEY` / `ENV OPENROUTER_API_KEY=${OPENROUTER_API_KEY}` placeholders; **no
  real key**.

## Validations run / results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed**
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**
- `docker build -t vquclinh/fastmcq-agent:no-key-test .` → **built OK** (normal safe image only;
  `Dockerfile.api` not built this phase)

### No-key Docker smoke
```
docker run --rm -v "$PWD/docker_smoke_data:/data:ro" -v "$PWD/docker_smoke_output:/output" \
  vquclinh/fastmcq-agent:no-key-test
  [entrypoint] profile: production_full_system_noapi ; api: off
  [FASTMCQ] input_count=2 ... output_written path=/output/pred.csv ; status: PASS
  docker_smoke_output/pred.csv:
    qid,answer
    docker_smoke_001,B
    docker_smoke_002,A
```
- `/output/pred.csv` created; header exactly `qid,answer`; input qids preserved; **no API call**
  (no-api profile). Test image + smoke dirs removed afterward.

## Confirmations

- **No core code changed** — `src/` untouched; model policy unchanged (audit PASS).
- **No real API key anywhere** — not in `Dockerfile.api`, docs, `.gitignore`, or staged/tracked
  files; `.env` ignored by both git and Docker.
- **`.env` not committed**; **`Dockerfile.api` not committed** (ignored, local-only).
- **No API calls**; no unrelated containers/volumes touched; no prune.
- **Docker `/data` → `/output/pred.csv` preserved** — no-key smoke wrote `/output/pred.csv`.
- **Not committed.**

## Exact local-only build commands (for the user, after commit)

```bash
# Normal safe image (committed Dockerfile; no secret) — push this to GitHub-backed builds:
docker build -t vquclinh/fastmcq-agent:no-key .
docker push vquclinh/fastmcq-agent:no-key

# OPTIONAL local API-baked image (uses the git-ignored Dockerfile.api; key only via --build-arg):
set -a; source .env; set +a          # loads OPENROUTER_API_KEY into the shell only
docker build \
  -f Dockerfile.api \
  --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -t vquclinh/fastmcq-agent:api-baked .
# (push only if you accept the secret-in-image risk; use a disposable key and revoke it after.)
```

## Git status (this phase)

```
 M .dockerignore        (smoke/output dirs — from 2L.45A)
 M .gitignore           (Dockerfile.api, Dockerfile.api.local — this phase)
 M DOCKER_SUBMISSION.md (api-baked section removed; safe path only — this phase)
?? docs/audits/AUDIT_PHASE_2L45A_OPTIONAL_API_BAKED_DOCKER_VARIANT.md
?? docs/audits/AUDIT_PHASE_2L45B_GITHUB_SAFE_API_BAKED_LOCAL_ONLY.md
# Dockerfile.api is present on disk but git-ignored (NOT shown by git status).
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E changes.) Nothing committed.

## Remaining risks

- `Dockerfile.api` being git-ignored relies on `.gitignore`; a future `git add -f Dockerfile.api`
  would override it. Documented as local-only; do not force-add.
- The `:api-baked` image (if built) is still secret-bearing at the image layer — only push it
  with a disposable key, and never to a public registry.
