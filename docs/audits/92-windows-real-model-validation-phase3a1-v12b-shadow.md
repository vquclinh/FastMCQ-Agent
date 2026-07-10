# AUDIT 92 — Windows Real-Model Observational Validation of Phase 3A-1 (V12B Shadow)

Audit number 92 (no prior `92-*` existed under `docs/audits/`; Audits 90–91 document the earlier
Fedora-host blocked attempts).

> **Nature of this record.** Unlike Audits 71/76/90/91 (which transcribed externally-supplied evidence
> or recorded environment-absence), this audit's Docker/GPU commands were **executed directly by the
> assistant in this session**, on the user's Windows machine, against the real GPU and the real baked
> model. All figures below are taken directly from command output and file inspection performed in this
> session — nothing here is transcribed from a separate external run.

## 1. Branch and full HEAD

- Branch: `main`
- Full HEAD (validation HEAD, current at session start): `75dc7ce3b79ec3688c6d4cc75cb10d9eddb9c987`
  ("document blocked phase 3A-1 runtime validation attempts")
- Previously expected Phase 3A-1 implementation HEAD: `73cf35b319273b8d6d009d66e140d9094a437ca1`
- Ancestor check: `git merge-base --is-ancestor 73cf35b3... 75dc7ce3...` → **exit 0 (success)**.
- Commits between the two: only `75dc7ce` — `git log --oneline 73cf35b3..HEAD` shows a single commit.
- `git diff --stat 73cf35b3..HEAD`: 2 files changed, 475 insertions(+), 0 deletions(-) —
  `docs/audits/90-windows-real-model-validation-phase3a1-v12b-shadow.md` and
  `docs/audits/91-windows-real-model-validation-phase3a1-v12b-shadow.md` only.
- No source, test, config, YAML, or Docker file changed between the approved Phase 3A-1 commit and the
  validation HEAD — the only changes are Audit 90–91 documentation.
- `git status --short` before and after this validation: **empty (clean)**, confirmed repeatedly
  throughout the session (last checked immediately after the failure-safety probe).

## 2. Windows / Docker / GPU / image / model verification

- Host OS: `Microsoft Windows NT 10.0.26200.0` (confirmed via `.NET` `OSVersion` from PowerShell — this
  session ran directly on the Windows host, not Fedora).
- `docker --version`: `Docker version 29.5.3, build d1c06ef`.
- `docker image inspect vquclinh/fastmcq-local-selective:d0d8c28-lf` → Id
  `sha256:e62473ed524962fd44da393842a6adde0b4faf575327d4758680494555b6634a` (matches the accepted
  digest supplied in the task; image was **not** rebuilt or repulled).
- Host `nvidia-smi`: NVIDIA GeForce RTX 4060 Laptop GPU, driver `610.62`, 8188 MiB total, 0 MiB used
  before the session's first container run, no other processes.
- Minimal inspection container (`bash` script mounted read-only alongside the repo, `--gpus all`):
  - `uname -a` inside container: `Linux ... 6.18.33.2-microsoft-standard-WSL2 ...` (Docker Desktop
    WSL2 backend — expected for Windows Docker).
  - `nvidia-smi` inside container: RTX 4060 Laptop GPU visible, 8188 MiB, driver reported as
    `610.43.02` by the container's bundled NVIDIA tooling (host reports `610.62`; both readings are
    from the same physical driver stack — the container-side utility reports a slightly different
    version string than the host-side one, a known NVIDIA-container-toolkit cosmetic difference, not a
    different GPU or driver).
  - `/models/qwen3-4b-instruct-2507` exists: `drwxr-xr-x 3 root root 4096 Jul 9 08:37`.
  - `python -c "import torch, transformers"`: `torch 2.7.1+cu128`, `transformers 5.12.1`,
    `cuda True`, `gpu NVIDIA GeForce RTX 4060 Laptop GPU`.
  - Repository mount: `test -f predict.py` passed; `git rev-parse HEAD` inside the container printed
    `75dc7ce3b79ec3688c6d4cc75cb10d9eddb9c987` — **identical to the host HEAD**.
  - `python predict.py --help` contained all three required flags: `--confidence-v12b-shadow`,
    `--v12b-shadow-path`, `--v12b-shadow-summary-path`.
- All preflight gates passed; Runs A–E proceeded only after this inspection container succeeded.

## 3. Dataset identity

- Input: `scratch/phase2_real/synthetic21_input.json` — the same file used in AUDIT 76, already
  present on disk (21 records, `qid`/`question`/`choices` only, no `expected`/ground-truth field).
- Source of truth for the 21 items: `scratch/phase1_real/synthetic21_confidence_validation.py`
  (self-authored synthetic diagnostic items; no organizer data).
- First qid: `syn_001_addition_3`; last qid: `syn_021_pills` — matches AUDIT 76.
- All 21 `qid` values are unique (`len(all_qids) == len(set(all_qids))`); the dataset contains **no
  duplicate records**, so this run cannot demonstrate duplicate-record *preservation* behavior — noted
  as a limitation in §13 and §20.

## 4. Sanitized Docker invocation

Repository root bind-mounted to `/workspace` (working dir `/workspace`), GPU passthrough, no rebuild,
no repull, no model download:

```
docker run --rm --gpus all `
  -v "<repo>:/workspace" -w /workspace `
  vquclinh/fastmcq-local-selective:d0d8c28-lf `
  python predict.py --input scratch/phase2_real/synthetic21_input.json `
    --submission <run_dir>/submission.csv `
    --submission-time <run_dir>/submission_time.csv `
    [--confidence-telemetry --telemetry-path <path>] `
    [--confidence-shadow-router --shadow-router-path <path> --shadow-router-summary-path <path>] `
    [--confidence-v12b-shadow --v12b-shadow-path <path> --v12b-shadow-summary-path <path>]
```

Image `ENTRYPOINT=[/opt/nvidia/nvidia_entrypoint.sh]`, default `CMD=[bash inference.sh]`,
`WORKDIR=/code`; each run explicitly overrode the command with `python predict.py ...` and `-w
/workspace`, so the image's own default `inference.sh`/`WORKDIR` were never relied upon. No `-e`
environment overrides, no alternate volumes beyond the repo (and, for the inspection step only, a
read-only scratch-script mount). Outputs were written under session-only `scratch/phase3a1_v12b_windows/`
subdirectories (gitignored, untracked).

## 5. Run A–E table

| Run | Mode | Exit | Wall duration | Reported predict-total | Official CSV SHA-256 (short) | Rows |
|---|---|---|---|---|---|---|
| A | Base-only | 0 | 155.62 s | 29.439 s | `3A8940B9…DBEB8D` | 21 |
| B | Base-only repeat | 0 | 60.11 s | 22.586 s | `3A8940B9…DBEB8D` (=A) | 21 |
| C | V12B shadow | 0 | 166.11 s | 14.151 s | `3A8940B9…DBEB8D` (=A) | 21 |
| D | Telemetry + router + V12B shadow | 0 | 184.99 s | 15.168 s | `3A8940B9…DBEB8D` (=A) | 21 |
| E | No-selected case | N/A — **unavailable** | — | — | — | — |
| Fail-probe | V12B shadow, unwritable artifact path | 0 | 162.39 s | 13.234 s | `3A8940B9…DBEB8D` (=A) | 21 |

Run E: no dedicated no-selected fixture exists anywhere in the repo (confirmed by search across
`docs/audits/77-91` and all scripts — the "no-selected case" is described only as a future test
scenario, e.g. in `docs/audits/86-*` and `87-*`, never as a shipped fixture). Forcing zero selections on
the 21-item set would require overriding `max_targets_override` or raising
`provisional_margin_threshold` above the observed maximum margin (27.75, per AUDIT 71) in a committed
or session config — explicitly forbidden by the task ("do not alter thresholds just to force it"). Run
E is therefore recorded as **unavailable**, not attempted, not simulated.

## 6. Exit codes and durations

All five executed container runs (A, B, C, D, fail-probe) exited **0**. Wall-clock durations above
include full container startup, CUDA init, and cold/warm model-weight loading (the `[predict]`-reported
"total" figures are the in-process prediction-loop timings only and must not be used to infer
model-load or per-question latency, consistent with the AUDIT 76 caveat). Weight-loading time varied
run to run (≈75 s on the coldest run, A, down to ≈1–24 s on later runs) due to OS filesystem/page-cache
warm-up between consecutive container runs — not a code or model behavior change.

## 7. Official CSV hashes / byte comparisons

- Run A SHA-256: `3A8940B96A0CB33D8F221E01B41CC7418C059CD51F5F51D3C82002C2D5DBEB8D`, 476 bytes, 22
  lines (1 header + 21 rows).
- Runs B, C, D, and the fail-probe run all produced the **exact same SHA-256 hash and the exact same
  476-byte file** as Run A (verified via `Get-FileHash` and a full `SequenceEqual` byte comparison for
  A vs B; hash equality checked for A vs C, A vs D, A vs fail-probe).
- This hash is **identical** to the baseline/shadow hash recorded in AUDIT 76
  (`3A8940B9…DBEB8D`), produced in an unrelated earlier session — strong cross-session evidence that
  greedy (temperature-0) generation on this fixed 21-item set, this exact model, and this exact image is
  deterministic on this hardware.
- Per §"Official output contract": since A and B were byte-identical (no nondeterminism observed), C, D,
  and the fail-probe run were required to match A exactly — **confirmed for all three.**

## 8. Base repeatability (Run A vs Run B)

- `Compare-Object` on line-by-line content: **no differences**.
- Byte-for-byte `SequenceEqual`: **true**.
- SHA-256: identical.
- qid order and every answer: identical (both files share the same 22 lines verbatim).

## 9. Selected / attempted / permutation counts (Run C, cross-checked against Run D)

From `confidence_v12b_shadow_summary.json` (Run C and Run D's V12B summary; **every field below was
verified identical between C and D**):

- `total_input_records`: 21
- `total_router_candidates`: 4
- `total_router_selected`: 3
- `total_v12b_attempted`: 3
- `total_v12b_skipped_invalid`: 0
- `total_v12b_failed`: 0
- `total_permutation_attempts`: 16
- `total_valid_permutations`: 10
- `selected_qids` (risk-rank order): `syn_020_sequence`, `syn_008_speed`, `syn_001_addition_3` — **these
  exactly match the selected set reported in AUDIT 76** for the Phase 2 shadow router on the same
  dataset.
- Run D's own `confidence_shadow_router_summary.json`: `n_input=21`, `budget_cap=3`,
  `provisional_threshold=10.0`, `candidate_count=4`, `selected_count=3`, `reason_counts.
  low_logit_margin=4`, `scoring_method=next_token_logits_one_forward` — matches AUDIT 76 exactly.
- The router's own internal `threshold_sweeps` diagnostic (emitted automatically, not triggered by any
  config change made in this session) shows `selected_after_cap` stays capped at 3 up to
  `margin_threshold=20.0` (8 candidates before cap) — illustrating why forcing a genuine "0 selected"
  case on this dataset would require a margin threshold above the observed max (27.75) or an explicit
  `max_targets_override=0`, neither of which was applied (see §5, Run E).

## 10. Parse / generation / status counts

- `parse_failure_total`: 0
- `generation_failure_total`: 0
- `input_validation_error_counts`: `{"ok": 3}` (all 3 attempted records passed input validation)
- `aggregate_status_counts`: `{"insufficient_valid_permutations": 1, "all_invalid": 1,
  "valid_unique_majority": 1}` — identical in Run C and Run D.
- Per-record `aggregate.record_error_code` values observed: `insufficient_valid_permutations`,
  `all_invalid`, `ok` — a closed, small enumerated set, no arbitrary text.
- Per-permutation `error_code` values observed: `ok`, `label_out_of_range` — closed set.
- Per-permutation `parse_status` values observed: `ok` only.
- Per-permutation `exception_class_name` values observed: `None` for all permutations in this run (no
  exceptions were raised during scoring/parsing on this dataset) — field is present and typed for future
  runs where it would hold a bare exception class name, never a message.

## 11. Base/V12B agreement diagnostics

- `base_v12b_disagreement_count`: **1** (identical in Run C and Run D).
- Record-level detail (labels only, no question/choice text):
  - `syn_001_addition_3`: `base_answer=A`, V12B `winning_label=A` → **agreement**.
  - `syn_008_speed`: `base_answer=A`, V12B status `all_invalid` (no winning label) → base preserved,
    no comparable V12B answer.
  - `syn_020_sequence`: `base_answer=C`, V12B `winning_label=D`, `hypothetical_answer=D` →
    **disagreement** (the 1 counted above). The official CSV answer for this qid remains `C` (Base) —
    confirmed by direct inspection of `submission.csv`.

## 12. Source-vs-runner ordinal evidence

For every selected record, the top-level `source_record_ordinal` (position in the original 21-item
input) differs from the nested `aggregate.record_ordinal` (local sequential index within this V12B run,
0/1/2), exactly as the schema contract requires:

| qid | top-level `source_record_ordinal` | nested `aggregate.record_ordinal` |
|---|---|---|
| `syn_001_addition_3` | 0 | 0 |
| `syn_008_speed` | 7 | 1 |
| `syn_020_sequence` | 19 | 2 |

The nested ordinal is a purely local 0/1/2 counter for the 3 records processed in this run; the
top-level ordinal (0, 7, 19) is the record's true position in the 21-item dataset. The two numbering
schemes are confirmed **not interchangeable** and were not conflated anywhere in the artifact.

## 13. Duplicate-record evidence

Not demonstrable on this dataset: all 21 input `qid` values are unique
(`len(all_qids) == len(set(all_qids))` confirmed by direct inspection), so no duplicate record ever
reached the V12B shadow runner in Runs A–D or the fail-probe. This audit does **not** claim duplicate
records were preserved — only that none were present to test with, consistent with the no-fixture
limitation for Run E (§5). Constructing a duplicate-qid fixture was out of scope (would require adding a
new committed/scratch dataset file beyond what the task authorized).

## 14. Real artifact privacy / schema inspection

Programmatic inspection (Python `json` parsing, not manual paste) of
`scratch/phase3a1_v12b_windows/runC/confidence_v12b_shadow.jsonl` (3 records) and its summary:

- All 3 lines parse as valid, finite JSON (`json.loads` succeeded for every line; no `NaN`/`Infinity`
  substring found anywhere in the serialized records).
- Top-level keys present: `aggregate`, `base_answer`, `base_logit_margin`, `base_normalized_entropy`,
  `base_top1`, `base_top2`, `input_index`, `input_validation_status`, `observational_only`,
  `official_answer_source`, `qid`, `router_candidate_reasons`, `router_selected_rank`,
  `selected_sequence_ordinal`, `source_record_ordinal`, `v12b_attempted`.
- `official_answer_source == "base"` at both the top level and inside the nested `aggregate` object, for
  all 3 records — confirmed programmatically.
- Nested `aggregate.permutation_results` entries contain only: `error_code`, `exception_class_name`,
  `label_option_match` (boolean), `mapped_original_label`, `parse_status`, `permutation_id`,
  `permutation_ordinal`, `permuted_to_original`, `valid` — **labels and booleans only**, no choice text.
- A naive substring scan for `question`/`choices`/`option`/`prompt`/`reasoning`/`confidence`/
  `expected`/`ground_truth`/`api_key` produced one match on the substring `"option"` — traced to the
  field name `label_option_match` (a boolean flag), **not** to any leaked option/choice text. No other
  forbidden field or content was found.
- No `hypothetical_answer` value was found copied into the official `submission.csv` — cross-checked:
  `syn_020_sequence`'s official answer is `C` (Base) while its `hypothetical_answer` is `D`.
- Artifact sizes: JSONL 7815 bytes (3 records), summary JSON 1309 bytes.
- This audit deliberately does **not** paste full JSONL records — only field names, closed-set values,
  and counts are reported above, per the task's "no raw record" constraint.

## 15. Artifact-path failure result

Two failure-probe attempts were made:

1. `--v12b-shadow-path /root/no_such_dir_xyz/confidence_v12b_shadow.jsonl` — the container runs as
   root, so `predict.py` successfully auto-created the missing parent directory and wrote the artifact;
   this was **not** a genuine failure case and is recorded here only to show the first attempt was
   invalidated, not silently dropped.
2. `--v12b-shadow-path /etc/hostname/confidence_v12b_shadow.jsonl` (and matching summary path) — `/etc/
   hostname` is an existing **file**, so attempting to create a path underneath it as a directory is
   guaranteed to fail even as root. Result:
   - `[predict] WARN v12b shadow JSONL not written (FileExistsError)`
   - `[predict] WARN v12b shadow summary not written (FileExistsError)`
   - Exit code: **0**. Official `submission.csv` (21 rows) was still written, with a SHA-256 identical
     to Run A.
   - The warning text contains only the operation name and the bare exception class (`FileExistsError`)
     — no path detail beyond what was passed on the command line by the operator, no raw exception
     message, no stack trace, no question/choice content.
   - `git status --short` confirmed clean immediately after this probe — no source/config change.

## 16. No-V13 / no-selector / no-legacy / no-API evidence

- Every `[predict]` log banner across all runs stated the enabled modes explicitly (e.g.
  `confidence-v12b-shadow: ON (observational; router-selected records only; no answer change, no
  V13/selector/legacy)`) — no run enabled `--legacy-dynamic-full`, and predict.py hard-refuses combining
  it with `--confidence-v12b-shadow` (`SystemExit("REFUSING: ... mutually exclusive")`, not exercised in
  this session since neither run requested legacy mode).
- No `V13`, `selector`, or `OpenRouter`/external-API flags exist in `predict.py --help`, and none were
  passed in any run.
- `official_answer_source` was `"base"` in every inspected V12B record (§14); the official CSVs in all
  five runs are byte-identical to the Base-only Run A.
- No network calls were made beyond what the Docker image itself performs internally (model was already
  baked into the image; no `huggingface_hub` download, no OpenRouter call — confirmed by the absence of
  any download/network log lines in any run's stdout).

## 17. GPU / runtime observations

Peak `nvidia-smi`-reported GPU memory (sampled at 1 Hz from the host during each run, `--rm` containers
so memory returns to ~0 MiB between runs):

| Run | Peak GPU memory |
|---|---|
| A | 6353 MiB |
| B | 6347 MiB (peak sampled from B's own log) |
| C | 6347 MiB |
| D | 6345 MiB |

All four peaks cluster tightly around **≈6.2–6.4 GiB**, consistent with AUDIT 71's real-model figure
(≈6.07 GiB *allocated*, measured differently — via `torch.cuda.max_memory_allocated()` — than
`nvidia-smi`'s *reserved* view here, so the two are not directly comparable but are in the same
ballpark). The GPU never approached the 8188 MiB card limit in any run. The failure-probe run's GPU
memory was not separately sampled (same model/config as Run C, so no different peak is expected).

## 18. Fake regression totals

Run inside the same image (CPU-only for these tests; `--gpus all` was omitted, producing a harmless
"NVIDIA Driver was not detected" notice from the base image's CUDA banner — the tests themselves require
no GPU):

- Suite 1 (`test_confidence_v12b_config_2l50a.py`, `test_qwen_predictor_backend_accessor_2l50b.py`,
  `test_confidence_v12b_artifacts_2l50c.py`, `test_confidence_v12b_shadow_2l50d.py`): **48 passed**.
- Suite 2 (`test_confidence_v12b_runner_2l49a.py`): **47 passed**.
- Suite 3 (`test_choice_scoring_2l48b.py`, `test_confidence_telemetry_2l48c.py`,
  `test_confidence_shadow_router_2l48d.py`, `test_confidence_shadow_router_2l48e.py`): **89 passed**.
- **Total: 184 passed, 0 failed** — matching the count previously reported from the Fedora-host
  mocked-test-only runs in AUDIT 90/91, now additionally confirmed inside the accepted Windows/GPU image
  itself.

## 19. Repository status

`git status --short` was checked before the first Docker command and again after the failure-safety
probe and the pytest suites: **clean** both times. All run outputs (submission CSVs, JSONL/summary
artifacts, stdout logs, GPU-memory samples) were written under session-only
`scratch/phase3a1_v12b_windows/` — `scratch/` is gitignored, and no tracked file was created, modified,
or deleted by any Docker run in this session. This audit file is the only tracked-repository change made
in this session.

## 20. Limitations

- **No organizer ground truth was used or is available.** All 21 items are self-authored synthetic
  diagnostics (same set as Audits 71/76); no accuracy or correctness claim is made anywhere in this
  audit.
- **Observational only.** V12B ran only inside the router-selected subset (3 of 21 records) and never
  influenced the official CSV in any of the five runs.
- **Thresholds remain provisional.** `provisional_margin_threshold=10.0` and `budget_divisor=8` are
  unchanged from AUDIT 76 and are not finalized by this run.
- **Run E was not executed.** No permitted no-selected fixture exists; constructing one would require
  altering committed thresholds, which was explicitly out of scope.
- **Duplicate-record preservation was not exercised** — the 21-item dataset has no duplicate `qid`s.
- **21 items is a small diagnostic set**, unsuitable for calibrating a final threshold or claiming
  routing/V12B effectiveness.
- **GPU-memory peaks were sampled from the host at 1 Hz**, not instrumented from inside the training
  loop, so brief sub-second spikes could be missed; figures should be read as approximate.
- **Weight-load timing varies with OS page-cache state** between consecutive container runs and must not
  be used to compare "V12B overhead" against Base — only the byte-identical official CSVs and JSONL
  counts are used to draw conclusions here.

## 21. Explicit confirmation

- No source, test, config, YAML, or Docker file was modified, added, or deleted in this session (only
  this audit file was created; `scratch/` outputs are gitignored/untracked).
- No Phase 3B implementation.
- No answer replacement — official CSV in every run (A, B, C, D, fail-probe) is byte-identical to
  Base-only Run A.
- No V13 execution or change.
- No selector execution or change.
- No legacy V12B (`--legacy-dynamic-full`) execution.
- No default promotion of shadow/V12B modes.
- No final threshold declared; `provisional_margin_threshold`/`budget_divisor` unchanged from AUDIT 76.
- No external API / OpenRouter call.
- No model download — model weights were already baked into the accepted image.
- No image rebuild or repull — the accepted digest
  `sha256:e62473ed524962fd44da393842a6adde0b4faf575327d4758680494555b6634a` was used for every run.
- No git commit and no git push were performed during this validation.
- AUDIT 90 and 91 were not modified.

## 22. Final verdict

**PHASE 3A-1 WINDOWS OBSERVATIONAL VALIDATION PASSED**

All required Docker/GPU preflight gates passed on the actual Windows host; Runs A–D and the
failure-safety probe executed successfully (exit 0) against the real accepted image and real baked
model; official CSVs were confirmed byte-identical to Base across every run including the two V12B-shadow
runs and the induced-failure run; V12B shadow artifacts were confirmed schema-clean, privacy-safe, and
internally consistent between Run C and Run D; 184/184 fake-regression tests passed. Run E is recorded
as unavailable (no permitted fixture) rather than fabricated. This verdict makes no accuracy, calibration,
or production-readiness claim beyond what is stated in §20.
