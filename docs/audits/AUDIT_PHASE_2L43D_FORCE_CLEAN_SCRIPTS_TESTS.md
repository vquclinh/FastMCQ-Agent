# Audit — Phase 2L.43D: Force-Clean `scripts/` Top Level + Reorganize `tests/`

**Date:** 2026-06-24  **Branch:** `main`  **Status:** structure reorg (no commit, no API)

This phase finishes what 2L.43A/B deferred: the `scripts/` top level is now genuinely clean,
and `tests/` is split into `integration/`, `unit/`, `legacy/`. Coverage is **preserved** — no
passing test was deselected; moved-script tests were repointed, not dropped.

## Stage 1 — production utilities → `scripts/tools/` (+ shims)

Moved the 4 production utilities to `scripts/tools/` with `_ROOT = parents[2]`, leaving
re-export shims at the old `scripts/` paths (for `run_full_system.sh`, the Docker entrypoint,
and external CLI callers):

- `scripts/tools/final_infer.py`, `output_quality_report.py`, `validate_submission.py`,
  `audit_model_policy.py`
- shims remain at `scripts/final_infer.py`, `scripts/output_quality_report.py`,
  `scripts/validate_submission.py`, `scripts/audit_model_policy.py`.

**Shim limitation fixed.** A re-export shim copies the real module's names into its own globals,
but the copied functions still close over the *real* module's globals. So a path-loading test
that did `monkeypatch.setattr(shim, "_can_create", ...)` had no effect on `_resolve_output`
(which looks up `_can_create` in the real module). Resolution: **production tests load the real
`scripts/tools/<name>.py` module**, not the shim. Updated the loaders/source-scans in
`test_btc_noarg_2l32b`, `test_btc_short_2l31b`, `test_fastmcq_dynamic_system_2l36b`,
`test_v13_dynamic_integration_2l37a`, `test_run_profiles_2l38c`, `test_model_policy`, and the
`from scripts.output_quality_report import …` in `test_full_system_output_contract_2l41a` →
`scripts.tools.…`. Shims stay only for CLI/Docker/back-compat.

## Part A — force-clean `scripts/` top level

Moved **57** non-keeper scripts from `scripts/` → `scripts/legacy/` via `git mv`
(`analyze_*`, `audit_*candidate*`, `build_*`, `apply_*`, `run_*` diagnostics, `check_*`,
`recommend_*`, `repair_*`, `review_*`, `plan_*`, `print_*`, `profile_dataset`,
`inspect_dataset`, `select_adaptive_pilot_qids`, `run_production_pipeline`,
`run_full_v11_independent_submission`, `run_local.sh`, `run_llm_full.sh`, `run_llm_smoke.sh`,
etc.). `scripts/legacy/` now holds **74** scripts (57 + the 17 from 43A/B).

**Final top-level `scripts/` — exactly the 7 keepers:**
```
run_full_system.sh          # OFFICIAL command
final_infer.py              # shim -> tools/
output_quality_report.py    # shim -> tools/
validate_submission.py      # shim -> tools/
audit_model_policy.py       # shim -> tools/
docker_entrypoint.sh        # legacy pipeline entry (env)
docker_entrypoint_v11.sh    # Dockerfile ENTRYPOINT
+ tools/ (4)  run/ (7)  legacy/ (74)
```

### Production references repointed (only 2 needed)
- `scripts/tools/final_infer.py` `--mode v11_independent` lazy-load →
  `scripts/legacy/run_full_v11_independent_submission.py` (verified present + loadable).
- `scripts/docker_entrypoint.sh` → `scripts/legacy/run_production_pipeline.py` (both refs).

The Dockerfile ENTRYPOINT (`docker_entrypoint_v11.sh`) only calls the `final_infer.py` shim →
`/output/pred.csv` contract unaffected.

### Legacy scripts: depth + sibling-load fix
Each moved script was authored at depth-1 (`scripts/`) so `Path(__file__).resolve().parent.parent`
meant repo root. At depth-2 (`scripts/legacy/`) that became `scripts/`. Applied a uniform,
exact-form bump across **62** `scripts/legacy/*.py`:
`resolve().parent.parent` / `resolve().parents[1]` → `resolve().parents[2]` (repo root again).
Fixed the 3 sibling loaders (`run_adaptive_pilot`, `run_full_adaptive_submission`,
`select_adaptive_pilot_qids`) to load siblings from `scripts/legacy/`.

### Tests repointed (coverage preserved, NOT deselected)
Every test that path-loads a moved script was updated to resolve it under `scripts/legacy/`,
keeping the test **collected**:
- `_load(name)` / spec helpers now resolve legacy-first with fallback:
  `(_ROOT/"scripts"/"legacy"/name if (…).exists() else _ROOT/"scripts"/name)` — works for both
  moved scripts and the `final_infer.py` keeper used by `test_final_package`.
- f-string variants `_ROOT/"scripts"/f"{script}.py"` got the same resolver
  (`test_v12b_permutation_2l34b`, `test_v13_multilayer_2l35a`).
- `test_model_compliance.py` `sys.path` → `scripts/legacy`; `test_adaptive_orchestrator.py`
  source-scan base → `scripts/legacy`.

## Part B — `tests/{integration,unit,legacy}`

Split the 53 collected test files (with `__init__.py` in each subdir; `tests/__init__.py`
already present → package mode):
- **`tests/integration/` (31)** — full-pipeline / CLI / multi-component (BTC, full-system
  contract, dynamic system, V13 integration, run profiles, production pipeline/timing/layers,
  v11 lineage, adaptive/submission/pilot, v12b/v13 candidates, selective API, model compliance).
- **`tests/unit/` (22)** — focused module tests (data_io, labels, model_policy, permutation
  debiaser, api progress resume, solvers, parsers, prompting, routing, etc.).
- **`tests/legacy/` (1, deselected)** — `test_v12_delta_2l34a.py` (unchanged).

Applied the same uniform depth bump to all **53** moved tests
(`resolve().parent.parent` / `parents[1]` → `parents[2]`) so `_ROOT`, `sys.path.insert(_ROOT)`,
and subprocess `cwd` still resolve to repo root at the new depth. `tests/conftest.py`
(`collect_ignore_glob=["legacy/*"]`) is unchanged and still deselects only `tests/legacy/`.

## Part D — `src/README.md` (docs only; no code moved)
Added `src/README.md` classifying the flat package (orchestrator/system, official layers, base
solvers, adaptive routing, retrieval/evidence, API, local HF, prompting/parsing, production
pipeline, I/O & utils). **`src/` stays flat** — the sub-package reorg remains blocked by the
`src/utils.py` (logging) vs `src/utils/` collision + relative-import breakage; documented, not
attempted.

## Part E — hardcode + path audit
- **`463`:** only the cosmetic profile NAME `public_api463`; none in `src/`, `scripts/tools/`,
  `run_full_system.sh`, Docker entrypoints, or production configs.
- **qid/answer hardcoding:** none in production logic. `configs/production/default.json`
  `changed_qids` is **pre-existing descriptive metadata** (a record of the frozen V13-vs-V12B
  diff), untouched this phase; it is not used to hardcode answers in the dynamic pipeline.
- **`outputs/`:** none in active code (fully migrated to `output/`).
- **Stale flat `scripts/<moved>` refs in active code (src, tools, run, keepers, collected
  tests):** none.

## Part F — validations
- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **738 passed** (legacy deselected) — same count as the pre-phase baseline.
- `python scripts/audit_model_policy.py`: **RESULT: PASS — only competition-allowed models
  referenced** (scan now includes `scripts/{tools,run,legacy}`).

### Official full-system no-API smoke
```
FASTMCQ_FINAL_DIR=scratch/2l43d_smoke_out \
  bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  status: PASS ; profile production_full_system_noapi
  final -> scratch/2l43d_smoke_out/pred.csv ; header "qid,answer" ; qids sm1..sm5 (exact)
  quality: top_ratio 60% < 70% (not degenerate)
```
Moved wrapper `scripts/run/run_dynamic_noapi.sh` syntax OK (`ROOT=.../../..`). Real
`output/pred.csv` and the 5 protected CSVs untouched.

## Confirmations
- **No API calls** (smoke `--no-api`; policy PASS).
- **No qid/answer hardcoding; no `463`; no hardcoded `private_test`/public artifact** in
  production logic.
- **`run_full_system.sh <test_file>` → `output/pred.csv` works** (smoke PASS).
- **Docker `/data` → `/output/pred.csv` preserved** (ENTRYPOINT `docker_entrypoint_v11.sh`
  calls the `final_infer.py` shim, unchanged).
- **Official historical prediction CSVs preserved** under `output/` — V13 md5
  `cb02fef569b31e7fb544abab46c0e282` unchanged.
- **Audits preserved** under `docs/audits/` (this file added).
- **Model-policy rules unchanged.**
- **Not committed.**

## Final structure
```
scripts/  run_full_system.sh + 4 shims + 2 docker entrypoints
          tools/ (4 production utilities)  run/ (7 diagnostic wrappers)  legacy/ (74)
tests/    conftest.py  __init__.py
          integration/ (31)  unit/ (22)  legacy/ (1, deselected)
src/      flat (60+ modules) + README.md (module map; repackage still blocked, documented)
configs/  production/{default,noapi}.json  profiles/run_profiles.json  +yaml
output/   5 protected best CSVs (+ pred.csv generated, gitignored)
docs/     README/FINAL_RUN/DOCKER_SUBMISSION + ARCHITECTURE/METHOD/… + audits/
```

## Remaining follow-ups (unchanged from prior phases)
1. `src/` repackage (blocked by `src/utils.py` vs `src/utils/` + relative imports).
2. Rebuild the Docker image before submitting; run one budgeted `production_full_system` API
   check (no API exercised this phase).
