# Audit — Phase 2L.10: Competition-Compliant Transformers Backends (BGE-M3 / Qwen3-Reranker)

**Date:** 2026-06-21  **Branch:** `main`  **Status:** uncommitted (for review)

## Outcome (one line)

The neural evidence reranker is now **actually usable** via **transformers + torch
only** (no FlagEmbedding / sentence-transformers) with the local
competition-compliant models. **Both `embedding` (BGE-M3) and `reranker`
(Qwen3-Reranker-0.6B) are USABLE** and meaningfully change chunk selection vs
lexical; everything fails closed to lexical otherwise.

## Repo state

Working tree clean at start (2L.8 committed). Phase changes (`git status --short`):

```
 M docs/EVIDENCE_RERANKER.md
 M docs/NEURAL_EVIDENCE_RERANKER.md
 M scripts/check_neural_reranker_env.py
 M src/evidence_reranker.py
 M tests/test_evidence_reranker.py
?? docs/AUDIT_PHASE_2L10_COMPETITION_COMPLIANT_NEURAL_BACKENDS.md
```

Frozen outputs `outputs/pred.csv`, `outputs/pred_v2_calc_rerank.csv` untouched
(both validate PASS). `outputs/pred_v5_calc_taxonomy_overlay.csv` does not exist.

## Model weights are gitignored (confirmed)

- `git check-ignore models/bge-m3/config.json` →
  `.gitignore:20:models/` (ignored). Same for the Qwen reranker.
- `git ls-files models/` → **empty** (no weights tracked); `models/` does not appear
  in `git status`. **No model weights added to git.**

## Model compliance interpretation

- Embedding: `models/bge-m3` = `BAAI/bge-m3` (config `architectures:
  ["XLMRobertaModel"]`, `1_Pooling` → CLS pooling). Compliant.
- Rerank: `models/qwen3-reranker-0.6b` = `Qwen/Qwen3-Reranker-0.6B` (config
  `architectures: ["Qwen3ForCausalLM"]`, `chat_template.jinja` = yes/no judge).
  Compliant.
- Main LLM unchanged (`qwen/qwen3.5-9b` via OpenRouter; not touched here).

## Files inspected

`src/evidence_reranker.py`, `src/openrouter_graph_solver.py`,
`scripts/check_neural_reranker_env.py`, `scripts/compare_neural_vs_lexical_chunks.py`,
`configs/default.yaml`, `run.py`, `tests/test_evidence_reranker.py`,
`tests/test_openrouter_graph_solver.py`, `docs/NEURAL_EVIDENCE_RERANKER.md`,
`docs/EVIDENCE_RERANKER.md`, plus the two local models' `config.json`,
`1_Pooling/config.json`, `chat_template.jinja`, `modules.json`.

## Files created / modified

- **M** `src/evidence_reranker.py` — added `_read_config`, `_looks_like_bge_m3`,
  `_bge_pooling_mode`, `_looks_like_qwen3_reranker`; new backends
  `TransformersBgeM3EmbeddingScorer`, `TransformersQwen3RerankerScorer`; reworked
  `build_neural_scorer` to prefer transformers-native backends with explicit
  fallback reasons; legacy ST/FlagEmbedding kept as optional fallbacks.
- **M** `scripts/check_neural_reranker_env.py` — transformers/torch/CUDA report,
  per-model presence + shape match, cheap usability decision (no weight load), and
  a `--deep` mode that loads weights `local_files_only` and scores a probe.
- **M** `tests/test_evidence_reranker.py` — 7 new fake/temp-dir tests + a
  standalone-monkeypatch shim; hardened source-inspection test (local_files_only on
  every `from_pretrained`; no `hf_hub_download`/`snapshot_download`).
- **M** `docs/NEURAL_EVIDENCE_RERANKER.md`, `docs/EVIDENCE_RERANKER.md` — backends,
  models, no-FlagEmbedding, CLI, fallback, current env status.

## Backend design

- **BGE-M3 (`embedding`)**: `AutoTokenizer`+`AutoModel` (XLM-RoBERTa),
  `local_files_only=True`, CLS-token pooling (per `1_Pooling/config.json`; mean
  available), L2-normalize, cosine vs query. CUDA when available.
- **Qwen3-Reranker (`reranker`)**: `AutoTokenizer`+`AutoModelForCausalLM`,
  `local_files_only=True`, official system/Instruct/Query/Document prompt → last
  token logits → `P("yes")` over {"no","yes"}. Empty `<think>` block, no hidden
  reasoning generated/logged. If yes/no token ids are missing it returns
  `unsupported_qwen_reranker_scoring_format` (no faked scores).
- **Selection** (`build_neural_scorer`): builds a backend only when the LOCAL path
  exists AND shape-matches AND `transformers`+`torch` import; otherwise explicit
  fallback reason. Path-shape gate prevents silently using an unrelated model
  (e.g. the plain Qwen generation model is rejected as a reranker — no "reranker" in
  name). Two-stage flow (lexical candidates → neural rerank) and lexical fallback
  unchanged.

## Env check result (shallow)

```
transformers installed; torch installed; CUDA available (RTX 4060)
sentence_transformers / FlagEmbedding: not installed (optional)
models/bge-m3               : present (looks like BGE-M3)
models/qwen3-reranker-0.6b  : present (looks like Qwen3-Reranker)
embedding method usable now : True
reranker  method usable now : True
```

## Deep check result (`--deep`, local_files_only, no network)

```
BGE-M3 embedding: OK, scores=[0.6788, 0.2866]  (relevant chunk ranked higher)
Qwen3-Reranker  : OK, scores=[0.9971, 0.0]     (relevant chunk ranked higher)
```

Both backends initialize and discriminate relevant vs noise correctly.

## BGE-M3 chunk smoke (30 long-context samples; no OpenRouter, no CSV)

```
neural usable 30/30; fallback 0; changed selected chunks 17/30
avg chunks lexical/neural 3.83 / 3.80; avg chars 3233 / 3233
report: outputs/neural_vs_lexical_bge_m3_chunk_report.jsonl (gitignored diagnostic)
```

## Qwen3-Reranker chunk smoke (30 samples)

```
neural usable 30/30; fallback 0; changed selected chunks 13/30
avg chunks lexical/neural 3.83 / 3.83; avg chars 3233 / 3083; ~26s total
report: outputs/neural_vs_lexical_qwen3_reranker_chunk_report.jsonl (gitignored)
```

Representative changed chunk ids are listed in the smoke output (e.g. lexical
`['src1','src2','src3.0','src3.1']` → reranker `['src1','src2','src3.0','src4']`).
**No accuracy is claimed** — this is chunk-selection evidence only.

## Usability summary

- **BGE-M3 embedding: USABLE** (fast, 0 fallback, 17/30 changed).
- **Qwen3-Reranker: USABLE** (0 fallback, 13/30 changed, ~0.9s/sample).

## Exact future neural smoke command (long-context subset, no OpenRouter)

```bash
.venv/bin/python scripts/compare_neural_vs_lexical_chunks.py \
  --input public-test_1780368312.json --method reranker \
  --model-path models/qwen3-reranker-0.6b \
  --max-samples 100 --top-k 4 --candidate-top-k 12 \
  --output outputs/neural_vs_lexical_qwen3_reranker_full_chunk_report.jsonl
```

## Exact future full run command (calls OpenRouter — user runs manually)

```bash
.venv/bin/python run.py --input public-test_1780368312.json \
  --solver openrouter_graph --model qwen/qwen3.5-9b --temperature 0 --max-tokens 1024 \
  --config configs/verifier_selective.yaml --calculation-solver \
  --evidence-reranker --evidence-reranker-method reranker \
  --evidence-reranker-model models/qwen3-reranker-0.6b --evidence-candidate-top-k 12 \
  --output outputs/pred_v6_neural_rerank.csv --trace outputs/run_v6_neural_rerank.jsonl
```
(Or `--evidence-reranker-method embedding --evidence-embedding-model models/bge-m3`.)
New filenames — v1/v2/v5 are never overwritten. Confirm exact flag spellings with
`run.py --help` before running.

## Tests added/updated

7 new tests (shape detection for BGE-M3 + Qwen reranker incl. rejecting the plain
Qwen model; backend selection via monkeypatched fakes; missing path / unsupported
path / missing-dep fail-closed). Source test now asserts `local_files_only=True` on
every `from_pretrained` and bans `hf_hub_download`/`snapshot_download`. **No real
weights required in pytest.** Full suite: **240 passed** (was 233); `compileall` OK;
standalone runner passes.

## Validation results

- `compileall -q src tests scripts`: OK
- `pytest -q`: **240 passed**
- `validate_submission.py` on `outputs/pred.csv`: PASS
- `validate_submission.py` on `outputs/pred_v2_calc_rerank.csv`: PASS
- `outputs/pred_v5_calc_taxonomy_overlay.csv`: not present (skipped)

## No-hardcoding / no-network interpretation

`grep` on `src/evidence_reranker.py` → no qid access, no `requests`/`urllib`/
`socket`/`httpx`, no `hf_hub_download`/`snapshot_download`, no `test_0xxx` literals.
Both `from_pretrained` calls pass `local_files_only=True`. The reranker reads only
`question`+`choices`; no ground truth, no answer table, no qid drives any decision.

## Confirmations

- No OpenRouter API call made.
- No full public inference run.
- No `outputs/pred.csv` / v1 / v2 (/ v5) created or overwritten.
- No leaderboard upload.
- No `OPENROUTER_API_KEY` printed/logged; `.env` not read.
- No model downloaded; no dependency installed; model dirs read locally only.
- Model weights gitignored, not added to git.

## Remaining risks

- No ground truth → the *net accuracy* effect of neural reranking is unverified;
  chunk-selection changes (17/30 BGE, 13/30 Qwen) are evidence of behavior change,
  not of correctness. Only the leaderboard confirms.
- Qwen reranker adds ~0.9 s/sample (per-pair LM forward); acceptable for
  long-context only (100 samples), bounded by `candidate_top_k`.
- BGE-M3 truncates chunks to 512 tokens (memory bound); long chunks lose tail
  context — acceptable since chunks are already small.

## Recommendation

1. **Qwen3-Reranker is usable and changes chunks meaningfully** → run the full
   long-context chunk smoke (command above), eyeball the changed selections, then a
   controlled **v6** OpenRouter run into a NEW file and A/B vs v1/v2 before any
   leaderboard claim.
2. BGE-M3 embedding is a faster alternative (more chunk changes, ~instant) — viable
   if reranker latency is a concern.
3. If a v6 A/B shows no gain, continue the **calculation taxonomy** expansion
   (Phase 2L.8 follow-ups) as the next accuracy lever.

Do not commit. All changes left uncommitted for user review.
