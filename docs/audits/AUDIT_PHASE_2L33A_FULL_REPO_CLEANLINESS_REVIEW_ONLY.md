# Audit — Phase 2L.33A: Full Repository Cleanliness Review (Review-Only)

**Date:** 2026-06-23  **Branch:** `main`  **HEAD:** `92ef1fa v11: frozen independent v11 78.4 default`
**Mode:** review-only (no code changes, no moves, no deletes, no staging, no commit, no API).

> **State change since 2L.32D:** the full repo has already been **committed to `main`**
> (commit `92ef1fa`, 154 files, working tree now **clean**). So this review assesses the
> *already-committed full-reproducibility repo*, not a pending minimal package.

---

## 1. Executive verdict

- **Clean enough to commit as minimal final package?** — **Yes** (and the frozen path is a
  small, verified subset: `final_infer.py` + `src/data_io` + `src/labels` + config + winning CSV).
- **Clean enough to commit the full repo?** — **Yes.** No secrets, no `.venv`/`scratch`/caches,
  only the 2 required CSVs in `outputs/`, 618 tests pass, model-policy PASS, frozen smoke
  reproduces the winning md5. The full commit already on `main` is **safe**.
- **Recommended strategy:** the repo is already committed full (Option 2, reproducibility).
  That is acceptable and reviewer-friendly for verifying the `--mode v11_independent` rerun.
  **Optional, non-blocking** future polish: relocate experimental scripts/src/tests under
  `*/experimental/` subfolders for at-a-glance clarity (NOT required; pure churn otherwise).
  Process note: the commit landed directly on `main` rather than a feature branch — fine for a
  solo submission repo, but a branch+PR is cleaner if collaborators are involved.

## 2. Required final package file list (the frozen BTC path)

| Path | Role |
|---|---|
| `scripts/final_infer.py` | entrypoint — frozen_csv default, no-arg I/O, validation, timing |
| `scripts/docker_entrypoint_v11.sh` | no-arg Docker entrypoint → `final_infer.py` |
| `scripts/validate_submission.py` | output validator |
| `src/data_io.py`, `src/labels.py` | **only** project modules imported by the frozen path |
| `configs/production_v11_independent.json` | `default_mode=frozen_csv`, points to winner + v10 |
| `outputs/pred_v11_independent_rerun1.csv` | winning 78.4 CSV (md5 `69f4e7c9…`) |
| `Dockerfile`, `.dockerignore`, `.gitignore`, `requirements.txt` | build/ignore rules |
| `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md` | run docs |
| `outputs/pred_v10_full_production_user_run.csv` | v10 fallback (77.75) — reproducibility |
| `experiments/best_candidate_manifest.json` | scores + md5 manifest |

## 3. Files that should remain uncommitted

In the current full-repo commit, the experimental pipeline **is** committed (the user's
Option-2 choice). That is acceptable. If a *minimal* package were ever preferred instead, the
following would be the candidates to drop: experimental `src/` modules (§5), experimental
`scripts/` (§6), and dev-phase `tests/` (§7). **No action recommended now.**

## 4. Files that should be deleted locally or ignored

- **Already correctly ignored & absent from the commit:** `.env`, `.venv/`, `scratch/` (12M,
  incl. the run evidence and the external 3-LLM sheet `scratch/first100_external_3llm.csv`),
  `__pycache__/`, `.pytest_cache/`, `models/`, `outputs/pred.csv`, `outputs/pred_v8_*`,
  `outputs/pred_v11_full_adaptive_test.csv`. **Nothing needs deleting for safety.**
- `scratch/` is purely local/disk (gitignored) — leave as-is (user decision in 2L.32D).

## 5. `src/` cleanliness review (Part B)

- **Required by frozen default:** **only** `src/data_io.py` and `src/labels.py`
  (verified: `final_infer.py` top-level project imports are exactly these two). **Enough for
  default inference — yes.**
- **Experimental-only (≈18 of 64 modules):** `adaptive_*` (7), `answer_factory.py`,
  `answer_ranker.py`, `api_candidate_agents.py`, `candidate_answer.py`,
  `candidate_consistency.py`, `evidence_pack.py`, `independent_answer_selector.py`,
  `option_grounding.py`, `rag_lite.py`, `selective_api_client.py`,
  `calculation_first_planner.py`, `model_policy.py`. These are reached **only** under
  `--mode v11_independent` (lazy-loaded), so the **frozen default does not import them**.
- **Old version-specific modules:** none named `*_v8/_v9/_v10` in `src/`. No obvious
  duplicate/conflicting modules detected by name.
- **Modified tracked source unrelated to final package:** none outstanding — the working tree
  is clean (everything committed). Earlier "pre-existing modifications" were committed in
  `92ef1fa`.
- **Verdict:** `src/` is functionally clean; the large module count is reproducibility surface,
  not a correctness risk. The frozen path is well-isolated.

## 6. `scripts/` cleanliness review (Part C)

- **Required for final package:** `final_infer.py`, `docker_entrypoint_v11.sh`,
  `validate_submission.py`.
- **Fallback/reproducibility:** `run_full_v11_independent_submission.py`,
  `repair_v11_independent_run.py`, `audit_production_candidate.py`,
  `audit_v11_independent_integrity.py`, `audit_model_policy.py`, `build_*`, manifest builders.
- **Experimental/dev only (~42 of 67):** `run_*`, `build_*`, `analyze_*`, `plan_*`, `select_*`,
  `review_*` (adaptive/selective/pilot/variants).
- **Too many top-level versioned scripts?** Yes — 67 scripts in a flat `scripts/` is busy. Only
  one is version-flavored (`analyze_v10_geography.py`, an analysis tool, not a default).
- **Is `final_infer.py` clearly the main entrypoint?** **Yes** — README/FINAL_RUN/
  DOCKER_SUBMISSION + the Docker ENTRYPOINT all route through it.
- **Risk of an old script looking like production default?** Low. `run_production_pipeline.py`
  exists (older detect/run) but the entrypoint no longer calls it; minor reader ambiguity only.
- **Recommendation (optional, later):** move experimental scripts to `scripts/experimental/`.

## 7. `tests/` cleanliness review (Part D)

- **Committed tests:** 45 files; **`pytest -q` → 618 passed**, none failing/obsolete.
- **Needed for final package:** the validator/label/data_io/`final_infer` tests
  (`test_final_package_2l31a.py`, `test_btc_noarg_2l32b.py`, `test_btc_short_2l31b.py`, etc.).
- **Phase/development tests:** the `*_2l2*`/`*_2l3*` and pipeline tests (accuracy engine,
  answer factory, adaptive, selective api, pilot gate, consistency, repair, hardening).
- **Too many for a minimal commit?** For a *minimal* package, yes — but they are committed
  under the full-repo choice and all pass, so they add verifiable coverage, not breakage.
- **Recommendation (optional, later):** group into `tests/final/` + `tests/experimental/` if a
  cleaner split is desired; **not required**.

## 8. Docker / BTC interface review (Part E)

| Check | Result |
|---|---|
| Base / build | `FROM python:3.11-slim`, `WORKDIR /app`, `COPY requirements.txt` → pip, `COPY . .` |
| Default = v11 frozen, not v10 | ✅ entrypoint runs `final_infer.py` frozen_csv (config points to winner); header says "NO v10, NO API" |
| No-arg BTC behavior | ✅ `ENTRYPOINT ["bash", scripts/docker_entrypoint_v11.sh]`; no args → `final_infer.py`; args forwarded |
| `/data/doc_public_test.csv` & `/data/private_test.csv` detected | ✅ `final_infer.py` autodetect order (verified by smoke on `doc_public_test.csv`) |
| `/output/pred.csv` produced | ✅ output resolves to `/output/pred.csv` in-container |
| No API key by default | ✅ frozen_csv copies CSV; no client constructed |
| `.dockerignore` excludes venv/.env/scratch/logs/caches/notebooks/weights | ✅ `.env`, `.env.*`, `.venv/`, `venv/`, `scratch/`, `__pycache__/`, `.pytest_cache/`, `*.ipynb`, `models/`, `.cache/`, `.git/` |
| Required frozen CSV in build context | ✅ winner + v10 NOT ignored; only `outputs/pred.csv` + `pred_v11_full_adaptive_test.csv` excluded |
| Elapsed time prints by default | ✅ `elapsed_seconds` in `final_infer.py` timing block |
| Docs unambiguous | ✅ README "Final submission" block, FINAL_RUN.md, DOCKER_SUBMISSION.md all name v11 78.4 |

**Docker build not run this phase** (review-only; image was already built & verified PASS in
2L.32B–D with output md5 `69f4e7c9…`). Local frozen smoke re-run here (below) reproduces it.

## 9. Version clarity review (Part F)

- **Is v11 clearly the production version?** **Yes** — config `default_mode=frozen_csv` +
  `current_best_csv=…v11_independent_rerun1.csv`; README/docs all state 78.4 default.
- **Is v10 clearly fallback only?** **Yes** — `baseline_v10_csv` in config; reachable only via
  explicit `--mode v10`; docs label it fallback (77.75).
- **Old artifacts confusing a reader?** **Minimal.** Committed `outputs/` has **only** the v11
  winner + v10 fallback (no v8/v9/adaptive CSVs). Only one v10-named script
  (`analyze_v10_geography.py`, analysis). The confusion surface is the large experimental
  `src/`+`scripts/` count, not competing version outputs.
- **Manifest/config enough to make status clear?** **Yes** — `best_candidate_manifest.json` +
  `production_v11_independent.json` make the winner explicit with md5.
- **Too many versions coexisting at top-level?** **No** for outputs/configs; the experimental
  *code* is plentiful but off the default path.
- **Recommendation:** leave as-is for submission; optionally archive experimental code under
  `*/experimental/` post-submission for reader clarity.

## 10. Results of safe checks (Part G)

```
git status --short                         -> (empty; working tree clean)
git check-ignore -v .env                   -> .gitignore:15:.env            (ignored ✅)
git check-ignore -v scratch/.../v11_independent_candidates.jsonl -> .gitignore:55:scratch/*  (ignored ✅)
git check-ignore -v outputs/pred_v11_independent_rerun1.csv      -> NOT ignored (trackable ✅, committed)
git check-ignore -v outputs/pred_v10_full_production_user_run.csv-> NOT ignored (trackable ✅, committed)
compileall -q src scripts tests            -> OK
pytest -q                                  -> 618 passed
scripts/audit_model_policy.py              -> RESULT: PASS — only competition-allowed models referenced.
```
**Final review smoke (offline, frozen):**
```
final_infer.py --input scratch/review_only_smoke/data/doc_public_test.csv --output .../pred.csv
  input detected: …/doc_public_test.csv   md5: 69f4e7c990e8c612e7bee53084d13b4d
  elapsed_seconds: 0.008   status: PASS
validate_submission.py -> RESULT: PASS — submission is valid.
smoke md5 == winning CSV md5 -> True
```
Secret scan of committed files: **no `.env`, no `*.key`/`*.pem`, no `sk-or-v1-` literal**; no
`.venv`/`scratch`/caches committed; no external/3-LLM sheet committed.

## 11. Final recommended staging command

The working tree is **clean — nothing to stage** (the full repo is already committed at
`92ef1fa`). No staging action is required or recommended this phase.

*If* a fresh **minimal** package commit were ever desired on a new branch, it would be:
```bash
git add scripts/final_infer.py scripts/docker_entrypoint_v11.sh \
  configs/production_v11_independent.json experiments/best_candidate_manifest.json \
  outputs/pred_v11_independent_rerun1.csv outputs/pred_v10_full_production_user_run.csv \
  Dockerfile .dockerignore .gitignore README.md FINAL_RUN.md DOCKER_SUBMISSION.md \
  src/data_io.py src/labels.py scripts/validate_submission.py requirements.txt
```
(Reasoning: frozen path = `final_infer` + `data_io` + `labels` + config + winning CSV; exclude
experimental scripts/src/tests.) **Not needed given the current clean full commit.**

## 12. Final recommended commit command

**None this phase** — nothing to commit (tree clean). The only new file produced by this
review is *this audit report*; if you wish to record it:
```bash
git add docs/audits/AUDIT_PHASE_2L33A_FULL_REPO_CLEANLINESS_REVIEW_ONLY.md
git commit -m "docs: phase 2L.33A full-repo cleanliness review (review-only)"
```
(Optional; left to the user — this phase does not commit.)

## 13. Git status summary

`On branch main; up to date with origin/main; nothing to commit, working tree clean.`
HEAD `92ef1fa` committed 154 files: 87 docs (incl. `docs/audits/`), 67 scripts, 64 src, 45
tests, 5 configs, 3 outputs (`.gitkeep` + 2 required CSVs), 3 experiments, plus root build/run
files. After this review the only uncommitted item is this audit Markdown (untracked).

## 14. Explicit confirmations

- **No code changes** — no source/script/config edited.
- **No file moves** — none (audits were already relocated in 2L.32D and committed).
- **No file deletion** — none.
- **No API calls** — frozen_csv smoke + offline validators only.
- **No outputs/best artifacts overwritten** — winner md5 still `69f4e7c990e8c612e7bee53084d13b4d`;
  v10 untouched; smoke wrote only under `scratch/review_only_smoke/`.
- **No secrets exposed** — `.env` confirmed gitignored & uncommitted; its contents were never
  printed or inspected.
- **Not committed** — this phase makes no commit.
