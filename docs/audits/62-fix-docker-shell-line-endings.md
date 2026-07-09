# AUDIT 62 — Permanent Fix for Docker Shell-Script Line-Ending Bug (CRLF → LF)

## 1. Date and branch

- Date: 2026-07-09
- Branch: `selective-migration` (confirmed via `git branch --show-current`)
- HEAD at start: `d0d8c28acbd1ebe2d6a85a772acd0b9ccc0d7866` (same commit as the failing image tag)
- Scope: line-ending / Docker build hardening ONLY. No runtime, model, or logic change.

## 2. Confirmed root cause

The repository had **no `.gitattributes`**, so line endings for `*.sh` were not enforced at
checkout. When the build context was produced on a CRLF-normalizing environment (e.g. a Windows
checkout with `core.autocrlf=true`, or an editor that saved CRLF), the shell scripts on disk gained
Windows `\r\n` endings. `Dockerfile` then copies the build context verbatim:

```dockerfile
COPY . /code
```

so the CRLF bytes were baked into the image. Under Linux `bash`, a script whose first line is
`#!/usr/bin/env bash\r` and whose `set -euo pipefail` line ends in `\r` fails because bash sees the
option token as `pipefail\r`, which is not a valid option name.

Note: in THIS Linux working tree the tracked `*.sh` blobs are already stored and checked out as LF
(`core.autocrlf` unset/false; `git add --renormalize .` produces no byte change for any `.sh`). The
defect therefore originated in the **build-context checkout environment**, not in the committed
bytes — which is exactly why a repo-level policy (`.gitattributes`) plus a build-time safeguard is
the correct permanent fix.

## 3. Original Docker error

```
: invalid option name set: pipefail
```

(emitted by `bash inference.sh` inside the container for the no-flag BTC default run of
`vquclinh/fastmcq-local-selective:d0d8c28`).

## 4. Original byte evidence

Inside the failing image, `/code/inference.sh` reported:

```
CRLF: 5
LF: 5
```

and its leading bytes were:

```
b'#!/usr/bin/env bash\r\n...'
```

i.e. every one of the 5 logical lines was terminated with `\r\n`.

## 5. Why the temporary hotfix proved the diagnosis

A throwaway in-container hotfix stripped the carriage returns:

```
sed -i 's/\r$//' /code/inference.sh
```

After it, the same file reported:

```
CRLF: 0
LF: 5
```

and the **unchanged** official BTC default run then completed successfully:

- host `private_test.json` mounted to `/code/private_test.json`;
- image default `CMD ["bash", "inference.sh"]` with no runtime flags;
- local Qwen model loaded;
- all input samples predicted;
- `/code/submission.csv` written;
- `/code/submission_time.csv` written;
- ended with `[predict] status: PASS`.

Because the ONLY change between failure and success was CR removal (no code, no model, no CMD
change), the carriage returns are conclusively the sole cause. This permanent fix reproduces that
CR removal at the source and at build time.

## 6. Files changed

| File | Change | Type |
|---|---|---|
| `.gitattributes` | created | new file (permanent checkout policy) |
| `Dockerfile` | LF-normalization + chmod safeguard added right after `COPY . /code` | modified (1 RUN step) |
| `docs/audits/62-fix-docker-shell-line-endings.md` | this audit | new file |

No `*.sh` file needed byte modification — all tracked shell scripts were already LF in this tree
(see §9). No logic in any shell script was altered.

## 7. Exact `.gitattributes` rules added

```gitattributes
# Line-ending policy (see docs/audits/62-fix-docker-shell-line-endings.md).
# Shell scripts and Dockerfiles MUST be checked out with Unix LF endings so the
# Linux container never receives CRLF — CRLF breaks `set -o pipefail` in bash
# (": invalid option name set: pipefail"). Rules are intentionally narrow so no
# binary file is ever rewritten.
*.sh text eol=lf
Dockerfile text eol=lf
Dockerfile.* text eol=lf
```

The rules are deliberately narrow (`*.sh`, `Dockerfile`, `Dockerfile.*`). No `* text=auto` or other
broad rule was added, so no binary file (model weights, images, archives) can be unexpectedly
rewritten. Verified in effect:

```
$ git check-attr text eol -- inference.sh scripts/run_full_system.sh Dockerfile
inference.sh: text: set              inference.sh: eol: lf
scripts/run_full_system.sh: text: set  scripts/run_full_system.sh: eol: lf
Dockerfile: text: set                Dockerfile: eol: lf
```

## 8. Exact Dockerfile safeguard added

Inserted immediately after `COPY . /code` (replacing the prior tolerant
`RUN chmod +x inference.sh 2>/dev/null || true`):

```dockerfile
# Defensive line-ending hardening (see AUDIT 62): strip any trailing CR from
# shell scripts copied into the image so they run under Linux bash even if the
# build context came from a CRLF checkout. CRLF breaks `set -o pipefail`. This
# only touches *.sh text; it never alters model weights, prompts, or runtime mode.
RUN find /code -type f -name "*.sh" \
      -exec sed -i 's/\r$//' {} + \
    && chmod +x /code/inference.sh
```

Placement and behavior:

- **Where files are copied:** `COPY . /code` (Dockerfile line 38); `WORKDIR` is `/code`.
- **Where LF normalization happens:** the RUN step immediately after that COPY (before the model
  download step and before the final `CMD`).
- **Why it runs before the default CMD:** the image layers execute top-to-bottom at build time; the
  normalization bakes LF endings into `/code/*.sh` during build, so by the time `CMD ["bash",
  "inference.sh"]` runs at container start the file is guaranteed LF and executable.
- **Why it does not affect model weights or runtime behavior:** the `find … -name "*.sh"` filter
  touches only shell text and removes only trailing `\r`; model weights are downloaded in a *later*
  step to `/models/...` (never matched by `*.sh`); no prompt, parser, routing, selector, model path,
  CUDA/torch pin, CMD, or ENV is touched. `chmod +x /code/inference.sh` preserves the executable bit
  the previous step provided.

The final `CMD ["bash", "inference.sh"]` is unchanged; the BTC input/output contract
(`/code/private_test.json` → `/code/submission.csv` + `/code/submission_time.csv`) is unchanged.

## 9. All shell files normalized

All 13 tracked `*.sh` files were byte-checked. Every one already had CRLF = 0 (LF only), so no byte
rewrite was required; `.gitattributes` now guarantees they stay LF on every future checkout, and the
Dockerfile safeguard scrubs any CRLF that a non-conforming build context could still introduce.

```
path                                             CRLF   LF
inference.sh                                        0    5
scripts/docker_entrypoint.sh                        0   18
scripts/docker_entrypoint_v11.sh                    0   19
scripts/legacy/run/run_llm_full.sh                  0   54
scripts/legacy/run/run_llm_smoke.sh                 0   51
scripts/legacy/run/run_local.sh                     0   18
scripts/run/run_local_auto.sh                       0   34
scripts/run/run_private_local.sh                    0   34
scripts/run/run_private_local200.sh                 0   34
scripts/run/run_public_local100.sh                  0   34
scripts/run/run_public_local50.sh                   0   36
scripts/run/run_public_replay.sh                    0   34
scripts/run_full_system.sh                          0   90
ALL_SH_CRLF_ZERO = True
```

## 10. Validation commands and outputs

**A. Git / line-ending checks**

- `git diff --check` → clean.
- `git ls-files '*.sh'` → the 13 files listed in §9.
- `git add --renormalize .` → produced **no** `*.sh` byte change (confirms blobs were already LF).
- Byte-level CRLF/LF table (§9) → every tracked `.sh` has CRLF = 0; `inference.sh` CRLF = 0, LF = 5.
- `git check-attr text eol` → `text: set, eol: lf` for `.sh` and `Dockerfile` (§7).

**B. Shell syntax validation** — `bash -n` on all 13 tracked scripts: all **OK** (including
`bash -n inference.sh`). No script required generated content to validate.

**C. Dockerfile inspection** — diff shown in §8/§13; safeguard placed after `COPY . /code`, CMD
unchanged.

**D. Repository validation**
- `python -m compileall -q src scripts tests` → **PASS**.
- `pytest tests/integration/test_btc_submission_contract_2l47a.py
  tests/integration/test_full_system_output_contract_2l41a.py tests/unit/test_data_io.py
  tests/unit/test_labels.py -q` → **38 passed**.
- `pytest tests -q` (full suite) → **16 failed, 565 passed**.

## 11. Tests that passed or failed

- Passed: full suite 565 passed; all BTC-contract / data-io / labels / shell-relevant tests pass;
  `compileall` passes; `bash -n` passes for all 13 scripts.
- Failed: 16 tests, **all pre-existing** and unrelated to this change. They are the known
  frozen-artifact / public-replay class that opens missing historical files
  (`output/pred_v11_independent_rerun1.csv`, `experiments/best_candidate_manifest.json`, the frozen
  public CSV, `output/pred_v13_multilayer_candidate_api30_from_v12b.csv`,
  `output/pred_v10_full_production_user_run.csv`). This count and set are identical to the
  documented baseline in AUDIT 61 (16 failed / 565 passed). A line-ending / Dockerfile /
  `.gitattributes` change cannot influence Python test behavior, and the failure set is byte-for-byte
  the same as before the change.

## 12. Confirmation — no logic changed

No change was made to: local Qwen inference behavior; Base / V12B / V13 / selector / routing /
formula-bank logic; model prompts; parser logic; model path; CUDA or PyTorch versions; default BTC
no-flag runtime behavior; selective runtime behavior; README architecture descriptions; Docker Hub
tags; image names; the `torch_dtype` deprecation warning; or any accuracy/quality issue from the
30-question test. The only edits are `.gitattributes` (new), one `Dockerfile` RUN step, and this
audit file.

## 13. Confirmation — no Docker build or push

No Docker image was built, tagged, or pushed. No `docker build`, `docker run`, `docker push`, or
registry operation was performed. No Git commit or push was performed.

Exact diffs applied:

```diff
# Dockerfile
-RUN chmod +x inference.sh 2>/dev/null || true
+# Defensive line-ending hardening (see AUDIT 62): strip any trailing CR from
+# shell scripts copied into the image so they run under Linux bash even if the
+# build context came from a CRLF checkout. CRLF breaks `set -o pipefail`. This
+# only touches *.sh text; it never alters model weights, prompts, or runtime mode.
+RUN find /code -type f -name "*.sh" \
+      -exec sed -i 's/\r$//' {} + \
+    && chmod +x /code/inference.sh
```

```
# .gitattributes (new)
*.sh text eol=lf
Dockerfile text eol=lf
Dockerfile.* text eol=lf
```

## 14. Risks and caveats

- **Not runtime-verified in a real image.** This fix was validated at the source/build-definition
  level only (byte checks, `bash -n`, `git check-attr`, tests). It has NOT been proven by building a
  fresh image and rerunning the BTC container, because building/pushing is explicitly out of scope
  for this task. The temporary in-container hotfix already demonstrated CR removal resolves the
  failure, so confidence is high, but a source-built image should still be smoke-tested.
- The Dockerfile safeguard now makes `chmod +x /code/inference.sh` a hard build step (the previous
  form swallowed errors with `2>/dev/null || true`). This is intentional: if normalization or chmod
  ever fails, failing the build is safer than shipping a broken entrypoint. `sed` and `find` are
  present in the `nvidia/cuda:12.8.0-...-ubuntu22.04` base, so this is not expected to fail.
- Existing local clones on Windows will not auto-convert until `git add --renormalize` or a fresh
  checkout after `.gitattributes` is committed; the Dockerfile safeguard covers builds made from
  such clones in the meantime.
- `.gitattributes` scope is intentionally narrow; if additional executable text types are added
  later (e.g. `*.bash`, `*.env` shell fragments) they would need their own rule.

## 15. Current `git status --short`

```
 M Dockerfile
?? .gitattributes
```

(plus `?? docs/audits/62-fix-docker-shell-line-endings.md` once this file is saved). No `*.sh` file
appears — none needed byte changes.

## 16. Recommended next steps

1. Review this audit and the two-file diff (`.gitattributes`, `Dockerfile`).
2. Continue fixing local selective quality **separately** (out of scope here; unrelated to line
   endings).
3. Only after review, build a **new source-based image** from this branch (do not reuse the
   hotfixed layer).
4. Rerun the official BTC default Docker command (no flags) against the new image and confirm
   `/code/inference.sh` reports CRLF = 0 and the run ends with `[predict] status: PASS`.
5. Push new immutable + `latest` tags ONLY after all runtime tests pass.

---

## Summary

- **Root cause:** no `.gitattributes` → a CRLF build-context checkout put `\r\n` into `inference.sh`,
  which `COPY . /code` baked into the image; Linux bash then failed `set -o pipefail`
  (`: invalid option name set: pipefail`). Byte evidence in the image: CRLF 5 / LF 5.
- **Permanent source fix:** added `.gitattributes` enforcing `*.sh`, `Dockerfile`, `Dockerfile.*` →
  `text eol=lf`. All 13 tracked `.sh` files confirmed CRLF = 0.
- **Dockerfile safeguard:** after `COPY . /code`,
  `RUN find /code -type f -name "*.sh" -exec sed -i 's/\r$//' {} + && chmod +x /code/inference.sh` —
  strips CR from all copied shell scripts and keeps `inference.sh` executable, before the default
  `CMD`; touches no weights, prompts, or runtime mode.
- **Validation:** `git diff --check` clean; `git check-attr` shows `eol: lf`; all `.sh` CRLF = 0;
  `bash -n` OK for all 13 scripts; `compileall` PASS; full suite 16 failed / 565 passed with the 16
  failures being the pre-existing frozen-artifact class (identical to baseline, unrelated to this
  change).
- **Audit path:** `docs/audits/62-fix-docker-shell-line-endings.md`.
- **Git status:** ` M Dockerfile`, `?? .gitattributes` (+ this audit). No `.sh` byte changes.
- **Not performed:** no Docker build, no Docker push, no Git commit, no Git push.
