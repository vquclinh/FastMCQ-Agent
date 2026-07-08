# FASTMCQ-Agent — Final System (Source of Truth)

This is the single, current source-of-truth document for understanding and presenting
FASTMCQ-Agent. It supersedes the earlier `ARCHITECTURE.md`, `METHOD.md`, `MODEL_COMPLIANCE.md`, the
`docs/archive/` research notes, and the phase-by-phase `docs/audits/` history (all consolidated here
and removed from the tree; Git history preserves them).

Companion documents retained alongside this one:
- `docs/BTC_SUBMISSION_COMPLIANCE.md`, `docs/BTC_FINAL_COMPLIANCE_MATRIX.md` — competition compliance.
- `docs/DATASET_PROFILE.md` — public-test dataset profile (schema, choice distribution, edge cases).
- `docs/hackaithon.pdf` — official competition rules (Hội Sinh Viên Việt Nam).
- `docs/Vietnamese_Student_HackAIthon.pdf` — team final submission technical report (Vòng 2).
- Root: `README.md`, `DOCKER_SUBMISSION.md`, `Dockerfile`, `inference.sh`, `predict.py`.

---

## 1. Project overview

- **Competition:** Vietnamese Student HackAIthon 2026, track **Bảng C — "Innovator"**, judged by the
  organizers ("BTC"). Author: Võ Quốc Linh.
- **Task:** Vietnamese, multi-domain multiple-choice question answering (MCQA). For each record
  (`qid`, `question`, `choices`), output exactly one answer label (`A`, `B`, `C`, …) sized to that
  question's number of choices (2–11 choices occur).
- **Status:** **Accepted — passed Round 2.** The Docker image was built, pushed to Docker Hub,
  executed by the organizers on the private test, and accepted.
- **Docker image:** `vquclinh/fastmcq-agent:latest`.
- **Why offline:** the BTC private-test runtime is **internet-isolated** and mandates a **single
  open-weight model ≤ 5B parameters**. No external API, OpenRouter, or web retrieval is permitted at
  runtime. The system therefore runs one local model with the weights baked into the image.

---

## 2. Current production architecture (what the accepted image actually runs)

```text
Dockerfile
  -> inference.sh                 (bash inference.sh -> python predict.py "$@")
    -> predict.py (default branch)
      -> input resolver           (--input/$INPUT_FILE -> /code/private_test.json -> /app/data -> /data)
      -> dataset normalization    (src/utils/data_io.load_dataset -> {qid, question, choices})
      -> local Qwen3-4B model      (src/local_model/qwen_mcq_predictor, loaded ONCE)
      -> prompt builder            (Vietnamese answer-only, labeled choices)
      -> deterministic generation  (greedy: do_sample=False, num_beams=1, max_new_tokens=64)
      -> label parser & validator  (first valid A–K label; validated against the sample's choices)
      -> fallback handling         (deterministic first valid label on any failure)
      -> per-sample timing         (real seconds around each prediction)
      -> submission writers        (/code/submission.csv, /code/submission_time.csv)
```

**Explicitly NOT part of the current default Docker runtime:** OpenRouter / any external API, the
legacy Base Predictor, the V12B option-permutation layer, the V13 multi-layer reasoning stack,
candidate pools, and the old dynamic conservative selector. Those belong to the research prototype
(section 6) and are reachable only via the dev-only flag `predict.py --legacy-dynamic-full`, never in
the offline submission.

---

## 3. Component-by-component explanation

Evidence in parentheses is the current source of truth.

1. **Docker build & model baking** (`Dockerfile`). Base `nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04`;
   installs `torch==2.7.1` from the CUDA 12.8 (`cu128`) wheel index, then `requirements.txt`
   (transformers, accelerate, safetensors, huggingface_hub, sentencepiece). At **build time**
   `scripts/download_local_model.py` fetches `Qwen/Qwen3-4B-Instruct-2507` into
   `/models/qwen3-4b-instruct-2507` (guarded by `ARG SKIP_MODEL_DOWNLOAD=0`; `=1` is CI/smoke only).
2. **Offline environment** (`Dockerfile`). `LOCAL_MODEL_PATH=/models/qwen3-4b-instruct-2507`,
   `TRANSFORMERS_OFFLINE=1`, `HF_HUB_OFFLINE=1`. Designed to pass `docker run --network none`.
   `CMD ["bash", "inference.sh"]`, `WORKDIR /code`.
3. **Input resolver** (`predict.py`). Priority: `--input` → `$INPUT_FILE` →
   `/code/private_test.json` → `/code/public_test.json` → `/app/data/*.json` → `/data/*.json` →
   `/data/*.csv`. Refuses with a clear error if nothing is found.
4. **Data normalization** (`src/utils/data_io.py`). Accepts a JSON list or a dict wrapper
   (`data`/`questions`/`items`/`samples`), or CSV (`csv.DictReader`). Normalizes each record to
   `{qid, question, choices}`: qid from `qid`/`id` else synthetic `q_0000`…; question from
   `question`/`text`/`prompt`/`content`; choices from a JSON list, a delimited/JSON `choices` string,
   or choice columns (`A`, `option_a`, `choice_1`).
5. **Prompt construction** (`src/local_model/qwen_mcq_predictor.build_mcq_prompt`). A Vietnamese
   answer-only instruction ("chỉ trả lời bằng ĐÚNG MỘT chữ cái…"), the question, the labeled choices
   sized by `labels_for(len(choices))`, and an answer cue. No chain-of-thought is requested.
6. **Local model loading** (`QwenMCQPredictor.load`). Lazy `torch`/`transformers` import (so the
   module is unit-testable without them); loaded **once**; `bfloat16` on CUDA else `float32`;
   `device_map="auto"` on CUDA; `AutoTokenizer`/`AutoModelForCausalLM.from_pretrained(...,
   trust_remote_code=True)`; `.eval()`.
7. **Inference parameters** (`QwenMCQPredictor.predict_one`). Chat template applied
   (`add_generation_prompt=True`, fallback to raw prompt); `model.generate(max_new_tokens=64,
   do_sample=False, num_beams=1, pad_token_id=eos)`; only the generated suffix is decoded.
8. **Output parsing** (`parse_label`). Returns the first character matching `[A-K]` that is a valid
   label for the sample; otherwise `None`.
9. **Fallback / validity coercion** (`predict.py._coerce_label`, `_fallback_answer`). A model label is
   accepted only if valid for the item; otherwise the deterministic fallback = the first valid label
   (`A` when there are no choices). Guarantees every input qid receives a valid label.
10. **Per-sample timing** (`predict.py` main loop). `time.time()` around each `predict_one` +
    coercion. Per-sample exceptions fall back and do **not** abort the run; a `failures` count is
    printed. Model-load and dataset-load time are excluded from per-sample timing.
11. **Output writing** (`predict.py`). `submission.csv` (header `qid,answer`) and
    `submission_time.csv` (header `qid,answer,time`, `%.6f` seconds). Also mirrors `submission.csv`
    to `--output`/`$OUTPUT_FILE` and to `/output/pred.csv` when writable (backward compatibility).

---

## 4. Current production strengths

- **Organizer-validated:** built, pushed, executed by BTC on the private test, **accepted in Round 2.**
- **Offline & self-contained:** one baked open-weight model; no API, no internet, no vector DB; passes
  `--network none`.
- **Reproducible:** exact-pinned `torch==2.7.1` + pinned `requirements.txt`; deterministic greedy
  decoding; model baked at a fixed path.
- **Strict Docker & output contract:** fixed input priority and the exact
  `submission.csv` / `submission_time.csv` schemas the organizer expects.
- **Deterministic inference:** greedy (`do_sample=False`, `num_beams=1`), no sampling, model in eval.
- **Model loaded once:** single load, then a per-sample loop — no per-question reload.
- **Per-sample failure isolation:** one bad sample cannot abort the whole run; it falls back.
- **Defensive label validation:** output is always a valid label from the sample's choices, or a
  deterministic fallback — never an out-of-range label; supports dynamic label counts (A–K+).
- **Target-environment fit:** CUDA 12.8+ image for the confirmed RTX 5060 Ti / Blackwell / 32 GB
  target; no vLLM, so `--ipc=host`/`--shm-size` are not required, only `--gpus all`.
- **Internally extensible:** the offline pipeline can be improved (section 8) without changing any
  organizer-facing Docker command or output contract.

---

## 5. Current limitations (confirmed)

- **Single-pass prediction:** one greedy generation per question; no self-consistency or second
  opinion in the production path.
- **Batch size one:** questions are processed sequentially (simple and robust, not throughput-optimal).
- **No selective second-pass reasoning yet:** the offline path has no risk-gated refinement.
- **Parser scope:** the label parser scans `[A-K]` only (labels beyond K, if a future set had them,
  would fall back), and picks the first matching letter — an answer embedded in stray text could be
  mis-parsed. Mitigated by the answer-only prompt.
- **Fallback is generic:** on failure it returns the first valid label (`A`), which is a coverage
  guarantee, not an accuracy strategy.
- **No confidence/risk routing:** every question takes the same single path; no difficulty triage.
- **No offline V12B/V13-style refinement in production:** the permutation-debiasing and multi-layer
  reasoning that helped the legacy prototype are not part of the accepted offline runtime.
- **UTF-8 BOM inputs** (e.g. PowerShell-generated JSON/CSV) use `encoding="utf-8"`, not `utf-8-sig` —
  a BOM can break parsing. Known, not yet fixed.
- **Model-load failure** happens outside the per-sample try/except: a missing model / no-CUDA / OOM at
  load aborts the run with no output file.
- **No fixed seed:** greedy decoding is deterministic in practice, but no seed is set.

---

## 6. System evolution (presentation-ready)

```text
baseline solver (AlwaysASolver)
  -> OpenRouter prototype (Round 1, qwen/qwen3.5-9b)
  -> V11  (independent full run)
  -> V12B (option-permutation debiasing)
  -> V13  (multi-layer reasoning: programmatic / content-first / least-to-most)
  -> competition offline constraint (internet-isolated, single ≤5B model)
  -> local Qwen3-4B production redesign (predict.py offline path)
  -> accepted Round-2 Docker system
```

Concise history with the only measured (public-leaderboard) scores that have clear repository
evidence — **all belonging to the legacy OpenRouter prototype**, not the offline submission:

| Stage | System | Model | Public score |
|---|---|---|---|
| Baseline | `AlwaysASolver` (format check) | none | — |
| Round 1 | OpenRouter ReAct graph | `qwen/qwen3.5-9b` | not recorded |
| V10 | dynamic full (fallback baseline) | `qwen3.5-9b` | 77.75 |
| V11 | independent full run | `qwen3.5-9b` | 78.40 |
| V12B | + option-permutation debiaser | `qwen3.5-9b` | 78.83 |
| V13 | + multi-layer reasoning | `qwen3.5-9b` | 79.7 |
| **Final** | **offline local model (submission)** | **Qwen3-4B-Instruct-2507** | **not benchmarked in-repo** |

**Important:** the legacy base→V12B→V13→selector system was a **research prototype** that depended on
a network-hosted 9B model via OpenRouter. It is **not** the final accepted runtime. When the offline
≤5B, internet-isolated constraint became binding, the submission was rewritten as the single-model
offline `predict.py` path (section 2). The V-scores measure the prototype, not the submitted Qwen3-4B
model — the offline model's accuracy on public/private test was never measured inside the repository.

---

## 7. Reusable legacy ideas for future offline improvement

These concepts were built and validated (as prototypes) in the legacy system and are worth reviving
**inside an offline, no-API pipeline**. None of them currently run in production.

- **Selective routing / risk scoring.** Deterministically profile each question (route:
  `calculation` / `long_context` / `short_knowledge` / `law_admin` / `ambiguous` / `safety_ethics`)
  and spend extra compute only on flagged, uncertain, or high-value questions. The legacy budget was
  `auto = ceil(N/8)` per selective layer, with full-coverage always guaranteed by a base pass.
- **Option-permutation debiasing (V12B).** Re-ask a hard question under several option orderings and
  keep an answer only if it is stable across permutations — removes option-position/ID bias. This is
  fully offline-compatible (it needs only repeated local generations).
- **Deterministic calculation solver (PAL-lite).** A registry of ~25 generic closed-form formula
  families (exponential decay/growth, Hess's law, related rates, GDP/inflation, price elasticity,
  expected-distinct, Kepler, relativistic γ/momentum, money multiplier, t/z statistic, acid–base
  neutralization, supply–demand gap, Cobb–Douglas isoquant, modular arithmetic, …). It computes an
  exact label from `question`+`choices` using **regex + arithmetic only** (no `eval`/`exec`, no qid
  logic, no answer table), and overrides the model only at high confidence (≥0.95). "Prefer no answer
  over a risky answer." Calculation was the largest bucket (~26% of the public set).
- **Calculation taxonomy discipline.** Families are added only with robust, safe parsing; ambiguous
  or optimizer-heavy cases are intentionally declined and left to the model. Each family ships with
  positive + decline + no-qid tests.
- **Content-first reasoning (V13).** Normalize/canonicalize the question content before answering
  (helps noisy or template-heavy items).
- **Least-to-most reasoning (V13).** Decompose a hard question into ordered sub-constraints before
  selecting the final option.
- **In-question evidence reranking.** For long-context items, chunk the passage already inside the
  question, score chunks against a choice-aware query (BM25-lite + char-trigram + title bonus), and
  pack the top chunks with the **question placed last** (a "lost-in-the-middle" mitigation). Default
  is dependency-free hybrid lexical; optional **local** neural rerankers (BGE-M3 embedding,
  Qwen3-Reranker-0.6B) exist and **fail closed** to lexical — never download anything,
  `local_files_only=True`. On the public set this cut long-context context length ~41% with zero
  fallbacks.
- **Selective MCQ verifier + option elimination.** A gated second pass that assesses each option and
  overrides the first answer only on confident disagreement (threshold ≥0.80), triggered only on
  uncertain/low-confidence/repair cases — a generic, private-test-safe robustness step.
- **Conservative candidate merge.** A base answer plus layer proposals are merged by a selector that
  overrides the base only when the agreement/confidence bar is cleared; otherwise the base stands.
  All qids are always emitted.

These require a compliant **local** model to run offline (no OpenRouter). The calculation solver,
permutation debiasing, and lexical evidence reranker are fully offline today; the verifier and V13
content-first/least-to-most passes previously used an LLM call that would need to be served by the
local model.

---

## 8. Future improvement architecture (intended direction — not yet implemented)

```text
accepted Round-2 baseline (offline Qwen3-4B, single pass)
  -> first-pass local Qwen prediction        (current production path, unchanged)
  -> offline risk scorer                      (deterministic route/risk features; no API)
  -> selective refinement for hard questions  (offline permutation debias / deterministic calc solver /
                                               local-model verifier, budget-gated)
  -> conservative final selector              (override the first pass only above a confidence bar)
  -> unchanged BTC output contract            (/code/submission.csv + submission_time.csv)
```

Design intent: keep the accepted single-pass offline prediction as the guaranteed-coverage base,
then add **offline-only** selective refinement (revived from the section-7 ideas, served by the local
model) for the minority of hard questions, merged conservatively — all **without changing** the
Docker command, model identifier, input priority, or output schemas. Any change must be A/B-validated
before adoption; no accuracy claim without evidence.

---

## 9. Presentation-ready summary (for final-round slides)

- **Problem:** Vietnamese, multi-domain MCQA (463 public questions; 2–11 choices; ~22% long-context;
  ~26% calculation/STEM); no local ground truth (leaderboard-driven).
- **Constraints:** organizer Docker image; internet-isolated runtime; single open-weight model ≤5B;
  GPU RTX 5060 Ti / 32 GB, CUDA 12.8+; strict input `/code/private_test.json` and outputs
  `submission.csv` + `submission_time.csv`; no vLLM.
- **Solution:** a fully offline, deterministic, single-model Docker inference pipeline built on
  `Qwen/Qwen3-4B-Instruct-2507`, baked into the image, answering each question with a greedy
  answer-only prompt and defensive label validation.
- **Architecture:** `Dockerfile → inference.sh → predict.py → (resolve → normalize → prompt →
  Qwen3-4B → parse/validate → fallback → time → write)`.
- **Strengths:** organizer-accepted (Round 2), offline & reproducible, strict output contract,
  per-sample failure isolation, extensible without changing organizer commands.
- **Research evolution:** baseline → OpenRouter prototype → V11 → V12B (78.83) → V13 (79.7) →
  offline ≤5B constraint → local Qwen3-4B production redesign → accepted Round-2 system.
- **Future improvement:** add offline risk-gated selective refinement (permutation debiasing,
  deterministic calculation solver, local-model verifier) with a conservative selector, keeping the
  BTC contract unchanged.

---

## 10. Current source-of-truth files (define production behavior)

| File | Role |
|---|---|
| `Dockerfile` | Final image: CUDA 12.8 base, torch cu128, deps, build-time model download, offline env, `CMD ["bash","inference.sh"]` |
| `inference.sh` | Container command wrapper: `python predict.py "$@"` |
| `predict.py` | End-to-end entrypoint: input resolve, per-sample loop, timing, output + mirrors (default = offline local model) |
| `src/local_model/qwen_mcq_predictor.py` | Local Qwen MCQ backend: prompt build, single load, greedy generation, label parse |
| `src/utils/data_io.py` | Dataset load/normalize (JSON/CSV → `{qid, question, choices}`) |
| `src/utils/labels.py` | Dynamic label helpers (A..Z sized to choice count) and validity checks |
| `src/utils/logging.py` | Runtime logging helper used by the local backend |
| `requirements.txt` | Pinned runtime dependencies (torch installed separately in the Dockerfile) |
| `scripts/download_local_model.py` | Build-time `snapshot_download` of `Qwen/Qwen3-4B-Instruct-2507` |
| `README.md`, `DOCKER_SUBMISSION.md` | Organizer-facing build/run commands and the I/O contract |

**Model:** `Qwen/Qwen3-4B-Instruct-2507` (4.0B < 5B, Apache-2.0). **Local path:**
`/models/qwen3-4b-instruct-2507`. **Model-policy note:** the competition allows a single open-weight
model ≤5B; the submitted Qwen3-4B satisfies this. (The earlier ≤9B / OpenRouter / BGE-M3 /
Qwen-Reranker allowlist belonged to the legacy prototype and is not the final policy; the offline
runtime runs exactly one generation model and no rerankers.)

---

*Historical detail (phase audits, OpenRouter strategy, adaptive-orchestrator design, neural-reranker
benchmarks, per-version freeze notes) is intentionally not reproduced in full here; it remains
recoverable from Git history. This document plus the retained compliance docs, dataset profile, and
the two PDFs are the current documentation set.*
