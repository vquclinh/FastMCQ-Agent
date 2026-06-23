# Audit — Phase 2A: Dataset Profiling + Experiment Tracking

**Date:** 2026-06-19
**Branch:** `deployment` (Phase 1 + 1.1 committed as `8e63cee`)
**Scope:** Deep dataset profiling, sample-submission inspection, experiment-
tracking scaffolding, and supporting docs.
**Out of scope (unchanged):** real LLM inference, model downloads, external APIs,
the I/O contract, the existing `AlwaysASolver` baseline.

## 1. Summary of files created / modified

### Created
| Path | Purpose |
|---|---|
| `scripts/profile_dataset.py` | Stdlib-only dataset profiler → Markdown + JSON; also inspects an optional sample submission. |
| `docs/DATASET_PROFILE.md` | Auto-generated human-readable dataset report. |
| `experiments/README.md` | Experiment workflow + column reference. |
| `experiments/leaderboard_log.csv` | Leaderboard log with the baseline row seeded. |
| `docs/AUDIT_PHASE_2A_DATASET_PROFILING.md` | This audit. |

### Modified
| Path | Change |
|---|---|
| `README.md` | Added "Profile the dataset" and "Experiment logging" subsections (commands + links). |

### Generated (git-ignored, not committed)
- `outputs/dataset_profile.json` — machine-readable profile (regenerable).
- `outputs/pred.csv` — baseline predictions (regenerable).

No files were deleted or moved. Dataset, sample submission, and PDF are untouched.

## 2. Exact commands run

```bash
# Profiling
python3 scripts/profile_dataset.py --input public-test_1780368312.json --sample-submission submission_1780332147.csv

# Baseline still works
python3 run.py --input public-test_1780368312.json --output outputs/pred.csv
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred.csv

# Tests
python3 -m pytest -q                 # -> "No module named pytest" (not installed locally)
python3 tests/test_labels.py         # standalone fallback
python3 tests/test_data_io.py        # standalone fallback
```

## 3. Dataset profiling highlights

From `docs/DATASET_PROFILE.md` / `outputs/dataset_profile.json`:

- **463 samples**, QID pattern `test_####` (`test_0001`..`test_0463`).
- **Question length (chars):** min 12, median 173, mean ~1371, max 8712 — a long
  tail of passage-based items.
- **Choices per question are NOT fixed at 4.** Distribution:

  | # choices | 2 | 3 | 4 | 5 | 10 | 11 |
  |---|---:|---:|---:|---:|---:|---:|
  | samples | 3 | 6 | 318 | 1 | 134 | 1 |

  → **136 samples (29.4%) have more than 4 choices** (mostly a large 10-choice
  bucket); **9 samples have only 2–3 choices**. Dynamic A–Z labels are essential.
- **Long-context passage questions:** 100 (21.6%), via keywords `Đoạn thông tin`,
  `Nội dung:`, `Tiêu đề:`, `-- Đoạn văn`. **Short standalone (<200 chars):** 259 (55.9%).
- **Rough categories (heuristic, single-label):** math/calculation 121 (26.1%),
  general knowledge 101 (21.8%), reading comprehension 100 (21.6%), economics 49,
  physics 42, law/admin 21, history/geo/culture 12, chemistry 8, biology 6,
  safety/ethics 3. The big 10-choice bucket overlaps heavily with calculation/STEM
  items (LaTeX + numeric answer options).
- **Template/near-duplicate groups:** 0 found by the cheap normalized-prefix
  heuristic — there are similar-looking calculation problems (e.g. the cylinder
  rate-of-change items `test_0009`/`test_0013`) but their wording differs enough
  that no exact-prefix family forms. Documented honestly rather than forced.
- **Edge cases:** 9 total — **6 with duplicate answer choices** (`test_0021`,
  `test_0222`, `test_0265`, `test_0408`, `test_0448`, `test_0452`) and 3 extreme-
  length questions (>8000 chars).

## 4. Sample submission findings

`submission_1780332147.csv`:

- **Columns:** `qid,answer` (matches the contract).
- **Rows:** only **4** — `test_0001, test_0003, test_0004, test_0005`. It **skips
  `test_0002`** and covers just 4 of 463 qids, so it is an **illustrative format
  sample, not a full submission**.
- **Unique labels:** `A, B, C, D` only.
- **Supports labels beyond A–D:** **no evidence either way** — the tiny sample
  happens to use only A–D. This does **not** imply the grader rejects E–K; the
  dataset itself clearly requires labels up to K (11-choice question), so our
  pipeline must and does emit dynamic labels.
- **Covers full dataset:** no (4 / 463).

## 5. Validation / test results

- **Profiler:** ran cleanly; wrote `docs/DATASET_PROFILE.md` and
  `outputs/dataset_profile.json`.
- **`run.py`:** loaded 463 samples, `AlwaysASolver`, wrote 463 rows.
- **`validate_submission.py`:** **RESULT: PASS** (all qids present, no dups, no
  empties, all labels valid).
- **Tests:** `python -m pytest -q` → **"No module named pytest"** (pytest is in
  `requirements.txt` but not installed in this local env). Ran the built-in
  standalone runners instead: **all 14 passed** (6 `test_labels`, 8 `test_data_io`).
  No new tests were required for Phase 2A (profiling is a reporting tool); the
  baseline contract remains covered.

## 6. Git status

```
On branch deployment
modified:   README.md
Untracked:  docs/DATASET_PROFILE.md
            experiments/
            scripts/profile_dataset.py
```

`outputs/dataset_profile.json` and `outputs/pred.csv` are correctly git-ignored.
Phase 1 + 1.1 were already committed (`8e63cee deploy: initial competition
pipeline baseline`). Phase 2A changes are uncommitted, pending review.

## 7. Risks / caveats

- **Category heuristics are rough.** Keyword + priority-order matching; overlaps
  exist (a 10-choice "chemistry" calculation may land in `math_calculation`).
  Treat counts as indicative, not authoritative.
- **Template detection is intentionally cheap** (normalized 80-char prefix). It
  will miss reworded templates — hence the 0 result despite visually similar
  items. Acceptable for Phase 2A; revisit only if dedup becomes important.
- **Sample submission is not a coverage oracle.** Its A–D-only labels must not be
  read as "labels beyond D are invalid"; the data requires up to K.
- **`profile_dataset.py` writes into `docs/` and `outputs/` by default.** The MD
  report is committed; the JSON is git-ignored and regenerable.
- **pytest unavailable locally** — install via `pip install -r requirements.txt`
  to use `pytest -q` directly instead of the standalone fallback.

## 8. Recommended next steps (Phase 2B)

1. **Zero-shot LLM solver** subclassing `BaseSolver`, selected via
   `configs/default.yaml` (`solver:`), emitting a single dynamic label.
2. **Choice-aware prompting:** enumerate options with their labels (A, B, C, ...
   sized to the list) and parse the model's chosen label, keeping
   `postprocess.py`'s fallback.
3. **Handle the two dominant shapes** surfaced here: long Vietnamese reading-
   comprehension passages (truncation/segmentation) and 10-choice numeric/LaTeX
   calculation items.
4. **Truncation budget** for >5k-char questions (82 of them) so prompts fit.
5. **Log every attempt** in `experiments/leaderboard_log.csv`; fill in
   `leaderboard_score` after submitting.
6. **Add pytest** to the dev environment so the canonical test command runs.
