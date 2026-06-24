# Audit — Phase 2L.46D: Showcase Full System Architecture in README

**Date:** 2026-06-25  **Branch:** `main`  **Base commit:** `891db48`  **Status:** docs only
(no commit, no API, no core-logic change)

Enhanced the README **System Architecture** section so reviewers immediately see this is a
dynamic full-system reasoning agent (base prediction → selective V12B/V13 → conservative
selector), not a single-shot baseline. Documentation only.

## README architecture changes

Replaced the old ASCII pipeline with a richer, still-concise section containing four parts:

1. **High-level Mermaid diagram** (`flowchart TD`) — `/data → Input Loader → Base Predictor →
   Selective Router → V12B / V13 → Candidate Pool → Final Selector → /output/pred.csv`. (Base
   predictor and both layers feed the candidate pool; the selector merges.)
2. **Modules table** — 8 rows mapping each `src/` subpackage (`system/ base/ layers/ api/
   selector/ solvers/ evidence/ utils/`) to its role.
3. **Reasoning stages table** — Base Predictor (all qids) / V12B (`ceil(N/8)`) / V13
   (`ceil(N/8)`) / Final Selector (all qids), with purpose per stage.
4. **Design Principles** mini-list — all-qid coverage first, selective reasoning budget,
   permutation debiasing, conservative selection, Docker-first reproducibility.

Followed by the budget note (`auto = ceil(input_count / 8)`, min 1; limits selective calls only;
output always contains all qids) and a link to `docs/METHOD.md` for full detail. A one-line intro
sentence frames it as a "dynamic full-system reasoning agent, not a single-shot baseline."

### Diagram / table sections added
Mermaid flowchart + Modules table + Reasoning-stages table + Design Principles list.

### Module groups documented
Yes — the 8-row Modules table (one row per `src/` subpackage).

### Design principles documented
Yes — the 5-item Design Principles list.

## METHOD.md changes

**None.** `docs/METHOD.md` already carries the detailed module-oriented "Final production
architecture" section (added in 2L.46A): base predictor, V12B, V13 sub-strategies, selector, the
`auto = ceil(N/8)` budget, allowed-model policy, and the Docker `/data` → `/output/pred.csv`
contract. README stays the polished overview; METHOD remains the detailed reference — no
duplication added.

## Conciseness

No raw logs, phase names, audit history, TODOs, private-test claims, or key details beyond the
existing Security Notes section. README remains a 2–3 minute read; deep detail is delegated to
`docs/METHOD.md`.

## Secret-safety proof

- `git check-ignore -v .env` → ignored; `git check-ignore -v Dockerfile.api` → ignored.
- `git ls-files | grep -E '(^\.env$|Dockerfile\.api$|Dockerfile\.api\.local$)'` → **none tracked**.
- README key-like scan → only the shell **placeholder** `-e OPENROUTER_API_KEY="$OPENROUTER_API_KEY"`
  (allowed). No real key anywhere in tracked files (other repo matches are the pre-existing
  non-secrets documented in 2L.46A–C). `463` appears only as a `ceil(N/8)` worked example.

## Validation results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed** (no test asserts README content; nothing broke)
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**

## Confirmations

- **No API calls** — README edit only.
- **No core inference logic changed** — `src/` untouched; Docker runtime unchanged; model policy
  unchanged.
- **No secret committed**; `.env` / `Dockerfile.api` git-ignored/local-only.
- **`FINAL_RUN.md` not re-added** (no reference outside `docs/audits/`).
- **Not committed.**

## Git status (this phase)

```
 M README.md
?? docs/audits/AUDIT_PHASE_2L46D_SHOWCASE_SYSTEM_ARCHITECTURE_README.md
```
(`FINAL_RUN.md` remains staged-deleted from 2L.46B. Plus the still-uncommitted
2L.43E–G / 2L.44D–E / 2L.45A–C / 2L.46A–C changes.) Nothing committed.

## Remaining final checklist

1. **Verify Mermaid renders** on the GitHub repo page after push (GitHub renders ```` ```mermaid ````
   fenced blocks natively; no action needed unless the org disables it).
2. **Rebuild + tag + push images** (requirements.txt already has the 2L.45C `httpx` fix):
   ```bash
   set -a; source .env; set +a
   docker build -t vquclinh/fastmcq-agent:no-key .
   docker build -f Dockerfile.api --build-arg OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
     -t vquclinh/fastmcq-agent:api-baked .
   docker tag vquclinh/fastmcq-agent:api-baked vquclinh/fastmcq-agent:latest
   docker push vquclinh/fastmcq-agent:no-key vquclinh/fastmcq-agent:api-baked vquclinh/fastmcq-agent:latest
   ```
   Use a disposable/limited-credit key; revoke after the contest.
3. **Commit** the accumulated uncommitted phases — review `git status`; never `git add -f` `.env`
   or `Dockerfile.api`.
