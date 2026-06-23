# Audit — Phase 2L.3: Controlled Calc+Rerank Generation Preflight

**Date:** 2026-06-21
**Branch:** `main` @ `5aa5f17`
**Type:** Preflight only. Prepares the exact manual command + safety checks for a
new v2 run combining the calculation override and the evidence reranker. **No
OpenRouter API call, no full inference, no `pred.csv`/full-file overwrite, no
leaderboard upload, no commit.**

## 1. Repo state

Branch `main`; latest commits `5aa5f17 add long-context evidence reranker`,
`694bf19 add deterministic calculation solver…`. Working tree otherwise clean.
v1 artifacts present and untouched: `outputs/pred.csv`,
`outputs/pred_phase2k3_openrouter_full.csv`, `outputs/run_phase2k3_openrouter_full.jsonl`.

## 2. Files inspected

`run.py`, `configs/default.yaml`, `src/openrouter_graph_solver.py`,
`src/calculation_solver.py`, `src/evidence_reranker.py`, `docs/CALCULATION_SOLVER.md`,
`docs/EVIDENCE_RERANKER.md`, `docs/AUDIT_PHASE_2L1B_*`, `docs/AUDIT_PHASE_2L2_*`.

Confirmed current defaults (from code/config):
- **Solver** `openrouter_graph`; **model** `qwen/qwen3.5-9b`; **temperature 0**;
  **reasoning disabled** (`reasoning:{"enabled":false}`); structured JSON on.
- **Calculation solver:** default **enabled** (`calc_enabled: true`,
  `calc_override_when_safe: true`, `calc_min_confidence: 0.95`); runs on
  `calculation`+`ambiguous`. CLI: `--calculation-solver` / `--no-calculation-solver`.
- **Evidence reranker:** default **enabled** (`evidence_reranker.enabled: true`,
  `method: hybrid_lexical`, `top_k 4`, `max_chars 4500`); `long_context` only.
  CLI: `--evidence-reranker` / `--no-evidence-reranker`.
- **max_tokens:** config default 512; the v2 command sets **1024** via
  `--openrouter-max-tokens` (the chosen Round-1 value).
- **Output/log:** `--output` and `--log-path` (with `--save-raw`).

## 3. v1 artifact validation status

- `validate_submission.py` on `outputs/pred.csv` → **PASS**.
- `validate_submission.py` on `outputs/pred_phase2k3_openrouter_full.csv` → **PASS**.
- **`pred.csv` ≡ full file:** answer diff = **0** across all 463 qids (only a
  trailing-newline byte difference). v1 is frozen and consistent.

## 4. Dry-run routing inventory (diagnostic only; no CSV written)

- total **463**; routes: short_knowledge **190**, calculation **159**,
  long_context **100**, ambiguous **7**, law_admin **7**.
- **calc safe-override (skips LLM): 9** — methods: elasticity 2, cylinder 2,
  decay 1, gdp_inflation 1, hess 1, sphere 1, resistor 1.
- **evidence reranker applied: 100/100** long_context (fallback to compressor: 0).
- **expected LLM calls: ~454** (= 463 − 9 calc overrides; the 100 reranked samples
  still call the LLM, but with focused evidence).
- expected new output: `outputs/pred_v2_calc_rerank.csv` (does **not** exist yet).

## 5. Exact manual command (run yourself — this agent did NOT run it)

```bash
.venv/bin/python run.py \
  --solver openrouter_graph \
  --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 \
  --openrouter-max-tokens 1024 \
  --calculation-solver \
  --evidence-reranker \
  --input public-test_1780368312.json \
  --output outputs/pred_v2_calc_rerank.csv \
  --save-raw \
  --log-path outputs/run_v2_calc_rerank.jsonl
```

Notes: calc + reranker are already default-on; the flags are explicit
belt-and-suspenders. Reasoning stays disabled (default). The `--output` is a
**new** file, so `outputs/pred.csv` and the v1 full file are **not** overwritten.
Optional: add `--resume outputs/pred_v2_calc_rerank.csv` to resume after an
interruption. Expect ~454 API calls and a small cost; the key is never printed.

## 6. Post-run validation command

```bash
.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json \
  --submission outputs/pred_v2_calc_rerank.csv
```

Expect **RESULT: PASS** (463 rows, full coverage, valid labels).

## 7. v1 → v2 comparison command

```bash
.venv/bin/python - <<'PY'
import csv, collections
from pathlib import Path
load = lambda p: {r["qid"]: r["answer"] for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}
a, b = load("outputs/pred.csv"), load("outputs/pred_v2_calc_rerank.csv")
diff = [(qid, a[qid], b[qid]) for qid in sorted(a) if a.get(qid) != b.get(qid)]
print("changed_answers:", len(diff))
print("first_30_changes:", diff[:30])
print("v1_dist:", dict(collections.Counter(a.values())))
print("v2_dist:", dict(collections.Counter(b.values())))
PY
```

Expected: the 9 calc-override answers are deterministic (≈4 differ from v1 per the
2L.1B dry-run); long-context answers may shift due to focused evidence. Review the
JSONL trace (`calculation_*`, `evidence_*` fields) for how each route behaved.

## 8. No-hardcoding interpretation

`grep` over `src/`/`tests/`/`configs/` for `if .*qid` / `test_[0-9]{4}` /
`answer_key` / `ground_truth` / `gold`:
- `src/postprocess.py: if pred["qid"] in seen` — generic **dedup** (one row per
  qid), not an answer decision. **Benign.**
- `tests/test_calculation_solver.py`, `tests/test_evidence_reranker.py` use
  public-looking qids **only to assert no-qid-effect** (same result regardless of
  qid). **Benign.**
- No answer tables, no `if qid == ...` answer mapping, no web retrieval, no
  `eval`/`exec`. **No hardcoding.**

## 9. Safe validation

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **179 passed**.

## 10. Confirmations

- **No OpenRouter API call, no full inference, no `pred.csv` / full-file
  overwrite, no leaderboard upload, no commit.**
- `.env`/`.venv`/`outputs`/model dirs untouched; key never read/printed.

## 11. Remaining risks

- v2 changes are *likely* improvements but **unverified** (no ground truth) until
  the leaderboard scores it; the calc override is deterministic, the reranker only
  reorders/selects existing evidence.
- A few elasticity/cylinder/GDP answers will change vs v1 — intended, but confirm
  via the leaderboard before trusting.
- Reranker is lexical; semantically-divergent evidence could be under-weighted.

## 12. Recommendation

1. **Record the v1 leaderboard score first** (baseline) in
   `experiments/leaderboard_log.csv`.
2. Then run the §5 command → §6 validation → §7 comparison.
3. **Submit v2 only if** it validates (full coverage, valid labels) **and** the
   leaderboard upload budget allows; keep v1 as the safe fallback.

## 13. Git status (uncommitted)

```
?? docs/AUDIT_PHASE_2L3_CONTROLLED_CALC_RERANK_PREFLIGHT.md
```

Only this audit is new; no code/config/output changed in this phase. All changes
**uncommitted**, for user review.
