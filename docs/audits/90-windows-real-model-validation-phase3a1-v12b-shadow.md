# AUDIT 90 — Windows Real-Model Observational Validation of Phase 3A-1 V12B Shadow (BLOCKED — environment)

Audit number 90 (no prior `90-*` existed under `docs/audits/`).

> **Nature of this record.** This audit documents an **attempt** to run the Phase 3A-1 real-model
> observational validation from the current host. The real-model Docker runs (Runs A–E) **could not be
> executed** because the accepted validation image and the model weights are **not present on this host**,
> and no user-supplied Windows runtime evidence accompanied the task. Per project precedent (AUDIT 71,
> AUDIT 76), the Windows real-model validation is produced on the user's Windows Docker machine and the
> evidence transcribed. **No run results were fabricated.** The model-free portions that *could* be run
> honestly (preflight, environment probe, CLI verification, fake regression tests, static forbidden-path
> checks) were completed and are recorded below.

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `73cf35b319273b8d6d009d66e140d9094a437ca1` ("add observational confidence-routed V12B
  integration")

## 2. Initial clean repository state

`git status --short`: empty (clean). `git diff --check` clean; `git diff --cached --check` clean; index
empty. Recent log: `73cf35b` (Phase 3A-1 integration), `e61c948` (3A-1 plan), `77e940d` (3A-0 runner).
AUDIT 88 and AUDIT 89 are committed at HEAD (`git ls-tree` confirmed). The Phase 3A-1 implementation,
its independent review, and the four new test files are committed as `73cf35b`.

## 3. Validation-only statement

This pass is observational validation only. It creates no code/test/config/YAML/Docker/dependency change
and only this audit file. It did not replace answers, enable V13/selector, invoke legacy V12B, promote a
default, finalize a threshold, use ground truth, call an external API, download a model, pull/build an
image, commit, or push.

## 4. Claude Code resumed-work context

Claude Code resumed from Git + audits. Phases 1/2 complete and Windows-validated (AUDIT 71/76); Phase
3A-0 committed and approved (AUDIT 85); Phase 3A-1 implemented (AUDIT 88) and independently reviewed
(AUDIT 89, verdict "safe to commit with non-blocking caveats"); Phase 3A-1 is now committed at
`73cf35b`. This task is the final authorized Windows real-model observational validation.

## 5. Governing audits reviewed

AUDIT 71 (Phase 1 Windows revalidation), 76 (Phase 2 Windows shadow validation), 77 (independent review
of 76), 85, 87, 88, 89. AUDIT 76 §2 establishes the operative precedent: *"The current Linux environment
did not rerun the GPU/model commands; it only records the supplied external runtime evidence,"* produced
in a Windows Docker container and transcribed.

## 6. Windows / Docker / GPU environment (this host)

- Host OS: **Linux Fedora** `7.0.13-100.fc43.x86_64` (x86_64) — **not** a Windows host.
- Docker: present, **v29.5.3** (build 1.fc43).
- GPU: **NVIDIA GeForce RTX 4060 Laptop GPU**; driver **580.159.04**; CUDA 13.0; total **8188 MiB**,
  free **7794 MiB**. (This is the same GPU model named in AUDIT 76.)
- Host Python: `torch`/`transformers` **not importable** (no model runtime on the host itself).

## 7. Docker image identity

Accepted image required: `vquclinh/fastmcq-local-selective:d0d8c28-lf`.
Result of `docker image inspect …:d0d8c28-lf`: **"No such image."** Local image count: **1** (none
matching `fastmcq`/`qwen`/`selective`). The accepted validation image is **not present** on this host and
was **not** pulled (pulling it would download the model baked into the image, which the task forbids).

## 8. Model identity and mount verification

Required model path: `/models/qwen3-4b-instruct-2507`.
Result: `/models` **does not exist**; no `qwen3-4b*` directory found under a bounded filesystem search;
`~/models` absent. The model weights are **not present** on this host and were **not** downloaded.

## 9. Validation datasets

The permitted 21-item synthetic diagnostic dataset (used in AUDIT 71/76) was **not** materialized for a
run because no run could execute. No dataset was created or modified. No organizer ground truth was used
or accessed.

## 10. Exact run matrix

| Run | Purpose | Status |
|---|---|---|
| A | Base-only control | **NOT EXECUTED** — no image/model on host |
| B | Base-only repeat (repeatability) | **NOT EXECUTED** — no image/model on host |
| C | Phase 3A-1 `--confidence-v12b-shadow` | **NOT EXECUTED** — no image/model on host |
| D | Combined telemetry + Phase 2 + V12B | **NOT EXECUTED** — no image/model on host |
| E | No-selected case | **NOT EXECUTED** — no image/model on host |

None of Runs A–E could be executed because the accepted image (`§7`) and model weights (`§8`) are absent,
and the task forbids rebuilding the image, downloading a model, and fabricating evidence.

## 11. Sanitized commands

No Docker `run` command was issued (nothing to run against). The model-free host commands actually
executed were: `git` preflight; `nvidia-smi --query-gpu=…`; `docker --version`; `docker image inspect …`
(returned "No such image"); `docker images`; a bounded `find` for the model dir; `python predict.py
--help`; and `pytest` on fake-only tests. No secrets, prompts, questions, choices, or raw model output
were produced or printed.

## 12. Exit codes and durations

Model-free checks only: `predict.py --help` exit 0; fake regression pytest exits 0 (see §32). No
Docker-run exit codes exist because no run occurred.

## 13. Base-only Run A results

**Not available** — not executed (§10).

## 14. Base-only repeat Run B results

**Not available** — not executed (§10).

## 15. V12B-shadow Run C results

**Not available** — not executed (§10). The CLI path is verified present (§20) but no real-model
generation, scoring, routing, or permutation execution occurred on this host.

## 16. Combined-mode Run D results

**Not available** — not executed (§10).

## 17. No-selected Run E results

**Not available** — not executed (§10).

## 18. Base repeatability finding

**Not determinable** on this host — Runs A/B did not execute. (Fake-backend byte-invariance evidence
remains from AUDIT 89; real-model Base repeatability requires the Windows run.)

## 19. Official CSV byte/hash/row comparison

**Not available from a real run.** No real `submission.csv` was produced. The fake-test exact-byte
invariance evidence (Base vs V12B, across failure modes) is retained from AUDIT 89 §16 and remains valid
for the *implementation* invariance claim, but does **not** substitute for real-model runtime evidence.

## 20. Scoring/router reuse evidence available from logs/tests

No runtime logs (no run). CLI verified via `python predict.py --help`: the flags exist exactly as
specified — `--confidence-v12b-shadow`, `--v12b-shadow-path`, `--v12b-shadow-summary-path`, plus
`--confidence-telemetry`/`--telemetry-path`, `--confidence-shadow-router`/`--shadow-router-path`/
`--shadow-router-summary-path`, `--input`, `--submission`, `--submission-time`, `--output`,
`--model-path`, `--max-new-tokens`, `--device`, `--legacy-dynamic-full`. **No seed/deterministic control
flag exists** beyond `--device`/`--max-new-tokens` (generation is greedy `temperature=0.0`; see
`local_qwen_backend.generate_text`). Score-once / router-once reuse is proven by fake tests (§32), not by
a real run here.

## 21. Real selected-record count

**Not available** — not executed.

## 22. Real V12B attempted-record count

**Not available** — not executed.

## 23. Real permutation counts

**Not available** — not executed. (Contract bound `total_permutation_attempts ≤ 6 × selected_valid_records`
is enforced in code and proven by fake tests; no real counts were produced.)

## 24. Parse/generation/aggregate-status counts

**Not available** — not executed.

## 25. Source-vs-runner ordinal evidence

**Not available from a real run.** The distinction (`source_record_ordinal` vs nested runner-local
`aggregate.record_ordinal`) is proven by fake tests and the AUDIT 89 probe, not by a real run here.

## 26. Duplicate-record handling evidence

**Not available from a real run.** Proven by fake tests (duplicate qid + input_index kept distinct), not
by a real run here.

## 27. Artifact privacy inspection

**No real artifacts were produced.** Privacy was independently proven against the *implementation* in
AUDIT 89 §17 (marker probe: markers in question/choices/raw-response/exception did not leak; whitelist-only,
labels-only mappings, closed codes, class-name-only exceptions, `allow_nan=False`). Real-artifact privacy
still requires inspection of files from an actual Windows run.

## 28. Artifact JSON/schema validity

**No real artifacts.** Fake-test artifacts parse and are finite (AUDIT 89). Real-run schema validity
pending the Windows run.

## 29. Artifact-failure probe

**Not performed against a real run** (no run). The failure-safety behavior (artifact-write failure keeps
the official CSV; warning carries operation + exception class only, no private text) is proven by fake
tests (`test_v12b_artifact_write_failure_preserves_official`) and the AUDIT 89 probes.

## 30. No-V13 / no-selector / no-legacy / no-API evidence

Static/import evidence (host, no run): `run_v12b_layer`/`select_v12b_targets`/`V13`/`selector`/
`fastmcq_system`/OpenRouter/`api_key` appear in the Phase 3A-1 integration path **only** inside
descriptive comments, never as calls (`grep` over `predict.py`, `confidence_v12b_artifacts.py`,
`confidence_v12b_runner.py`). The only V12B implementation reachable from `predict.py` is
`src/local_model/confidence_v12b_runner.py`. Runtime confirmation still requires the Windows run.

## 31. GPU memory / runtime observations

A GPU is present (RTX 4060 Laptop, 8188 MiB) but was **not exercised** (no image/model). No runtime or GPU
memory figures for Phase 3A-1 are available from this host.

## 32. Fake regression-test results

- `test_confidence_v12b_config_2l50a.py` + `..._backend_accessor_2l50b.py` + `..._artifacts_2l50c.py` +
  `..._v12b_shadow_2l50d.py` → **48 passed**.
- `test_confidence_v12b_runner_2l49a.py` → **47 passed**.
- `test_choice_scoring_2l48b.py` + `test_confidence_telemetry_2l48c.py` +
  `test_confidence_shadow_router_2l48d.py` + `test_confidence_shadow_router_2l48e.py` → **89 passed**.

## 33. Files created outside Git

None. No runtime output directories were created (no run). No dataset or artifact files were written.

## 34. Repository diff/status evidence

`git diff --name-only`: empty (no tracked change). Working tree clean apart from this new untracked audit.
No source/test/config/YAML/Docker file was modified.

## 35. Limitations

- **No real-model evidence was produced on this host** — the accepted image and model are absent.
- No ground truth; no accuracy-improvement claim; observational only; thresholds provisional.
- Real-model Base repeatability / nondeterminism is undetermined here.
- Fake-test and static evidence establish *implementation* correctness (AUDIT 88/89) but do **not**
  substitute for real-model runtime confirmation.

## 36. Explicit confirmation

- No source/test/config/YAML/Docker change (only this audit created).
- No Phase 3B; no answer replacement; no V13; no selector; no legacy V12B; no default promotion; no final
  threshold; no organizer ground truth; no external API; no model download; no image pull/build; no commit
  or push.

## 37. Current git status

```
?? docs/audits/90-windows-real-model-validation-phase3a1-v12b-shadow.md
```

(Working tree otherwise clean; this audit is the only new file.)

## 38. Recommended next action

Run the Phase 3A-1 real-model observational validation on the accepted **Windows Docker** machine that
holds image `vquclinh/fastmcq-local-selective:d0d8c28-lf` with the model at
`/models/qwen3-4b-instruct-2507`, following the AUDIT 76 invocation pattern, and **supply the sanitized
runtime evidence** (SHA-256 of each official `submission.csv`; row/qid/answer comparison A-vs-B-vs-C-vs-D;
selected-record / attempted / permutation / parse / generation / aggregate-status counts; artifact
privacy/schema check; artifact-failure probe; GPU/runtime figures) so it can be transcribed into a
validation audit — exactly as AUDIT 71/76 were produced.

Alternatively, if this Fedora host is to be used, **explicit user authorization** is required to provision
the accepted image and model here (which entails pulling the model-containing image — currently forbidden
by this task's constraints); only then can Runs A–E be executed locally.

## 39. Final verdict

**PHASE 3A-1 WINDOWS VALIDATION BLOCKED — ENVIRONMENT OR EVIDENCE**

The accepted validation image and the Qwen model weights are not present on this host, and no
user-supplied Windows runtime evidence accompanied the task. The real-model runs (A–E) were therefore not
executed and were **not** fabricated. Model-free evidence (preflight, environment probe, CLI verification,
184 fake tests passing, static forbidden-path checks) is recorded above. This verdict authorizes nothing
further; it does not authorize Phase 3B, answer replacement, V13, selector, default promotion, or final
thresholds. Provide the Windows runtime evidence (or authorize provisioning the image+model here) to
complete the observational validation.
