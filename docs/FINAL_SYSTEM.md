# FASTMCQ-Agent — Final System (Source of Truth)

This is the single, current source-of-truth document for understanding and presenting
FASTMCQ-Agent. It supersedes the earlier `ARCHITECTURE.md`, `METHOD.md`, `MODEL_COMPLIANCE.md`, and
the phase-by-phase development audit trail (all consolidated here; the repository now retains only
the final production system, essential documentation, and validation tests — the historical
phase-by-phase audit records were removed once their conclusions were folded into this document).
This document is self-contained: it does not require any external audit file to be understood.

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
- **Status:** Round 2 was accepted with an earlier, Base-only Docker image
  (`vquclinh/fastmcq-agent:latest`, historical fact — see the evolution table in §6). This document
  now describes the **current, final submission**: a confidence-routed pipeline built on the same
  offline foundation, submitted as `vquclinh/fastmcq-agent-final:latest` (§2, §10).
- **Why offline:** the BTC private-test runtime is **internet-isolated** and mandates a **single
  open-weight model ≤ 5B parameters**. No external API, OpenRouter, or web retrieval is permitted at
  runtime. The system therefore runs one local model with the weights baked into the image.

---

## 2. Current production architecture (what the final image runs by default)

```text
Dockerfile
  -> inference.sh                    (bash inference.sh -> python predict.py "$@")
    -> predict.py (no-flag default = full confidence pipeline)
      -> input resolver              (--input/$INPUT_FILE -> /code/private_test.json ->
                                       /code/public_test.json -> /app/data/* -> /data/*)
      -> dataset normalization       (src/utils/data_io.load_dataset -> {qid, question, choices})
      -> local Qwen3-4B model        (src/local_model/qwen_mcq_predictor, loaded ONCE, shared
                                       across every stage below)
      -> Base generation             (every record, once: deterministic greedy prompt + parse)
      -> one-forward confidence      (every record, once: next_token_logits_one_forward reads raw
         scoring                     next-token logits of the bare option labels -> top1, top2,
                                      logit_margin, normalized_entropy)
      -> confidence router           (deterministic ranking by margin/entropy; budget cap
                                       ceil(N / 20); selects at most that many low-confidence
                                       records; never backfills to reach the cap)
      -> V12B (router-selected only) (up to 6 option-order permutations per record, one greedy
                                       generation each, map back to original labels, accept only on
                                       valid_unique_majority; otherwise unresolved -> V13)
      -> V13 (V12B-unresolved only)  (one deterministic layer chosen automatically per record:
                                       programmatic_solver / content_first / least_to_most)
      -> deterministic selector      (src/local_model/confidence_full_pipeline.run_full_pipeline;
                                       final_source in {base, v12b, v13, base_fallback}; canonical
                                       label re-validated before write)
      -> whole-pipeline fallback     (any exception before the official write reverts every row to
                                       its Base answer; the run never aborts without output)
      -> per-sample timing           (real seconds around each prediction)
      -> submission writers          (/code/submission.csv, /code/submission_time.csv)
      -> optional diagnostics        (privacy-safe JSONL/summary artifacts; no question, choices,
                                       prompt, or model-response text ever written)
```

**Two names, two systems — do not confuse them.** The codebase contains two independent
implementations that both happen to be called "V12B" and "V13":

| | Legacy (`--legacy-dynamic-full` only) | Current default (this section) |
|---|---|---|
| Modules | `src/layers/v12b_dynamic_layer.py`, `v13_dynamic_layer.py` | `src/local_model/confidence_v12b_runner.py`, `confidence_v13_runner.py` |
| Model | OpenRouter-era `qwen/qwen3.5-9b` prototype origin | Offline local `Qwen3-4B-Instruct-2507` (same shared instance as Base) |
| Budget | `ceil(N / 8)` per selective layer | `ceil(N / 20)` shared router budget |
| Reachable via | `predict.py --legacy-dynamic-full` (isolated dev path, §6) | no flag (default), or `--confidence-full-pipeline` (explicit alias) |

### Execution-mode table

| Flag | Behavior | Official answers |
|---|---|---|
| *(none)* | Full confidence pipeline (Base → scoring → router → V12B → V13 → selector) | Pipeline output |
| `--confidence-full-pipeline` | Explicit alias of the same default pipeline; executed exactly once (not twice) | Pipeline output |
| `--base-only` | Base-only escape hatch: no router, no V12B, no V13, no selector | Base generation only |
| `--confidence-v12b-shadow` | Router + V12B run observationally against a fake/real backend for diagnostics | **Always Base** — never overridden |
| `--confidence-shadow-router` | Router runs observationally, no V12B/V13 | **Always Base** — never overridden |
| `--confidence-telemetry` | Confidence scoring recorded to JSONL, no routing decision | **Always Base** — never overridden |
| `--legacy-dynamic-full` | Isolated legacy dev path (§6/§7); mutually exclusive with every confidence-pipeline flag above | Legacy selector output |

No-flag and `--confidence-full-pipeline` resolve to the identical code path in `predict.py`'s
execution-mode resolver — the pipeline is never accidentally run twice. Six pairwise mode conflicts
(e.g. `--legacy-dynamic-full` + `--confidence-v12b-shadow`) are rejected with `SystemExit` before the
model is constructed.

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
   `CMD ["bash", "inference.sh"]`, `WORKDIR /code`, no `ENTRYPOINT` beyond that.
3. **Input resolver** (`predict.py`). Priority: `--input` → `$INPUT_FILE` →
   `/code/private_test.json` → `/code/public_test.json` → `/app/data/*.json` → `/data/*.json` →
   `/data/*.csv`. Refuses with a clear error if nothing is found.
4. **Data normalization** (`src/utils/data_io.py`). Accepts a JSON list or a dict wrapper
   (`data`/`questions`/`items`/`samples`), or CSV (`csv.DictReader`). Normalizes each record to
   `{qid, question, choices}`: qid from `qid`/`id` else synthetic `q_0000`…; question from
   `question`/`text`/`prompt`/`content`; choices from a JSON list, a delimited/JSON `choices` string,
   or choice columns (`A`, `option_a`, `choice_1`).
5. **Local model loading** (`QwenMCQPredictor.load`). Lazy `torch`/`transformers` import (so the
   module is unit-testable without them); loaded **once** and shared by every pipeline stage;
   `bfloat16` on CUDA else `float32`; `device_map="auto"` on CUDA; `AutoTokenizer`/
   `AutoModelForCausalLM.from_pretrained(..., trust_remote_code=True)`; `.eval()`.
6. **Base generation** (`QwenMCQPredictor.predict_one`). Vietnamese answer-only prompt
   (`build_mcq_prompt`), chat template applied (`add_generation_prompt=True`, fallback to raw
   prompt); `model.generate(max_new_tokens=64, do_sample=False, num_beams=1, pad_token_id=eos)`;
   `parse_label` returns the first `[A-K]` character valid for the item; invalid/missing falls back
   to the first valid label (`predict.py._coerce_label`/`_fallback_answer`) — every qid always gets a
   valid label from this stage alone, independent of every later stage.
7. **One-forward confidence scoring** (`src/local_model/choice_scoring.py`,
   `next_token_logits_one_forward`). One additional forward pass per record reads the raw
   next-token logits over the bare, single-token option labels (no generation, no sampling) and
   derives `top1`, `top2`, `logit_margin` (`top1_logit − top2_logit`), and `normalized_entropy`
   (softmax entropy over valid labels, normalized to `[0, 1]`). Governed by
   `configs/confidence_selective.yaml` / `src/local_model/confidence_config.py`
   (`ChoiceScoringConfig`); disabled ⇒ router/V12B/V13 are skipped entirely and every record is Base.
8. **Confidence router** (`src/local_model/confidence_shadow_router.py`). Flags a record as a
   candidate against a configured margin/entropy threshold, ranks candidates deterministically, and
   selects at most `budget_cap = ceil(N / budget_divisor)` (`budget_divisor = 20` by default; see §
   "Router budget" below). The cap is a ceiling, not a target — fewer genuinely uncertain records
   means fewer selected, and the router never backfills with high-confidence records to fill the
   budget.
9. **V12B — option-permutation majority vote** (`src/local_model/confidence_v12b_runner.py`). For
   each router-selected record only: up to 6 permutations of the option ordering, one independent
   greedy generation per permutation, votes mapped back to the record's original labels. Accepted
   only when `aggregate_status == valid_unique_majority` and the resulting label is valid for the
   item; any generation failure on a permutation is counted, not fatal to the record.
10. **V13 — deterministic multi-layer reasoning** (`src/local_model/confidence_v13_runner.py`). Runs
    only for records V12B leaves unresolved. `_choose_layer` deterministically selects exactly one
    of: `programmatic_solver` (safe AST-based arithmetic evaluator — never `eval`/`exec`),
    `content_first` (states the answer's content before mapping it to a label), or `least_to_most`
    (ordered constraint decomposition). Each layer either returns a valid label or defers.
11. **Deterministic selector** (`src/local_model/confidence_full_pipeline.py:run_full_pipeline`).
    Conservative priority across the four candidate sources (`base`, `v12b`, `v13`, `base_fallback`)
    produces `final_source` per record; every label is re-validated against the item's own choices
    inside the selector before it can reach the output writer (the canonical-label enforcement fix).
12. **Whole-pipeline fallback**. Any exception raised anywhere in stages 7–11, before the official
    CSV is written, reverts every row to its already-computed Base answer — the run still completes
    and still writes valid output.
13. **Per-sample timing** (`predict.py` main loop). `time.time()` around each prediction; per-sample
    exceptions fall back and do **not** abort the run; a `failures` count is printed. Model-load and
    dataset-load time are excluded from per-sample timing.
14. **Output writing** (`predict.py`). `submission.csv` (header `qid,answer`) and
    `submission_time.csv` (header `qid,answer,time`, `%.6f` seconds). Also mirrors `submission.csv`
    to `--output`/`$OUTPUT_FILE` when set.
15. **Privacy-safe diagnostics** (optional, off by default; `--confidence-telemetry`,
    `--confidence-shadow-router`, `--confidence-v12b-shadow`, `--confidence-full-pipeline-path`/
    `-summary-path`). JSONL + summary artifacts keyed by `qid`/`source_record_ordinal`, carrying only
    numeric/categorical fields (scores, margins, flags, counts) — never the raw question, choices,
    prompt, or any model-generated text. Diagnostic write failures are independent, atomic, and
    degrade to a warning without ever affecting the official CSVs.

### Router budget: `ceil(N / 20)`

`budget_cap = max_targets_override` if explicitly set, `else ceil(N / budget_divisor)` with
`budget_divisor = 20` (dataclass default in `confidence_shadow_router.py`, and the fallback in
`confidence_config.py` and `configs/confidence_selective.yaml`). Worked examples:

| N (input records) | `ceil(N / 20)` |
|---|---|
| 30 | 2 |
| 120 | 6 |
| 463 (current public test) | 24 |
| 2000 | **100** |

Only records the router actually selects (at most this many) ever reach V12B; only the subset V12B
leaves unresolved ever reaches V13. It is normal, and expected, for the realized candidate count to
be smaller than the cap. `ceil`, not `floor`, is used deliberately so that a nonzero remainder
always rounds up to at least one additional candidate (confirmed by the budget-cap unit tests in
`tests/unit/test_confidence_shadow_router_2l48d.py`).

---

## 4. Current production strengths

- **Bounded, budget-capped escalation:** every record gets a fast Base pass; at most `ceil(N/20)`
  genuinely low-confidence records get the extra V12B/V13 compute — cost and latency stay
  predictable even in the worst case.
- **Fail-closed at every layer:** per-permutation, per-record, and whole-pipeline fallbacks all
  revert to the already-valid Base answer; the run cannot lose or corrupt a row because an
  escalation stage failed.
- **Offline & self-contained:** one baked open-weight model, one shared instance across every
  stage; no API, no internet, no vector DB; passes `--network none`.
- **Reproducible:** exact-pinned `torch==2.7.1` + pinned `requirements.txt`; deterministic greedy
  decoding at every generation call; model baked at a fixed path.
- **Strict Docker & output contract:** fixed input priority and the exact
  `submission.csv` / `submission_time.csv` schemas the organizer expects, unchanged by any
  execution mode.
- **Privacy-conscious diagnostics:** optional artifacts never contain question text, choice text,
  prompts, or model responses — only numeric/categorical signals.
- **Model loaded once:** single load, shared across Base generation, confidence scoring, V12B, and
  V13 — no per-stage reload.
- **Defensive label validation:** the selector re-validates every candidate label against the
  item's own choices before it can reach the output — never an out-of-range label.
- **Target-environment fit:** CUDA 12.8+ image for the confirmed RTX 5060 Ti / Blackwell / 32 GB
  target; no vLLM, so `--ipc=host`/`--shm-size` are not required, only `--gpus all`.

---

## 5. Current limitations (confirmed)

- **No organizer ground truth in-repo:** every accuracy figure cited anywhere in this repository is
  from self-authored synthetic diagnostic sets, not the real private test — true competition
  accuracy is unknown until the organizers score it.
- **V12B/V13 add generation cost only for the routed subset:** worst case still bounds to
  `ceil(N/20)` extra records, but that subset's wall-clock is higher than a pure Base run; not yet
  benchmarked against a hard per-submission time budget. Diagnostic-mode timing is not necessarily
  representative of default full-pipeline-mode timing.
- **Parser scope:** the label parser scans `[A-K]` only (labels beyond K, if a future set had them,
  would fall back), and picks the first matching letter. Mitigated by the answer-only prompt.
- **`base_fallback` is generic:** when the selector cannot accept `v12b`/`v13` and must fall back, it
  falls back to the already-computed Base answer — a coverage guarantee, not an accuracy strategy.
- **UTF-8 BOM inputs** (e.g. PowerShell-generated JSON/CSV) use `encoding="utf-8"`, not `utf-8-sig` —
  a BOM can break parsing. Known, not yet fixed.
- **Model-load failure** happens outside the per-sample try/except: a missing model / no-CUDA / OOM
  at load aborts the run with no output file.
- **No fixed seed:** greedy decoding is deterministic in practice, but no seed is set.
- **Windows/Docker Desktop/WSL2 operational risk:** real-model validation runs on the development
  machine have intermittently hit a Docker Desktop/WSL2 "unexpected EOF" crash immediately after
  model-weight loading, requiring a manual Docker Desktop restart. This is host/OS tooling
  instability, not a defect in the image itself, but is worth the evaluator knowing about if a
  first run appears to hang or die right after weight loading.
- **V12B/V13 coverage is not identical to the legacy prototype's scope:** e.g. the current
  `programmatic_solver` layer is a safe AST-based evaluator, not necessarily the same ~25-family
  formula registry described for the legacy prototype in §7 — exact family coverage should be
  verified against `confidence_v13_runner.py` before making specific coverage claims.

---

## 6. System evolution (presentation-ready)

```text
baseline solver (AlwaysASolver)
  -> OpenRouter prototype (Round 1, qwen/qwen3.5-9b)
  -> V11  (independent full run)
  -> V12B (option-permutation debiasing, legacy/OpenRouter)
  -> V13  (multi-layer reasoning: programmatic / content-first / least-to-most, legacy/OpenRouter)
  -> competition offline constraint (internet-isolated, single <=5B model)
  -> local Qwen3-4B production redesign (predict.py offline path, Base-only)
  -> accepted Round-2 Docker system (vquclinh/fastmcq-agent:latest, Base-only)
  -> confidence-routed pipeline (offline, local-model V12B/V13, budget-capped)
  -> current final submission (vquclinh/fastmcq-agent-final:latest, this document, §2)
```

Concise history with the only measured (public-leaderboard) scores that have clear repository
evidence — **all belonging to the legacy OpenRouter prototype**, not the offline submission:

| Stage | System | Model | Public score |
|---|---|---|---|
| Baseline | `AlwaysASolver` (format check) | none | — |
| Round 1 | OpenRouter ReAct graph | `qwen/qwen3.5-9b` | not recorded |
| V10 | dynamic full (fallback baseline) | `qwen3.5-9b` | 77.75 |
| V11 | independent full run | `qwen3.5-9b` | 78.40 |
| V12B (legacy) | + option-permutation debiaser | `qwen3.5-9b` | 78.83 |
| V13 (legacy) | + multi-layer reasoning | `qwen3.5-9b` | 79.7 |
| Round 2 | offline local model, Base-only (accepted) | **Qwen3-4B-Instruct-2507** | not benchmarked in-repo |
| **Final** | **confidence-routed pipeline (current default)** | **Qwen3-4B-Instruct-2507** | **not benchmarked in-repo (synthetic diagnostics only)** |

**Important:** the legacy base→V12B→V13→selector row in this table was a **research prototype** that
depended on a network-hosted 9B model via OpenRouter (`src/layers/v12b_dynamic_layer.py`,
`v13_dynamic_layer.py`, reachable today only through `predict.py --legacy-dynamic-full`). It is a
**different codebase** from the current default confidence-routed V12B/V13
(`src/local_model/confidence_v12b_runner.py`, `confidence_v13_runner.py`, §2) — the scores above
measure the OpenRouter prototype only, never the offline Qwen3-4B model in any configuration.

---

## 7. Legacy ideas — status against the current confidence-routed pipeline

These concepts were built and validated as prototypes in the legacy (OpenRouter-era) system. Most
now have an **offline, local-model equivalent** as part of the current default pipeline (§2–§3); a
few remain aspirational. Do not assume the current implementation matches the legacy one in exact
mechanism or scope — only the underlying idea carries over.

- **Selective routing / risk scoring — now implemented, differently.** The legacy design routed by
  a deterministic question-category tag (`calculation` / `long_context` / `short_knowledge` /
  `law_admin` / `ambiguous` / `safety_ethics`) with budget `ceil(N/8)` per layer. The current
  confidence router instead routes by a **model-confidence signal** (logit margin / normalized
  entropy from one extra forward pass), not category tags, with a shared budget `ceil(N/20)` (§3).
- **Option-permutation debiasing (V12B) — now implemented.** `src/local_model/
  confidence_v12b_runner.py` re-asks each router-selected question under several option orderings
  and keeps an answer only on a valid unique majority — the same debiasing idea, offline and
  local-model-served.
- **Deterministic calculation solver (PAL-lite) — now implemented, scope not re-verified.** The
  `programmatic_solver` layer in `confidence_v13_runner.py` is a safe, non-`eval` AST arithmetic
  evaluator in the same spirit as the legacy ~25-family registry described here; exact formula-family
  coverage has not been re-verified against the legacy list as part of this documentation pass (see
  §5) and should not be assumed identical.
- **Content-first reasoning (V13) — now implemented.** `content_first` layer in
  `confidence_v13_runner.py`.
- **Least-to-most reasoning (V13) — now implemented.** `least_to_most` layer in
  `confidence_v13_runner.py`.
- **Conservative candidate merge — now implemented, differently.** The legacy design merged base +
  layer proposals via a confidence-bar override. The current selector
  (`confidence_full_pipeline.py:run_full_pipeline`) instead uses a fixed source-priority rule across
  `{base, v12b, v13, base_fallback}` with canonical-label re-validation (§3, item 11).
- **In-question evidence reranking — not yet implemented.** Long-context chunk reranking
  (BM25-lite + char-trigram + title bonus, optional local BGE-M3/Qwen3-Reranker with lexical
  fallback) has no equivalent in the current confidence pipeline.
- **Selective MCQ verifier + option elimination — not implemented in this exact form.** The current
  pipeline's uncertainty gating is the confidence router (§3, item 8) and its correction mechanism is
  V12B/V13, not a separate per-option verifier with a fixed override threshold.

---

## 8. Realized design intent, and what remains genuinely future work

The design intent originally sketched here — first-pass local prediction, an offline risk/confidence
signal, budget-gated selective refinement for hard questions, and a conservative final selector, all
without changing the Docker command or output contract — **is now the current default pipeline**
described in §2–§3. It was implemented and promoted incrementally (shadow-router → V12B-shadow →
full pipeline default → budget divisor 8→20), with each step validated before promotion.

What remains genuinely unimplemented, per §7:

- In-question evidence reranking for long-context items.
- A dedicated per-option verifier / elimination pass distinct from V12B's majority vote.
- Re-verification of `programmatic_solver`'s exact formula-family coverage against the legacy
  ~25-family registry.
- Any accuracy measurement against real organizer ground truth (synthetic diagnostics only, to date).

Any further change to this pipeline must be evidence-validated before adoption — no accuracy claim
without evidence, and no change to the Docker command, model identifier, input priority, or output
schemas without an explicit, documented decision.

---

## 9. Presentation-ready summary (for final-round slides)

- **Problem:** Vietnamese, multi-domain MCQA (463 public questions; 2–11 choices; ~22% long-context;
  ~26% calculation/STEM); no local ground truth (leaderboard-driven).
- **Constraints:** organizer Docker image; internet-isolated runtime; single open-weight model ≤5B;
  GPU RTX 5060 Ti / 32 GB, CUDA 12.8+; strict input `/code/private_test.json` and outputs
  `submission.csv` + `submission_time.csv`; no vLLM.
- **Solution:** a fully offline, single-model, confidence-routed Docker inference pipeline built on
  `Qwen/Qwen3-4B-Instruct-2507`. Every record gets one Base generation and one confidence-scoring
  forward pass; at most `ceil(N/20)` genuinely low-confidence records are escalated to an
  option-permutation majority vote (V12B) and, if still unresolved, a deterministic reasoning layer
  (V13); a conservative selector chooses the final answer with a whole-pipeline fallback to Base.
- **Architecture:** `Dockerfile → inference.sh → predict.py → (resolve → normalize → Base generate →
  confidence score → router → V12B → V13 → selector → fallback → time → write)`.
- **Strengths:** bounded worst-case escalation cost, fail-closed at every layer, offline &
  reproducible, strict unchanged output contract, privacy-safe diagnostics.
- **Research evolution:** baseline → OpenRouter prototype → V11 → legacy V12B (78.83) → legacy V13
  (79.7) → offline ≤5B constraint → local Qwen3-4B Base-only (accepted Round 2) → confidence-routed
  local V12B/V13 pipeline (current final submission).
- **Honesty note:** all accuracy figures cited in this repository are from internal synthetic
  diagnostics, not organizer ground truth.

---

## 10. Current source-of-truth files (define production behavior)

| File | Role |
|---|---|
| `Dockerfile` | Final image: CUDA 12.8 base, torch cu128, deps, build-time model download, offline env, `CMD ["bash","inference.sh"]` |
| `inference.sh` | Container command wrapper: `python predict.py "$@"` |
| `predict.py` | Entrypoint: execution-mode resolver, input resolve, per-sample loop, timing, output + diagnostics |
| `src/local_model/qwen_mcq_predictor.py` | Local Qwen backend: prompt build, single load, greedy generation, label parse (Base generation) |
| `src/local_model/choice_scoring.py` | One-forward confidence scoring (`next_token_logits_one_forward`, top1/top2/margin/entropy) |
| `src/local_model/confidence_config.py` | Loads `configs/confidence_selective.yaml`; defaults incl. `budget_divisor=20` |
| `src/local_model/confidence_shadow_router.py` | Confidence router: candidate flagging, ranking, `budget_cap = ceil(N/budget_divisor)` |
| `src/local_model/confidence_v12b_runner.py` | V12B: option-permutation majority vote for router-selected records |
| `src/local_model/confidence_v13_runner.py` | V13: `programmatic_solver` / `content_first` / `least_to_most`, automatic layer selection |
| `src/local_model/confidence_full_pipeline.py` | Deterministic selector (`run_full_pipeline`) and whole-pipeline fallback |
| `configs/confidence_selective.yaml` | Confidence-pipeline configuration (thresholds, `budget_divisor: 20`) |
| `src/utils/data_io.py` | Dataset load/normalize (JSON/CSV → `{qid, question, choices}`) |
| `src/utils/labels.py` | Dynamic label helpers (A..Z sized to choice count) and validity checks |
| `requirements.txt` | Pinned runtime dependencies (torch installed separately in the Dockerfile) |
| `scripts/download_local_model.py` | Build-time `snapshot_download` of `Qwen/Qwen3-4B-Instruct-2507` |
| `README.md`, `DOCKER_SUBMISSION.md` | Organizer-facing build/run commands and the I/O contract |

**Model:** `Qwen/Qwen3-4B-Instruct-2507` (4.0B < 5B, Apache-2.0). **Local path:**
`/models/qwen3-4b-instruct-2507`. **Model-policy note:** the competition allows a single open-weight
model ≤5B; the submitted Qwen3-4B satisfies this, and it is the only generation model loaded at any
stage of the current pipeline (Base, V12B, and V13 all share the one loaded instance). The earlier
≤9B / OpenRouter / BGE-M3 / Qwen-Reranker allowlist belonged to the legacy prototype and is not the
final policy.

---

*Historical detail (phase-by-phase development history, OpenRouter strategy, adaptive-orchestrator
design, neural-reranker benchmarks, per-version freeze notes) is intentionally not reproduced in
full here; it remains recoverable from Git history. This document plus the retained compliance
docs, dataset profile, and the two PDFs are the current documentation set.*
