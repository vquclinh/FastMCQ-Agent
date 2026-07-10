# `scripts/legacy/` — research / diagnostic / experiment tools

These are **old** research, diagnostic, audit, and experiment scripts from the development
history. **They are NOT part of the official submission workflow** and are kept for reference and
reproducibility only. The production architecture lives in `src/`.

**Official Docker/BTC command (use this):**

```bash
python predict.py       # run via inference.sh inside the Docker image; no flag required
```

The image's `CMD ["bash", "inference.sh"]` runs `python predict.py "$@"`, which by default runs
the confidence-routed pipeline and writes `/code/submission.csv` + `/code/submission_time.csv`.
See [`../../docs/FINAL_SYSTEM.md`](../../docs/FINAL_SYSTEM.md) and
[`../../DOCKER_SUBMISSION.md`](../../DOCKER_SUBMISSION.md). None of the scripts here, nor
`scripts/run_full_system.sh` / `scripts/docker_entrypoint_v11.sh`, are part of that official path
— those are separate, older, non-Docker development runners over the `src/system/`/`src/layers/`
modules, kept for reference only.

## Categories

| Folder | Contents |
|---|---|
| `analysis/` | `analyze_*`, `compare_*`, `profile_*`, `inspect_*`, `inventory_*` — dataset/result analysis |
| `audit/` | `audit_*` — candidate/quality/risk audits |
| `build/` | `build_*`, `plan_*` — candidate/plan builders (non-submission) |
| `run/` | `run_*` — legacy OpenRouter-era experiment runners (`run_llm_full.sh`, `run_llm_smoke.sh`, `run_local.sh`) |
| `review/` | `review_*` — candidate reviews |
| `repair/` | `repair_*`, `apply_*` — prediction repair / post-hoc fix appliers |
| `benchmark/` | `benchmark_*` — runtime / speed benchmarks |
| `submission/` | submission-candidate generation, ensembling, variants, runbook, output cleanup |
| `checks/` | `check_*` — environment / model-compliance checks |
| `misc/` | anything not fitting the above (e.g. `create_*`, `export_*`, pilot-qid selection) |

Scripts resolve the repo root via `Path(__file__).resolve().parents[3]` and load any sibling
legacy script by recursive glob under `scripts/legacy/**`, so they keep working from these
subfolders. They are intentionally excluded from the main docs' primary workflow.
