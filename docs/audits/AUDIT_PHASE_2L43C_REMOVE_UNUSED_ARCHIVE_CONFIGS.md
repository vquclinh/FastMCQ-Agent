# Audit — Phase 2L.43C: Remove Unused Archive Configs

**Date:** 2026-06-24  **Branch:** `main`  **Status:** config cleanup (no commit, no API)

## Files inspected

`configs/` tree; all references to `configs/archive/`, `production_v11_independent.json`,
`production_v12b_permutation_7883.json` across the repo (excl. `.git`/`.venv`/`scratch`/
`docs/audits`).

## References found

```
configs/archive/production_v11_independent.json:3-4  -> self/sibling cross-reference (status/superseded_by)
tests/legacy/test_v12_delta_2l34a.py:176             -> reads configs/production_v12b_permutation_7883.json
```
- The only inter-file reference was the two archived configs pointing at **each other**
  (`superseded_by`) — irrelevant once both are removed.
- `tests/legacy/test_v12_delta_2l34a.py` is in **`tests/legacy/`**, which `tests/conftest.py`
  deselects (`collect_ignore_glob=["legacy/*"]`) → **not collected by `pytest`**, and it
  references the *old* path (already non-existent), so it neither runs nor affects the suite.
- **No active production / docs / collected-test reference** required the archived configs.

## Files deleted

- `configs/archive/production_v11_independent.json`
- `configs/archive/production_v12b_permutation_7883.json`
- `configs/archive/` (directory removed; now empty)

Removed via `git rm` (they were tracked since commit `e2d8f5d`), so the historical content is
**preserved in git history** — only the working tree is cleaned.

## Final `configs/` tree

```
configs/
  production/
    default.json          # active production (API)
    noapi.json            # active production (offline)
  profiles/
    run_profiles.json     # run profiles
  allowed_models.yaml
  adaptive_reasoning.yaml
  default.yaml
  verifier_selective.yaml
```
Matches the target active tree exactly; no version-numbered or archive configs remain.

## Docs

No non-audit doc referenced the archived configs as active paths, so no doc edits were needed.
(Historical configs remain recoverable from git history and are described in `docs/audits/`.)

## Validations run / results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **738 passed** (legacy deselected)
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

### Full-system no-API smoke
```
bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  status: PASS ; final -> output/pred.csv ; header "qid,answer" ; qids sm1..sm5 (exact)
```

## Confirmations

- **No API calls** (smoke `--no-api`; model policy enforced).
- **No qid/answer hardcoding** (configs unchanged except deletions; production logic untouched).
- **Official historical prediction CSVs preserved** under `output/` — md5 unchanged:
  V13 `cb02fef569b31e7fb544abab46c0e282`, V12B `075646ad…`, v11 `69f4e7c9…` (v10/v8 also intact).
- **Audits preserved** — 93 files under `docs/audits/` (incl. this one).
- **`run_full_system.sh` still works** (smoke PASS).
- **Docker `/data` → `/output/pred.csv` preserved** (entrypoint references
  `configs/production/default.json` + `/output/pred.csv`, unaffected by the archive removal).
- **Model-policy rules unchanged.**
- **Not committed.**

## Git status (config-related)

```
R  configs/production_v13_multilayer_7970.json -> configs/production/default.json
R  configs/run_profiles.json -> configs/profiles/run_profiles.json
D  configs/production_v11_independent.json          (archived in 43A, now removed)
D  configs/production_v12b_permutation_7883.json    (archived in 43A, now removed)
?? configs/production/noapi.json
?? docs/audits/AUDIT_PHASE_2L43C_REMOVE_UNUSED_ARCHIVE_CONFIGS.md
```
(Plus the broader 43A/43B reorg renames/edits still uncommitted on top of `e2d8f5d`.)
Nothing committed.

## Remaining cleanup candidates (from 43B, unchanged this phase)

1. `src/` repackage (blocked by `src/utils.py` vs `src/utils/` collision + relative imports).
2. ~40 phase-specific scripts + their path-loading tests still at top level (coordinated
   script+test → `legacy/` move recommended).
3. `tests/integration|unit` subfoldering (needs `_ROOT` depth fix across ~30 files).
4. `scripts/tools/` move for production utilities (needs re-export shims).
5. Rebuild Docker image before submitting; run one budgeted `production_full_system` API check.
