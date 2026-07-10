# AUDIT 97 — Documentation Synchronization With Default Full Pipeline

## 1. Date, branch, starting HEAD

- **Date:** 2026-07-11
- **Branch:** `main`
- **Starting HEAD:** `ba5a8845c7011f76ec79145aa0f36bb9fdcd3337` — "promote confidence pipeline to
  default with divisor 20" (AUDIT 96's commit).

## 2. Initial Git status

`git status --short` was clean at the start of this task (no pre-existing uncommitted work). A
prior session's `docs/pitch/final_pitch_dossier.md`, `docs/pitch/slide_outline.md`, and
`docs/audits/97-final-pitch-dossier-and-research-grounding.md` were found to no longer exist in the
working tree and are absent from `git log` — they were apparently never committed and were lost
between sessions. This freed the `97-` audit-number slot for this task without conflict. No
unrelated user changes were present or at risk of being overwritten.

## 3. Source-of-truth files read

Before any edit: `docs/audits/94-*.md`, `docs/audits/95-*.md`,
`docs/audits/96-default-full-pipeline-and-budget-divisor20.md` (governing implementation state),
`Dockerfile`, `inference.sh`, `.dockerignore`, `predict.py` (execution-mode resolver, CLI flag
list, input resolver, output resolver via `grep`), `src/local_model/confidence_shadow_router.py`,
`src/local_model/confidence_config.py`, `configs/confidence_selective.yaml`,
`scripts/run_full_system.sh`, and every active Markdown file listed in §4.

## 4. Markdown inventory summary

Every `.md` file in the repository, excluding `.git/`, `scratch/`, `node_modules/`, `build/`,
`dist/`, and virtual environments:

| File | Category | Action |
|---|---|---|
| `README.md` | (1) current user-facing | Rewritten (Step 5) |
| `docs/FINAL_SYSTEM.md` | (2) current technical architecture | Rewritten (Step 3/7) |
| `DOCKER_SUBMISSION.md` | (3) Docker/submission/run instructions | Rewritten (Step 6) |
| `docs/BTC_SUBMISSION_COMPLIANCE.md` | (3) Docker/submission/run instructions | Patched: image name, canonical-doc pointer |
| `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` | (3)/(6) point-in-time compliance snapshot | Patched: image name, prominent staleness notice |
| `docs/DATASET_PROFILE.md` | (5) development/process (pure dataset stats) | Left unchanged — no pipeline-architecture claims |
| `src/README.md` | (5) development/process | Patched: corrected stale entrypoint claim |
| `scripts/legacy/README.md` | (5) development/process | Patched: corrected stale entrypoint claim |
| `docs/audits/*.md` (1–96) | (6) historical audit record | Left unchanged (immutable evidence) |
| `.pytest_cache/README.md` | generated (pytest boilerplate) | Excluded — not repository documentation |
| `docs/pitch/` (any file) | (4) pitch/presentation | Does not exist — see §7 |
| `docs/CURRENT_SYSTEM.md`, `docs/ARCHITECTURE.md` | (2) — would-be architecture docs | Do not exist; not created (see §7 — `docs/FINAL_SYSTEM.md` is the canonical document) |

No file fell into category (7) deprecated/duplicate requiring removal; the two compliance docs
were quasi-duplicative of `DOCKER_SUBMISSION.md`'s commands and were handled with a pointer notice
rather than deletion, per the task's explicit preference for notices over silent removal.

## 5. Historical files deliberately left unchanged

- All of `docs/audits/1-*.md` through `docs/audits/96-*.md` — immutable evidence, not rewritten.
- `docs/DATASET_PROFILE.md` — pure dataset statistics, no architecture/Docker claims to correct.
- Within `docs/FINAL_SYSTEM.md` §6 (System evolution): the Round-1/V10/V11/legacy-V12B/legacy-V13
  public-score table and the "Round 2 accepted with `vquclinh/fastmcq-agent:latest`" fact were
  preserved as historical record (two new rows were appended to reflect the subsequent
  confidence-routed promotion and the current final image, but nothing already-true was rewritten).

## 6. Active documentation files updated

- `README.md` — full rewrite (453 → 192 lines): current architecture, current image
  (`vquclinh/fastmcq-agent-final:latest`), default/custom Docker commands, `--base-only` escape
  hatch, `ceil(N/20)` budget explanation with the 2000→100 worked example, offline statement, links,
  honest evidence/limitations language. All 13 items from Step 5 are present.
- `docs/FINAL_SYSTEM.md` — full rewrite. §2 and §3 now describe the confidence-routed default
  pipeline end-to-end (Base → confidence scoring → router → V12B → V13 → selector → fallback →
  diagnostics), with an explicit table distinguishing the current `src/local_model/confidence_v12b_
  runner.py`/`confidence_v13_runner.py` from the legacy `src/layers/v12b_dynamic_layer.py`/
  `v13_dynamic_layer.py` (both are literally named "V12B"/"V13" — this distinction is the single
  highest-risk confusion point in the whole documentation set and is called out explicitly). §4/§5
  updated (removed the now-false "no confidence/risk routing" and "no offline V12B/V13-style
  refinement" limitations; added currently-true limitations, including the Windows/Docker
  Desktop/WSL2 operational risk documented in AUDIT 94/96). §6 evolution table extended with two new
  rows (confidence-routed promotion, current final image) without altering existing historical
  rows. §7 rewritten to mark each legacy idea as "now implemented" / "now implemented, differently"
  / "not yet implemented" against the current pipeline. §8 reframed from "future, not yet
  implemented" to "realized design intent, remaining genuine future work." §9/§10 updated
  accordingly, including adding the new `confidence_*.py` modules and `configs/confidence_selective
  .yaml` to the source-of-truth file table.
- `DOCKER_SUBMISSION.md` — full rewrite as the one canonical Docker guide: new image name/URL,
  explicit ENTRYPOINT/CMD contract statement, default run command with the correct mount contract
  and an explicit warning against mounting a host directory over `/code`, custom-path example,
  Windows PowerShell equivalent, an execution-mode table, and the required notes (full pipeline
  already default; `--confidence-full-pipeline` unnecessary for normal submission; `--base-only` is
  emergency/control use only). In its final, corrected form (after §24's follow-up pass) the default
  run command and the `--base-only` example both use a named container + `docker cp` (matching §12
  exactly, no `--rm`), since neither mounts an output directory; the custom-path, offline-verification,
  and PowerShell examples keep `--rm` because they mount `SUBMISSION_FILE`/`SUBMISSION_TIME_FILE`
  into a host-mounted directory. The previous "Optional local selective path" section's example
  command (`bash scripts/run_full_system.sh ...`) was removed — it actually invokes the unrelated
  `scripts/final_infer.py` legacy runner, not `predict.py --legacy-dynamic-full`, so it was not just
  stale but factually mismatched to the flag it was documenting (see §17).
- `docs/BTC_SUBMISSION_COMPLIANCE.md` — image name corrected throughout; added a scope note
  pointing to `docs/FINAL_SYSTEM.md` and `DOCKER_SUBMISSION.md` as canonical. Dockerfile-level
  compliance facts (base image, CUDA, offline env) were verified still accurate and left otherwise
  unchanged. In its final, corrected form, the `/app/data` sample-compatible example also uses a
  named container + `docker cp` (§24.1) since it does not mount an output directory.
- `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` — image name corrected throughout; a prominent notice was
  added at the top stating this is a point-in-time static-verification snapshot (Phase 2L.47G) and
  that its extensive `README.md:NN-NN` line-number citations were not re-verified line-by-line
  against the rewritten README (see §18 for the reasoning). In its final, corrected form, step 3's
  `/app/data` example also uses a named container + `docker cp` (§24.1) for the same reason.
- `src/README.md` — corrected the "official entrypoint" claim from
  `bash scripts/run_full_system.sh <test_file>` → `output/pred.csv` to the real Docker/BTC
  entrypoint (`predict.py` via `inference.sh`), and clarified that `run_full_system.sh` is a
  separate, non-Docker legacy runner.
- `scripts/legacy/README.md` — corrected the same stale "Official command" claim and the stale
  `/data/private_test.csv` → `/output/pred.csv` via `scripts/docker_entrypoint_v11.sh` Docker claim.

## 7. Deprecated/duplicate documents handled

No file required outright deprecation or deletion. `docs/BTC_SUBMISSION_COMPLIANCE.md` and
`docs/BTC_FINAL_COMPLIANCE_MATRIX.md` duplicate some Docker commands already in
`DOCKER_SUBMISSION.md`; rather than delete this duplication (they serve as evaluator-facing
compliance evidence with their own structure), both now carry an explicit pointer to
`DOCKER_SUBMISSION.md` as authoritative if the two ever diverge. `docs/pitch/` does not exist in
this working tree (see §2) — Step 8 (pitch documentation review) is therefore a no-op for this
pass; no pitch Markdown exists to review or correct. No new `docs/CURRENT_SYSTEM.md` or
`docs/ARCHITECTURE.md` was created, per the task's explicit preference: `docs/FINAL_SYSTEM.md`
already self-declared as the canonical current-system document and was updated in place.

## 8. Final architecture summary

```text
Input -> Base Qwen3-4B generation -> one-forward confidence scoring -> confidence router
  -> V12B for router-selected records -> V13 for V12B-unresolved records
  -> deterministic selector -> submission.csv / submission_time.csv
```

Every record receives Base generation and confidence scoring in the default full-pipeline mode; at
most `ceil(N/20)` genuine router candidates enter V12B; only V12B-unresolved records enter V13; the
candidate count can be smaller than the budget; the router never backfills. Any exception before
the official write reverts every row to Base. Full detail: `docs/FINAL_SYSTEM.md` §2–§3.

## 9. Final execution-mode table

| Flag | Behavior | Official answers |
|---|---|---|
| *(none)* | Full confidence pipeline (default) | Pipeline output |
| `--confidence-full-pipeline` | Explicit alias of the default; executed exactly once | Pipeline output |
| `--base-only` | Base-only escape hatch | Base generation only |
| `--confidence-v12b-shadow` | Router + V12B observational | Always Base |
| `--confidence-shadow-router` | Router observational, no V12B/V13 | Always Base |
| `--confidence-telemetry` | Confidence scoring recorded, no routing | Always Base |
| `--legacy-dynamic-full` | Isolated legacy dev path | Legacy selector output |

Verified against `predict.py`'s execution-mode resolver and its full `add_argument` list (both
inspected directly, not assumed from prior documentation).

## 10. Final Docker image and Docker Hub URL

- **Image:** `vquclinh/fastmcq-agent-final:latest`
- **Docker Hub URL:** <https://hub.docker.com/r/vquclinh/fastmcq-agent-final>

## 11. Verified default paths and ENTRYPOINT/CMD behavior

Verified directly from `Dockerfile` and `inference.sh` (not copied from prior docs):

- No `ENTRYPOINT`. `CMD ["bash", "inference.sh"]`, `WORKDIR /code`.
- `inference.sh` is exactly: `#!/usr/bin/env bash`, `set -euo pipefail`, `python predict.py "$@"`.
  With no extra `docker run` arguments, `predict.py` receives zero CLI flags.
- Input resolver priority (`predict.py`, `grep`-verified): `--input` → `$INPUT_FILE` →
  `/code/private_test.json` → `/code/public_test.json` → `/app/data/*.json` → `/data/*.json` →
  `/data/*.csv`.
- Output resolver (`predict.py`, `grep`-verified): `_resolve_out(args.submission,
  os.environ.get("SUBMISSION_FILE"), "submission.csv")` and the equivalent for
  `submission_time.csv` — default resolves relative to `WORKDIR /code`, i.e.
  `/code/submission.csv` and `/code/submission_time.csv`, with no env var or CLI flag required.
  `--output`/`$OUTPUT_FILE` and a legacy `/output/pred.csv` mirror remain additionally available.

## 12. Verified default BTC run command

```bash
docker rm -f fastmcq_btc_test 2>/dev/null || true

docker run \
  --name fastmcq_btc_test \
  --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent-final:latest

docker cp fastmcq_btc_test:/code/submission.csv ./submission.csv
docker cp fastmcq_btc_test:/code/submission_time.csv ./submission_time.csv

docker rm fastmcq_btc_test
```

No CLI path flags are required under this default mount contract — the input resolver finds
`/code/private_test.json` and the output resolver writes `/code/submission.csv` /
`/code/submission_time.csv` with no arguments. This already runs the full confidence pipeline; no
mode flag needed. This command deliberately does **not** use `--rm`: the outputs are written only
under `/code` inside the container (no output directory is mounted from the host in this example),
so the container must stay alive long enough to `docker cp` them out before it is removed. Using
`--rm` here would delete the container — and the only copies of `submission.csv` /
`submission_time.csv` with it — the instant the process exits. This is the single canonical default
command; every other reference to it in this document (§6, §24) is consistent with it.

## 13. Verified custom-path run command

```bash
docker run --rm --gpus all \
  -v "$PWD/btc_data/private_test.json:/code/private_test.json:ro" \
  -v "$PWD/btc_output:/code/btc_output" \
  -e SUBMISSION_FILE=/code/btc_output/submission.csv \
  -e SUBMISSION_TIME_FILE=/code/btc_output/submission_time.csv \
  vquclinh/fastmcq-agent-final:latest
```

Uses the real, currently supported `SUBMISSION_FILE`/`SUBMISSION_TIME_FILE` env vars (equivalently
`--submission`/`--submission-time` CLI flags), verified against `predict.py`'s `add_argument` calls
and `_resolve_out` priority (CLI flag > env var > default). Unlike §12, this command correctly uses
`--rm`: `SUBMISSION_FILE`/`SUBMISSION_TIME_FILE` point inside `/code/btc_output`, which is itself
bind-mounted from the host (`-v "$PWD/btc_output:/code/btc_output"`), so the outputs persist on the
host after the container is removed. This is the second half of the output-retrieval contract
stated in §12 and §24.3: named container + `docker cp` when the output is unmounted (default), `--rm`
allowed when the output directory is host-mounted.

## 14. Budget divisor and exact ceil(N/20) behavior

`budget_cap = max_targets_override` if explicitly set, else `ceil(N / budget_divisor)` with
`budget_divisor = 20` — confirmed as the dataclass default in
`src/local_model/confidence_shadow_router.py`, the fallback in
`src/local_model/confidence_config.py`, and the value in `configs/confidence_selective.yaml`
(all three unmodified in this documentation-only pass; last changed by AUDIT 96, which this task
does not re-litigate). `ceil`, not `floor`, is preserved per AUDIT 96's explicit reasoning.

## 15. Explicit proof/documentation that N=2000 gives 100

`ceil(2000 / 20) = ceil(100.0) = 100`. Documented with a worked-example table (N=30→2, N=120→6,
N=463→24, N=2000→100) in `README.md` and `docs/FINAL_SYSTEM.md` §3.

## 16. Paper-grounding corrections

Not applicable this pass: `docs/pitch/` does not exist in the working tree (§2, §7), so there is no
pitch Markdown containing research citations to review or correct. No paper titles, venues, or
citation relationships were touched. If `docs/pitch/` is recreated in a future session, it must be
checked against the research-grounding rules in this task's governing instructions before being
treated as current.

## 17. Stale claims removed

- "No-flag is Base-only" / "full pipeline is opt-in only" — corrected everywhere (`README.md`,
  `docs/FINAL_SYSTEM.md` §2 previously stated V12B/V13/selector were "Explicitly NOT part of the
  current default Docker runtime").
- "Router divisor is 8" / "routing budget is N/8" as a *current* claim — corrected; `ceil(N/8)` is
  now clearly scoped only to the legacy `--legacy-dynamic-full` path in `docs/FINAL_SYSTEM.md` §2's
  comparison table and §7.
- "2000 records allow 250 selected" — no such claim existed in the pre-edit active docs (grep
  confirmed no `250` occurrences); not present to remove, and the correct `ceil(N/20)=100` value is
  now documented.
- "V13 not integrated" / "selector is legacy-only" — corrected; `docs/FINAL_SYSTEM.md` §5 previously
  stated "No offline V12B/V13-style refinement in production" — removed and replaced with accurate
  current limitations.
- "`--base-only` doesn't exist" — not an actual prior claim (the flag already existed in code); the
  docs now document it explicitly as the emergency/control escape hatch.
- "Current image is `vquclinh/fastmcq-agent:latest`" — corrected to
  `vquclinh/fastmcq-agent-final:latest` in every active document (`README.md` ×9,
  `DOCKER_SUBMISSION.md` ×7, `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` ×7,
  `docs/BTC_SUBMISSION_COMPLIANCE.md` ×5, `docs/FINAL_SYSTEM.md` ×1); the two remaining occurrences
  of the bare old tag in `docs/FINAL_SYSTEM.md` §1 and §6 are intentional, explicitly labeled
  historical facts about the Round-2 acceptance, not current-state claims.
- "`fastmcq-local-selective`" image name — never found in the active doc set (grep-confirmed).
- Docker commands using unsupported paths/flags — the "Optional local selective path" example in
  the old `DOCKER_SUBMISSION.md` showed `bash scripts/run_full_system.sh path/to/private_test.json`
  as if it were an example of `--legacy-dynamic-full`; it actually runs a different script
  (`scripts/final_infer.py`) entirely. Removed from `DOCKER_SUBMISSION.md`; the `--base-only`
  example there now shows a real, verified command.
- "Official entrypoint is `bash scripts/run_full_system.sh <test_file>` → `output/pred.csv`" — this
  incorrect claim in `src/README.md` and `scripts/legacy/README.md` was corrected to point at the
  real Docker/BTC entrypoint (`predict.py` via `inference.sh`).
- No instance was found anywhere in the active doc set claiming organizer ground truth was used, or
  presenting internal synthetic accuracy as organizer accuracy — both `README.md` and
  `docs/FINAL_SYSTEM.md` explicitly state accuracy figures are from self-authored synthetic
  diagnostics only.
- No instance was found claiming every selected record necessarily reaches V13, or that all records
  run V12B/V13 — the "at most `ceil(N/20)`, router never backfills, only V12B-unresolved records
  reach V13" language is now explicit in `README.md`, `docs/FINAL_SYSTEM.md` §2/§3, and
  `DOCKER_SUBMISSION.md`.

## 18. Link/command validation

- All relative Markdown links added or retained in the updated files were checked against the
  filesystem: `docs/FINAL_SYSTEM.md`, `docs/BTC_SUBMISSION_COMPLIANCE.md`,
  `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`, `docs/DATASET_PROFILE.md`, `docs/hackaithon.pdf`,
  `docs/Vietnamese_Student_HackAIthon.pdf`, `docs/audits/96-default-full-pipeline-and-budget-
  divisor20.md`, `README.md`, `DOCKER_SUBMISSION.md`, `Dockerfile`, `inference.sh`, `predict.py` all
  confirmed to exist. `docs/audits/97-documentation-sync-current-architecture.md` (this file) is a
  forward reference from `docs/FINAL_SYSTEM.md` that resolves as of this file's creation. No active
  Markdown document contains a link to a nonexistent `docs/pitch/` file: `README.md` originally
  linked to `docs/pitch/final_pitch_dossier.md` and to the `docs/pitch/` directory itself, both
  hedged "(when present)" — a hedge annotation does not make a broken link acceptable, so both links
  were removed in the follow-up correction pass (§24.2) rather than left in place.
- No markdown-link-check tool exists in the repository (`node_modules`, no such binary found);
  per the task's explicit instruction not to add a new dependency solely for this task, link
  verification was performed manually as described above.
- Code-block syntax reviewed manually: Bash blocks use `\` line continuations; the one PowerShell
  block (`DOCKER_SUBMISSION.md`) uses backtick line continuations; no mixing found.
- No placeholder image name or tag (e.g. `<your-image>`, `TODO`, `xxx`) remains in any updated file
  (grep-reviewed).
- A full grep sweep for `budget_divisor`, `N/8`, `/ 8`, `Base-only default`, `opt-in`,
  `confidence-full-pipeline`, `fastmcq-agent:latest` (bare), `fastmcq-local-selective`,
  `private_test`, `submission.csv`, `submission_time.csv`, and `250` across every active,
  non-audit Markdown file was run and every match reviewed manually (§17 records the outcome).

## 19. `git diff --check` result

```text
$ git diff --check
(no output — exit 0)
$ git diff --cached --check
(no output — exit 0)
```

Only benign `LF will be replaced by CRLF` autocrlf notices were printed to stderr by the wrapping
`git diff` invocation; `--check` itself reported no whitespace or conflict-marker errors.

## 20. Remaining limitations or items requiring manual verification

- `docs/pitch/` does not exist in this working tree; Step 8 (pitch/citation review) could not be
  performed against real content this pass. If pitch documentation is recreated later, it must be
  checked against the research-grounding rules before being trusted as current.
- `docs/BTC_FINAL_COMPLIANCE_MATRIX.md`'s extensive `README.md:NN-NN` line-number citations were
  **not** re-verified line-by-line against the rewritten (much shorter) `README.md`; a prominent
  notice was added instead, per the pragmatic approach agreed for this pass. A future pass could
  re-derive exact line numbers if the matrix needs to remain byte-accurate.
- `docs/FINAL_SYSTEM.md` §5 flags that `programmatic_solver`'s exact formula-family coverage was
  not re-verified against the legacy ~25-family registry description in §7 as part of this
  documentation-only pass — this is a source-code comparison task, not a documentation task, and
  was left for a future, code-focused session.
- No real-model inference, Docker build, or Docker push was performed in this task (by design,
  per the task's restrictions) — the run commands in this pass are verified against the Dockerfile/
  `inference.sh`/`predict.py` contract by static inspection, not by execution.

## 21. Current Git status

```text
 M DOCKER_SUBMISSION.md
 M README.md
 M docs/BTC_FINAL_COMPLIANCE_MATRIX.md
 M docs/BTC_SUBMISSION_COMPLIANCE.md
 M docs/FINAL_SYSTEM.md
 M scripts/legacy/README.md
 M src/README.md
?? docs/audits/97-documentation-sync-current-architecture.md
```

7 files changed (533 insertions, 596 deletions per `git diff --stat`), plus this new audit file.
No production code was modified. No commit was made, per the task's restrictions.

## 22. Recommended next action

1. Review this diff (`git diff` / `git status`) and, if satisfied, commit it as a documentation-only
   change referencing AUDIT 96 and this audit.
2. When real Docker build/run access is available, execute the default BTC command in §12 and the
   custom-path command in §13 against a real `private_test.json` to confirm the documented
   contract matches actual behavior end-to-end (this pass verified it by static code inspection
   only, per the task's explicit restriction against running real-model inference or Docker).
3. If/when `docs/pitch/` is recreated, run the Step 8 research-grounding review against real
   content before treating any pitch document as current.
4. Consider a follow-up, code-focused (not documentation-only) task to verify
   `programmatic_solver`'s exact formula-family coverage against the legacy registry description,
   per §20.

## 23. Final verdict

CURRENT DOCUMENTATION SYNCHRONIZED WITH DEFAULT FULL PIPELINE

---

## 24. Follow-up correction pass — output-retrieval contract and broken pitch links

A second, smaller correction pass was made to this same documentation-sync change before commit,
addressing two defects the first pass missed.

### 24.1 Defect: `docker run --rm` combined with reliance on default `/code/submission*.csv`

Several examples across the updated docs used `--rm` while relying on the **default**, unmounted
`/code/submission.csv` / `/code/submission_time.csv` output paths. `--rm` deletes the container
(and everything written only inside it) the moment the process exits, so those examples would
silently produce no retrievable output — a real defect, not merely a stale claim. Every default
(non-host-mounted) `docker run` example was audited and fixed to use the canonical pattern:

```bash
docker rm -f <name> 2>/dev/null || true

docker run \
  --name <name> \
  --gpus all \
  -v "$PWD/private_test.json:/code/private_test.json:ro" \
  vquclinh/fastmcq-agent-final:latest

docker cp <name>:/code/submission.csv ./submission.csv
docker cp <name>:/code/submission_time.csv ./submission_time.csv

docker rm <name>
```

Fixed instances:

- `README.md` — "Escape hatch: Base-only" example (was `--rm` with no output mount; now named +
  `docker cp`, container `fastmcq_base_only`). The "Default BTC run" example was already correct
  from the first pass (container `fastmcq_btc_test`) and required no change.
- `DOCKER_SUBMISSION.md` — the "Run — BTC default" example (was `--rm` with a separate,
  contradictory "Retrieve" section immediately below showing the *correct* named-container
  pattern; the two were merged into one consistent block, container `fastmcq_btc_test`). The
  "Execution modes" `--base-only` example (was `--rm` with no output mount; now named + `docker cp`,
  container `fastmcq_base_only`).
- `docs/BTC_SUBMISSION_COMPLIANCE.md` — the `/app/data` sample-compatible run (was `--rm` with no
  output mount; now named + `docker cp`, container `fastmcq_app_data_test`).
- `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` — step 3, the `/app/data` path test (same fix, same
  container name for consistency).

Examples that already mount a host output directory and point `SUBMISSION_FILE`/
`SUBMISSION_TIME_FILE` into it (the "Custom input/output paths" examples, the offline
`--network none` verification examples, and the PowerShell equivalent) correctly keep `--rm` —
that satisfies the documented exception (custom-path example may use `--rm` only when the output
directory is host-mounted).

One additional, related defect: `DOCKER_SUBMISSION.md`'s "Legacy compatibility (old `/data` →
`/output/pred.csv`)" example uses `--rm` with `/output` host-mounted, which is a valid retrieval
strategy for `pred.csv` — but the accompanying prose overclaimed that the standard
`/code/submission.csv` / `/code/submission_time.csv` outputs were "in addition to" obtained by the
same run. Since `/code` is not mounted in that example and `--rm` is used, those two files are
written but not persisted. The prose was corrected to state this explicitly and to point at
`/output/pred.csv` as the artifact actually retrieved in that mode.

### 24.2 Defect: broken links to nonexistent `docs/pitch/` files

`README.md` contained two Markdown links into `docs/pitch/`, a directory confirmed not to exist in
this working tree (§2, §7): a link to `docs/pitch/final_pitch_dossier.md` (hedged "(when present)")
and a link to the `docs/pitch/` directory itself in the documentation list. Per the instruction that
a hedge annotation does not excuse a broken link, both were removed:

- The sentence pointing at the pitch dossier was shortened to end after the `docs/FINAL_SYSTEM.md`
  link (no dangling reference to nonexistent content).
- The `docs/pitch/` bullet was removed entirely from the "Documentation" list.

No other active document linked into `docs/pitch/` (only this AUDIT 97 file mentions the path, in
plain prose discussing its absence — not as a Markdown link).

### 24.3 Verified output-retrieval contract (final)

Every `docker run` example across `README.md`, `DOCKER_SUBMISSION.md`, `docs/FINAL_SYSTEM.md`,
`docs/BTC_SUBMISSION_COMPLIANCE.md`, and `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` was re-inspected
(`docs/FINAL_SYSTEM.md` has no `docker run` example blocks, only a passing mention of
`--network none`). Each now has exactly one of these two valid retrieval strategies:

1. **Named container + `docker cp`** (no `--rm`): used whenever the example relies on the default,
   unmounted `/code/submission.csv` / `/code/submission_time.csv` paths.
2. **Host-mounted output directory** (`--rm` allowed): used whenever the example sets
   `SUBMISSION_FILE`/`SUBMISSION_TIME_FILE` (or, for the legacy-compat mirror, `/output`) into a
   directory mounted from the host.

No remaining example combines `--rm` with reliance on an unmounted default output path.

### 24.4 `git diff --check` / `git status --short` (after this correction pass)

```text
$ git diff --check
(no output — exit 0)
$ git status --short
 M DOCKER_SUBMISSION.md
 M README.md
 M docs/BTC_FINAL_COMPLIANCE_MATRIX.md
 M docs/BTC_SUBMISSION_COMPLIANCE.md
 M docs/FINAL_SYSTEM.md
 M scripts/legacy/README.md
 M src/README.md
?? docs/audits/97-documentation-sync-current-architecture.md
```

Only benign `LF will be replaced by CRLF` autocrlf notices were printed to stderr; `--check`
reported no whitespace or conflict-marker errors. Same file set as §21 (no new files touched by
this correction pass beyond this audit). No production code was modified. No commit was made.

### 24.5 Verdict (unchanged)

CURRENT DOCUMENTATION SYNCHRONIZED WITH DEFAULT FULL PIPELINE
