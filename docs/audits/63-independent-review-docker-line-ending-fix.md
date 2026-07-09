# AUDIT 63 — Independent Adversarial Review of the Docker Line-Ending Fix (AUDIT 62)

Audit number: 63 (no prior `63-*` existed under `docs/audits/`).

## 1. Date, branch, HEAD

- Date: 2026-07-10
- Branch: `selective-migration` (verified via `git branch --show-current`; matches the required branch)
- HEAD: `d0d8c28acbd1ebe2d6a85a772acd0b9ccc0d7866` (same commit as the failing image tag
  `vphuclinh/... :d0d8c28`)
- Mode: read-only verification. The only file created is this audit. No production file was
  repaired.

## 2. Files reviewed

- `docs/audits/62-fix-docker-shell-line-endings.md` (the fix's own audit — verified, not trusted)
- `.gitattributes` (new, untracked)
- `Dockerfile` (modified, unstaged)
- `inference.sh` + all 13 tracked `*.sh` files
- `.dockerignore`, root and nested `.gitattributes`, `.gitignore`

## 3. Methodology

Independent verification, not re-derivation from AUDIT 62: raw-byte inspection (Python), `git
check-attr`, `git ls-files --stage`, a from-scratch CRLF/LF/binary fixture simulation of the exact
Dockerfile command outside the repo, `bash -n` on every tracked script, full Dockerfile structural
read (not just the diff), `compileall`, focused + full pytest runs with failure-cause
classification, and a semantic scope diff against every forbidden runtime term.

## 4. Git working-tree findings

```
$ git status --short
 M Dockerfile
?? .gitattributes
?? docs/audits/62-fix-docker-shell-line-endings.md

$ git diff --stat
 Dockerfile | 8 +++++++-
 1 file changed, 7 insertions(+), 1 deletion(-)

$ git diff --check      -> clean
$ git diff --summary    -> (empty; no mode/type changes)
$ git diff --cached     -> (empty; nothing staged)
```

- Exactly one tracked file changed (`Dockerfile`); two untracked files exist (`.gitattributes`,
  AUDIT 62). This review adds a third untracked file (AUDIT 63).
- No unrelated source file changed. No `.py`, `.yaml`, `.json`, or `*.sh` file was modified.
- **No file-mode / executable-bit change** was introduced (`git diff --summary` empty). This is
  consistent with AUDIT 62.
- Nothing is staged.

## 5. Byte-level results (line endings / BOM / NUL / final newline)

| File | CRLF | LF | BOM | NUL | final NL | shebang |
|---|---|---|---|---|---|---|
| `.gitattributes` | 0 | 8 | no | no | yes | (n/a) |
| `Dockerfile` | 0 | 67 | no | no | yes | (n/a) |
| `inference.sh` | 0 | 5 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/docker_entrypoint.sh` | 0 | 18 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/docker_entrypoint_v11.sh` | 0 | 19 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/legacy/run/run_llm_full.sh` | 0 | 54 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/legacy/run/run_llm_smoke.sh` | 0 | 51 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/legacy/run/run_local.sh` | 0 | 18 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run/run_local_auto.sh` | 0 | 34 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run/run_private_local.sh` | 0 | 34 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run/run_private_local200.sh` | 0 | 34 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run/run_public_local100.sh` | 0 | 34 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run/run_public_local50.sh` | 0 | 36 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run/run_public_replay.sh` | 0 | 34 | no | no | yes | `#!/usr/bin/env bash` |
| `scripts/run_full_system.sh` | 0 | 90 | no | no | yes | `#!/usr/bin/env bash` |

All expectations met: every tracked `*.sh`, `Dockerfile`, and `.gitattributes` has CRLF = 0, no BOM,
no NUL, a final newline; `inference.sh` retains LF and a valid shebang. (The comment lines in
`.gitattributes`/`Dockerfile` contain UTF-8 em-dashes — multi-byte but not a BOM and not NUL.)

`git add --renormalize .` produced **no** `*.sh` byte change (it only re-adds the already-modified
`Dockerfile`, a content edit, not a line-ending change); index verified empty afterward via
`git reset`/`git diff --cached`. This confirms the committed `.sh` blobs were already LF and the
defect originated in the build-context checkout environment, exactly as AUDIT 62 states.

## 6. `.gitattributes` precedence and conflict review

Root `.gitattributes` content is exactly the intended narrow policy (plus explanatory comments):

```
*.sh text eol=lf
Dockerfile text eol=lf
Dockerfile.* text eol=lf
```

`git check-attr text eol` returns `text: set, eol: lf` for `inference.sh`,
`scripts/run_full_system.sh`, and `Dockerfile` — the policy is in effect.

Nested `.gitattributes` found only in `models/bge-m3/` and `models/qwen3-reranker-0.6b/`. Both are:
untracked; inside `models/` which is git-ignored (`.gitignore:25`) and excluded from the Docker
build context (`.dockerignore:50 models/`); contain only Hugging Face LFS rules
(`*.safetensors filter=lfs …`) with **no** `*.sh`, `eol`, `text=auto`, or `working-tree-encoding`
rule; and apply only within their own directory subtrees (which contain no shell scripts). They
cannot override the root policy for any shell script or Dockerfile. No other `eol=`/`text=auto`/
`working-tree-encoding` rule exists in any tracked `.gitattributes`. No broader or conflicting rule
was found.

## 7. Dockerfile ordering and semantic review

Structural map (line numbers):

- `WORKDIR /code` (18)
- `COPY requirements.txt .` (33) → `/code/requirements.txt` (no `.sh`)
- `COPY . /code` (38) — the only source copy
- Safeguard `RUN find /code -type f -name "*.sh" -exec sed -i 's/\r$//' {} + && chmod +x /code/inference.sh` (44–46)
- Model download to `/models/...` (51–57) — after the safeguard, writes no `.sh`
- `ENV LOCAL_MODEL_PATH/TRANSFORMERS_OFFLINE/HF_HUB_OFFLINE` (60–62)
- `CMD ["bash", "inference.sh"]` (67)

Checklist:

1. Build context is copied to `/code` ✔.
2. Safeguard runs **after** `COPY . /code` ✔ and **before** the model download and `CMD` ✔.
3. Dockerfile syntax valid (valid line continuations; no trailing whitespace after `\`; valid
   JSON-array CMD; final newline present) ✔.
4. POSIX-shell of the RUN is valid; idempotent; safe on already-LF files; limited to `*.sh`;
   cannot touch weights/prompts/Python/runtime mode ✔ (proven in §8).
5. `/code/inference.sh` exists when `chmod` runs (copied at line 38) ✔.
6. `find` and `sed` exist in `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04` (findutils/sed are part
   of the Ubuntu base rootfs) ✔.
7. Hard-failing `chmod` (via `&&`, no `|| true`) is intentional: if normalization/chmod ever fail,
   failing the build is safer than shipping a broken entrypoint ✔.
8. No `ENTRYPOINT` exists (before or after); `CMD` is byte-unchanged ✔.
9. No `COPY`/`ADD` occurs after the safeguard, so nothing can reintroduce CRLF into `.sh` files;
   `inference.sh` invocation only runs `python predict.py "$@"` and sources no other script ✔.
10. No later instruction overwrites `/code/inference.sh` ✔.

Semantic scope: the working-tree diff's only matches for forbidden runtime terms
(`local_qwen|Base|V12B|V13|selector|router|formula|parser|prompt|confidence|model|CUDA|torch|
transformers|private_test|submission|legacy-dynamic-full|CMD|ENTRYPOINT`) are in **comment** lines.
The functional lines `FROM nvidia/cuda`, `torch==2.7.1`, `download_local_model`, `LOCAL_MODEL_PATH`,
`TRANSFORMERS_OFFLINE`, `HF_HUB_OFFLINE`, and `CMD ["bash", …]` are byte-identical to HEAD.

## 8. CRLF-fixture simulation (exact Dockerfile command, outside the repo)

Fixtures in a temp dir: `crlf.sh` (CRLF, `set -euo pipefail`), `lf.sh` (LF), `fixture.bin`
(binary with CR bytes), `keep.txt` (CRLF non-`.sh`). Ran the exact
`find <root> -type f -name "*.sh" -exec sed -i 's/\r$//' {} +`:

| Fixture | Before | After 1st | After 2nd | Byte-identical when untargeted |
|---|---|---|---|---|
| `crlf.sh` CRLF | 3 | 0 | 0 | — |
| `lf.sh` | CRLF 0 | CRLF 0 | — | YES (md5 unchanged) |
| `fixture.bin` | CRLF 2 | CRLF 2 | — | YES (md5 unchanged) |
| `keep.txt` (non-.sh) | CRLF 2 | CRLF 2 | — | YES (md5 unchanged) |

`bash -n` passed for both scripts; the normalized `crlf.sh` executed and printed `PASS`. Confirms:
CRLF→LF on `.sh` only, LF files untouched, non-`.sh` (incl. binary) untouched, idempotent, and the
exact original failure (`set -o pipefail` under CRLF) is resolved. Fixtures deleted afterward; no
repo file touched.

## 9. Shell syntax results

`bash -n` passes for all 13 tracked `*.sh` (table verified in a clean bash subshell; an earlier
apparent failure was a zsh command-substitution word-split artifact in the reviewer's shell, not a
real syntax error — confirmed by direct `bash -n inference.sh` returning rc=0). Every script has a
valid `#!/usr/bin/env bash` shebang on line 1. `shellcheck` is not installed and was not installed
(per constraints); style linting not performed.

Note: git tracks all `*.sh` as mode `100644` (non-executable). This is **pre-existing** (not changed
by this fix) and harmless in the BTC path because (a) the Dockerfile runs `chmod +x
/code/inference.sh`, and (b) `CMD ["bash", "inference.sh"]` invokes via `bash`, which does not
require the execute bit. Recorded as Informational.

## 10. Dockerfile static validation

`docker`, BuildKit, and `hadolint` are **not available** in this environment, so `docker build
--check` / hadolint could not be run. No full `docker build` was attempted (forbidden and would
download weights). Validation was therefore a careful manual structural inspection (§7): line
continuations valid, no trailing whitespace after `\`, valid JSON-array `CMD`, final newline
present, and `find`/`sed`/`chmod` all available in the base image before use (they are in the base
rootfs, not dependent on the `apt-get` step). Build-cache note: the safeguard sits between
`COPY . /code` and the model-download layer, exactly where the previous `chmod` RUN sat, so it adds
no new cache invalidation — the model-download layer was already rebuilt on any source change
(pre-existing property, not introduced here).

## 11. Compile / test results

- `python -m compileall -q src scripts tests` → **PASS**.
- Focused: `pytest tests/integration/test_btc_submission_contract_2l47a.py
  tests/integration/test_full_system_output_contract_2l41a.py tests/unit/test_data_io.py
  tests/unit/test_labels.py -q` → **38 passed**.
- Full: `pytest tests -q` → **16 failed, 565 passed** — identical to the AUDIT 61/62 baseline.

## 12. Full-suite failure classification

All 16 failures are the pre-existing missing-frozen-artifact / public-replay class; none reference
line endings, the Dockerfile, `.gitattributes`, or shell scripts. Root causes:

- `output/pred_v11_independent_rerun1.csv` missing → `test_btc_short_2l31b` (2),
  `test_fastmcq_dynamic_system_2l36b` (3), `test_v13_dynamic_integration_2l37a` (1),
  `test_v12b_permutation_2l34b::test_frozen_v11_md5_stable`, `test_run_profiles_2l38c` (1),
  `test_final_package_2l31a` (several).
- `experiments/best_candidate_manifest.json` missing → `test_final_package_2l31a::
  test_manifest_freezes_v13_as_default`.
- `output/pred_v13_multilayer_candidate_api30_from_v12b.csv` missing →
  `test_v12b_permutation_2l34b::test_selector_validates_and_no_change_on_empty`,
  `test_v13_multilayer_2l35a::test_selector_validates_no_change_on_empty` (the lone AssertionError
  is the downstream "REFUSING: public frozen artifact not found" message for this same file).
- `output/pred_v10_full_production_user_run.csv` missing → `test_final_package_2l31a::
  test_v10_mode_is_fallback_copy`.

Independently verified as file-absence failures (not logic). No new or changed failure. Not
blocking; unrelated to this change.

## 13. Scope / non-regression confirmation

No functional runtime code changed. The Dockerfile edit replaces one build-time RUN
(`chmod +x inference.sh …`) with a CR-stripping + chmod RUN; it cannot alter default BTC mode,
selective (`--legacy-dynamic-full`) mode, model loading, GPU selection, input/output resolution,
generated answers, or runtime arguments — all of those live in Python/entrypoint files that are
byte-unchanged, and the model-path/offline/CMD Dockerfile lines are byte-identical to HEAD.

## 14. Reproducibility matrix

| Scenario | Protected by | Result |
|---|---|---|
| Linux checkout (LF) | git default + `.gitattributes` | LF — safe |
| Windows checkout, `core.autocrlf=true` | `.gitattributes eol=lf` (overrides autocrlf on checkout) | LF — safe |
| Windows editor saves a `.sh` as CRLF | Dockerfile safeguard (build-time strip); git renormalize on commit | safe in image |
| Stale clone made before `.gitattributes` committed | Dockerfile safeguard | safe in image |
| Clean clone after `.gitattributes` committed | `.gitattributes` | LF — safe |
| Build context with an untracked CRLF `.sh` | Dockerfile safeguard (`find` matches all `.sh` under `/code`, tracked or not) | safe in image |

Remaining unprotected scenario: running a shell script **outside Docker** from a non-git working
copy that acquired CRLF by some non-git means (e.g. a re-zipped download). `.gitattributes` covers
any git checkout; the Dockerfile covers any image build; a non-git, non-Docker copy run directly is
outside the BTC path and outside this fix's scope.

## 15. Security / build-context observations

- `find /code` is rooted at `/code`; `-type f` does not match symlinks and no `-L/-follow` is used,
  so it cannot traverse or write outside `/code`. No symlinked `*.sh` exists in the repo. Only
  `*.sh` regular files are edited by `sed -i`.
- No secrets, model files, archives, images, or binaries are modified; the model download is a
  later step writing to `/models`. No network operation, build ARG, or ENV was added/changed. No
  registry/Docker Hub state touched.
- `.dockerignore` correctly excludes `.env` (secrets), `.git` (measured 19 GB), `models/` (5.4 GB),
  `scratch/`, `output/` (except the required frozen CSVs), caches, and notebooks.
- **Informational (pre-existing, unrelated to this fix):** `Dockerfile.api` (git-ignored, ~4 KB) is
  **not** listed in `.dockerignore`, so `COPY . /code` would copy it into the image. It is not a
  `.sh` file (the safeguard does not touch it) and does not affect the line-ending fix. Consider
  adding `Dockerfile.api` to `.dockerignore` in a separate change; not modified here.

## 16. Findings by severity

- **Critical:** none.
- **High:** none.
- **Medium:** none.
- **Low:**
  - **L1 — Fix not yet committed (protection currently inactive).** `.gitattributes` is untracked
    and the `Dockerfile` change is unstaged/uncommitted. Until both are committed, a fresh clone
    receives neither the checkout-time LF enforcement nor the build-time safeguard. Affected:
    `.gitattributes` (untracked), `Dockerfile` (working tree). Consequence: a new build from a fresh
    clone on a CRLF environment could still reproduce the original failure. Reproducibility:
    deterministic until committed. Correction: commit both files (and the audits) on
    `selective-migration`; this is expected follow-up, not a source defect — recorded as a
    verification caveat, not a blocker.
- **Informational:**
  - **I1 — Tracked `*.sh` git mode is `100644` (non-exec).** Pre-existing; harmless because of the
    Dockerfile `chmod +x` and `bash inference.sh` invocation.
  - **I2 — `Dockerfile.api` not in `.dockerignore`** (see §15).
  - **I3 — Model-download layer rebuilds on any source change** (it follows `COPY . /code`).
    Pre-existing; the safeguard does not worsen it.
  - **I4 — No fresh image was built/run** to prove the fix end-to-end in a real container. The
    in-container hotfix from AUDIT 62 already demonstrated CR removal resolves the failure, so
    confidence is high, but a source-built smoke test is still recommended (verification caveat, not
    a source defect).

## 17. Final verdict

**SAFE TO KEEP WITH CAVEATS.**

The permanent fix is correct, minimal, and correctly scoped: the root cause (CRLF baked into the
image from a non-LF-enforced checkout) is independently confirmed; `.gitattributes` enforces LF at
checkout; the Dockerfile safeguard deterministically strips CR from `*.sh` at build, is idempotent,
touches nothing but shell text, and preserves the BTC CMD, I/O contract, model, and runtime modes.
Tests match baseline exactly. The caveats are operational, not defects: the change is **not yet
committed** (L1), and no fresh image has been built to prove it end-to-end (I4). Neither blocks
keeping the working tree.

## 18. Explicit confirmations

- No production code was modified (only this audit file was created).
- No full Docker image was built.
- No model was downloaded.
- No Docker image was pushed.
- No Git commit was created.
- No Git push was performed.
- No repository file was repaired/normalized during this review; the CRLF simulation ran only on
  throwaway temp fixtures, which were deleted.

## 19. Current repository state

```
$ git status --short
 M Dockerfile
?? .gitattributes
?? docs/audits/62-fix-docker-shell-line-endings.md
?? docs/audits/63-independent-review-docker-line-ending-fix.md

$ git diff --stat
 Dockerfile | 8 +++++++-
 1 file changed, 7 insertions(+), 1 deletion(-)
```

## 20. Recommended next steps

1. Commit `.gitattributes`, the `Dockerfile` change, and AUDIT 62/63 on `selective-migration` so
   both protection layers become active (resolves L1).
2. Continue local-selective quality work separately (out of scope here).
3. Only after review, build a **fresh source-based image** from this branch (not the hotfixed
   layer); optionally verify inside the image that `/code/inference.sh` reports CRLF = 0.
4. Rerun the official no-flag BTC Docker command and confirm `[predict] status: PASS`.
5. Optionally add `Dockerfile.api` to `.dockerignore` (I2) in a separate change.
6. Push new immutable + `latest` tags only after all runtime tests pass.
```
