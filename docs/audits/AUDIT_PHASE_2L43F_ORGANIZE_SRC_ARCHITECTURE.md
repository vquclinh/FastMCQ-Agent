# Audit — Phase 2L.43F: Organize `src/` Architecture by Module Type with Compatibility Shims

**Date:** 2026-06-24  **Branch:** `main`  **Base commit:** `891db48`  **Status:** structure reorg
(no commit, no API)

Resolves the long-deferred `src/` repackage (blocked in 2L.43B/2L.43D by the `src/utils.py` vs
`src/utils/` collision). Done safely with `sys.modules`-alias compatibility shims so every old
import path still works and resolves to the **same module object** as the new path.

## Part A — preflight (before any change)

`pytest -q` → **765 passed**; `compileall` OK; `audit_model_policy.py` PASS. Green → proceeded.

## How it was done (staged, validated after each)

1. **Relative → absolute imports.** Converted every `from .X import …` → `from src.X import …`
   in `src/*.py` (14 files; behavior-identical). This makes modules location-independent so they
   resolve through shims after moving. → 765 passed.
2. **`src/utils.py` collision resolved.** `git mv src/utils.py src/utils/logging.py`; created
   `src/utils/__init__.py` doing `from src.utils.logging import *` (+ explicit `log`,
   `load_config`). `from src.utils import log` and `from src.utils.logging import log` both work
   and are the same object. → 765 passed.
3. **Moved 63 flat modules into subpackages** (`git mv`) and left an alias shim at each old path:
   ```python
   # src/<name>.py
   import importlib as _il, sys as _sys
   _sys.modules[__name__] = _il.import_module("src.<sub>.<name>")
   ```
   plus the 7 util modules into `src/utils/`. A mapping assertion guaranteed every flat module
   was assigned (no module invented, none missed).

## Files moved (64 total, incl. utils.py)

| Subpackage | # | Modules |
|---|---:|---|
| `system/` | 4 | fastmcq_system, production_inference, production_policy, production_prompts |
| `base/` | 5 | dynamic_base_predictor, baseline_solver, answer_factory, solver_factory, solver_base |
| `layers/` | 15 | v12b/v13 layers + v13_layer_registry, mcq_permutation_debiaser, content_first_answerer, least_to_most_constraint_solver, programmatic_solver_layer, question_router, question_profiler, adaptive_* (6) |
| `api/` | 6 | openrouter_client, selective_api_client, openrouter_prompts, openrouter_graph_solver, api_candidate_agents, model_policy |
| `selector/` | 7 | system_candidate_selector, independent_answer_selector, candidate_answer, candidate_consistency, confidence, answer_ranker, mcq_verifier |
| `solvers/` | 10 | concept_solver, calculation_solver, calculation_first_planner, formula_bank_solver, formula_registry, hf_common, hf_generate_solver, hf_option_score_solver, programmatic_solver, pot_lite |
| `evidence/` | 9 | evidence_pack, evidence_reranker, evidence_sufficiency, evidence_verifier_policy, knowledge_cards, option_evidence, option_grounding, rag_lite, passage_compressor |
| `utils/` | 8 | logging (← utils.py), data_io, labels, output_parser, prompting, postprocess, run_logger, structured_answer |

## Shims created

63 alias shims at the old `src/<name>.py` paths (sys.modules alias to the new subpackage
module). `src/utils/` provides compatibility for the former `src/utils.py` via its `__init__`.
Verified from a clean process: `import src.v13_dynamic_layer, src.openrouter_client,
src.fastmcq_system, src.data_io, src.model_policy; from src.utils import log` → all OK.

## Final `src/` tree

```
src/
  __init__.py
  <63 compatibility shims>.py          # old flat paths -> new subpackages
  system/ (4)   base/ (5)   layers/ (15)   api/ (6)   selector/ (7)
  solvers/ (10) evidence/ (9)  utils/ (8: logging + 7)
  tool_solvers/ (7)   formula_cards/    # KEPT as-is (see below)
  README.md
```

### Kept as-is: `tool_solvers/` and `formula_cards/`
Already organized subpackages with internal cross-imports
(`from src.tool_solvers import _candidate_from_rule`, `from src.formula_cards import CARDS`).
Moving nested packages risks breaking those imports for **no flatness gain**, so they remain
top-level `src/` packages (documented deviation from the spec's `solvers/tool_solvers` layout).
Their consumers (`answer_factory`, `formula_registry`) import them unchanged.

## How the `src/utils.py` collision was resolved

`src/utils.py` (file) → `src/utils/logging.py`; `src/utils/__init__.py` re-exports it. The other
former-flat utilities live in the same package. `from src.utils import log` works via the
package `__init__`; `from src.utils.logging import log` is the explicit new path; both are the
same object.

## Production imports updated (Part E)

Prefer new paths in the headline files (old paths still work via shims):
- `scripts/tools/final_infer.py` → `src.utils.data_io`, `src.utils.labels`,
  `src.system.fastmcq_system`.
- `src/system/fastmcq_system.py` → `src.utils.data_io`, `src.utils.labels`,
  `src.base.dynamic_base_predictor`, `src.layers.v12b_dynamic_layer`,
  `src.layers.v13_dynamic_layer`, `src.selector.system_candidate_selector`.
- `scripts/tools/audit_model_policy.py` `_EXCLUDE` → added `src/api/model_policy.py` (the policy
  file legitimately names disallowed models as rejection examples; the old `src/model_policy.py`
  shim has no model names).
- Docker entrypoint: unchanged — it calls `final_infer.py`, which owns the imports.

## Tests

- No test required import edits: tests import src via `from src.X`/`import src.X` (124 sites),
  all covered by the shims (0 tests path-load src modules).
- Added `tests/unit/test_src_compatibility_imports_2l43f.py` (5 tests): old+new paths both
  import; old path **is the same object** as new (alias); `src.utils` compat; direct
  `import`/`from src import` statements; kept subpackages still importable.

## Part I — validations

- `compileall -q src scripts tests` → **OK**
- `pytest -q` → **770 passed** (765 baseline + 5 new; legacy deselected)
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
- **No production behavior changed** — structure-only: file moves + alias shims + import-path
  preference. Answer logic, selector thresholds, V12B/V13 policies, max-qid `auto` formula,
  OpenRouter behavior, model policy, I/O priority, and Docker behavior are untouched.
- **No qid/answer hardcoding; no `463`** — no logic touched.
- **`run_full_system.sh <test_file>` still works** — smoke PASS.
- **Docker `/data` → `/output/pred.csv` preserved.**
- **Official historical CSVs preserved** — repo `output/` untouched; V13 md5
  `cb02fef569b31e7fb544abab46c0e282`.
- **Not committed.**

## Git status (summary; cumulative with uncommitted 2L.44D/E + 2L.43E)

```
 96 M    (import edits, shims at old paths, audit _EXCLUDE, README, prior phases)
 63 RM   (src module renames into subpackages with edits)
 56 A / 15 AM   (new subpackage files / __init__.py)
 12 R
  3 ??   (this audit; tests/unit/test_src_compatibility_imports_2l43f.py; …)
```
64 src modules moved via `git mv` (history preserved). Nothing committed.

## Remaining risks

- **Alias shims rely on `sys.modules` reassignment.** This preserves object identity (good for
  monkeypatching) but adds one import indirection; a *new* hard top-level circular import between
  two modules could surface as a partial-module error. None exists today (full suite + smoke
  green), because the pre-move flat layout had no such cycle.
- `tool_solvers/` and `formula_cards/` remain top-level packages (deliberate; documented).
- This phase stacks on the still-uncommitted 2L.43E / 2L.44D / 2L.44E changes; commit together
  when ready. Consider committing the `src/` reorg as its own commit for a clean history.
