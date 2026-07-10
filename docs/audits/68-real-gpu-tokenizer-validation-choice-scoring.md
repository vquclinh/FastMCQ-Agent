# AUDIT 68 — Real-GPU / Tokenizer Validation of Phase 1 Choice Scoring (evidence record)

Audit number 68 (no prior `68-*` existed under `docs/audits/`).

> **Nature of this record.** This audit is an **evidence record** of a real-model validation the
> **user ran externally in a Windows Docker container**. It was **NOT independently rerun in the
> current Linux environment** — that environment has **no torch, no transformers, and no baked model
> weights** (`/models/qwen3-4b-instruct-2507` absent), so it cannot reproduce these GPU numbers. The
> figures below are transcribed from the user-supplied run and are used only to justify the
> correction in AUDIT 69. No GPU measurement in this file was produced locally.

## 1. Runtime environment (user-run, Windows Docker)

- Image: `vquclinh/fastmcq-local-selective:d0d8c28-lf`
- Model path: `/models/qwen3-4b-instruct-2507` (weights baked into the image)
- Host source: bind-mounted from committed `main`
- GPU: NVIDIA GeForce RTX 4060 Laptop GPU, ≈ 8 GiB VRAM
- torch `2.7.1+cu128`, transformers `5.12.1`
- No model download, no external API.

Current Linux review environment (for contrast): GPU visible (`nvidia-smi` RTX 4060, 8 GiB) but
`import torch` → ModuleNotFoundError, transformers absent, `/models/qwen3-4b-instruct-2507` absent,
`LOCAL_MODEL_PATH` unset. Therefore local reproduction was impossible.

## 2. Real tokenizer A–J results

- Tokenizer class: `Qwen2Tokenizer`.
- Bare `A`…`J` each tokenize to **exactly one token**; bare A–J token IDs are **32…41**.
- Space-prefixed `" A"`…`" J"` each also tokenize to exactly one token (different IDs, e.g. `" A"`=362,
  `" B"`=425, `" C"`=356, `" D"`=422).

## 3. Contextual tokenization results

- On the production-style rendered answer context, contextual candidate extraction was
  **prefix-consistent for 17/17 tested candidates**.
- No label required the isolated-encoding fallback.

## 4. Boundary-fallback count

- **0** boundary-merge fallbacks among the tested A–J labels. Sequence-length bias was therefore not
  observed for these single-token labels.

## 5. Real greedy first-token result

For `question="What is 2 + 2?"`, choices `A. 3 / B. 4 / C. 5 / D. 6`:
- Production greedy generation parsed answer: **B**.
- Raw next-token argmax token ID: **33**, decoded **bare `"B"`**.
- One-token greedy generation token ID: **33**, decoded **bare `"B"`**.
- The generated first token matched the **bare-label** group, and **matched none of the
  space-prefixed** label tokens.

## 6. Bare versus space-prefixed token IDs

| label | bare id | space-prefixed id |
|---|---|---|
| A | 32 | 362 |
| B | 33 | 425 |
| C | 34 | 356 |
| D | 35 | 422 |

## 7. Bare versus space-prefixed logits (one real forward, same next-token distribution)

Bare-label next-token logits: A(32)=**25.75**, B(33)=**53.5**, C(34)=**28.875**, D(35)=**30.0** →
top1 **B**, top2 **D**, true raw-logit margin **23.5**; generated first token matched this bare group.

Space-prefixed logits: `" A"`(362)=**−3.703125**, `" B"`(425)=**25.5**, `" C"`(356)=**−0.1348**,
`" D"`(422)=**3.09375** → top1 **B**, top2 **D**, margin **22.40625**; generated first token matched
**none** of these tokens.

Current Phase 1 scorer (`canonical_prefix=" "`) returned space-prefixed **full-vocabulary
log-probabilities**: A=−57.203125, B=−28.0, C=−53.634765625, D=−50.40625. A corrected bare scorer
returned raw logits A=−27.75, B=0.0, C=−24.625, D=−23.5 (relative to B; illustrative).

## 8. Why normalized label probabilities can approach 1.0 even when the wrong token family is scored

Softmax is computed over **only the candidate scores**. On an easy item the intended letter dominates
its family, so the space-prefixed family also yields a high normalized `P(B)` — the number *looks*
confident. But those scores come from the `" B"`-token distribution, **not** the token the model
actually emits (bare `B`). The confidence is internally consistent yet **measures the wrong event**,
so its absolute value and margin must not drive routing. On this easy example top-1/top-2 happened to
agree; on harder items the two families can diverge.

## 9. Three-item smoke-test results (user-run)

- scoring valid: **3/3**; generated/scored agreement: **3/3**; synthetic generated answers correct:
  **3/3**; scored top-1 correct: **3/3**.

## 10. Runtime and GPU-memory observations (user-run)

- Peak allocated GPU memory ≈ **6.19 GiB**.
- Scoring latency grew with option count: ≈ **1.19 s** (3 choices), ≈ **1.17 s** (4 choices),
  ≈ **3.10 s** (10 choices) — consistent with **one forward per label** (not one per item).

## 11. Confirmed canonical-prefix mismatch

The model's real first answer token is a **bare** label (id 33 = `"B"`), not a space-prefixed token.
The Phase 1 scorer scored `" "+label` and read a **different token family** from the one greedy
generation samples. The `canonical_prefix=" "` assumption is therefore **wrong** for this model.

## 12. Why further 20-item confidence-distribution characterization was stopped

Because the scoring method was found to evaluate the wrong token family and to perform N forwards per
item, collecting a 20-item margin/entropy distribution would characterize an **invalid** signal.
Distribution characterization was deferred until the scorer is corrected (AUDIT 69) and re-validated.

## 13. Verdict

**NOT READY FOR PHASE 2 — SCORING METHOD INVALID.**

## 14. Required correction

Score the **exact generation context + one model forward + bare valid-label next-token logits**:
render the same generation prefix, run the model once, read the next-token logits at the same
position greedy generation uses, and gather the raw logits of the **bare** single-token labels
(A, B, …) — no canonical space, no per-candidate teacher forcing. Implemented and audited in
**AUDIT 69**.

## 15. Confirmations

- No production code, test, or config was modified by this evidence record.
- The GPU numbers were **user-supplied** (Windows Docker) and were **not** rerun locally.
- No model was downloaded; no external API called; no API key inspected/printed; no Docker build/push;
  no Git commit/push performed for this record.
