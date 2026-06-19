# FastMCQ-Agent — Project Status & Roadmap

_Last updated: 2026-06-19 · Branch: `deployment` @ `137269d` · Working tree clean_

> This is a project-overview and planning document. **No solver features were
> changed while producing it.** Where something has not been executed on a real
> model, it is stated explicitly.

---

## A. Executive summary

**What this is.** FastMCQ-Agent is an inference system for a **Vietnamese
multiple-choice QA** competition (HackAIthon 2026, Board C / Innovator). It reads
a question set, predicts one answer label per question, and writes a submission
CSV.

**The task.** For each record (`qid`, `question`, `choices`), output a single
label (`A`, `B`, `C`, ...) sized to that question's number of choices. The public
test has **463 samples** with **2–11 choices** each. There is no ground-truth
file, so development is **leaderboard-driven**.

**Current maturity.** Solid, well-tested *infrastructure* with a *baseline*
solver and a *built-but-unexecuted* local-LLM framework. Four phases are
complete (1, 1.1, 2A, 2B/C); each has an audit. 33/33 unit tests pass; the
baseline validates end-to-end and in Docker.

**Ready for baseline submission?** **Yes.** `AlwaysASolver` produces a
structurally valid `pred.csv` (463 rows, all labels valid) locally and in Docker.
A baseline submission would score at roughly random-choice accuracy, but it is a
safe, valid fallback.

**Ready for a competitive LLM submission?** **Not yet.** The LLM solver code
exists and is unit-tested up to the model boundary, but **no real model has ever
been run** (no local model / no torch / no transformers in the environment).
Until a real local-model run is done and validated, no accuracy claim can be made.

---

## B. Competition contract checklist

| Item | Status | Notes |
|---|---|---|
| Reads from `/data` | **DONE** | `run.py` auto-detects `private_test.csv` → `private-test.json` → `public_test.csv` → `public-test.json` → any `.csv`/`.json`. |
| Writes `/output/pred.csv` | **DONE** | Default output path; parent dir auto-created. |
| Output columns `qid,answer` | **DONE** | Enforced by `data_io.write_predictions`; checked by validator. |
| Supports JSON input | **DONE** | List-of-objects + wrapper keys; verified on the 463-sample public test. |
| Supports CSV input | **DONE** | `A,B,C,D` / `option_*` / `choice_*` / single `choices` column. Unit-tested; **not yet seen on a real competition CSV** → some residual schema risk. |
| Variable number of choices | **DONE** | Dynamic `A..Z` labels (2–11 verified); never hard-coded to A–D. |
| Docker works | **DONE** | Builds on `python:3.11-slim`; baseline run + validate PASS; auto-detect works for any mounted filename. |
| GitHub reproduction instructions | **PARTIAL** | README has full local + Docker instructions, **but all work is on branch `deployment`; `main` still points at the bare initial commit.** Must merge/push before graders clone. |
| Method document exists | **DONE** | `docs/METHOD.md` covers Phase 1 → 2B/C + future work. |
| Experiment log exists | **DONE** | `experiments/leaderboard_log.csv` with baseline + two pending LLM rows (scores blank). |
| Docker Hub readiness | **NOT STARTED** | Image builds locally; not tagged/pushed to a registry. Verify whether the competition requires Docker Hub. |
| Final model packaging | **NOT STARTED** | No model selected, no weights packaged, no model-bearing image. The light baseline image carries no model. |

---

## C. Dataset understanding

From `docs/DATASET_PROFILE.md` (auto-generated; 463 samples):

**Reliable, structural facts (trust these):**
- **463 samples**, QID pattern `test_####`.
- **Choice-count distribution:** 4→318, 10→134, 3→6, 2→3, 5→1, 11→1.
  → **136 (29.4%) have >4 choices** (a large 10-choice cluster); **9 have 2–3**.
  Dynamic labels are mandatory, and ~29% of the test cannot be served by an
  A–D-only system.
- **Long-context passage questions: 100 (21.6%)** via markers (`Đoạn thông tin`,
  `Nội dung:`, `Tiêu đề:`, `-- Đoạn văn`). **Short standalone (<200 chars): 259 (55.9%)**.
- **Question length:** median 173 chars, mean ~1371, **max 8712** — a long tail
  that will exceed small prompt budgets without truncation.
- **6 samples have duplicate answer choices** (edge cases to keep in mind).

**Rough, NOT-reliable signals (do not over-trust):**
- The category breakdown (math 26%, general 22%, reading 22%, economics 11%,
  physics 9%, then law/history/chem/bio/ethics) is **single-label keyword
  heuristic**. Categories overlap heavily (a 10-choice chemistry calculation may
  be tagged `math_calculation`), and the keyword lists are hand-made. Treat these
  as *indicative proportions only* — **never** branch critical logic on them
  without independent verification.
- Template/near-duplicate detection found **0 groups**; that is a limitation of a
  cheap prefix heuristic, not proof that no templated families exist.

**Implications for solver design:**
- Must handle variable choice counts (done) and long contexts (head-tail
  truncation done, real-model behaviour unverified).
- The big 10-choice numeric/LaTeX cluster is the most distinctive sub-population
  and a natural target for later math-specific handling — *if* accuracy data
  later justifies it.
- Vietnamese throughout → model language coverage matters for model selection.

---

## D. Current architecture

```
            ┌─────────────┐
  /data ──► │  data_io    │  load JSON/CSV → normalise → {qid, question, choices}
            └─────┬───────┘
                  │ samples
                  ▼
            ┌─────────────┐   build_solver(name, model_path, ...)
            │ solver_     │◄───────────────── configs/default.yaml  +  CLI flags
            │  factory    │                   (CLI > config > default)
            └─────┬───────┘
                  │ selects one solver
     ┌────────────┼───────────────────────────────┐
     ▼            ▼                                 ▼
 AlwaysA     HFGenerateSolver                HFOptionScoreSolver
 (baseline)  prompting → generate →          prompting(mode=score) →
             output_parser → label           score " A.<text>" continuations →
                                              best avg log-prob → label
                  │            │ (per-sample debug → run_logger → outputs/run_debug.jsonl)
                  └─────┬──────┘
                        │ labels (dynamic A..K), fallback to A
                        ▼
                 ┌─────────────┐
                 │ postprocess │  validate each label; 1 row/qid; invalid → "A"
                 └─────┬───────┘
                       ▼
              /output/pred.csv  (qid,answer)
                       │
                       ▼
            scripts/validate_submission.py  (columns, coverage, dups, valid labels)
```

Component notes:
- **data loading** (`src/data_io.py`) — JSON + 3 CSV schemas → normalised dicts.
- **label handling** (`src/labels.py`) — index↔label, validity sized to choices.
- **baseline solver** (`src/baseline_solver.py`) — `AlwaysASolver` → "A".
- **solver factory** (`src/solver_factory.py`) — name→solver; lazy HF imports;
  clear errors for unknown name / missing model path.
- **prompting** (`src/prompting.py`) — Vietnamese prompts, shape detection,
  head-tail truncation that never drops choices; `direct`/`score` modes.
- **output parsing** (`src/output_parser.py`) — explicit-phrase patterns then
  standalone label; rejects out-of-range labels.
- **HF generation solver** (`src/hf_generate_solver.py`) — deterministic short
  generation → parse → fallback "A".
- **HF option-scoring solver** (`src/hf_option_score_solver.py`) — length-
  normalised continuation log-prob; `torch.no_grad()`; fallback to generation→A.
- **logging** (`src/run_logger.py`) — per-sample JSONL debug (never `pred.csv`).
- **validation** (`scripts/validate_submission.py`) — full contract checks.
- **Docker** — light `python:3.11-slim`; baseline only (no torch/model).

---

## E. What has been implemented (by phase)

### Phase 1 — Repository skeleton & baseline
- **Purpose:** clean, reproducible pipeline; valid submission contract.
- **Main files:** `run.py`, `src/{data_io,labels,solver_base,baseline_solver,postprocess,utils}.py`, `scripts/{validate_submission,inspect_dataset,run_local}.py`, `Dockerfile`, `requirements.txt`, tests.
- **Validation:** baseline run + validate PASS; tests pass.
- **Limitations:** zero real accuracy (format baseline only).

### Phase 1.1 — Docker hardening
- **Purpose:** make the container filename-agnostic.
- **Main files:** `Dockerfile` (CMD no longer hard-codes the input filename).
- **Validation:** built and ran with `public-test.json` and `private-test.json` mounted — both auto-detected, validate PASS.
- **Limitations:** none material; image is still baseline-only.

### Phase 2A — Dataset profiling & experiment tracking
- **Purpose:** understand the data; set up leaderboard-driven workflow.
- **Main files:** `scripts/profile_dataset.py`, `docs/DATASET_PROFILE.md`, `experiments/{README.md,leaderboard_log.csv}`.
- **Validation:** profiler runs; 463-sample profile produced; sample submission inspected (only 4 rows, A–D only — an illustrative format sample, not a coverage oracle).
- **Limitations:** category heuristics rough; template detection cheap (0 groups).

### Phase 2B/C — Competitive local-LLM framework
- **Purpose:** modular local-LLM solvers behind `BaseSolver`.
- **Main files:** `src/{prompting,output_parser,hf_common,hf_generate_solver,hf_option_score_solver,solver_factory,run_logger}.py`; updated `run.py`/`configs/default.yaml`; `scripts/{run_llm_smoke,run_llm_full}.sh`, `scripts/benchmark_runtime.py`; tests for prompting/parser/factory.
- **Validation:** 33/33 unit tests pass; baseline + Docker still pass; negative tests (missing model path / unknown solver / bad path) error cleanly (exit 2); lazy imports confirmed (no torch needed for baseline/tests).
- **Limitations:** **never executed on a real model**; scoring math reviewed but unverified end-to-end; torch/transformers not in `requirements.txt`.

---

## F. What has NOT been done yet

- **No real LLM inference has ever been run.** `outputs/run_debug.jsonl` is empty.
- **No leaderboard score is known** for any solver (all `leaderboard_score` cells blank).
- **No model selected or packaged.** No weights in the repo or image.
- **No quantization / batching / vLLM / llama.cpp backend.**
- **No adaptive routing** (shape detection exists and tailors the prompt, but does not switch solvers/models).
- **No self-consistency / PAL / math verification.**
- **No final Docker image carrying model weights.**
- **No Docker Hub push.**
- **`main` branch not updated** — all work is on `deployment`.

---

## G. Risk assessment (ranked)

**1. Highest-risk submission blockers**
- **Branch/reproducibility:** `origin/main` is still the bare initial commit; all
  work is on `deployment`. If graders clone the default branch, they get nothing.
  → *Merge/publish before any deadline.* **(Highest)**
- **Exact scoring rubric unknown from repo:** the bundled PDF is the **general**
  HackAIthon rules (Board C = "use LLMs to build multi-task AI agents") and does
  **not** state the MCQA accuracy/speed weighting or the submission mechanism.
  → *Verify the precise metric, time budget, and submission/packaging format.*
- **LLM path unproven:** a competitive submission depends entirely on code that
  has never run on a model.

**2. Accuracy risks**
- Option-scoring scores `label + choice text`, so a choice's intrinsic fluency
  influences its score (known property; unverified impact).
- Prompt/parse quality is untested on real outputs; parser may need tuning per model.
- Head-tail truncation can drop a passage's decisive middle.

**3. Runtime risks**
- Option scoring does one forward pass **per choice**; 10–11-choice questions
  (135 of them) cost 10–11× a single pass. With no batching and possible CPU-only
  execution, full-set latency is unknown and could be large.

**4. Docker / model-packaging risks**
- No model-bearing image exists; size, load time, and (if required) offline
  weight bundling are all unaddressed. `trust_remote_code` defaults off (safe) but
  some models need it on.

**5. Dataset / schema risks**
- CSV loader is unit-tested but unseen on the real private CSV; an exotic header
  could misparse (validator would surface the symptom).
- 6 duplicate-choice and a few extreme-length samples are edge cases.

**6. Documentation / reproducibility risks**
- Strong docs/audits, but they live on `deployment` (see risk 1). Method report
  for the final submission not yet assembled.

---

## H. Strategic direction

Assuming the stated criteria — **accuracy, inference speed, optimization/creativity
explanation** — the rational play under time pressure is to **prove the LLM path
quickly on a small model, lock in a valid submission early, then optimise only
where it pays.**

**Must-do before ANY leaderboard run**
1. **Resolve the branch/reproducibility risk** (publish work to the graded branch).
2. **Confirm the real scoring rubric, time budget, and submission format** (not in repo).
3. **Add an optional LLM dependency path** (`requirements-llm.txt`) so a real run is possible without bloating the baseline image.
4. **Obtain a local model** (small, Vietnamese-capable) and run the **smoke test**.

**Must-do before FINAL Docker submission**
5. A validated full run that produces `pred.csv` for the private set within the time budget.
6. A model-packaging decision (bundled weights vs. mounted) consistent with the rules.
7. Final `pred.csv` validated; method report assembled from these docs.

**Nice-to-have (only if time remains and data justifies)**
8. Speed: batching, quantization, faster backend (vLLM/llama.cpp).
9. Accuracy: prompt tuning, self-consistency, math handling for the 10-choice cluster, adaptive routing.

**Risky — avoid unless clearly ahead**
- Large/unfamiliar models without latency headroom; heavy multi-pass ensembles
  under an unknown time budget; broad refactors near the deadline.

Priority order: **1 → 2 → 3 → 4 → 5 → 6**, then optimise (8/9) as time allows.

---

## I. Recommended next phases

> **Canonical roadmap.** This supersedes earlier draft phase numbering in this
> document. The authoritative phase definitions live in
> [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) §11; the same names are used across
> all docs.

| Phase | Title | Status |
|---|---|---|
| 2C.1 | Model compliance + optional LLM requirements + score-mode hardening | **done** |
| 2D.1 | Local venv + LLM dependency readiness | **done** (env LLM-ready, GPU 7.6 GB) |
| 2E | Research-grounded multi-agent architecture | **done** (`docs/ARCHITECTURE.md`) |
| 2E.1 | Architecture hardening before implementation | **done** (this pass) |
| 2F | Lightweight agent modules (profiler, router, compressor, confidence) | **done** (with tests) |
| 2G | AdaptiveAgentSolver v1 | **done** (`adaptive_agent`, opt-in; gated advanced methods off) |
| 2H | Real model ablation and leaderboard logging | planned (needs `MODEL_PATH`) |
| 2I | Runtime optimization / quantization / batching | planned |
| 2J | Selective advanced reasoning (self-consistency / PAL-lite / debate-lite / ToT-lite) | planned, evidence-gated |
| 3 | Final packaging and report | planned |

Per-phase objectives, files touched, validation commands, success criteria, and
stop conditions are specified in `docs/ARCHITECTURE.md` §11. The **Minimal Viable
Agent v1** scope (exactly five modules; no PAL/debate/ToT/GoT/self-consistency) is
in `docs/ARCHITECTURE.md` §14.

---

## J. Immediate next action

**Implement Phase 2F — the lightweight agent modules** (`question_profiler`,
`question_router`, `passage_compressor`, `confidence`). They are pure Python, need
no model, are fully testable now, and unblock the AdaptiveAgentSolver (2G). This
is the highest-value work available without a `MODEL_PATH`.

**In parallel (non-code blockers):** confirm with BTC the MCQA scoring rubric,
time budget, and whether the Docker image must bundle weights; and standardise the
submission branch on `main` (now up to date — the earlier "main empty" blocker is
resolved). The first real leaderboard score (Phase 2H) remains blocked until a
compliant local model is provided.

**Suggested next prompt to request:**
> "Phase 2F: implement the lightweight agent modules (`src/question_profiler.py`,
> `src/question_router.py`, `src/passage_compressor.py`, `src/confidence.py`) per
> `docs/ARCHITECTURE.md` §14, with tests, keeping the baseline default and adding
> no torch dependency."
