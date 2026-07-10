# AUDIT 71 — Windows Real-Model Revalidation of Corrected Phase 1 Scoring (evidence record)

Audit number 71 (no prior `71-*` existed under `docs/audits/`).

> **Nature of this record.** This is an **evidence record** of a real-model revalidation the user ran
> externally in a **Windows Docker container**. The current Linux environment did **not** independently
> rerun the GPU/model measurements (no torch/transformers/baked model here). All figures are transcribed
> from the user-supplied run. **No organizer data or organizer ground truth was used** — every labeled
> question is a **self-created synthetic diagnostic** item; the "expected" answers are the author's own.

## 1. Runtime environment (user-run, Windows Docker)

- Docker image: `vquclinh/fastmcq-local-selective:d0d8c28-lf`
- Local model path inside the image: `/models/qwen3-4b-instruct-2507`
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, ≈ 8 GiB
- torch `2.7.1+cu128`, transformers `5.12.1`
- Corrected host source from committed `main` was bind-mounted into the container; model weights were
  already baked into the image; no model download and no external API call occurred.

## 2. Corrected three-item revalidation

- Total items: 3; scoring valid: **3/3**.
- Generation token IDs and scoring prompt IDs were **identical** for all 3.
- Greedy first token matched scored top-1 for all 3.
- Exactly **one** actual model forward per scoring call for 3-, 4-, and 10-choice items.
- Scoring method for all 3: `next_token_logits_one_forward`.
- Max difference between directly captured raw logits and `scores_by_label`: **0.0**.
- Mean scoring latency ≈ **0.308391 s**; max peak allocated GPU memory ≈ **6.069078 GiB**.

| choices | generated | top-1 | top-2 | logit margin | latency (s) |
|---|---|---|---|---|---|
| 3 | B | B | C | 23.125 | ≈ 0.306 |
| 4 | B | B | D | 21.375 | ≈ 0.313 |
| 10 | J | J | D | 27.75 | ≈ 0.306 |

This confirms: bare A–J token scoring matches real greedy generation; generation/scoring tokenization
is identical on the real tokenizer; the scorer reads the correct next-token distribution; one-forward
behavior is **real, not merely mocked**; scoring latency no longer grows with choice count in the
tested 3/4/10-choice cases.

## 3. Twenty-one-item synthetic evidence

- Total items: 21 — 2×(3 choices), 18×(4 choices), 1×(10 choices).
- Scoring valid: **21/21** (rate 1.0).
- Generated accuracy: **16/21 = 0.7619047619**.
- Scored-top1 accuracy: **16/21 = 0.7619047619**.
- Generated/scored-top1 agreement: **21/21 = 1.0**.
- All methods: `next_token_logits_one_forward`.
- Mean generation latency ≈ **0.572978 s**; mean scoring latency ≈ **0.298773 s**.
- Peak allocated GPU memory ≈ **6.071396 GiB**; model load + warm generation ≈ **44.870261 s**.

Raw-logit margin distribution (all 21): min 0.0, p10 7.75, p25 12.25, median 22.5, p75 23.625,
p90 23.875, max 27.5, mean 18.1071428571.

Margins when generation **correct**: min 9.0, p10 12.125, p25 20.71875, median 23.25, p75 23.65625,
p90 23.9375, max 27.5, mean 21.0.

Margins when generation **wrong**: min 0.0, p10 1.7, p25 4.25, median 7.75, p75 13.75, p90 16.6,
max 18.5, mean 8.85.

Lowest-margin items:

| # | qid | expected | gen/top1 | top2 | margin | entropy | correct |
|---|---|---|---|---|---|---|---|
| 1 | `syn_020_sequence` | D | C | D | 0.0 | ≈0.50002295 | wrong |
| 2 | `syn_008_speed` | C | A | C | 4.25 | ≈0.05333236 | wrong |
| 3 | `syn_001_addition_3` | B | A | C | 7.75 | ≈0.00455163 | wrong |
| 4 | `syn_007_bat_ball` | A | A | B | 9.0 | — | correct |
| 5 | `syn_021_pills` | B | B | A | 12.0 | — | correct |
| 6 | `syn_004_fraction_4` | C | C | B | 12.25 | — | correct |
| 7 | `syn_003_algebra_4` | C | B | C | 13.75 | — | wrong |

High-confidence wrong case: `syn_017_vn_spelling` — expected A, gen/top1 C, margin **18.5**, wrong.

## 4. Interpretation

- Raw-logit margin showed **useful diagnostic separation** on this small synthetic set.
- The three lowest-margin items were all wrong; correct-answer **median margin 23.25** vs wrong-answer
  **median 7.75**.
- Margin is useful **but not sufficient**: wrong answers also occurred at margins **13.75** and
  **18.5**.
- **Probability margin was heavily saturated** (softmax) and must **not** be the primary routing signal.
- **Entropy** is useful mainly as a **secondary / tie-breaking** signal.
- **Generated/scored agreement is an implementation consistency check, not an independent uncertainty
  signal**, because both use the same next-token distribution (agreement 21/21 by construction).
- **No final routing threshold** may be claimed from only 21 synthetic items.
- These results are **diagnostic, not competition accuracy**.

## 5. Verdict

**PHASE 1 REAL-MODEL VALIDATION PASSED — READY FOR PHASE 2 SHADOW ROUTER IMPLEMENTATION.**

This does **not** claim readiness for Phase 3, V12B, V13, default promotion, or leaderboard
improvement.

## 6. Confirmations

- Evidence is user-supplied (Windows Docker); the Linux environment did not rerun it.
- No organizer data / ground truth used; all labels are self-created synthetic.
- No model downloaded; no external API called; no Docker build/push; no Git commit/push for this record.
