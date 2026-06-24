# `scripts/legacy/` — research / diagnostic / experiment tools

These are **old** research, diagnostic, audit, and experiment scripts from the development
history. **They are NOT part of the official submission workflow** and are kept for reference and
reproducibility only. The production architecture lives in `src/`.

**Official command (use this):**

```bash
bash scripts/run_full_system.sh <test_file>     # -> output/pred.csv
```

Docker: `/data/private_test.csv` (or `/data/public_test.csv`) → `/output/pred.csv` via
`scripts/docker_entrypoint_v11.sh`. None of the scripts here are required for that path.

## Categories

| Folder | Contents |
|---|---|
| `analysis/` | `analyze_*`, `compare_*`, `profile_*`, `inspect_*`, `inventory_*` — dataset/result analysis |
| `audit/` | `audit_*` — candidate/quality/risk audits |
| `build/` | `build_*`, `plan_*` — candidate/plan builders (non-submission) |
| `run/` | `run_*` — experiment/pipeline runners (incl. the experimental `run_full_v11_independent_submission.py` used by `final_infer.py --mode v11_independent`, and the legacy `run_production_pipeline.py` used by `docker_entrypoint.sh`) |
| `review/` | `review_*` — candidate reviews |
| `repair/` | `repair_*`, `apply_*` — prediction repair / post-hoc fix appliers |
| `benchmark/` | `benchmark_*` — runtime / speed benchmarks |
| `submission/` | submission-candidate generation, ensembling, variants, runbook, output cleanup |
| `checks/` | `check_*` — environment / model-compliance checks |
| `misc/` | anything not fitting the above (e.g. `create_*`, `export_*`, pilot-qid selection) |

Scripts resolve the repo root via `Path(__file__).resolve().parents[3]` and load any sibling
legacy script by recursive glob under `scripts/legacy/**`, so they keep working from these
subfolders. They are intentionally excluded from the main docs' primary workflow.
