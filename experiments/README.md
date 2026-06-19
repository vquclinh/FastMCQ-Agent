# Experiments

This folder tracks leaderboard-driven development for FastMCQ-Agent. Every run
that we might submit (or learn from) gets one row in
[`leaderboard_log.csv`](leaderboard_log.csv).

## Workflow

1. Build or tweak a solver.
2. Generate predictions:
   ```bash
   python run.py --input public-test_1780368312.json --output outputs/pred.csv
   ```
3. Validate the submission:
   ```bash
   python scripts/validate_submission.py \
     --input public-test_1780368312.json --submission outputs/pred.csv
   ```
4. (Re)profile the data if it changed:
   ```bash
   python scripts/profile_dataset.py \
     --input public-test_1780368312.json \
     --sample-submission submission_1780332147.csv
   ```
5. Add a row to `leaderboard_log.csv` and, after submitting, fill in
   `leaderboard_score`.

## `leaderboard_log.csv` columns

| Column | Meaning |
|---|---|
| `date` | Run date (YYYY-MM-DD). |
| `version` | Short tag for the attempt (e.g. `phase2b-zeroshot-v1`). |
| `solver` | Solver class used (e.g. `AlwaysASolver`). |
| `model` | Model name/id, or `none` for non-LLM baselines. |
| `prompt` | Prompt strategy (`none`, `zero_shot`, `few_shot`, `cot`, ...). |
| `decoding` | Decoding settings (`deterministic`, `greedy`, `temp=0.7`, ...). |
| `runtime_notes` | Hardware, batch size, wall-clock, anything perf-relevant. |
| `local_validation` | `PASS`/`FAIL` from `validate_submission.py`. |
| `leaderboard_score` | Official score once known (blank until submitted). |
| `upload_file` | Path of the submitted CSV. |
| `notes` | Free-form: what changed, hypotheses, observations. |

## Conventions

- **One row per attempt.** Never overwrite a previous row — append.
- **Always validate before logging.** Only log `local_validation=PASS` runs as
  submission candidates; record `FAIL` runs too if they are informative.
- **Keep `version` tags sortable and descriptive** so the log reads as a history.
- Large prediction CSVs live in `outputs/` (git-ignored); reference them by path.
