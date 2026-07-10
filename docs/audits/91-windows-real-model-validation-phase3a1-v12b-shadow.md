# AUDIT 91 — Windows Real-Model Observational Validation of Phase 3A-1 V12B Shadow (BLOCKED — environment unchanged)

Audit number 91 (no prior `91-*` existed under `docs/audits/`).

> **Nature of this record.** A second attempt to run the Phase 3A-1 real-model observational validation.
> The runtime environment is **unchanged from AUDIT 90**: this host is Linux Fedora (not Windows), the
> accepted validation image is **still absent**, and the model weights are **still absent**. The task
> instruction is explicit: *"Stop with a truthful blocked verdict if the accepted image or mounted model
> is still unavailable. Do not pull or rebuild anything."* Accordingly, Runs A–E were **not executed and
> not fabricated.** Only the honest model-free checks were performed. AUDIT 90 is preserved unchanged.

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `73cf35b319273b8d6d009d66e140d9094a437ca1` ("add observational confidence-routed V12B
  integration") — matches the expected Phase 3A-1 HEAD.

## 2. Initial repository state

`git status --short`: only `?? docs/audits/90-…md` untracked (AUDIT 90 not yet committed). `git diff
--check` and `git diff --cached --check` clean; no tracked source/test/config change. AUDIT 88 and 89
committed at HEAD.

## 3. Validation-only statement

Observational validation only. No code/test/config/YAML/Docker/dependency change; only this audit
created. No answer replacement, V13, selector, legacy V12B, default promotion, threshold finalization,
ground truth, external API, model download, image pull/build, commit, or push.

## 4. Relationship to blocked AUDIT 90

AUDIT 90 blocked the Fedora attempt for the same reason (image + model absent). This task was issued as
if running "on the user's Windows machine," but the **verified** environment is the **same Fedora host**;
the accepted image and model are still not present. AUDIT 90 is not modified; AUDIT 91 is a distinct new
record of the second attempt.

## 5. Governing audits reviewed

AUDIT 71 (Phase 1 Windows revalidation), 76 (Phase 2 Windows shadow validation, incl. the working Docker
invocation, RTX 4060 GPU, and the 21-item synthetic dataset), 77, 87, 88, 89, 90. AUDIT 76 §2 confirms
the operative pattern: the real-model validation is produced on the Windows Docker machine and the
sanitized evidence transcribed.

## 6. Windows / Docker / GPU environment (verified this host)

- Host OS: **Linux Fedora** `7.0.13-100.fc43.x86_64` (x86_64) — `uname` succeeded; **not** Windows.
- Docker: **v29.5.3** (build 1.fc43).
- GPU: **NVIDIA GeForce RTX 4060 Laptop GPU**; driver **580.159.04**; total **8188 MiB**, free
  **7794 MiB**.
- Host Python: `torch`/`transformers` not importable (no model runtime on the host).

## 7. Docker image ID / digest

`docker image inspect vquclinh/fastmcq-local-selective:d0d8c28-lf` → **"No such image."** No local image
matches `fastmcq`/`qwen`/`selective` (`docker images`). The accepted image was **not** pulled or built.

## 8. Model identity and mount verification

Required `/models/qwen3-4b-instruct-2507` → **does not exist** on this host. No model was downloaded and
no container was started (nothing to mount into). Model-path-inside-container verification is therefore
**not available**.

## 9. Validation dataset identity

The permitted 21-item synthetic diagnostic dataset (AUDIT 71/76) was **not** instantiated because no run
could execute. No fixture was created or modified. No organizer ground truth was used or accessed.

## 10. Exact sanitized Docker invocation pattern

No `docker run` was issued (no image/model). The intended pattern (from AUDIT 76, for the Windows host
that has the assets) is: run the accepted image with `--gpus all`, the repository bind-mounted to the
working directory, the model available at `/models/qwen3-4b-instruct-2507`, input under a mounted
validation directory, and `python predict.py --input … --submission … --submission-time …
[--confidence-v12b-shadow --v12b-shadow-path … --v12b-shadow-summary-path …]`. This is recorded for the
Windows operator, **not** executed here.

## 11. Run matrix completion table

| Run | Purpose | Status |
|---|---|---|
| A | Base-only control | **NOT EXECUTED** — image/model absent |
| B | Base-only repeat | **NOT EXECUTED** — image/model absent |
| C | V12B shadow | **NOT EXECUTED** — image/model absent |
| D | Combined telemetry + Phase 2 + V12B | **NOT EXECUTED** — image/model absent |
| E | No-selected case | **NOT EXECUTED** — image/model absent |

## 12–17. Run A / B / C / D / E results and artifact-failure probe

**Not available** — no run executed (§7/§8). No official CSV, timing CSV, V12B JSONL, or summary was
produced; no artifact-failure probe was run against a real container. (The artifact-write-failure
behavior — official CSV preserved, warning carries operation + exception class only, no private text — is
proven against the implementation by fake tests and the AUDIT 89 probe, not by a real run here.)

## 18. Exit codes and durations

Model-free only: `python predict.py --help` → exit 0 (verified in AUDIT 90 that all three V12B flags are
present); `pytest` fake suites → exit 0 (§34). No Docker-run exit codes (no run).

## 19. GPU memory observations

GPU present (RTX 4060 Laptop, 8188 MiB) but **not exercised** — no Phase 3A-1 GPU/runtime figures exist
from this host.

## 20. Base repeatability

**Not determinable** here — Runs A/B did not execute.

## 21–22. Official CSV hashes / byte / row / qid / answer comparisons

**Not available** — no real official CSV produced. The fake-test exact-byte invariance evidence (Base vs
V12B across failure modes) is retained from AUDIT 89 §16 for the *implementation* claim and does not
substitute for a real run.

## 23–28. Selected / attempted / permutation / parse / generation / aggregate-status / disagreement counts

**Not available** — no run executed. (Code enforces `total_permutation_attempts ≤ 6 × attempted_valid`,
proven by fake tests; no real counts produced.)

## 29. Source-vs-runner ordinal evidence

**Not available from a real run.** The `source_record_ordinal` vs nested runner-local
`aggregate.record_ordinal` distinction is proven by fake tests and the AUDIT 89 probe.

## 30. Duplicate-record evidence

**Not available from a real run.** Proven by fake tests (duplicate qid + input_index kept distinct).

## 31. Real artifact schema validation

**No real artifacts.** Fake-test artifacts parse and are finite (AUDIT 89).

## 32. Real artifact privacy inspection

**No real artifacts.** Implementation privacy independently proven in AUDIT 89 §17 (marker probe: markers
in question/choices/raw-response/exception did not leak; whitelist-only; labels-only mappings; closed
codes; class-name-only exceptions; `allow_nan=False`). Real-artifact privacy still requires a Windows run.

## 33. No-V13 / no-selector / no-legacy / no-API evidence

Static/import evidence (no run): forbidden tokens appear only in descriptive comments in the Phase 3A-1
integration path; the only V12B implementation reachable from `predict.py` is
`src/local_model/confidence_v12b_runner.py`. Runtime confirmation pending the Windows run.

## 34. Fake regression-test results

- `test_confidence_v12b_config_2l50a.py` + `..._backend_accessor_2l50b.py` + `..._artifacts_2l50c.py` +
  `..._v12b_shadow_2l50d.py` → **48 passed**.
- `test_confidence_v12b_runner_2l49a.py` → **47 passed**.
- `test_choice_scoring_2l48b.py` + `test_confidence_telemetry_2l48c.py` +
  `test_confidence_shadow_router_2l48d.py` + `test_confidence_shadow_router_2l48e.py` → **89 passed**.

Total: **184 fake tests passing** (model-free), consistent with AUDIT 89.

## 35. Runtime outputs created outside Git

None. No run occurred; no output directories, datasets, or artifacts were written.

## 36. Repository status / diff evidence

`git diff --name-only`: empty. `git diff --check` / `git diff --cached --check`: clean. Working tree
clean apart from untracked AUDIT 90 and this new AUDIT 91.

## 37. Limitations

- **No real-model evidence** was produced — accepted image and model absent on this host.
- No ground truth; no accuracy-improvement claim; observational only; thresholds provisional.
- Real-model Base repeatability / nondeterminism undetermined here.
- Implementation correctness is established by AUDIT 88/89 (fake tests + probes), which does not
  substitute for real-model runtime confirmation.

## 38. Explicit confirmation

- No source/test/config/YAML/Docker change (only this audit created).
- No Phase 3B; no answer replacement; no V13; no selector; no legacy V12B; no default promotion; no final
  threshold; no organizer ground truth; no external API; no model download; no image pull/build; no
  commit or push.

## 39. Current git status

```
?? docs/audits/90-windows-real-model-validation-phase3a1-v12b-shadow.md
?? docs/audits/91-windows-real-model-validation-phase3a1-v12b-shadow.md
```

## 40. Recommended next action

Execute the validation on the actual **Windows Docker** machine that holds image
`vquclinh/fastmcq-local-selective:d0d8c28-lf` with the model at `/models/qwen3-4b-instruct-2507`
(per AUDIT 76), and **supply the sanitized runtime evidence** — per-run official `submission.csv` SHA-256,
A/B/C/D byte+row+qid+answer comparison, selected/attempted/valid-invalid/permutation/parse/generation/
aggregate-status/disagreement counts, `source_record_ordinal` vs nested runner ordinal, duplicate-record
handling, artifact privacy+schema report, artifact-failure probe result, and GPU/runtime figures — so it
can be transcribed into the validation audit (as AUDIT 71/76 were). Alternatively, with **explicit user
authorization**, provision the accepted image + model on this Fedora host (which entails pulling the
model-containing image — currently forbidden) and re-run Runs A–E here.

## 41. Final verdict

**PHASE 3A-1 WINDOWS VALIDATION BLOCKED — ENVIRONMENT OR EVIDENCE**

The accepted image and model weights are not present on the verified host (unchanged since AUDIT 90), and
no user-supplied Windows runtime evidence accompanied the task. Runs A–E were not executed and were **not**
fabricated. Model-free evidence (preflight, environment verification, CLI flags confirmed in AUDIT 90,
184 fake tests passing, static forbidden-path checks) is recorded. This verdict authorizes nothing
further — not Phase 3B, answer replacement, V13, selector, legacy V12B, default promotion, or final
thresholds. Provide the Windows runtime evidence, or authorize provisioning the image+model here, to
complete the observational validation.
