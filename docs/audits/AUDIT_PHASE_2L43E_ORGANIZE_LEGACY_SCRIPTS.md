# Audit — Phase 2L.43E: Organize Legacy Scripts by Purpose

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** structure reorg
(no commit, no API)

Goal: reorganize the flat `scripts/legacy/` (74 files) into purpose subfolders, without changing
the production workflow.

## Files moved

All 74 scripts in `scripts/legacy/*.py|*.sh` were `git mv`'d into category subfolders. Category
assignment: submission-themed names first, then by name prefix.

| Category | Count | Rule |
|---|---:|---|
| `analysis/` | 11 | `analyze_`, `compare_`, `profile_`, `inspect_`, `inventory_` |
| `audit/` | 16 | `audit_` (minus `audit_submission_variants`) |
| `build/` | 11 | `build_`, `plan_` (minus submission builders) |
| `run/` | 16 | `run_` (incl. `run_full_v11_independent_submission`, `run_production_pipeline`) |
| `review/` | 1 | `review_` (`recommend_submission_candidate` → submission) |
| `repair/` | 4 | `repair_`, `apply_` |
| `benchmark/` | 2 | `benchmark_` |
| `submission/` | 7 | submission candidate/variant/ensemble/runbook + `cleanup_outputs_for_submission` + `audit_submission_variants` + `recommend_submission_candidate` |
| `checks/` | 3 | `check_` |
| `misc/` | 3 | `create_verifier_smoke_subset`, `export_risk_review_pack`, `select_adaptive_pilot_qids` |
| **TOTAL** | **74** | |

## Final `scripts/legacy/` tree

```
scripts/legacy/
  README.md            # index (categories + "not the official workflow")
  analysis/  (11)   audit/  (16)   build/  (11)   run/  (16)   review/  (1)
  repair/    (4)    benchmark/ (2) submission/ (7) checks/ (3)  misc/ (3)
```
Top level now holds only `README.md` + the 10 category dirs (no flat scripts).

## Internal/script fixes (so moved scripts still run)

- **Depth:** every moved `.py` now one level deeper — `Path(__file__).resolve().parents[2]`
  (repo root at the old depth) → `parents[3]` (62 files updated). Verified: no `parents[2]`
  remain in `scripts/legacy/**`.
- **Sibling loaders** (load another legacy script by path) now resolve **recursively** under
  `scripts/legacy/**`:
  - `run/run_full_adaptive_submission.py::_load_script` → `glob("**/<name>")` (loads
    `run_adaptive_selective_api` in `run/` AND `build_submission_variant` in `submission/`).
  - `run/run_adaptive_pilot.py`, `misc/select_adaptive_pilot_qids.py` → point at
    `legacy/run/run_adaptive_selective_api.py`.

## References updated

Production / entrypoint:
- `scripts/tools/final_infer.py` — `--mode v11_independent` runner →
  `scripts/legacy/run/run_full_v11_independent_submission.py` (verified resolvable).
- `scripts/docker_entrypoint.sh` (legacy pipeline entry) — `run_production_pipeline.py` →
  `scripts/legacy/run/run_production_pipeline.py`.
- `scripts/tools/audit_model_policy.py` `_EXCLUDE` — `audit_first100_consensus_risks.py` →
  `audit/…`, `export_risk_review_pack.py` → `misc/…`.
- `scripts/legacy/run/run_llm_full.sh` — internal refs → `legacy/benchmark/benchmark_runtime.py`,
  `legacy/checks/check_model_compliance.py`.

Tests (kept collected — coverage preserved, not deselected):
- Path-loading helpers / resolvers converted to recursive glob:
  `next(iter((_ROOT / "scripts" / "legacy").glob(f"**/{name}")), _ROOT / "scripts" / name)`
  (covers `name`/`{script}.py`/`{name}.py` variants, direct Path-join literals, and string
  literals `scripts/legacy/<name>` → categorized paths).
- `test_model_compliance.py` `sys.path` → `scripts/legacy/checks`.
- `test_adaptive_orchestrator.py` source-scan base → recursive glob.

Docs:
- `README.md`, `docs/{ARCHITECTURE,METHOD,MODEL_COMPLIANCE,DATASET_PROFILE}.md`,
  `src/README.md` — legacy references repointed to category paths (kept under
  "Legacy / research diagnostics only"; not promoted as a main workflow).

## Legacy README created

`scripts/legacy/README.md` — explains these are old research/diagnostic/experiment tools, NOT the
official submission workflow; states the official command
`bash scripts/run_full_system.sh <test_file>`; lists all 10 categories.

## Part D — production path unchanged

Unchanged this phase (verified via `git status`): `scripts/run_full_system.sh`,
`scripts/docker_entrypoint_v11.sh` (Dockerfile ENTRYPOINT), `src/fastmcq_system.py`,
`configs/production/{default,noapi}.json`, `configs/profiles/run_profiles.json`. `src/` and
`tests/` directory layouts were **not** moved (only test *references* updated).
`scripts/tools/final_infer.py` changed by exactly one line (the v11_independent runner path).

## Validations run / results

- `.venv/bin/python -m compileall -q src scripts tests` → **OK**
- `.venv/bin/python -m pytest -q` → **765 passed** (legacy deselected; same count as pre-phase)
- `.venv/bin/python scripts/audit_model_policy.py` → **RESULT: PASS — only competition-allowed
  models referenced** (scan now covers `scripts/legacy/<category>/`)

### Full-system no-API smoke
```
bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  [FASTMCQ] input_count=5 ... profile=production_full_system_noapi v12b_max_qids=auto(1/5) v13_max_qids=auto(1/5)
  status  : PASS
  output -> scratch/2l43e_smoke/pred.csv (FASTMCQ_FINAL_DIR)
    header: qid,answer
    qids  : sm1 sm2 sm3 sm4 sm5   (exactly the input qids)
```
(The gitignored smoke fixture had been cleaned; recreated a tiny 5-qid file per Part E.)

## Confirmations

- **No API calls** — smoke `--no-api`; model policy PASS.
- **No production logic changed** — only file locations + reference paths; orchestrator,
  selector, layers, configs, and the official command/profiles untouched.
- **No qid/answer hardcoding; no `463`** — no production logic touched; the only `463` is the
  cosmetic `public_api463` profile name.
- **`run_full_system.sh <test_file>` still works** — smoke PASS.
- **Docker `/data` → `/output/pred.csv` preserved** — `docker_entrypoint_v11.sh` unchanged.
- **Official historical CSVs preserved** — repo `output/` untouched; V13 md5
  `cb02fef569b31e7fb544abab46c0e282`.
- **Not committed.**

## Git status (summary; cumulative with uncommitted 2L.44D/E)

```
 33 M    (final_infer.py v11 path; audit_model_policy _EXCLUDE; tests' legacy refs; docs; …)
 11 R    (a portion of the legacy renames recorded as pure renames)
 63 RM   (legacy renames with depth/sibling edits)
  1 ??   (docs/audits/AUDIT_PHASE_2L43E_… ; scripts/legacy/README.md is a tracked rename target area)
```
74 legacy scripts moved via `git mv` (history preserved). Nothing committed.

## Remaining cleanup risks

- Legacy scripts are exercised by collected tests via **recursive glob** under
  `scripts/legacy/**`; if two legacy scripts ever share a basename across categories the glob
  would pick the first match. None currently collide (all 74 basenames are unique).
- The gitignored smoke fixture (`scratch/smoke_api/…`) is recreated on demand; not part of the
  repo.
- 2L.43E stacks on the still-uncommitted 2L.44D/2L.44E changes; commit all together when ready.
