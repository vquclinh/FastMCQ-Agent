# Audit — Initial Setup (Phase 1)

**Date:** 2026-06-19
**Scope:** Repository skeleton, data contract, baseline solver, validation,
Docker setup, and documentation for FastMCQ-Agent (HackAIthon 2026 — Board C).
**Explicitly out of scope:** any real LLM inference.

## 1. Summary of files created / modified

### Created
| Path | Purpose |
|---|---|
| `run.py` | Entry point: auto-detect input → baseline solve → write `pred.csv`. |
| `requirements.txt` | Minimal deps (PyYAML; pytest optional). |
| `Dockerfile` | `python:3.11-slim`, installs deps, default CMD runs `run.py`. |
| `.gitignore` | Ignores caches, venvs, runtime `data/*` and `outputs/*`. |
| `configs/default.yaml` | Config; Phase 1 uses `solver`, rest are Phase 2 placeholders. |
| `src/__init__.py` | Package marker + version. |
| `src/data_io.py` | Load/normalise JSON & CSV; read/write predictions. |
| `src/labels.py` | Index↔label conversion + validity (supports >4 choices). |
| `src/solver_base.py` | `BaseSolver` interface (`predict_one`/`predict_batch`). |
| `src/baseline_solver.py` | `AlwaysASolver` (format-check baseline). |
| `src/postprocess.py` | Validate, fallback to `A`, one answer per qid. |
| `src/utils.py` | Logging + optional YAML config loading. |
| `scripts/run_local.sh` | Run + validate end-to-end locally. |
| `scripts/inspect_dataset.py` | Dataset size/choice stats/schema. |
| `scripts/validate_submission.py` | Submission validator with pass/fail report. |
| `tests/__init__.py`, `tests/test_labels.py`, `tests/test_data_io.py` | Tests (pytest or standalone). |
| `data/.gitkeep`, `outputs/.gitkeep` | Keep runtime dirs in git. |
| `docs/METHOD.md` | Method placeholder + Phase 2 roadmap. |
| `docs/AUDIT_INITIAL_SETUP.md` | This audit. |

### Modified
| Path | Change |
|---|---|
| `README.md` | Replaced 2-line stub with full project docs. |

### Preserved (untouched)
`public-test_1780368312.json`, `submission_1780332147.csv`, `docs/hackaithon.pdf`.

## 2. Final directory tree

```
FASTMCQ-AGENT/
├── README.md                 (modified)
├── Dockerfile
├── requirements.txt
├── .gitignore
├── run.py
├── configs/
│   └── default.yaml
├── src/
│   ├── __init__.py
│   ├── data_io.py
│   ├── labels.py
│   ├── solver_base.py
│   ├── baseline_solver.py
│   ├── postprocess.py
│   └── utils.py
├── scripts/
│   ├── run_local.sh
│   ├── validate_submission.py
│   └── inspect_dataset.py
├── data/
│   └── .gitkeep
├── outputs/
│   └── .gitkeep
├── docs/
│   ├── hackaithon.pdf        (preserved)
│   ├── METHOD.md
│   └── AUDIT_INITIAL_SETUP.md
├── tests/
│   ├── __init__.py
│   ├── test_labels.py
│   └── test_data_io.py
├── public-test_1780368312.json   (preserved)
└── submission_1780332147.csv     (preserved)
```

## 3. Exact commands run

```bash
# Environment probe
python3 --version           # Python 3.14.5
# pyyaml available; pytest and pandas NOT installed

# Dataset inspection
python3 scripts/inspect_dataset.py --input public-test_1780368312.json

# Baseline run
python3 run.py --input public-test_1780368312.json --output outputs/pred.csv

# Submission validation
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred.csv

# Tests
python3 -m pytest -q          # -> "No module named pytest"
python3 tests/test_labels.py  # standalone fallback
python3 tests/test_data_io.py # standalone fallback

# Auto-detect verification (temp /data simulation)
# detect_input() correctly resolved public-test.json from a temp dir.
```

## 4. Validation / test results

**`inspect_dataset.py`** — 463 samples; choices min **2**, max **11**, avg **5.73**.
Confirms labels must extend beyond A–D.

**`run.py`** — loaded 463 samples, solver `AlwaysASolver`, wrote 463 rows to
`outputs/pred.csv`.

**`validate_submission.py`** — **RESULT: PASS** (exit 0). All qids present, no
duplicates, no empty answers, all labels valid.

**Tests** — pytest unavailable in this environment, so tests were run via their
built-in standalone runners. **All 14 passed:**

- `test_labels.py`: 6/6 (index↔label, roundtrip, case-insensitivity, `labels_for`,
  choice-count-aware validity, junk rejection).
- `test_data_io.py`: 8/8 (load public JSON; 3 CSV schemas; baseline all-`A`;
  write+validate baseline; invalid-label fallback; qid dedupe).

## 5. What was intentionally NOT implemented

- **No real LLM inference.** The only solver is `AlwaysASolver`. No models are
  downloaded, no external APIs are called, no secrets are used.
- **Config placeholders are inert.** `model`, `prompt`, `runtime` keys in
  `configs/default.yaml` are documented but unused in Phase 1.
- **No accuracy.** The baseline targets format correctness, not score.
- **No CI pipeline / linters configured** (kept minimal per the brief).

## 6. Risks / caveats

- **CSV schema heuristics.** `data_io.py` recognises `A,B,C,D`, `option_*`,
  `choice_*`, `opt_*`, and a single `choices` column (JSON or `| ; tab`
  delimited). An unusual real CSV header could be misparsed — mitigated by
  `validate_submission.py` catching resulting invalid/missing labels.
- **Docker default targets `/data/public-test.json`.** If BTC mounts a
  differently named file, run with no `--input` so auto-detect picks it up
  (documented in README and Dockerfile comments).
- **Label cap at 26 (A–Z).** Sufficient for the observed max of 11 choices;
  multi-letter labels (AA, AB) are not supported by design.
- **PyYAML optional at runtime.** If absent, config loading degrades to an
  empty dict rather than failing — Phase 1 behaviour is unaffected.
- **Python version.** Developed/tested on 3.14; Docker image pins 3.11-slim.
  Code uses only broadly-compatible stdlib features (`from __future__ import
  annotations` keeps the `X | Y` type hints safe).

## 7. Git status

Branch: `main`. At audit time:

```
 M README.md
?? .gitignore
?? Dockerfile
?? configs/
?? data/
?? docs/METHOD.md
?? outputs/
?? requirements.txt
?? run.py
?? scripts/
?? src/
?? tests/
```

Nothing committed yet (changes staged for review). Existing tracked files
(`public-test_1780368312.json`, `submission_1780332147.csv`,
`docs/hackaithon.pdf`) are unchanged. `outputs/pred.csv` and any `data/*` are
git-ignored.

## 8. Recommended next steps (Phase 2)

1. **Add an LLM solver** subclassing `BaseSolver`, selected via
   `configs/default.yaml` (`solver:`) — no `run.py` changes needed.
2. **Prompt formatting** of question + enumerated choices; map output to a
   single label with the existing `postprocess` fallback as a safety net.
3. **Account for Vietnamese, long passages, and variable option counts** (up to
   11) in prompting / scoring.
4. **Speed**: batching, quantization, and caching within the time budget;
   record latency alongside accuracy.
5. **Ablation harness** (METHOD.md §Ablation) comparing strategies on the
   public test.
6. **Add pytest to the runtime/CI image** so `pytest -q` is the canonical test
   command (today it falls back to standalone runners).
