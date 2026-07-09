# `src/` — FASTMCQ architecture (organized by system area)

The core package is organized into subpackages by system area. Import modules from their
subpackage, e.g.:

```python
from src.system.fastmcq_system import run_fastmcq_system, FastMCQSystemConfig
from src.layers.v13_dynamic_layer import run_v13_layer
from src.local_model.local_qwen_backend import get_local_qwen_backend
from src.utils.data_io import load_dataset
from src.utils import log
```

There are **no flat compatibility shims** at the `src/` root — every module lives in its
subpackage. (The earlier flat `src/<name>.py` paths from Phase 2L.43F were removed in 2L.43G.)

## Subpackages

### `system/` — orchestrator / production entrypoint
`fastmcq_system.py` (the dynamic full-system orchestrator: base → V12B → V13 → selector),
`production_inference.py`, `production_policy.py`, `production_prompts.py`.

### `base/` — base prediction & solver scaffolding
`dynamic_base_predictor.py`, `baseline_solver.py`, `answer_factory.py`, `solver_factory.py`,
`solver_base.py`.

### `layers/` — official layers + routing
`v12b_dynamic_layer.py`, `v13_dynamic_layer.py`, `v13_layer_registry.py`,
`mcq_permutation_debiaser.py`, `content_first_answerer.py`,
`least_to_most_constraint_solver.py`, `programmatic_solver_layer.py`, `question_router.py`,
`question_profiler.py`, and the adaptive routing/orchestration modules (`adaptive_routing.py`,
`adaptive_orchestrator.py`, `adaptive_agent_solver.py`, `adaptive_accuracy_planner.py`,
`adaptive_proposal_common.py`, `adaptive_types.py`).

### `local_model/` — shared local Qwen backend
`local_qwen_backend.py`, `qwen_mcq_predictor.py`, and `candidate_agents.py`.

### `selector/` — candidate selection / verification
`system_candidate_selector.py`, `independent_answer_selector.py`, `candidate_answer.py`,
`candidate_consistency.py`, `confidence.py`, `answer_ranker.py`, `mcq_verifier.py`.

### `solvers/` — domain solvers
`concept_solver.py`, `calculation_solver.py`, `calculation_first_planner.py`,
`formula_bank_solver.py`, `formula_registry.py`, `hf_common.py`, `hf_generate_solver.py`,
`hf_option_score_solver.py`, `programmatic_solver.py`, `pot_lite.py`.

### `evidence/` — retrieval & evidence
`evidence_pack.py`, `evidence_reranker.py`, `evidence_sufficiency.py`,
`evidence_verifier_policy.py`, `knowledge_cards.py`, `option_evidence.py`,
`option_grounding.py`, `rag_lite.py`, `passage_compressor.py`.

### `utils/` — I/O, labels, parsing, logging
`logging.py` (`log`, `load_config`), `data_io.py`, `labels.py`, `output_parser.py`,
`prompting.py`, `postprocess.py`, `run_logger.py`, `structured_answer.py`. `from src.utils
import log` works via `src/utils/__init__.py`.

### `tool_solvers/` and `formula_cards/`
Pre-existing organized subpackages (per-domain tool solvers; formula cards) with internal
cross-imports; imported as `from src.tool_solvers import …` / `from src.formula_cards import
CARDS`.

## Not user-facing

These modules are internal architecture, not commands. The official entrypoint is
`bash scripts/run_full_system.sh <test_file>` → `output/pred.csv` (Docker: `/output/pred.csv`).
