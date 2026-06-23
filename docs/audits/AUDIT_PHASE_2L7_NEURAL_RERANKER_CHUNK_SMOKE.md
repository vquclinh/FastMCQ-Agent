# Audit — Phase 2L.7: Neural Reranker Usability + Long-Context Chunk Smoke

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Outcome (one line)

**Neural rerank is still not usable** (`sentence-transformers`/`FlagEmbedding` not
installed, no local reranker/embedding model staged). No smoke was run; **a future
v4 would fall back to lexical**. The comparison tooling is created and verified
(with a fake backend) so it is ready the moment a local model + dep are staged.

## Repo state

`git status --short` at audit (additions from 2L.6 + 2L.7, nothing committed):

```
 M configs/default.yaml
 M docs/EVIDENCE_RERANKER.md
 M run.py
 M src/evidence_reranker.py
 M src/openrouter_graph_solver.py
 M tests/test_evidence_reranker.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2L6_NEURAL_EVIDENCE_RERANKER_ADAPTER.md
?? docs/AUDIT_PHASE_2L7_NEURAL_RERANKER_CHUNK_SMOKE.md
?? docs/NEURAL_EVIDENCE_RERANKER.md
?? scripts/check_neural_reranker_env.py
?? scripts/compare_neural_vs_lexical_chunks.py
```

Frozen outputs present and untouched: `outputs/pred.csv`,
`outputs/pred_v2_calc_rerank.csv`. (`outputs/pred_v3a_verifier_selective.csv` does
not exist — v3a was only ever a subset-input experiment preflight, never a
committed CSV.)

## Step 1 — env check (`scripts/check_neural_reranker_env.py`)

```
sentence_transformers : NOT installed
FlagEmbedding         : NOT installed
torch                 : installed
CUDA                  : available (NVIDIA GeForce RTX 4060 Laptop GPU)
candidate model dirs  : 1
  - /mnt/vquclinh/models/Qwen3.5-9B  [config.json]
embedding method usable now : False
reranker  method usable now : False
=> Neural rerank NOT usable now. Falls back to hybrid_lexical.
```

A read-only scan of `/mnt/vquclinh/models`, `./models`, `/mnt/models` confirms the
only model present is the **Qwen3.5-9B generation model** — not a reranker/embedder
(it merely matched the `qwen` name hint). **Recommended local model path: none
available yet.**

## Step 2 — code/config confirmation

- `rerank_evidence_for_sample(sample, *, max_chars, top_k, candidate_top_k=12,
  method, optional_embedding_model, optional_reranker_model,
  neural_fallback_to_lexical=True, neural_scorer=None)` — two-stage: lexical
  candidates → optional neural rerank → pack.
- `build_neural_scorer(method, emb, rer)` builds a backend only with a LOCAL path
  AND importable dep; else `(None, False, reason)` (e.g.
  `dependency_missing:FlagEmbedding`, `no_reranker_model_path`).
- CLI flags (run.py): `--evidence-reranker-method {hybrid_lexical|embedding|reranker}`,
  `--evidence-embedding-model <local>`, `--evidence-reranker-model <local>`,
  `--evidence-candidate-top-k <int>`, `--no-evidence-reranker`.
- Trace fields: `evidence_reranker_requested_method`, `…_effective_method`,
  `evidence_neural_available`, `evidence_neural_fallback_reason`,
  `evidence_candidate_chunk_count`, `evidence_selected_chunk_count`,
  `evidence_selected_chars`.
- Usable method now: **none** (`embedding` and `reranker` both fall back to lexical).

## Step 3 — chunk-comparison script (created)

`scripts/compare_neural_vs_lexical_chunks.py`:
- Selects only `long_context` samples (`has_long_context`).
- Per sample: runs lexical rerank and neural rerank, compares `kept_chunk_ids`,
  records effective method, fallback reason, candidate count, selected chars,
  and a `changed` flag; writes compact JSONL (no full passages).
- No OpenRouter, no CSV, no ground truth, no qid-based decisions.
- If the neural backend is unavailable it prints the reason and **writes no file**.

## Step 4 — chunk smoke

**Not run live** — neural backend unusable. The script's graceful path was
exercised with the real (wrong-type) Qwen path → `neural usable: False (reason:
dependency_missing:FlagEmbedding)`, **no file written**.

The comparison *loop* was verified with an **injected fake scorer** (no dep, no
model, scratchpad output): 12 long-context samples, 12 neural-usable, 0 fallback,
**4/12 changed** selected chunk ids, effective_method=`reranker`, avg chunks
3.83/3.83, avg chars 3201/3067. This proves the report path is correct and will
produce meaningful diffs once a real model is staged. No `outputs/` file was
created.

## Step 5 — exact v4 commands (DO NOT RUN until neural is usable)

`<MODEL>` = a LOCAL reranker dir (for `--method reranker`) or embedding dir (for
`--method embedding`). Re-run the env check until "usable now: True" first.

**(a) Chunk smoke (no OpenRouter):**
```bash
.venv/bin/python scripts/compare_neural_vs_lexical_chunks.py \
  --input public-test_1780368312.json \
  --method reranker --model-path <MODEL> \
  --max-samples 30 --top-k 4 --candidate-top-k 12 \
  --output outputs/neural_vs_lexical_reranker_chunk_report.jsonl
```

**(b) v4 targeted smoke (calls OpenRouter — user runs manually):**
```bash
.venv/bin/python run.py \
  --input <LONG_CONTEXT_SUBSET.json> \
  --solver openrouter_graph --model qwen/qwen3.5-9b \
  --temperature 0 --max-tokens 1024 \
  --config configs/verifier_selective.yaml \
  --calculation-solver \
  --evidence-reranker --evidence-reranker-method reranker \
  --evidence-reranker-model <MODEL> --evidence-candidate-top-k 12 \
  --output outputs/pred_v4_neural_rerank_smoke.csv \
  --trace outputs/run_v4_neural_rerank_smoke.jsonl
```

**(c) v4 full (calls OpenRouter — user runs manually):**
```bash
.venv/bin/python run.py \
  --input public-test_1780368312.json \
  --solver openrouter_graph --model qwen/qwen3.5-9b \
  --temperature 0 --max-tokens 1024 \
  --config configs/verifier_selective.yaml \
  --calculation-solver \
  --evidence-reranker --evidence-reranker-method reranker \
  --evidence-reranker-model <MODEL> --evidence-candidate-top-k 12 \
  --output outputs/pred_v4_neural_rerank.csv \
  --trace outputs/run_v4_neural_rerank.jsonl
```

**(d) Validation + comparison (after a run):**
```bash
.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission outputs/pred_v4_neural_rerank.csv
# A/B vs prior versions (no leaderboard claim without validation):
diff <(sort outputs/pred_v2_calc_rerank.csv) <(sort outputs/pred_v4_neural_rerank.csv) | head
```
(For the smoke, validate against the **subset** input JSON, not the full file —
partial-vs-full validation falsely FAILs.) These v4 files are new names; v1/v2/v3
are never overwritten.

> Flag/CLI-name caveat: confirm exact `run.py` flag spellings (e.g. `--trace` vs
> `--trace-output`) with `run.py --help` before the manual run.

## Step 6 — safe validation results

- `compileall` (src tests scripts): **OK**
- `pytest -q`: **206 passed**
- `validate_submission.py` on `outputs/pred.csv`: **PASS**
- `validate_submission.py` on `outputs/pred_v2_calc_rerank.csv`: **PASS**
- `outputs/pred_v3a_verifier_selective.csv`: not present (skipped)

## No-hardcoding interpretation

Sample selection uses only `has_long_context` (markers / length) — no qids, no
answers, no ground truth. The comparison reports *which chunks* are selected, never
*whether an answer is correct*. A private question of the same shape is handled
identically.

## Confirmations

- No OpenRouter API call made.
- No full public inference run.
- No `outputs/pred.csv` / v1 / v2 / v3 created or overwritten.
- No leaderboard upload.
- No `OPENROUTER_API_KEY` printed/logged; `.env` not read.
- No model downloaded; no dependency installed; model dirs touched read-only only.

## Remaining risks

- Net accuracy effect of neural rerank remains unverified (no ground truth;
  leaderboard decides). It only changes which in-question chunks are selected.
- The real neural backends (`SentenceTransformer` / `FlagReranker`) are still
  exercised only by fakes; a first real run needs a staged model + smoke before any
  full run.

## Recommendation

Neural is **not usable**, so:
1. Outside Claude, install `FlagEmbedding` (or `sentence-transformers`) and stage a
   **local** compliant reranker/embedding model; re-run
   `scripts/check_neural_reranker_env.py` until "usable now: True".
2. Re-run this phase: chunk smoke (Step 5a). If neural **meaningfully changes**
   selected chunks with **0 fallback** → proceed to v4 targeted smoke (5b).
3. If, once usable, neural **does not change chunks much** → defer v4 and instead
   prioritize expanding the **calculation taxonomy** (higher expected accuracy
   yield than marginal chunk reordering).

Do not commit. All changes left uncommitted for user review.
