# Audit — Phase 2L.43G: Remove Flat `src/` Compatibility Shim Clutter

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** structure
cleanup (no commit, no API)

Completes the `src/` reorg: 2L.43F moved real modules into subpackages and left 63 flat
compatibility shims at the `src/` root. This phase repointed every active import to the
subpackage paths and **deleted all 63 shims**, leaving a clean `src/` root.

## Shim files identified

63 flat `src/*.py` files, each of the form:
```python
import importlib as _il, sys as _sys
_sys.modules[__name__] = _il.import_module("src.<subpackage>.<module>")
```
The authoritative name→subpackage map was parsed from the shim bodies. None were imported by
production code in a way that the subpackage path couldn't replace (verified below).

## Imports updated

A scripted rewrite updated **three import forms** for every shimmed name across `src/**`,
`scripts/**`, `tests/**`, and docs (safe word-boundaries so e.g. `programmatic_solver` never
corrupted `programmatic_solver_layer`):
- `from src.<name> import …` → `from src.<sub>.<name> import …`
- `from src import <name>` → `from src.<sub> import <name>`
- `import src.<name>` → `import src.<sub>.<name>`  (≈161 files touched)

Plus non-`import` references that would break once shims were gone:
- **Test source-path reads** of `src/<name>.py` → repointed to the subpackage, or converted to a
  recursive glob `next(iter((_ROOT / "src").glob("**/<name>.py")))` for the cases that iterate
  module names at runtime (≈22 files).
- **`src/layers/v13_layer_registry.py`** metadata strings (`"module": "src.programmatic_solver_layer"`
  → `"src.layers.programmatic_solver_layer"`, +2).
- **`scripts/tools/final_infer.py`** source label string → `"src.system.fastmcq_system"`.
- **`scripts/tools/audit_model_policy.py`** `_EXCLUDE` already covers `src/api/model_policy.py`
  (from 2L.43F).
- Legacy scripts under `scripts/legacy/` were updated by the same rewrite (mechanical/simple).

Residual flat-import scan (`from src.<shim> import` / `import src.<shim>` /
`from src import <shim>`): **0** in active code.

## Shim files deleted

All 63 flat shims removed (guarded: each confirmed to contain `_sys.modules[__name__]` before
deletion). `src/__init__.py` and `src/README.md` preserved.

## Final top-level `src/` listing

```
src/
  __init__.py
  README.md
  api/  base/  evidence/  layers/  selector/  solvers/  system/  utils/
  tool_solvers/   formula_cards/
```
No flat module files remain at the `src/` root.

## Final `src/` package tree (module counts)

`system/`(4) `base/`(5) `layers/`(15) `api/`(6) `selector/`(7) `solvers/`(10) `evidence/`(9)
`utils/`(8, incl. `logging.py`) + pre-existing `tool_solvers/`(7) and `formula_cards/`.

## Files kept at root and why

- `src/__init__.py` — package marker (`__version__`).
- `src/README.md` — package documentation (updated to the shim-free structure).

No non-shim flat module remained, so nothing needed relocating or justifying beyond these two.

## Tests updated

- `tests/unit/test_src_compatibility_imports_2l43f.py` — rewritten: no longer requires old flat
  imports; now verifies new subpackage imports, the official full-system import, `src.utils`
  logging, the kept subpackages, the 8 subpackages exist, and **that no flat shim files remain at
  `src/*.py`** (only `__init__.py` + `README.md`).
- Source-path-reading tests (v13_multilayer, fastmcq_dynamic_system, layer_only, v13_dynamic,
  api_progress_resume, mcq_permutation, concept_solver, independent_v11, evidence_reranker,
  answer_factory, candidate_lab, accuracy_engine, production_layers/pipeline, formula_bank,
  selective_api, adaptive_branch_calibration, adaptive_orchestrator) → repointed to subpackage
  paths / recursive globs.

## Docs updated

- `src/README.md` — removed all "old flat paths remain as compatibility shims" language;
  documents the clean subpackage structure.
- `README.md`, `FINAL_RUN.md`, `DOCKER_SUBMISSION.md`, `docs/*.md` — `src/<name>` references
  repointed to subpackage paths (e.g. `src/selector/system_candidate_selector.py`,
  `src/layers/v12b_dynamic_layer.py`).

## Validations run / results

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **771 passed** (765 baseline + 6 in the rewritten compat test; legacy deselected)
- `audit_model_policy.py` → **RESULT: PASS — only competition-allowed models referenced**

### Full-system no-API smoke
```
bash scripts/run_full_system.sh scratch/smoke_api/smoke5_arbitrary_qids.json --no-api
  [FASTMCQ] input_count=5 ... profile=production_full_system_noapi v12b_max_qids=auto(1/5) v13_max_qids=auto(1/5)
  status  : PASS
  final pred header: qid,answer ; qids: sm1 sm2 sm3 sm4 sm5 (exactly the input)
```
Docker entrypoint still targets `/output/pred.csv` (2 references in `docker_entrypoint_v11.sh`).

## Confirmations

- **No API calls** — smoke `--no-api`; policy PASS.
- **No production behavior changed** — only import paths/locations; answer logic, selector
  thresholds, V12B/V13 policies, max-qid `auto` formula, OpenRouter behavior, model policy, I/O
  priority, and Docker behavior untouched.
- **No qid/answer hardcoding; no `463`** — no logic touched.
- **`run_full_system.sh <test_file>` still works** — smoke PASS.
- **Docker `/data` → `/output/pred.csv` preserved.**
- **Official historical CSVs preserved** — repo `output/` untouched; V13 md5
  `cb02fef569b31e7fb544abab46c0e282`.
- **Not committed.**

## Git status (summary; cumulative with uncommitted 2L.43E/2L.43F/2L.44D/2L.44E)

```
 75 R / 63 RM   src module renames (flat -> subpackage); the 2L.43F shim creation + 2L.43G
                deletion cancel out, so git records clean renames (0 stray deletes).
 75 M           import-path edits across src/scripts/tests/docs, README updates
  8 A / 4 ??    new subpackage __init__.py files / audits / etc.
```
Nothing committed.

## Remaining risks

- Any **external** caller that hard-codes an old flat import (`from src.v13_dynamic_layer import
  …`) would now fail — intended; there are no such callers in this repo (residual scan = 0).
- `tool_solvers/` and `formula_cards/` remain top-level packages (unchanged; deliberate).
- This phase stacks on the still-uncommitted 2L.43E/2L.43F/2L.44D/2L.44E changes; committing the
  `src/` reorg (2L.43F+2L.43G together) as one commit keeps history clean (git already shows it
  as renames).
