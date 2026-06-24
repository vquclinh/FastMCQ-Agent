# Audit — Phase 2L.43A: Final Repository Structure Cleanup

**Date:** 2026-06-24  **Branch:** `main`  **Status:** structure cleanup (no commit, no API)

## Safety preflight (Part A)

`git status --short` → **clean** (working tree matches commit `e2d8f5d "finalize full-system BTC
submission workflow"`). The stable full-system workflow is committed, so a safe fallback exists
(`git checkout .`). Preflight **passed** → proceeded with cleanup.

## Files inspected

`configs/`, `scripts/`, `src/`, `tests/`, `docs/` trees; `scripts/final_infer.py`,
`scripts/run_full_system.sh`, `scripts/docker_entrypoint_v11.sh`, README/FINAL_RUN/
DOCKER_SUBMISSION, and all references to versioned configs / `run_profiles.json`.

## Files moved (via `git mv`, history preserved)

**Configs (Part C):**
- `production_v13_multilayer_7970.json` → **`configs/production/default.json`** (active).
- `production_v11_independent.json`, `production_v12b_permutation_7883.json` →
  **`configs/archive/`** (historical/superseded).
- `run_profiles.json` → **`configs/profiles/run_profiles.json`**.
- New: **`configs/production/noapi.json`** (active offline production config).

**Scripts (Part D) — superseded v12_delta experiment → `scripts/legacy/`:**
`build_v12_delta_plan.py`, `run_v12_delta_verifier.py`, `build_v12_delta_candidate.py`,
`audit_v12_delta_candidate.py` (the 2L.34A delta experiment, fully superseded by the V12B
permutation debiaser; not on the production path).

**Tests (Part E):** `tests/test_v12_delta_2l34a.py` → **`tests/legacy/`**; added
`tests/conftest.py` with `collect_ignore_glob = ["legacy/*"]` so legacy tests are **not run** by
default `pytest`.

**Docs (Part F) → `docs/archive/`:** `ADAPTIVE_REASONING_ARCHITECTURE`, `CALCULATION_SOLVER`,
`CALCULATION_TAXONOMY`, `EVIDENCE_RERANKER`, `MCQ_VERIFIER`, `NEURAL_EVIDENCE_RERANKER`,
`OPENROUTER_ROUND1_STRATEGY`, `PROJECT_STATUS_AND_ROADMAP`, `RESEARCH_STRATEGY`.

## Files deleted

None. (Everything was moved/archived, never deleted — honoring "do not delete official artifacts".)

## Files changed (reference updates)

- `scripts/final_infer.py` — `_DEFAULT_CONFIG → configs/production/default.json`;
  `_PROFILES_PATH → configs/profiles/run_profiles.json`; help text.
- `scripts/docker_entrypoint_v11.sh` — `CFG → configs/production/default.json`.
- `DOCKER_SUBMISSION.md` — config path → `configs/production/default.json`.
- `tests/test_run_profiles_2l38c.py`, `tests/test_layer_only_api_profile_2l39d.py`,
  `tests/test_full_system_output_contract_2l41a.py` — profiles path → `configs/profiles/…`.
- `tests/test_v12b_permutation_2l34b.py`, `tests/test_v13_multilayer_2l35a.py`,
  `tests/test_fastmcq_dynamic_system_2l36b.py` — production-default guard now reads
  `configs/production/default.json` and asserts the **V13** best CSV.

## Files kept as compatibility / in place (deliberate)

- `scripts/run_full_system.sh` (official command, top level — allowed by spec).
- `scripts/final_infer.py`, `output_quality_report.py`, `validate_submission.py`,
  `audit_model_policy.py`, `docker_entrypoint_v11.sh` kept at `scripts/` (referenced by the
  wrapper, Docker, and ~10 tests; a `scripts/tools/` move would need shims — **deferred**, see
  Remaining risks).
- `run_full_v11_independent_submission.py` kept (final_infer `--mode v11_independent` imports it).
- `src/` kept **flat** — a `src/{base,layers,api,selector,utils}` package migration touches every
  intra-package import and is the highest-risk change; the spec explicitly says not to do it
  unless safe. **Deferred** with a documented plan (see Remaining risks).
- The V12B/V13 **candidate-builder** scripts (`build_v12b_*`, `build_v13_*`,
  `run_v12b_option_permutation`, `run_v13_multilayer_verifier`, `audit_v12b_*`, `audit_v13_*`)
  kept: their tests cover **production `src/` core modules**, and they are the documented pilot
  tooling that produced the official 78.83 / 79.7 artifacts.

## New final repo structure (active paths)

```
configs/
  production/{default.json, noapi.json}     # active; no version-numbered names
  profiles/run_profiles.json
  archive/{production_v11_independent.json, production_v12b_permutation_7883.json}
  allowed_models.yaml, default.yaml, verifier_selective.yaml, adaptive_reasoning.yaml
scripts/
  run_full_system.sh                        # OFFICIAL command
  docker_entrypoint_v11.sh, final_infer.py, output_quality_report.py,
  validate_submission.py, audit_model_policy.py, run_*.sh (research wrappers)
  legacy/ (v12_delta experiment)
src/  (flat: fastmcq_system, dynamic_base_predictor, v12b_dynamic_layer, v13_dynamic_layer,
       system_candidate_selector, mcq_permutation_debiaser, programmatic_solver_layer,
       content_first_answerer, least_to_most_constraint_solver, data_io, labels, model_policy, …)
tests/  (conftest deselects legacy/) + tests/legacy/test_v12_delta_2l34a.py
docs/  README/FINAL_RUN/DOCKER_SUBMISSION at root; ARCHITECTURE/METHOD/DATASET_PROFILE/
       MODEL_COMPLIANCE kept; archive/ (research docs); audits/ (all audits)
output/  5 official best CSVs (tracked) + .gitkeep; pred.csv generated (gitignored)
```

## Active production config names

`configs/production/default.json` (API default) and `configs/production/noapi.json` (offline).
No active path uses a version-numbered production filename.

## Scripts classification summary

- **Official production:** `run_full_system.sh`, `docker_entrypoint_v11.sh`, `final_infer.py`,
  `output_quality_report.py`, `validate_submission.py`, `audit_model_policy.py`.
- **Research/diagnostic (kept, documented as legacy in docs):** `run_public_replay.sh`,
  `run_dynamic_noapi.sh`, `run_public_api50/100.sh`, `run_public_layer_api50.sh`,
  `run_private_*.sh`, V12B/V13 candidate-builder + pilot scripts.
- **Legacy (moved):** the v12_delta experiment → `scripts/legacy/`.
- **Obsolete (recommended follow-up):** assorted one-off `analyze_*`/`audit_*_candidates`/
  `build_submission_*`/`run_adaptive_*` from phases 2L.25–2L.30 (not referenced by production;
  left in place this turn to avoid a large coordinated script+test removal pre-submission).

## Tests classification summary

Default `pytest` (738 tests) covers the full-system contract, BTC `/data`→`/output/pred.csv`,
local `output/pred.csv`, arbitrary qids, CSV+JSON parsing, model policy, no-hardcode, selector +
API-client safety, resume/progress. `tests/legacy/` (deselected) holds the v12_delta tests.

## Docs moved to archive

9 research/phase docs → `docs/archive/`. Root keeps the 3 primary docs + ARCHITECTURE/METHOD/
DATASET_PROFILE/MODEL_COMPLIANCE (README-linked). All audits retained under `docs/audits/`.

## Hardcode audit results (Part G)

- `463`: **absent from production logic**; the only occurrence is the cosmetic profile NAME
  `public_api463` (a research profile whose caps are now `"all"`).
- versioned `production_v1*` config names: **absent from active code/scripts/src**.
- `public-test_1780368312.json`: **absent from production logic** (only a last-resort entry in
  final_infer's input-autodetect candidate list; BTC names come first).
- `outputs/`: migrated to `output/` (2L.41A/2L.42A).
- `test_0001`/`test_0463`: not used as production behavior.

## Validations (Part H)

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **738 passed** (legacy deselected; was 751 with the 13 v12_delta tests).
- `scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models referenced.**

### Full-system no-API smoke
```
bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  profile=production_full_system_noapi  v12b_max_qids=all(5) v13_max_qids=all(5)  status: PASS
  output/pred.csv -> header "qid,answer"; qids sm1..sm5 (exact); quality_report.json written
```
No API calls. Docker entrypoint still targets `/output/pred.csv` with `configs/production/default.json`.

## Confirmations

- **No API calls** (smoke `--no-api`; model policy enforced).
- **No qid/answer hardcoding; no 463 in production logic.**
- **Official historical artifacts preserved** — 5 best CSVs under `output/` (md5 unchanged, V13
  `cb02fef5…`); old configs archived (not deleted).
- **`run_full_system.sh` still works** (smoke PASS) and **Docker `/output/pred.csv`** behavior
  preserved (+ `INPUT_FILE`/`OUTPUT_FILE` overrides).
- **Model-policy rules unchanged.**
- **Not committed.**

## Git status

```
R  configs/production_v13_multilayer_7970.json -> configs/production/default.json
R  configs/production_v11_independent.json -> configs/archive/...
R  configs/production_v12b_permutation_7883.json -> configs/archive/...
R  configs/run_profiles.json -> configs/profiles/run_profiles.json
R  scripts/{build,run,audit}_v12_delta*.py -> scripts/legacy/...
R  tests/test_v12_delta_2l34a.py -> tests/legacy/...
R  docs/<9 research docs>.md -> docs/archive/...
 M scripts/final_infer.py  scripts/docker_entrypoint_v11.sh  DOCKER_SUBMISSION.md
 M tests/{test_run_profiles_2l38c,test_layer_only_api_profile_2l39d,test_full_system_output_contract_2l41a}.py
 M tests/{test_v12b_permutation_2l34b,test_v13_multilayer_2l35a,test_fastmcq_dynamic_system_2l36b}.py
?? configs/production/noapi.json  tests/conftest.py  docs/audits/AUDIT_PHASE_2L43A_*.md
```
Nothing committed.

## Remaining risks before final submission

1. **`src/` package migration deferred** — `src/` is still flat. A `base/layers/api/selector/
   utils` split needs coordinated import updates or shims across ~15 modules + all tests; doing
   it pre-submission risks the green suite. Recommended as a dedicated, separately-verified
   change after committing this checkpoint.
2. **`scripts/tools/` move deferred** — `final_infer.py` et al. kept at `scripts/` (referenced by
   the wrapper, Docker, and many tests); a move needs compat shims.
3. **Obsolete one-off scripts (phases 2L.25–2L.30) still present** — functional repo, not maximally
   lean; safe follow-up is a coordinated `scripts/legacy/` move + test deselection.
4. **No real API full-system run yet** — exercise `production_full_system` (budgeted) once before
   final submission.
5. **Docker image not rebuilt** this turn (entrypoint + config path changed) — rebuild before
   submitting.
6. Reranker vocab files (gitignored/unused) were best-effort restored in 2L.41A.
