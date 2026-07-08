# AUDIT 53: docs/ consolidation and cleanup

Date: 2026-07-08

## Scope

Aggressively consolidate and clean `docs/`. Create one current-system source-of-truth document
(`docs/FINAL_SYSTEM.md`), extract still-useful facts from the archive and audit history into it,
delete redundant/temporary/legacy/superseded documentation, correct documentation links, and reduce
`docs/audits/` to a single new audit. No production runtime code, Docker behavior, model, prompt,
generation parameters, I/O paths, CSV schemas, or organizer-facing commands were changed.

## Branch and HEAD SHA

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD SHA | `d504296ecf648a9a159f556b37df3607fc2d5e72` |
| HEAD subject | `BTC DockerHub default run` |

## Git status before (docs-relevant)

- Tracked under `docs/`: `ARCHITECTURE.md`, `METHOD.md`, `MODEL_COMPLIANCE.md`, `DATASET_PROFILE.md`,
  `BTC_SUBMISSION_COMPLIANCE.md`, `BTC_FINAL_COMPLIANCE_MATRIX.md`, `hackaithon.pdf`,
  `Vietnamese_Student_HackAIthon.pdf`, `archive/` (9 files), `audits/` (113 tracked `AUDIT_*`).
- Untracked under `docs/` (from earlier tasks this session): `CONFIGS_REVIEW.md`,
  `HANDOFF_FASTMCQ_AGENT.md`, `audits/AUDIT_49…`, `audits/AUDIT_50…`, `audits/AUDIT_51…`,
  `audits/AUDIT_52…`.
- Pre-existing unrelated working-tree changes (not part of this task): `D output/pred_v*.csv` (5
  files). Config-cleanup changes from the immediately prior task (Audit 52) were also uncommitted in
  the tree: `D configs/production/noapi.json`, `M configs/profiles/run_profiles.json`,
  `M tests/integration/test_production_auto_budget_2l44e.py`,
  `M tests/integration/test_run_profiles_2l38c.py`. None of these were touched by this task.

## Git status after (this task's changes)

- Created: `docs/FINAL_SYSTEM.md` (untracked), `docs/audits/AUDIT_53_docs_cleanup.md` (this file).
- Modified (documentation links only): `README.md`, `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`.
- Staged deletions (`git rm`): 125 tracked docs — `docs/ARCHITECTURE.md`, `docs/METHOD.md`,
  `docs/MODEL_COMPLIANCE.md`, all 9 `docs/archive/*`, and all 113 tracked `docs/audits/AUDIT_*`.
- Removed from working tree (were untracked, `rm`): `docs/CONFIGS_REVIEW.md`,
  `docs/HANDOFF_FASTMCQ_AGENT.md`, `docs/audits/AUDIT_49…`, `…AUDIT_50…`, `…AUDIT_51…`, `…AUDIT_52…`.

## Final docs/ tree

```
docs/
├── FINAL_SYSTEM.md                    # NEW — single source of truth
├── BTC_SUBMISSION_COMPLIANCE.md       # retained — competition compliance
├── BTC_FINAL_COMPLIANCE_MATRIX.md     # retained — competition compliance (link updated)
├── DATASET_PROFILE.md                 # retained — unique dataset profile
├── hackaithon.pdf                     # retained — OFFICIAL competition rules
├── Vietnamese_Student_HackAIthon.pdf  # retained — team final submission report (Vòng 2)
└── audits/
    └── AUDIT_53_docs_cleanup.md        # NEW — only remaining audit
```

## Exact files retained and why

| File | Reason |
|---|---|
| `docs/FINAL_SYSTEM.md` | New consolidated source of truth (architecture, components, strengths, limitations, evolution, reusable ideas, future direction, presentation summary). |
| `docs/BTC_SUBMISSION_COMPLIANCE.md` | Concise Dockerfile/CUDA/offline compliance checklist; competition evidence; accurate for the current offline image. |
| `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` | Full requirement-by-requirement compliance matrix; broader than the checklist, not a duplicate; competition evidence. |
| `docs/DATASET_PROFILE.md` | Unique, current public-test profile (463 samples, choice-count distribution, long-context share, edge cases); useful for input schema + presentation. |
| `docs/hackaithon.pdf` | OFFICIAL competition rules (Hội Sinh Viên Việt Nam, Thông báo Số 1, 11 pages). Competition evidence — keep. |
| `docs/Vietnamese_Student_HackAIthon.pdf` | Team final submission technical report (author Võ Quốc Linh, Bảng C, Vòng 2). Presentation-relevant — keep. |

## Exact files deleted

- **Intermediate/temporary (untracked):** `docs/CONFIGS_REVIEW.md`, `docs/HANDOFF_FASTMCQ_AGENT.md`,
  `docs/audits/AUDIT_49_pre_vck_repo_review.md`, `AUDIT_50_handoff_reconstruction.md`,
  `AUDIT_51_configs_review.md`, `AUDIT_52_configs_dead_entries_cleanup.md`.
- **Legacy/superseded root docs (tracked):** `docs/ARCHITECTURE.md` (legacy adaptive/dynamic design),
  `docs/METHOD.md` (mixed legacy + current), `docs/MODEL_COMPLIANCE.md` (old ≤9B/OpenRouter policy).
- **Archive research notes (tracked, 9):** `ADAPTIVE_REASONING_ARCHITECTURE.md`,
  `CALCULATION_SOLVER.md`, `CALCULATION_TAXONOMY.md`, `EVIDENCE_RERANKER.md`, `MCQ_VERIFIER.md`,
  `NEURAL_EVIDENCE_RERANKER.md`, `OPENROUTER_ROUND1_STRATEGY.md`, `PROJECT_STATUS_AND_ROADMAP.md`,
  `RESEARCH_STRATEGY.md`.
- **Old audits (tracked, 113):** every `docs/audits/AUDIT_INITIAL_SETUP.md`,
  `AUDIT_PROJECT_OVERVIEW.md`, `AUDIT_PHASE_*` (Phase 1 → 2L.47G), and
  `AUDIT_REMOVE_*_CLAUDE_COMMITS_*`.

Historical information remains fully recoverable from Git history.

## Archive files inspected — useful information extracted into FINAL_SYSTEM.md §7

- `CALCULATION_SOLVER.md` / `CALCULATION_TAXONOMY.md` → deterministic PAL-lite calculation solver:
  ~25 generic closed-form formula families, regex+arithmetic only (no `eval`/`exec`/qid), conservative
  override ≥0.95, "prefer no answer over a risky answer"; calculation ≈26% of the public set.
- `EVIDENCE_RERANKER.md` / `NEURAL_EVIDENCE_RERANKER.md` → in-question evidence reranking (hybrid
  lexical default; optional local BGE-M3 / Qwen3-Reranker-0.6B that fail closed, `local_files_only`);
  question-last packing for lost-in-the-middle; ~41% context reduction on public long-context.
- `MCQ_VERIFIER.md` → selective second-pass option-elimination verifier, override only on confident
  disagreement (≥0.80), triggered on uncertain/low-confidence/repair cases.
- `ADAPTIVE_REASONING_ARCHITECTURE.md` → selective routing/risk scoring across routes
  (calculation/long_context/short_knowledge/law_admin/ambiguous); formula cards retrieve *templates*
  not answers.
- `OPENROUTER_ROUND1_STRATEGY.md` → Round-1 ReAct node graph on `qwen/qwen3.5-9b` (legacy prototype).
- `RESEARCH_STRATEGY.md` / `PROJECT_STATUS_AND_ROADMAP.md` → problem framing, likelihood-based option
  scoring rationale, dataset structural properties (2–11 choices, mixed length), leaderboard-driven
  development.

These concepts are captured in `docs/FINAL_SYSTEM.md` §6 (evolution) and §7 (reusable legacy ideas),
explicitly labeled as **not currently running in production**.

## Audit files — essential facts preserved into FINAL_SYSTEM.md / this audit

- Accepted default Docker runtime architecture (`Dockerfile → inference.sh → predict.py` offline
  local model) — FINAL_SYSTEM §2–§3.
- Final model + contract: `Qwen/Qwen3-4B-Instruct-2507`, `/models/qwen3-4b-instruct-2507`,
  `/code/private_test.json` → `submission.csv` + `submission_time.csv` — FINAL_SYSTEM §1–§3, §10.
- Round-2 success (built/pushed/organizer-executed/accepted) — FINAL_SYSTEM §1, §4.
- Legacy public scores V10 77.75 → V11 78.40 → V12B 78.83 → V13 79.7 (OpenRouter `qwen3.5-9b`
  prototype, NOT the offline submission) — FINAL_SYSTEM §6.
- Config cleanup already completed (Audit 52: removed dead `configs/production/noapi.json` and the
  `public_noapi` / `public_api463` profiles) — recorded here; the config working-tree changes remain
  uncommitted and were not touched by this task.
- Known risks that remain relevant (UTF-8 BOM inputs; model-load failure aborts with no output;
  single-pass/batch-1; A–K parser scope; offline Qwen accuracy never benchmarked in-repo) —
  FINAL_SYSTEM §5.

## PDF identity and retention decisions

- `docs/hackaithon.pdf` — first page: "HỘI SINH VIÊN VIỆT NAM … THÔNG BÁO SỐ 1 … điều chỉnh thể lệ
  Cuộc thi 'Vietnamese Student HackAIthon 2026'". **Official competition rules document.** Retained
  as competition evidence.
- `docs/Vietnamese_Student_HackAIthon.pdf` — first page: "VIETNAMESE STUDENT HACKAITHON 2026 / BẢNG C
  - INNOVATOR / FASTMCQ Agent / FINAL SUBMISSION DOCUMENTATION … Author: Võ Quốc Linh …
  vquclinh/fastmcq-agent:latest". **Team-generated final submission technical report.** Retained for
  the final presentation. Neither PDF is a duplicate or obsolete copy; neither was edited or
  regenerated.

## Link updates

- `README.md`: three references to the deleted `docs/METHOD.md` repointed to `docs/FINAL_SYSTEM.md`
  (the "full method" link, the repository-structure listing, and the Documentation section). README
  Docker build/run/copy commands, paths, model instructions, and organizer-facing workflow were
  **not** changed.
- `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`: two `docs/METHOD.md:229-242` evidence references repointed to
  `docs/FINAL_SYSTEM.md` (§2–§3).
- `docs/audits/` references in README remain valid (the folder still exists with this audit).

## Validation commands and results

| Validation | Result |
|---|---|
| `find docs -type f` before/after | before 128 files → after 7 files (6 root + 1 audit) |
| Broken references to deleted docs in retained markdown (`README.md`, `DOCKER_SUBMISSION.md`, `src/README.md`, `docs/*.md`) | NONE — the only remaining mentions are the intentional "supersedes" prose inside `FINAL_SYSTEM.md`, not links |
| `git diff --stat -- Dockerfile inference.sh predict.py src/local_model src/utils` | EMPTY (no runtime source changed) |
| Organizer-facing `docker pull/run/build/cp` commands in `README.md` | unchanged (verified by inspection) |
| Retained PDFs readable + identified | `hackaithon.pdf` (official rules, 11pp), `Vietnamese_Student_HackAIthon.pdf` (team report) — both readable |
| Staged docs deletions | 125 tracked docs removed via `git rm` |

Not run (per constraints / environment): package install, model download, external API, Docker
build/push, real model inference. `pytest` remains unavailable in this environment (no venv); this
task changed no test logic, so no test run was required.

## Unresolved risks

- `FINAL_SYSTEM.md` cites some line ranges (e.g. in retained compliance docs) that will drift if
  files are later edited; the doc mostly uses file/section references to stay robust.
- The offline Qwen3-4B accuracy/timing is still not benchmarked in-repo (documented as a known gap in
  FINAL_SYSTEM §5) — unaffected by this docs task.
- The prior config-cleanup changes (Audit 52) remain uncommitted in the working tree; committing the
  docs cleanup should be coordinated with them or done as a separate, file-scoped commit.

## Rollback instructions

- Restore deleted tracked docs: `git checkout -- docs/ARCHITECTURE.md docs/METHOD.md
  docs/MODEL_COMPLIANCE.md docs/archive docs/audits` (or `git restore --staged --worktree <paths>`),
  which recovers every `git rm`-staged file from HEAD.
- Restore the untracked intermediate docs (CONFIGS_REVIEW/HANDOFF/AUDIT_49–52): recover from Git
  history of the session or regenerate; they were review artifacts, not part of HEAD.
- Revert the link edits: `git checkout -- README.md docs/BTC_FINAL_COMPLIANCE_MATRIX.md`.
- Remove the new files: `rm docs/FINAL_SYSTEM.md docs/audits/AUDIT_53_docs_cleanup.md`.

## Recommended next step

Commit the docs consolidation as a file-scoped commit (docs + the two link edits), coordinated with
the prior config-cleanup changes. Then proceed to the legacy-entrypoint audit
(`predict.py --legacy-dynamic-full`, `scripts/tools/final_infer.py`, `scripts/run/`, `run.py`) that
still pins the remaining `configs/` files, to decide relocation vs retirement.

## Required explicit statements

- No runtime source code was modified.
- No Docker behavior was changed.
- No model, prompt, generation parameter, input/output path, CSV schema, timing behavior, or
  organizer-facing command was changed.
- Historical information remains recoverable from Git history.
- `docs/FINAL_SYSTEM.md` is now the documentation source of truth.
- The previous intermediate review/handoff documents (`CONFIGS_REVIEW.md`,
  `HANDOFF_FASTMCQ_AGENT.md`, `AUDIT_49`–`AUDIT_52`) were intentionally removed.
- The previous audit files were intentionally removed after consolidation.
- No external API, model download, Docker build, or Docker push was performed.
- Pre-existing output CSV deletions and the prior config-cleanup working-tree changes were not
  touched.
- The only repository changes in this task are: create `docs/FINAL_SYSTEM.md` and
  `docs/audits/AUDIT_53_docs_cleanup.md`; edit links in `README.md` and
  `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`; delete the legacy/intermediate/archive/audit documentation
  listed above.
