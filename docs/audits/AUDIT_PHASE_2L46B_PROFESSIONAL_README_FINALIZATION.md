# Audit — Phase 2L.46B: Professional GitHub README Finalization

**Date:** 2026-06-25  **Branch:** `main`  **Base commit:** `891db48`  **Status:** docs +
test-reference cleanup (no commit, no API, no core-logic change)

Rewrote `README.md` into a concise, professional, GitHub-facing submission README; removed the
now-redundant `FINAL_RUN.md` and repointed the few tests that referenced it.

## README sections created / changed

`README.md` was fully rewritten to a clean structure:
- **FASTMCQ Agent** — one-paragraph description (Vietnamese MCQ system; Docker-delivered; reads
  `/data`, writes `/output/pred.csv`).
- **Official Docker Submission** — table of the three image tags.
- **Quick Start** — `mkdir -p data output` + the official `docker run … :latest` command.
- **Input and Output Contract** — input priority list, output path, `qid,answer`, label space.
- **Runtime Modes** — `latest`/`api-baked` vs `no-key`; runtime-key example; secret-safety notes.
- **System Overview** — base predictor (all qids) → selective V12B → selective V13 → conservative
  selector; `auto = ceil(input_count/8)` (min 1); selector writes all qids.
- **Repository Structure** — short tree.
- **Reproducibility and Validation** — the three validation commands.
- **Documentation** — links to `DOCKER_SUBMISSION.md`, `docs/METHOD.md`, `docs/audits/`.
- **Notes** — HackAIthon/BTC note; no invented license.

Removed from the README: the Phase-1 `run.py` baseline walkthrough, the legacy diagnostic command
list, the local-LLM-solver section, the changelog-ish "Final submission" prose, and the
`FINAL_RUN.md` link.

### Accuracy note on the answer label space
The spec template suggested "`answer` must be one of `A/B/C/D`". The actual system validates a
label **sized to each question's choice count** (the public test has up to 11 choices → up to
`K`). To avoid an inaccurate/misleading contract, the README states answers are
`A`, `B`, `C`, `D`, … sized to the choices (most are 4-choice `A`–`D`; up to `K` for wider
questions). No qids/answers/`463` are hardcoded; `463` appears only as a worked example of the
`ceil(N/8)` formula.

## FINAL_RUN.md removed

`git rm FINAL_RUN.md` (it duplicated Docker/run/validation content already in
`DOCKER_SUBMISSION.md` + the new README, and the spec said not to promote it). The single
reference inside `DOCKER_SUBMISSION.md` ("See `FINAL_RUN.md`.") was removed.

Three collected tests referenced `FINAL_RUN.md` — repointed (no inference logic touched):
- `tests/integration/test_btc_short_2l31b.py::test_docs_contain_dynamic_and_replay_commands` →
  reads `DOCKER_SUBMISSION.md` (contains `scripts/final_infer.py --input`, `--mode public_replay`,
  `dynamic_full`).
- `tests/integration/test_btc_noarg_2l32b.py::test_docs_contain_btc_noarg_docker_command` →
  reads `DOCKER_SUBMISSION.md` only (contains `docker run --rm`, `-v "$PWD/data:/data"`,
  `fastmcq-final`).
- `tests/integration/test_run_profiles_2l38c.py::test_docs_mention_public_api50` → now checks only
  `DOCKER_SUBMISSION.md` for `run_public_api50.sh` (README no longer lists legacy diagnostics).

No remaining `FINAL_RUN` references in tests/`src`/`scripts`/committed docs (only historical
mentions inside `docs/audits/`, which are immutable records).

## Docs linked from README

`DOCKER_SUBMISSION.md`, `docs/METHOD.md`, `docs/audits/`.

## Docker command shown in README

```bash
docker run --rm -v "$PWD/data:/data:ro" -v "$PWD/output:/output" vquclinh/fastmcq-agent:latest
```

## Input/output contract documented

Input priority `/data/private_test.csv` → `/data/public_test.csv` → `.json` equivalents (with
`INPUT_FILE`/`--input` override); output `/output/pred.csv`; format `qid,answer`; label sized to
choices. ✓

## Runtime modes documented

`latest`/`api-baked` (API-enabled, key in image layer), `no-key` (offline default; runtime
`-e OPENROUTER_API_KEY=...`), and the secret-safety notes (`.env` and `Dockerfile.api`
git-ignored; no key in GitHub). ✓

## Method / system overview documented

README "System Overview" summarizes base → V12B → V13 → selector and the `auto = ceil(N/8)`
budget; `docs/METHOD.md` carries the full description (added in 2L.46A). No unsupported
private-test claims — only the observed public checkpoints 78.40 → 78.83 → 79.7. ✓

## Secret-safety proof

- `git check-ignore -v .env` → `.gitignore:15:.env`; `git check-ignore -v Dockerfile.api` →
  `.gitignore:21:Dockerfile.api` (both ignored).
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$)'` → **none tracked**.
- `git grep -nE 'sk-or-|OPENROUTER_API_KEY=.{20,}|api[_-]?key=.{20,}' -- . ':!docs/audits/*'` →
  matches are **all non-secrets**: placeholders (`...`), shell-variable references
  `"$OPENROUTER_API_KEY"` (README/DOCKER_SUBMISSION — explicitly allowed), archive `sk-or-...`
  placeholders, a false positive (`--require-low-ri`**`sk-or`**`-reviewed`), and test fixtures
  (`dummy-key-not-real`; `sk-or-SECRETVALUE123` in a test that asserts it is **redacted**). **No
  real key in any tracked file.**

## Validation results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed** (the 3 repointed doc tests pass against `DOCKER_SUBMISSION.md`; the
  README rewrite broke nothing)
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**

## Confirmations

- **No API calls** — docs/test-reference edits only.
- **No core inference logic changed** — `src/` untouched; the only test edits repoint doc-content
  assertions; model policy unchanged.
- **No secret committed**; `.env` / `Dockerfile.api` remain git-ignored/local-only.
- **Not committed.**

## Git status (this phase)

```
 M README.md
 M DOCKER_SUBMISSION.md          (removed the FINAL_RUN.md reference)
 D FINAL_RUN.md                  (git rm)
 M tests/integration/test_btc_short_2l31b.py
 M tests/integration/test_btc_noarg_2l32b.py
 M tests/integration/test_run_profiles_2l38c.py
?? docs/audits/AUDIT_PHASE_2L46B_PROFESSIONAL_README_FINALIZATION.md
```
(Plus the still-uncommitted 2L.43E–G / 2L.44D–E / 2L.45A–C / 2L.46A changes.) Nothing committed.

## Remaining final checklist

1. **Rebuild + tag + push images** (current `requirements.txt` includes the 2L.45C `httpx` fix):
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
   Use a disposable/limited-credit key in the baked image; revoke after the contest.
2. **Commit** the accumulated uncommitted phases — review `git status`; never `git add -f`
   `.env` or `Dockerfile.api`.
3. Optionally run one budgeted real-API check on a tiny input before the final push (not done
   here — no API this phase).
