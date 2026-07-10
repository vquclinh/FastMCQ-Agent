# AUDIT 76 — Windows Real-Model Validation of the Phase 2 Confidence-Aware Shadow Router (evidence record)

Audit number 76 (no prior `76-*` existed under `docs/audits/`).

## 1. Date, branch, full HEAD

- Date: 2026-07-10
- Branch: `main`
- Full HEAD: `7b8134cc8ada80fc4c0a5e15d45601bca7316364` ("add confidence-aware shadow router")
- Working tree: clean; AUDIT 71–75 committed.

> **Nature of this record.** This is a **documentation-only evidence record** of a real-model
> validation the user ran externally in a **Windows Docker container**. It creates no code/test/config
> change. The values below are transcribed from the user-supplied run.

## 2. Evidence provenance

- This evidence was produced by a **user-run Windows Docker validation**.
- The current Linux environment **did not** rerun the GPU/model commands; it only records the supplied
  external runtime evidence.
- The dataset was **21 self-created synthetic diagnostic MCQs**.
- **No organizer test labels or organizer ground truth** were used.
- **No model was downloaded**; **no external API / OpenRouter call** occurred.

## 3. Runtime environment

- Committed branch: `main`; Phase 2 commit: `7b8134c` ("add confidence-aware shadow router").
- Docker image: `vquclinh/fastmcq-local-selective:d0d8c28-lf`.
- Local model: `/models/qwen3-4b-instruct-2507`.
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU; CUDA availability: **true**.
- Source repository bind-mounted into: `/workspace/fastmcq`.
- Model weights were already present inside the image (no download).

## 4. Input preparation

- Input path inside the container: `scratch/phase2_real/synthetic21_input.json`.
- Item count produced by the preparation script: **21**.
- First qid: `syn_001_addition_3`; last qid: `syn_021_pills`.

## 5. PowerShell count-check caveat

- A PowerShell pre-check printed `Expected 21 input records; found 1`.
- Cause: PowerShell treated the parsed top-level JSON **array** as a single wrapped object in that
  particular count expression — **not** a model, router, dataset, or repository defect.
- Subsequent independent runtime checks proved **both** prediction runs processed **21** samples and
  **both** output CSVs contained **21** rows.
- Therefore this **harness-only** count warning does not invalidate the runtime evidence. This audit
  does **not** claim the faulty count expression itself passed — only that the actual runs and outputs
  were verified to be 21 records.

## 6. Baseline run

- Mode: normal **no-shadow** local-model prediction.
- Model loaded successfully.
- Samples predicted: **21**; deterministic fallbacks: **0**; official rows written: **21**.
- Mirrored baseline path: `scratch/phase2_real/baseline/submission.csv`.
- Reported prediction total: ≈ **37.153 s**. Status: **PASS**.

> The baseline total must **not** be used to estimate model-load time or per-question latency.

## 7. Shadow run

- Explicit flag: `--confidence-shadow-router`.
- Log explicitly stated: observational, **no answer change, no V12B/V13**.
- Model loaded successfully.
- Samples predicted: **21**; deterministic fallbacks: **0**; decisions written: **21**;
  selected: **3 of budget cap 3**; official rows written: **21**.
- Shadow decision path: `scratch/phase2_real/shadow/confidence_shadow_router.jsonl`.
- Shadow summary path: `scratch/phase2_real/shadow/confidence_shadow_router_summary.json`.
- Shadow CSV path: `scratch/phase2_real/shadow/submission.csv`.
- Reported prediction total: ≈ **27.154 s**. Status: **PASS**.

> The baseline (≈37.153 s) and shadow (≈27.154 s) elapsed totals must **not** be interpreted as proof
> that shadow mode is faster: they were **separate container/model-load runs** with different
> load/cache conditions. This run did **not** instrument the exact number of model-forward calls;
> one-forward scoring was already established by Phase 1 Windows validation (AUDIT 71) and by
> code/tests, and combined telemetry-plus-shadow single-scoring was established by integration tests
> (AUDIT 72/74), not measured by this shadow-only runtime run.

## 8. Official CSV byte-invariance evidence

SHA-256 (baseline): `3A8940B96A0CB33D8F221E01B41CC7418C059CD51F5F51D3C82002C2D5DBEB8D`
SHA-256 (shadow):   `3A8940B96A0CB33D8F221E01B41CC7418C059CD51F5F51D3C82002C2D5DBEB8D`

- Both hashes are non-empty and **identical**.

## 9. Row / order / answer invariance

- Both CSV files contain **21 rows**.
- qid order is identical.
- Every official answer is identical.
- No row was added, dropped, or reordered.
- **Phase 2 shadow mode did not change official predictions.**

## 10. Shadow summary

- `n_input`: 21
- `budget_cap`: 3
- `provisional_threshold`: 10.0
- `candidate_count`: 4
- `selected_count`: 3
- `scoring_method`: `next_token_logits_one_forward`

## 11. Candidate and selected-count behavior

- Cap = `ceil(21 / 8) = 3`.
- Selected count (3) did **not** exceed the cap.
- The router filtered candidates (4) **before** applying the cap (3) — i.e. threshold filtering then
  maximum-cap; no non-candidate backfill.
- Threshold 10.0 remains **provisional, shadow-only, and not final**.

## 12. Selected records and risk ranks

Selected records in risk-rank order:

| rank | qid | input_index | generated | top1 | top2 | logit_margin | normalized_entropy | reason |
|---|---|---|---|---|---|---|---|---|
| 1 | `syn_020_sequence` | 19 | C | C | D | 0.0 | ≈0.500023 | `low_logit_margin` |
| 2 | `syn_008_speed` | 7 | A | A | C | 4.25 | ≈0.053332 | `low_logit_margin` |
| 3 | `syn_001_addition_3` | 0 | A | A | C | 7.75 | ≈0.004552 | `low_logit_margin` |

These **exactly match** the prior metadata-only 21-record replay (AUDIT 72/74). (Synthetic
diagnostic interpretation of correctness lives only in AUDIT 71; correctness labels are not part of
this runtime-artifact discussion.)

## 13. Artifact schemas and sizes

- Baseline CSV size: **476 bytes**.
- Shadow CSV size: **476 bytes**.
- Shadow JSONL size: **9490 bytes**.
- Shadow summary size: **3247 bytes**.
- JSONL decision count: **21**; selected decision count: **3**.
- All decision records used `next_token_logits_one_forward`.
- Selected ranks were **1, 2, 3**.
- `selected_items` contained `qid`, `input_index`, and `selected_rank`.

## 14. Privacy and finite-JSON checks

All passed — the artifacts contain:

- no question field; no choices field; no prompt field; no reasoning field;
- no expected-answer field; no correctness/ground-truth field; no API-key field;
- no NaN; no positive or negative Infinity.

## 15. Git / scope invariance

- The working tree was clean before and after the Windows validation.
- The validation created only ignored/untracked runtime files under `scratch/`.
- **No tracked repository file changed.**
- No production code, test, config, audit, prompt, parser, formula bank, model setting, Docker file,
  dependency, V12B, V13, selector, or official-output contract changed.
- No commit or push occurred during the validation.

## 16. What the run proves (confirmed by real-model runtime)

- The Phase 2 CLI (`--confidence-shadow-router`) is present and functional.
- The local model loads under Docker/GPU.
- Shadow mode completes on **21 real model predictions**.
- **No parser fallback** occurred (0 deterministic fallbacks).
- The corrected score method (`next_token_logits_one_forward`) is present in **all** shadow records.
- The primary routing policy produced the expected **4 candidates** and **3 selected** records.
- The budget cap (`ceil(21/8)=3`) was respected.
- Selected ranks (1,2,3) and `selected_items` were emitted correctly.
- Official output remained **byte-identical** (SHA-256 match).
- Artifacts were **finite and privacy-safe**.

## 17. What it does not prove (not established by this run)

- A final production threshold.
- Calibrated accuracy improvement; leaderboard improvement.
- V12B effectiveness; V13 effectiveness; selector effectiveness.
- Combined telemetry-plus-shadow runtime forward count (not instrumented here).
- Exact shadow overhead — baseline/shadow runs had different model-load/cache conditions.
- Phase 3 correctness; readiness for default promotion.

The **21-item set is diagnostic only** and too small to finalize threshold calibration.

## 18. Remaining risks / caveats

- The provisional threshold `10.0` is a placeholder; no final threshold is claimed.
- Latency figures are single-run, load-condition-dependent, and not a valid speed comparison.
- Forward-count / combined-mode single-scoring rest on Phase 1 validation + integration tests, not on
  this shadow-only run.
- Real accuracy requires a larger permitted labeled set (future calibration task, not Phase 2).

## 19. Explicit confirmation

- No Phase 3 implementation.
- No V12B execution or change.
- No V13 execution or change.
- No selector execution or change.
- No answer override (official CSV byte-identical).
- No final threshold declared.
- No organizer ground truth used.
- No external API / OpenRouter call.
- No model download.
- No source / test / config change (only this audit file was created).
- No commit or push.

## 20. Current `git status --short`

```
?? docs/audits/76-windows-real-model-validation-phase2-shadow-router.md
```

(Working tree otherwise clean; this audit is the only new file.)

## 21. Recommended next action

Independent review of this evidence record, then **Phase 3 planning** (confidence-routed V12B) — with
a larger permitted labeled validation set to inform, not yet finalize, routing thresholds. Do **not**
promote the shadow/selective pipeline to the no-flag default on the basis of this diagnostic run.

## 22. Final verdict

**PHASE 2 WINDOWS REAL-MODEL SHADOW VALIDATION PASSED — PHASE 2 COMPLETE; READY FOR PHASE 3 PLANNING,
NOT DEFAULT PROMOTION**

Phase 3 has **not** been implemented or validated.
