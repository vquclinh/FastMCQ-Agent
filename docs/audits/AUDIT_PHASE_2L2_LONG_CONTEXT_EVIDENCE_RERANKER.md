# Audit — Phase 2L.2: Long-Context In-Question Evidence Reranking

**Date:** 2026-06-21
**Branch:** `main` @ `694bf19` (+ uncommitted 2L.2 changes)
**Result:** Added a generic, in-question evidence reranker for the `long_context`
route and integrated it conservatively (falls back to the lexical compressor).
**No OpenRouter API call, no full inference, no `pred.csv` change, no leaderboard
upload, no commit.** Priority honored: correctness/generalization first.

## 1. Repo state

Branch `main` @ `694bf19` (prior calc-solver phase committed). `outputs/pred.csv`
present and **untouched** (re-validated PASS).

## 2. Files inspected

`src/passage_compressor.py`, `src/openrouter_graph_solver.py`,
`src/openrouter_prompts.py`, `src/question_profiler.py`, `src/question_router.py`,
`src/structured_answer.py`, `configs/default.yaml`, `run.py`, `docs/ARCHITECTURE.md`,
`docs/OPENROUTER_ROUND1_STRATEGY.md`, `docs/AUDIT_PHASE_2K4_*`,
`docs/CALCULATION_SOLVER.md`, `public-test_1780368312.json` (pattern inventory only).

## 3. Files created / modified

### Created
- `src/evidence_reranker.py` — `EvidenceChunk`, `RerankResult`,
  `rerank_evidence_for_sample`, chunking + hybrid-lexical scoring + packing.
- `tests/test_evidence_reranker.py` — 12 tests.
- `docs/EVIDENCE_RERANKER.md`, `docs/AUDIT_PHASE_2L2_...md`.

### Modified
- `src/openrouter_graph_solver.py` — `OpenRouterConfig` evidence fields;
  `_evidence_node` now tries the reranker on `long_context` then falls back to the
  compressor; evidence trace fields in `_init_state`.
- `configs/default.yaml` — nested `evidence_reranker:` block (`openrouter:`).
- `run.py` — flattens the nested block into solver fields; `--evidence-reranker` /
  `--no-evidence-reranker`.
- `tests/test_openrouter_graph_solver.py` — 3 integration tests.
- `docs/OPENROUTER_ROUND1_STRATEGY.md` — v2/v3 improvement note.

## 4. Design summary

Reranks evidence **already inside the question** (no web retrieval, no ground
truth, no qid). Splits off the trailing question stem, chunks the embedded
context, scores chunks against a **choice-aware** query, and packs
`[NGỮ CẢNH TỔNG QUAN]` (global overview) + `[BẰNG CHỨNG]` (top chunks) +
`[CÂU HỎI]` (question **last**, near the choices — lost-in-the-middle mitigation).

## 5. Chunking formats supported

`[n] Tiêu đề: … Nội dung: …`; `-- Đoạn văn N --`; single `Tiêu đề:/Nội dung:`;
fallback paragraph/sentence windows; plus **subdivision** of an over-long single
source into windows (inheriting title/index) so one big passage is rerankable.

## 6. Scoring strategy

Default **hybrid lexical** (dependency-free): BM25-lite (idf-weighted token
relevance) + char-trigram overlap (Vietnamese-accent robust) + title-relevance
bonus + length penalty for boilerplate. Query = question stem + all choice texts.
Top-`k` by score, restored to reading order, packed within `max_chars`.

## 7. Optional embedding/reranker status

`method: embedding|reranker` with a local model path is supported as a hook but is
**off by default** and **fails closed** to hybrid lexical unless
`sentence-transformers`/`FlagEmbedding` is installed and a path is given. **Nothing
is downloaded;** tests do not require these deps. (The embedding scorer is a stub
that raises → caught → lexical fallback.)

## 8. Integration behavior

Runs in `openrouter_graph` **only on the `long_context` route**. On a match it
sets the prompt body to the reranked text; if it declines (too little structure)
or errors, it **falls back to the existing lexical compressor**, then to the raw
question. Disabling (`--no-evidence-reranker`) restores prior behavior exactly.
Trace: `evidence_reranker_enabled/method/selected_chunk_count/selected_chars/
fallback_used` (+ light diagnostics; no full passage in logs).

## 9. Tests added/updated

`pytest -q` → **179 passed** (164 prior + 12 reranker + 3 integration). Coverage:
titled multi-source + `-- Đoạn văn` parsing; selects relevant chunk over generic
noise; global context + question-last; respects `max_chars`; fallback when
unstructured; deterministic; **no-qid-effect**; **optional embedding unavailable →
lexical**; never empty; Vietnamese stem extraction; **source has no
web/eval/qid usage**; graph: runs on long_context + logs, disabled preserves
behavior, not engaged on short_knowledge.

## 10. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **179 passed**.
- `validate_submission.py --submission outputs/pred.csv` → **PASS** (unchanged).
- No prediction CSV created/overwritten.

## 11. Dry-run inventory (public set; diagnostic only, no CSV written)

- total **463**; `long_context` routed **100**.
- reranker **matched 100/100** (fallback to compressor: **0**); method 100%
  `hybrid_lexical`.
- avg original context **5766** chars → avg reranked evidence **3400** chars
  (**~41% reduction**); low-relevance chunks dropped.
- example (qid, chunks_total, kept, kept_ids): `test_0001 5 4 [src1.1..src1.4]`;
  `test_0004 14 4 [p0,p4,p5,p11]`; `test_0014 8 4 [src1.0,src1.1,src3.1,src6]`.
  (Diagnostic only — generic output, not hardcoded; no accuracy claimed.)

## 12. Confirmations

- **No OpenRouter API call, no full inference, no `pred.csv` overwrite** (PASS,
  unchanged), **no leaderboard upload, no commit.**
- **No hardcoding:** no qid logic, no public-test answer table, no web/external
  retrieval, no `eval`/`exec` (asserted by tests).
- `.env`/`.venv`/`outputs`/model dirs untouched; key never read/printed.

## 13. Remaining risks

- Lexical scoring may miss semantically-relevant-but-lexically-different chunks
  (optional embedding hook is the future remedy).
- Question-stem heuristic could mis-split unusual phrasings; reranking never adds
  information and falls back safely.
- No ground truth — reduction/selection quality is confirmed only by the leaderboard.

## 14. Recommended next step

- Record the **v1 leaderboard score** first, then a **controlled v2/v3 run**
  combining the **calculation override** (calc route) **+ evidence reranking**
  (long-context route) into a **new** file (e.g. `outputs/pred_v3_calc_rerank.csv`),
  validated and A/B-compared against v1.

## 15. Git status (uncommitted)

```
 M configs/default.yaml
 M docs/OPENROUTER_ROUND1_STRATEGY.md
 M run.py
 M src/openrouter_graph_solver.py
 M tests/test_openrouter_graph_solver.py
?? docs/AUDIT_PHASE_2L2_LONG_CONTEXT_EVIDENCE_RERANKER.md
?? docs/EVIDENCE_RERANKER.md
?? src/evidence_reranker.py
?? tests/test_evidence_reranker.py
```

All changes **uncommitted**, for user review. `pred.csv` unchanged.
