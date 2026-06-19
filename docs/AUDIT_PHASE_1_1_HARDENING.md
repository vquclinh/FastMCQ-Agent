# Audit — Phase 1.1 Hardening

**Date:** 2026-06-19
**Scope:** Small hardening pass on top of Phase 1 — make the Docker default
command filename-agnostic, confirm `pytest` and `.gitignore` are correct, and
re-validate locally and in Docker.
**Out of scope:** any real LLM inference (unchanged: solver is still
`AlwaysASolver`).

## 1. Summary of changed files

| Path | Change |
|---|---|
| `Dockerfile` | **Changed.** Default `CMD` no longer hard-codes `--input /data/public-test.json`. It is now `["python", "run.py", "--output", "/output/pred.csv"]`, relying on `run.py`'s `/data` auto-detection. Comment updated to explain. |

### Verified already-correct (no change needed)
- **`requirements.txt`** — already contains `pytest>=7.0` (added in Phase 1).
  No reason to remove it, so left as-is. (Task 4 satisfied.)
- **`.gitignore`** — already ignores `outputs/*` and `data/*` while keeping
  `!outputs/.gitkeep` and `!data/.gitkeep` trackable. Runtime files like
  `outputs/pred.csv` are correctly ignored. (Task 5 satisfied.)
- **`run.py`** — already auto-detects input in `/data` (priority:
  `private_test.csv` → `private-test.json` → `public_test.csv` →
  `public-test.json` → any other sorted `.csv`/`.json`) and already defaults
  `--output` to `/output/pred.csv`. No change required.

No files were deleted. Preserved Phase 1 artifacts and the dataset/PDF are
untouched.

## 2. Exact commands run

```bash
# Local validation
python3 scripts/inspect_dataset.py --input public-test_1780368312.json
python3 run.py --input public-test_1780368312.json --output outputs/pred.csv
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred.csv
python3 -m pytest -q                  # -> "No module named pytest" (not installed)
python3 tests/test_labels.py          # standalone fallback
python3 tests/test_data_io.py         # standalone fallback

# Auto-detect verification for all four expected filenames (temp dirs)
# public-test.json / private-test.json / public_test.csv / private_test.csv -> all OK

# Docker validation
docker build -t fastmcq-agent .
mkdir -p tmp_data tmp_output
cp public-test_1780368312.json tmp_data/public-test.json
docker run --rm -v "$PWD/tmp_data:/data" -v "$PWD/tmp_output:/output" fastmcq-agent
python3 scripts/validate_submission.py --input public-test_1780368312.json --submission tmp_output/pred.csv

# Repeated with tmp_data/private-test.json to prove the filename is not hard-coded
# (then tmp_data/ and tmp_output/ removed)
```

## 3. Local validation results

- **`inspect_dataset.py`** — 463 samples; choices min **2**, max **11**, avg **5.73**.
- **`run.py`** — loaded 463 samples, solver `AlwaysASolver`, wrote 463 rows.
- **`validate_submission.py`** — **RESULT: PASS** (all qids present, no
  duplicates, no empty answers, all labels valid).
- **Auto-detect check** — `detect_input()` returned the correct file for each of
  `public-test.json`, `private-test.json`, `public_test.csv`, `private_test.csv`.
- **Tests** — `python -m pytest -q` failed with **"No module named pytest"**
  (pytest is listed in `requirements.txt` but not installed in this local
  environment). Ran the tests via their built-in standalone runners instead:
  **all 14 passed** (6 in `test_labels.py`, 8 in `test_data_io.py`).

## 4. Docker validation results

**Docker available:** yes (Docker version 29.5.2).

- **Build** — `docker build -t fastmcq-agent .` succeeded.
- **Run (public-test.json mounted):** container logged
  `input : /data/public-test.json`, loaded 463 samples, wrote 463 rows to
  `/output/pred.csv`. Validating the host-side `tmp_output/pred.csv`:
  **RESULT: PASS**.
- **Run (private-test.json mounted):** container logged
  `input : /data/private-test.json`, loaded 463 samples, wrote 463 rows.
  Validation: **RESULT: PASS**.

This confirms the hardening goal: the image picks up whatever input file is
mounted into `/data` without the filename being hard-coded. `tmp_data/` and
`tmp_output/` were removed after validation.

## 5. Git status

Branch: `main`. Nothing has been committed yet; all work remains uncommitted for
review. At audit time:

```
 M README.md
?? .gitignore
?? Dockerfile
?? configs/
?? data/
?? docs/AUDIT_INITIAL_SETUP.md
?? docs/METHOD.md
?? outputs/
?? requirements.txt
?? run.py
?? scripts/
?? src/
?? tests/
```

(The full set of untracked entries reflects that Phase 1 + Phase 1.1 have not
yet been committed. The only change made in this pass is to `Dockerfile`; the
`?? docs/AUDIT_PHASE_1_1_HARDENING.md` entry is this file.) Preserved files —
`public-test_1780368312.json`, `submission_1780332147.csv`,
`docs/hackaithon.pdf` — are unchanged. Runtime `outputs/pred.csv` is git-ignored.

## 6. Remaining risks / caveats

- **pytest not installed locally.** It is declared in `requirements.txt` (and
  installed inside the Docker image), but the host Python used here lacks it, so
  local CI relied on the standalone test runners. Install with
  `pip install -r requirements.txt` to use `pytest -q` directly.
- **Auto-detect priority favours private over public.** If BTC ever mounts both
  a private and a public file simultaneously, the private one wins. This matches
  the intended competition behaviour but is worth remembering.
- **Generic fallback is alphabetical.** If `/data` contains unexpected extra
  `.csv`/`.json` files, the first sorted one is chosen. Realistically the
  harness mounts a single dataset, so this is low-risk.
- **CSV schema heuristics** (from Phase 1) are unchanged; unusual headers could
  still be misparsed, but `validate_submission.py` would surface the result.
- **Still zero accuracy by design** — `AlwaysASolver` only guarantees a
  well-formed submission.

## 7. Recommended next steps (Phase 2)

1. Implement an LLM-backed solver subclassing `BaseSolver`, selected via
   `configs/default.yaml` (`solver:`) — no `run.py` pipeline changes needed.
2. Design prompt formatting for question + enumerated choices; map output back
   to a single label, keeping `postprocess`'s fallback as a safety net.
3. Handle Vietnamese text, long embedded passages, and variable option counts
   (up to 11).
4. Optimize for the time budget (batching, quantization, caching) and record
   latency alongside accuracy.
5. Build the ablation harness described in `docs/METHOD.md`.
6. Ensure `pytest` is available in the dev/CI environment so `pytest -q` is the
   canonical test entry point.
