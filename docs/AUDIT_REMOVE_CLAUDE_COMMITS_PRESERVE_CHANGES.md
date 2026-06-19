# Audit — Remove Claude-Created Commits, Preserve Changes

**Date:** 2026-06-19
**Branch:** `main`
**Goal:** Remove the two most recent (Claude-created) commits from local history
so the user can commit the work themselves, while **preserving all file changes**
in the working tree. No work deleted, no new commit, no push/force-push.

> This audit file is intentionally **left uncommitted**, per instructions.

## 1. Original last 5 commits (before reset)

```
2dff905 docs: record commit hash in Phase 2FG.1 hardening audit   <- removed
4c2ac00 Implement adaptive multi-agent MCQA solver                 <- removed
9b371dc add model compliance and LLM environment setup            (kept, new HEAD)
f1181ea Merge pull request #1 from vquclinh/deployment
137269d add competitive local LLM solver framework
```

The two removed commits were confirmed to be the Claude-created checkpoint
commits (the adaptive multi-agent implementation + its hash-record follow-up).

## 2. Backup branch

```
backup/before-remove-claude-commits-20260619-190037
```

Created **before** the reset; it still points at `2dff905`, so both removed
commits are fully recoverable:

```
$ git log --oneline -2 backup/before-remove-claude-commits-20260619-190037
2dff905 docs: record commit hash in Phase 2FG.1 hardening audit
4c2ac00 Implement adaptive multi-agent MCQA solver
```

## 3. Reset command used

```bash
git reset --mixed HEAD~2
```

`--mixed` moves `HEAD` back two commits and unstages their changes, leaving every
modification in the working tree. **No `--hard`, no `--soft`, no new commit.**

## 4. Last 5 commits after reset

```
9b371dc add model compliance and LLM environment setup   <- new HEAD
f1181ea Merge pull request #1 from vquclinh/deployment
137269d add competitive local LLM solver framework
ad1f477 add dataset profiling and experiment tracking
8e63cee deploy: initial competition pipeline baseline
```

## 5. git status after reset

```
 M configs/default.yaml
 M docs/METHOD.md
 M docs/PROJECT_STATUS_AND_ROADMAP.md
 M docs/RESEARCH_STRATEGY.md
 M run.py
 M src/hf_option_score_solver.py
 M src/run_logger.py
 M src/solver_factory.py
?? docs/ARCHITECTURE.md
?? docs/AUDIT_PHASE_2D1_VENV_AND_FIRST_LLM_SMOKE.md
?? docs/AUDIT_PHASE_2D_REAL_MODEL_SMOKE.md
?? docs/AUDIT_PHASE_2E1_ARCHITECTURE_HARDENING.md
?? docs/AUDIT_PHASE_2E_RESEARCH_GROUNDED_MULTIAGENT_ARCHITECTURE.md
?? docs/AUDIT_PHASE_2FG_FULL_CORE_ADAPTIVE_AGENT_IMPLEMENTATION.md
?? docs/AUDIT_PHASE_2FG1_ADAPTIVE_AGENT_HARDENING_AND_COMMIT.md
?? src/adaptive_agent_solver.py
?? src/confidence.py
?? src/passage_compressor.py
?? src/question_profiler.py
?? src/question_router.py
?? tests/test_adaptive_agent_solver.py
?? tests/test_confidence.py
?? tests/test_passage_compressor.py
?? tests/test_question_profiler.py
?? tests/test_question_router.py
```

(Plus this audit file, `docs/AUDIT_REMOVE_CLAUDE_COMMITS_PRESERVE_CHANGES.md`,
added afterward and left uncommitted.) `.venv/` and `outputs/` remain git-ignored
and do not appear in status.

## 6. Validation commands and results

```bash
.venv/bin/python -m pytest -q                       # 84 passed
.venv/bin/python run.py --input public-test_1780368312.json --output outputs/pred_after_reset_check.csv
.venv/bin/python scripts/validate_submission.py --input public-test_1780368312.json --submission outputs/pred_after_reset_check.csv  # PASS
```

- **pytest: 84 passed** — the preserved working tree is fully functional.
- **Baseline:** 463 samples, solver `always_a`, **validate PASS**.

## 7. Confirmations

- **No work deleted.** All 21 changed files (8 modified + 13 untracked) are
  present in the working tree; the removed commits also survive on the backup
  branch.
- **No commit created.** `git reset --mixed` removed commits and created none;
  this audit is left uncommitted.
- **No push / force-push.** No network git operation was performed.
- **No `git reset --hard`.** Only `--mixed` was used.
- **`.venv` / `outputs` safe.** Confirmed git-ignored; not in status.

## 8. Recommended next step (for the user)

Review the changes and commit them under your own authorship, e.g.:

```bash
git add configs/default.yaml run.py src tests docs
git status --short                 # confirm no .venv/ or outputs/ staged
git commit -m "Implement adaptive multi-agent MCQA solver"
```

Once you are satisfied the commit is correct, you may delete the backup branch:

```bash
git branch -D backup/before-remove-claude-commits-20260619-190037
```

(Keep the backup until then — it is the only copy of the removed commit objects.)
You may also choose not to commit this audit file.
