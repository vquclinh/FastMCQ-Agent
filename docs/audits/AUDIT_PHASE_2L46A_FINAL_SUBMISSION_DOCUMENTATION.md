# Audit — Phase 2L.46A: Final Submission Documentation Audit

**Date:** 2026-06-25  **Branch:** `main`  **Base commit:** `891db48`  **Status:** docs only
(no commit, no API, no core-logic change)

Documentation-only pass to finalize the submission story (Docker Hub `:latest`/`:api-baked`),
keep GitHub secret-safe, and ensure `docs/METHOD.md` explains the production strategy.

## Docs inspected / changed

Inspected: `README.md`, `DOCKER_SUBMISSION.md`, `FINAL_RUN.md`, `docs/METHOD.md`, `.gitignore`,
`.dockerignore`.

Changed:
- **`README.md`** — added an **"Official Docker Hub submission image"** subsection (below).
- **`DOCKER_SUBMISSION.md`** — added an **"Official submission image (Docker Hub)"** section
  documenting `:latest` / `:api-baked`, the run command, and that the submitted image may contain
  the contest key (never in GitHub).
- **`docs/METHOD.md`** — appended a **"Final production architecture — the dynamic full system"**
  section (base predictor → V12B → V13 → selector, `auto = ceil(N/8)` budget, allowed-model
  policy, Docker `/data` → `/output/pred.csv`).

`FINAL_RUN.md`, `.gitignore`, `.dockerignore` already correct → not modified.

## README final Docker command (added)

```bash
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/output:/output" vquclinh/fastmcq-agent:latest
```
The README section states: image `vquclinh/fastmcq-agent:latest` (≡ `:api-baked`); input
`/data/private_test.csv` first, fallback `/data/public_test.csv` (then `.json`); output
`/output/pred.csv` (`qid,answer`); default layer budget `auto = ceil(input_count/8)`, min 1; and
that the **base predictor processes all input qids and the selector writes all qids** (the budget
only limits how many qids V12B/V13 may revise).

## Docker Hub image / tag documented

- `vquclinh/fastmcq-agent:latest` → intended to point at the `:api-baked` image (contest key
  baked in, for BTC convenience; API `production_full_system` profile).
- `vquclinh/fastmcq-agent:api-baked` → explicit equivalent tag.
- `vquclinh/fastmcq-agent:no-key` → safe image; offline by default, accepts a runtime key via
  `-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`.
- Docs make explicit: the baked key lives **only inside the Docker Hub image layer, never in
  GitHub** (`Dockerfile.api` git-ignored, `.env` never committed); use a disposable key and
  revoke after the contest.

## Method document status

`docs/METHOD.md` **exists** (not created) and now documents the full production strategy: base
predictor (all-qid coverage), V12B option-permutation debiaser, V13 multi-layer reasoning
(programmatic / content-first / least-to-most), unified conservative selector, the
`auto = ceil(N/8)` selective-API budget (min 1, never limits output coverage), the allowed-model
policy (`model_policy.py`, ≤9B), and the Docker `/data` → `/output/pred.csv` contract. Only the
observed public-leaderboard checkpoints (78.40 → 78.83 → 79.7) are claimed; no unverified private
claims, no secrets.

## Secret-safety proof

- `git check-ignore -v .env` → `.gitignore:15:.env` (ignored).
- `git check-ignore -v Dockerfile.api` → `.gitignore:21:Dockerfile.api` (ignored).
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$)'` → **none tracked**.
- `git grep -nE 'sk-or-|OPENROUTER_API_KEY=.{20,}|api[_-]?key=.{20,}' -- . ':!docs/audits/*'` →
  matches are **all non-secrets**, verified line-by-line:
  - placeholders `--build-arg OPENROUTER_API_KEY=...` / `-e OPENROUTER_API_KEY=...` (`.gitignore`,
    `README.md`, `requirements.txt`);
  - shell-variable references `"$OPENROUTER_API_KEY"` (`DOCKER_SUBMISSION.md`);
  - `docs/archive/OPENROUTER_ROUND1_STRATEGY.md` — `sk-or-...` ellipsis placeholders (how to set
    the env var / .env), not a real key;
  - false positive: `--require-low-ri`**`sk-or`**`-reviewed` in a legacy script flag name;
  - test fixtures `dummy-key-not-real` and `sk-or-SECRETVALUE123` (the latter in a test that
    **asserts the key is redacted** from output).
  - **No real OpenRouter key is present in any tracked file.**
- `git status` does not show `.env` or `Dockerfile.api`.

## Validation results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed**
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**

## Confirmations

- **No API calls** — docs-only phase; no Docker run, no model call.
- **No core inference logic changed** — only `README.md`, `DOCKER_SUBMISSION.md`,
  `docs/METHOD.md`; `src/` untouched; model policy unchanged (audit PASS).
- **No qid/answer hardcoding; no `463`** in the doc edits (the `auto` budget is described by the
  `ceil(N/8)` formula; `463` appears only as a worked *example* of the formula's output, never as
  a hardcoded cap).
- **Docker `/data` → `/output/pred.csv` documented** in README, DOCKER_SUBMISSION.md, and
  METHOD.md.
- **No secret committed**; `.env` and `Dockerfile.api` remain git-ignored/local-only.
- **Not committed.**

## Git status (this phase)

```
 M README.md
 M DOCKER_SUBMISSION.md
 M docs/METHOD.md
?? docs/audits/AUDIT_PHASE_2L46A_FINAL_SUBMISSION_DOCUMENTATION.md
# .env and Dockerfile.api present on disk but git-ignored (NOT shown by git status).
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E / 2L.45A–C changes.) Nothing committed.

## Remaining submission checklist

1. **Rebuild images from current `requirements.txt`** (now includes `httpx`, fixed in 2L.45C):
   ```bash
   set -a; source .env; set +a
   docker build -t vquclinh/fastmcq-agent:no-key .
   docker build -f Dockerfile.api --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
     -t vquclinh/fastmcq-agent:api-baked .
   docker tag vquclinh/fastmcq-agent:api-baked vquclinh/fastmcq-agent:latest
   ```
2. **Push** the intended submission tag(s): `:latest` (= api-baked) and optionally `:no-key`.
   Use a **disposable/limited-credit** key in the baked image; revoke after the contest.
3. **Commit** the accumulated uncommitted phases (2L.43E–G repo reorg, 2L.44D–E I/O contract,
   2L.45A–C Docker, 2L.46A docs) — review `git status` first; never `git add -f Dockerfile.api`
   or `.env`.
4. Optionally run one budgeted real-API check on a tiny input to confirm live V12B/V13 before the
   final push (not done here — no API this phase).
