# Audit — Phase 2L.11A: Clean `outputs/` Before Full v6 Run

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Tidied the `outputs/` root so only **full-run** prediction/log files remain; all
smoke/diagnostic artifacts were **moved** (not deleted) into a timestamped archive.
Filesystem-only change — every `outputs/*` file except `.gitkeep` is gitignored, so
`git status` is unchanged apart from this new audit doc.

## Repo state before cleanup

Branch `main`, working tree clean. `outputs/` root contained 15 files + `.gitkeep`
and two dirs (`archive_before_cleanup/`, a stray empty `outputs/`). Model weights
gitignored (`.gitignore:20:models/`).

## CSV row-count classification

| File | rows (incl. header) | data rows | class |
|---|---|---|---|
| pred.csv | 464 | 463 | FULL |
| pred_phase2i0_baseline.csv | 464 | 463 | FULL |
| pred_phase2k3_openrouter_full.csv | 464 | 463 | FULL |
| pred_v2_calc_rerank.csv | 464 | 463 | FULL |
| pred_v3a_verifier_selective_smoke.csv | 22 | 21 | smoke → archived |

(No accuracy inferred — row counts only.)

## Files kept in `outputs/` root

```
.gitkeep
pred.csv
pred_phase2i0_baseline.csv          # 463 rows, full public submission -> kept
pred_phase2k3_openrouter_full.csv
pred_v2_calc_rerank.csv
run_phase2k3_openrouter_full.jsonl
run_v2_calc_rerank.jsonl
```

## Files moved to archive

Archive folder: `outputs/archive_before_cleanup/phase2_11a_20260621_123433/`

```
dataset_profile.json
input_v3a_verifier_selective_smoke.json
input_v3b_verifier_broad_smoke.json
neural_vs_lexical_bge_m3_chunk_report.jsonl
neural_vs_lexical_qwen3_reranker_chunk_report.jsonl
neural_vs_lexical_qwen3_reranker_full_chunk_report.jsonl
pip_freeze_before_flagembedding.txt
pred_v3a_verifier_selective_smoke.csv
run_v3a_verifier_selective_smoke.jsonl
```

(9 files moved. Nothing deleted. `neural_vs_lexical_qwen3_reranker_full_chunk_report.jsonl`
is the user's full long-context chunk smoke — archived as a diagnostic artifact.)

## Note: stray empty directory

`outputs/outputs/` exists and is **empty**. Left untouched per the "do not move
directories except the archive" constraint; it is harmless and can be removed
manually if desired (`rmdir outputs/outputs`).

## Validation results (preserved full submissions)

| File | validate_submission.py |
|---|---|
| pred.csv | **PASS** |
| pred_phase2k3_openrouter_full.csv | **PASS** |
| pred_v2_calc_rerank.csv | **PASS** |
| pred_phase2i0_baseline.csv | **PASS** |

## Confirmations

- No OpenRouter API call made.
- No full inference run.
- No new prediction CSV created; no full-run file modified or overwritten.
- No leaderboard upload.
- `.env` not read; no `OPENROUTER_API_KEY` printed/exposed.
- No source code modified.
- Model files untouched and not deleted.
- Model weights remain gitignored (`.gitignore:20:models/`); 0 model files tracked.
- Files were **moved** into the archive, not deleted.

## Final `outputs/` root listing

```
.gitkeep
pred.csv
pred_phase2i0_baseline.csv
pred_phase2k3_openrouter_full.csv
pred_v2_calc_rerank.csv
run_phase2k3_openrouter_full.jsonl
run_v2_calc_rerank.jsonl
```

## Final `git status --short`

```
?? docs/AUDIT_PHASE_2L11A_OUTPUTS_CLEANUP.md
```

(All `outputs/*` are gitignored, so the move produced no git changes; only this
audit doc is new.)

## Recommended next command — full v6 run (user runs manually; calls OpenRouter)

Flag names verified against `run.py --help`.

```bash
.venv/bin/python run.py \
  --solver openrouter_graph \
  --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 \
  --openrouter-max-tokens 1024 \
  --config configs/verifier_selective.yaml \
  --calculation-solver \
  --evidence-reranker \
  --evidence-reranker-method reranker \
  --evidence-reranker-model models/qwen3-reranker-0.6b \
  --evidence-candidate-top-k 12 \
  --mcq-verifier \
  --input public-test_1780368312.json \
  --output outputs/pred_v6_qwen_rerank_calc_verifier.csv \
  --save-raw \
  --log-path outputs/run_v6_qwen_rerank_calc_verifier.jsonl
```

After the run: validate with `scripts/validate_submission.py` and A/B-diff against
`outputs/pred_v2_calc_rerank.csv` / `outputs/pred.csv` before any leaderboard claim.

Do not commit. All changes left uncommitted for user review.
