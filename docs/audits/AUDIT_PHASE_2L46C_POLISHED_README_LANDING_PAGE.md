# Audit — Phase 2L.46C: Polished Professional README Landing Page

**Date:** 2026-06-25  **Branch:** `main`  **Base commit:** `891db48`  **Status:** docs only
(no commit, no API, no core-logic change)

Rewrote `README.md` into a polished, GitHub-landing-page-style README. Documentation only — no
`src/`, Docker runtime, or model-policy changes.

## README structure after rewrite

Centered title block + tagline + badges → Table of Contents → 10 sections (anchors match the
TOC):
1. **Competition Context** — `## Competition Context`
2. **Official Docker Submission** — `## Official Docker Submission`
3. **Quick Start** — `## Quick Start`
4. **Input and Output Contract** — `## Input and Output Contract`
5. **System Architecture** — `## System Architecture`
6. **Runtime Modes** — `## Runtime Modes`
7. **Repository Structure** — `## Repository Structure`
8. **Validation** — `## Validation`
9. **Documentation** — `## Documentation`
10. **Security Notes** — `## Security Notes`

Plus a centered closing line. No phase history, changelog, raw logs, or audit minutiae.

## Badges added

`Python 3.11`, `Docker Hub`, `Status: Final Submission`, `Model Policy: PASS`,
`Output: qid,answer`. **No license badge** (no license file exists).

## Table of Contents added

Yes — 10 entries linking to the section anchors above.

## Docker command documented

```bash
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/output:/output" vquclinh/fastmcq-agent:latest
```
plus the three-tag table (`:latest` / `:api-baked` / `:no-key`) and the `output/pred.csv` result.

## Competition context documented

Vietnamese Student HackAIthon 2026 / BTC Docker-based evaluation; private-test round runs the
Docker Hub container; reads `/data`, writes `/output/pred.csv` (`qid,answer`). No private-test
performance claimed.

## System architecture documented

Text diagram `/data/private_test.csv → Base Predictor → V12B → V13 (programmatic / content-first /
least-to-most) → Final Selector → /output/pred.csv`, followed by: base predictor covers all qids;
V12B/V13 selective; default budget `auto = ceil(input_count / 8)` (min 1); selector writes all
qids.

## Runtime modes documented

Table: API-enabled (`OPENROUTER_API_KEY` present → `production_full_system`) vs no-key fallback
(no key → `production_full_system_noapi`, still writes `pred.csv`), plus the runtime-key example
for the `:no-key` image and the note that `latest` is intended API-enabled while `no-key` is the
safe/offline fallback.

## Repository structure documented

Concise annotated tree of `src/` subpackages (`system/ base/ layers/ api/ selector/ solvers/
evidence/ utils/`), `scripts/`, `configs/`, `tests/`, `docs/METHOD.md`, `DOCKER_SUBMISSION.md`,
`docs/audits/`.

## Security notes documented

No real key committed; `.env` ignored; `Dockerfile.api` local-only and git-ignored; the
API-enabled Docker Hub image may carry a **disposable** contest key in the image layer only;
revoke after evaluation.

### Label-space wording
Per the spec, the README says `answer` is an option label such as `A`/`B`/`C`/`D` and that the
parser supports wider choice sets when the input provides more options — aligned with BTC's
A/B/C/D expectation without misstating the system's actual capability. No qids/answers/`463`
hardcoded (`463` appears only as a worked example of the `ceil(N/8)` formula).

## FINAL_RUN reference cleanup result

`FINAL_RUN.md` was removed in 2L.46B and is **not** re-added. Repo scan
(`grep -RIn FINAL_RUN ... --exclude-dir=.git --exclude-dir=.venv`) outside `docs/audits/`:
**none**. Only historical audit references remain (immutable records).

## Secret-safety proof

- `git check-ignore -v .env` → ignored; `git check-ignore -v Dockerfile.api` → ignored.
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$)'` → **none tracked**.
- `git grep -nE 'sk-or-|OPENROUTER_API_KEY=.{20,}|api[_-]?key=.{20,}' -- . ':!docs/audits/*'` →
  README's only match is the shell **placeholder** `-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`
  (allowed); other repo matches are the pre-existing non-secrets (placeholders, archive
  `sk-or-...` examples, a `low-ri`**`sk-or`**`-reviewed` false positive, redaction test fixtures).
  **No real key in any tracked file.**

## Validation results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed** (README is no longer asserted by any test after 2L.46B; nothing
  broke)
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**

## Confirmations

- **No API calls** — README edit only.
- **No core inference logic changed** — `src/` untouched; Docker runtime unchanged; model policy
  unchanged.
- **No secret committed**; `.env` / `Dockerfile.api` remain git-ignored/local-only.
- **`Dockerfile.api` not promoted as a committed file**; **`FINAL_RUN.md` not re-added.**
- **Not committed.**

## Git status (this phase)

```
 M README.md
?? docs/audits/AUDIT_PHASE_2L46C_POLISHED_README_LANDING_PAGE.md
```
(`FINAL_RUN.md` remains staged-deleted from 2L.46B. Plus the still-uncommitted
2L.43E–G / 2L.44D–E / 2L.45A–C / 2L.46A–B changes.) Nothing committed.

## Remaining final checklist

1. **Rebuild + tag + push images** (requirements.txt already has the 2L.45C `httpx` fix):
   ```bash
   set -a; source .env; set +a
   docker build -t vquclinh/fastmcq-agent:no-key .
   docker build -f Dockerfile.api --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
     -t vquclinh/fastmcq-agent:api-baked .
   docker tag vquclinh/fastmcq-agent:api-baked vquclinh/fastmcq-agent:latest
   docker push vquclinh/fastmcq-agent:no-key
   docker push vquclinh/fastmcq-agent:api-baked
   docker push vquclinh/fastmcq-agent:latest
   ```
   Use a disposable/limited-credit key; revoke after the contest.
2. **Commit** the accumulated uncommitted phases — review `git status`; never `git add -f` `.env`
   or `Dockerfile.api`.
3. Optionally run one budgeted real-API check on a tiny input before the final push.
