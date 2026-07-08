# AUDIT 54: experiments/ and output/ cleanup

Date: 2026-07-08

## Scope

Determine whether `experiments/` is still necessary and, if it has no live executable or test
dependency, delete the entire directory. Also review repository-level generated artifacts under
`output/`. Runtime, Docker contract, model, prompt, generation parameters, I/O paths, CSV schemas,
timing behavior, and organizer-facing commands are invariant.

## Branch and HEAD SHA

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD SHA | `dd21ed8` (`clean legacy configs and consolidate documentation`) |
| Tracking | `main...origin/main` |

## Git status before

```
## main...origin/main
```
(Clean working tree. The earlier config/docs cleanup and the frozen-CSV removals were already
committed as `dd21ed8`.)

## Git status after

```
## main...origin/main
D  experiments/README.md
D  experiments/best_candidate_manifest.json
D  experiments/leaderboard_log.csv
?? docs/audits/AUDIT_54_experiments_output_cleanup.md
```
(No blanket `git add` was used. Nothing was committed. No unrelated file was staged or restored.)

## Purpose of every former experiment file

- **`experiments/best_candidate_manifest.json`** — legacy manifest freezing the "current best"
  candidate of the OpenRouter/V10–V13 *dynamic* research system. Recorded `production_default`,
  `recommended_final_csv`, per-version public scores (V10 77.75 / V11 78.40 / V12B 78.83 / V13 79.7),
  md5s, `official_layers`, and `score_progression`. **Legacy** — belongs to the pre-offline dynamic
  system, not the accepted Qwen3-4B runtime.
- **`experiments/leaderboard_log.csv`** — legacy leaderboard-driven development log. Contained only
  4 rows (header + 3 Phase-1 entries dated 2026-06-19: `phase1-baseline` PASS, `hf_generate_zero_shot_v1`
  PENDING, `hf_option_score_v1` PENDING). **No leaderboard scores were ever recorded in it.**
- **`experiments/README.md`** — documented the (legacy) leaderboard workflow and the CSV columns.
  Its example commands invoked `run.py` / `scripts/validate_submission.py` / `scripts/profile_dataset.py`,
  the legacy solver framework.

## Was `experiments/` used by the accepted default Docker runtime?

**No.** `experiments/` is explicitly excluded from the Docker build context (`.dockerignore:11`) and
is never imported or read by the default path (`predict.py` → `src.local_model.qwen_mcq_predictor` →
`src.utils.*`). `git diff -- Dockerfile inference.sh predict.py src/local_model src/utils` is empty.

## Was it used by any active legacy path or tests?

Only by **legacy, already-broken** consumers:

| Reference | Type | State |
|---|---|---|
| `scripts/legacy/audit/audit_production_candidate.py:27` (`_MANIFEST = "experiments/best_candidate_manifest.json"`) | legacy executable | Already non-functional — also depends on `scratch/full_v11.../...repaired.csv` and the frozen output CSVs, all removed in `dd21ed8`. |
| `tests/integration/test_final_package_2l31a.py:38` (reads the manifest) | active integration test | Already broken — the same test also reads `output/pred_v13_multilayer_candidate_api30_from_v12b.csv` and `output/pred_v10_full_production_user_run.csv` (its `_BEST`/`_V10`), both deleted in `dd21ed8`. |
| `docs/DATASET_PROFILE.md:160`; `scripts/legacy/analysis/profile_dataset.py:385`; `scripts/legacy/run/run_llm_full.sh:53` | documentation / historical prose / echo string | Not executable reads of the files. |
| `DOCKER_SUBMISSION.md:150`; `.dockerignore:11` | build-context exclusion | Remain mutually consistent after deletion (excluding an absent dir is a no-op). |

**Key context (pre-existing issue, not introduced here):** the prior cleanup commit `dd21ed8`
removed the five frozen `output/pred_v*.csv` artifacts but left **13 legacy integration tests** that
reference those filenames (`test_final_package_2l31a`, `test_btc_short_2l31b`,
`test_fastmcq_dynamic_system_2l36b`, `test_btc_noarg_2l32b`, `test_formula_bank_solver`,
`test_concept_solver`, `test_layer_only_api_profile_2l39d`, `test_independent_v11_2l30b`,
`test_v12b_permutation_2l34b`, `test_v13_multilayer_2l35a`, `test_v13_dynamic_integration_2l37a`,
`test_run_profiles_2l38c`, and `tests/legacy/test_v12_delta_2l34a`). These were already broken before
this task. Deleting the manifest does not create a new functioning breakage; it removes the last
data file of an already-orphaned legacy test/script cluster.

## Consumer classification (fresh repo-wide search)

- production executable: **none**
- legacy executable: `audit_production_candidate.py` (already broken), `profile_dataset.py` (echo
  string only), `run_llm_full.sh` (echo string only)
- test-only: `test_final_package_2l31a.py` (already broken by missing CSVs)
- documentation-only: `docs/DATASET_PROFILE.md:160` (historical prose)
- historical mention: `DOCKER_SUBMISSION.md:150`, `.dockerignore:11`
- dead reference: every path inside `best_candidate_manifest.json` (all 6 referenced files —
  `output/pred_v13/v12b/v11/v10*.csv` and `configs/production_v13_multilayer_7970.json` — `exist=False`)

Because no *production*, *functioning-test*, *retained-and-working-script*, or *documentation-link*
consumer requires `experiments/`, and the presentation-relevant scores are already preserved in
`docs/FINAL_SYSTEM.md`, the whole directory was deleted.

## Exact files deleted and retained

**Deleted (via `git rm`):**
- `experiments/best_candidate_manifest.json`
- `experiments/leaderboard_log.csv`
- `experiments/README.md`
- `experiments/` directory (now empty, auto-removed)

**Retained (unchanged):**
- `output/.gitkeep` — keeps the tracked local `output/` directory that legacy `final_infer.py` uses
  as its default local write target (`output/pred.csv`, `scripts/tools/final_infer.py:128`) and that
  `predict.py`'s legacy `/output/pred.csv` mirror can populate. Harmless; kept.
- `output/pred.csv`, `output/pred_final.csv` — **git-ignored local generated results**. Owner has not
  approved their removal and the task forbids deleting current local results without approval; left
  untouched.

## output/ folder findings

- `output/.gitkeep` — tracked; only tracked file under `output/`. Generated-dir placeholder; still
  useful (see above). Retained.
- `output/pred.csv`, `output/pred_final.csv` — ignored (`!!` in `git status --ignored`), locally
  generated. Not part of the production output contract (which is `/code/submission.csv` +
  `/code/submission_time.csv`). Retained (local results; not approved for deletion).
- The former legacy frozen artifacts (`pred_v8/v10/v11/v12b/v13*.csv`) were already removed in
  `dd21ed8`; none remain.

## References updated

**None.** No *functioning* reference breaks:
- The two references that would error at run time (`audit_production_candidate.py`,
  `test_final_package_2l31a.py`) are legacy and were already broken by `dd21ed8`; repairing the
  orphaned legacy test/script suite is out of this task's scope.
- The prose/echo mentions (`DATASET_PROFILE.md`, `profile_dataset.py`, `run_llm_full.sh`) are
  historical and were intentionally left per the "do not rewrite historical prose" rule.
- `.dockerignore:11` and `DOCKER_SUBMISSION.md:150` remain internally consistent.

`docs/FINAL_SYSTEM.md` does **not** mention `experiments/` and already preserves the V10–V13 scores
(lines 165–168), so no documentation update was required.

## Validation commands and results

| Check | Result |
|---|---|
| `git status --short --branch` (before) | clean (`## main...origin/main`) |
| `find experiments -maxdepth 2 -type f` (before) | 3 files (manifest, leaderboard, README) |
| `find output -maxdepth 2 -type f` (before) | `.gitkeep`, `pred.csv`, `pred_final.csv` |
| JSON parse `best_candidate_manifest.json` | PASS (valid); all 6 referenced paths `exist=False` |
| CSV parse `leaderboard_log.csv` | PASS; 4 rows, header 11 cols, no recorded scores |
| repo-wide search for the 3 files | only legacy/doc/historical refs (table above) |
| `git rm experiments/*` | OK; empty dir auto-removed |
| `git diff -- Dockerfile inference.sh predict.py src/local_model src/utils` | **empty (PASS)** |
| post-deletion broken-reference search | only pre-existing legacy/prose refs; no functioning break |
| `find output` (after) | unchanged: `.gitkeep`, `pred.csv`, `pred_final.csv` |
| pytest targeted run | **not run** — pytest is not installed and no venv exists; install prohibited |

## Final `experiments/` and `output/` trees

```
experiments/   -> deleted (directory no longer exists)

output/
├── .gitkeep          (tracked; retained)
├── pred.csv          (git-ignored local result; retained, untouched)
└── pred_final.csv    (git-ignored local result; retained, untouched)
```

## Unresolved risks

- **Orphaned legacy test/script suite (pre-existing):** ~13 legacy integration tests and the legacy
  `audit_production_candidate.py` reference frozen CSVs removed in `dd21ed8` and are already broken;
  `test_final_package_2l31a.py` additionally now references a deleted manifest. This task did **not**
  repair or delete them (out of scope). **Recommend a dedicated follow-up** to prune/repair the
  legacy dynamic-system tests and the legacy audit script, or to formally exclude them (e.g. move
  under `tests/legacy/`, which `tests/conftest.py` already ignores).
- pytest could not be executed here to demonstrate the tests' status; the breakage is established
  statically (referenced files confirmed missing).

## Rollback instructions

- Restore the deleted directory from the index/HEAD (file-scoped, no blanket commands):
  - `git checkout -- experiments/best_candidate_manifest.json experiments/leaderboard_log.csv experiments/README.md`
  - or `git restore --staged --worktree experiments/` then `git checkout -- experiments/`
- Remove this audit if reverting: `git rm docs/audits/AUDIT_54_experiments_output_cleanup.md` (it is
  currently untracked, so deleting the file suffices).
- No runtime or output file needs rollback (none were changed).

## Required explicit statements

- `experiments/` was **not** used by the accepted default Docker runtime (excluded by
  `.dockerignore`; no import/read on the default path).
- `experiments/` was referenced only by **legacy** consumers that were **already broken** by the
  prior `dd21ed8` frozen-CSV removal; it had no functioning active-test or production dependency.
- No production runtime code was changed.
- No Docker contract, model, prompt, generation parameter, I/O path, CSV schema, timing behavior, or
  organizer-facing command was changed.
- No Docker build/push, model download, or external API call occurred.
- Historical information (manifest scores, leaderboard entries) remains recoverable from Git history,
  and the V10–V13 scores are also preserved in `docs/FINAL_SYSTEM.md`.
- The only repository changes in this task are the deletion of the three `experiments/` files and the
  addition of this audit.
