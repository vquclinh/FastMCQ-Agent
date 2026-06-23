# Audit — Phase 2L.5: Verifier Experiment Preflight (Selective vs Broad)

**Date:** 2026-06-21
**Branch:** `main` @ `f73b6b8`
**Type:** Preflight only. Prepares exact commands + estimates for two verifier
variants (v3a selective, v3b broad). **No OpenRouter API call, no inference, no
`pred.csv`/v1/v2 overwrite, no leaderboard upload, no commit.**

## 1. Repo state

Branch `main`; latest `f73b6b8 add selective MCQ verifier for option elimination`.
Frozen outputs present and **untouched**: `pred.csv`, `pred_phase2k3_openrouter_full.csv`,
`pred_v2_calc_rerank.csv`, `run_v2_calc_rerank.jsonl`. `pred.csv` and
`pred_v2_calc_rerank.csv` re-validate **PASS**.

## 2. Files inspected

`run.py`, `configs/default.yaml`, `src/openrouter_graph_solver.py`,
`src/mcq_verifier.py`, `docs/MCQ_VERIFIER.md`,
`docs/AUDIT_PHASE_2L4_SELECTIVE_MCQ_VERIFIER.md`, `outputs/run_v2_calc_rerank.jsonl`.

**CLI capability finding:** verifier flags are `--mcq-verifier` /
`--no-mcq-verifier` / `--mcq-verifier-threshold`. There is **no CLI flag** to set
`trigger_on_reranked_long_context` — it is **config-only**. So v3a (selective)
needs a config override; v3b (broad) is the default behavior.

**Resolution chosen (no code change):** created `configs/verifier_selective.yaml`
(a minimal override: `mcq_verifier.enabled: true`,
`trigger_on_reranked_long_context: false`). Verified it resolves to
`mcq_verifier_enabled=True`, `trigger_on_reranked_long_context=False`, with all
other settings (model, calc, reranker, other triggers) kept at defaults; the CLI
still supplies `--openrouter-max-tokens 1024` etc. (No code was modified; adding a
CLI flag is deferred unless desired later.)

## 3. Trigger estimates from `run_v2_calc_rerank.jsonl` (no API)

| Policy | Settings | Triggers (+calls) | Routes | Reasons |
|---|---|---|---|---|
| **B — v3b broad** (default) | rerank-trigger ON | **102** | long_context 100, ambiguous 2 | reranked_long_context 91; partial+lowconf+reranked 9; partial+lowconf 2 |
| **A — v3a selective** | rerank-trigger OFF | **11** | long_context 9, ambiguous 2 | partial_parse+low_confidence 11 |
| **C — ultra-conservative** | rerank OFF, conf<0.5 | **11** | long_context 9, ambiguous 2 | partial_parse+low_confidence 11 |

- Overlap with calculation override: **0** (9 calc-overrides return before the
  verifier and are excluded by `should_run_verifier`).
- Long-context verified: 100 (B) vs 9 (A/C).
- Estimated total calls (full set ≈ 454 base): **~556** (v3b) vs **~465** (v3a).
- Note: on the v2 trace the 11 selective triggers all had confidence 0.0
  (partial-parse), so Policy C equals Policy A here.

## 4. Exact SMOKE commands (run manually; --limit 50)

### v3a selective smoke
```bash
.venv/bin/python run.py \
  --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --config configs/verifier_selective.yaml \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input public-test_1780368312.json --limit 50 \
  --output outputs/pred_v3a_verifier_selective_smoke.csv \
  --save-raw --log-path outputs/run_v3a_verifier_selective_smoke.jsonl
```

### v3b broad smoke (default config has rerank-trigger ON)
```bash
.venv/bin/python run.py \
  --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input public-test_1780368312.json --limit 50 \
  --output outputs/pred_v3b_verifier_broad_smoke.csv \
  --save-raw --log-path outputs/run_v3b_verifier_broad_smoke.jsonl
```

## 5. Exact FULL-RUN commands (only after smoke passes; do NOT overwrite v1/v2)

### v3a selective full
```bash
.venv/bin/python run.py \
  --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --config configs/verifier_selective.yaml \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input public-test_1780368312.json \
  --output outputs/pred_v3a_verifier_selective.csv \
  --save-raw --log-path outputs/run_v3a_verifier_selective.jsonl
```

### v3b broad full
```bash
.venv/bin/python run.py \
  --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input public-test_1780368312.json \
  --output outputs/pred_v3b_verifier_broad.csv \
  --save-raw --log-path outputs/run_v3b_verifier_broad.jsonl
```

(Optional `--resume <output.csv>` to continue after an interruption. None of these
write `outputs/pred.csv` or `outputs/pred_v2_calc_rerank.csv`.)

## 6. Validation + comparison commands

```bash
# Validate any produced file
.venv/bin/python scripts/validate_submission.py \
  --input public-test_1780368312.json --submission <FILE.csv>

# Diffs vs v1 and v2
.venv/bin/python - <<'PY'
import csv
load=lambda p:{r["qid"]:r["answer"] for r in csv.DictReader(open(p,newline="",encoding="utf-8"))}
new=load("outputs/pred_v3a_verifier_selective.csv")   # or v3b
for base in ("outputs/pred.csv","outputs/pred_v2_calc_rerank.csv"):
    b=load(base)
    diff=[(q,b[q],new[q]) for q in sorted(b) if b.get(q)!=new.get(q)]
    print(base, "changed:", len(diff), diff[:15])
PY
```

## 7. Verifier log-analysis command

```bash
.venv/bin/python - <<'PY'
import json, collections
rows=[json.loads(x) for x in open("outputs/run_v3a_verifier_selective.jsonl") if x.strip()]
rows=[r for r in rows if not r.get("_summary")]
trig=[r for r in rows if r.get("verifier_triggered")]
ovr=[r for r in trig if r.get("verifier_override_applied")]
print("triggered:", len(trig), "| overrides:", len(ovr),
      "| parse_fail:", sum(1 for r in trig if r.get("verifier_parse_source") in (None,"none")),
      "| errors:", sum(1 for r in trig if r.get("verifier_error")))
print("override routes:", dict(collections.Counter(r.get("route") for r in ovr)))
print("override examples (qid, orig->new, conf, reason, route):")
for r in ovr[:15]:
    print("  ", r["qid"], r.get("verifier_original_answer"),"->",r.get("verifier_answer"),
          round(r.get("verifier_confidence") or 0,2), r.get("verifier_trigger_reason"), r.get("route"))
PY
```

## 8. No-hardcoding grep interpretation

`grep` over `src/` for `if .*qid` / `test_[0-9]{4}` / `ground_truth` /
`answer_table` / `answer_map`: the only `qid` use is `pred["qid"] in seen`
(generic dedup in `postprocess.py`). No answer tables, no qid-keyed logic. Clean.

## 9. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **198 passed**.
- `pred.csv` and `pred_v2_calc_rerank.csv` → **PASS** (unchanged).
- `configs/verifier_selective.yaml` resolves to the intended selective settings
  (verified, no API).

## 10. Confirmations

- **No OpenRouter API call, no inference, no `pred.csv`/v1/v2 overwrite, no
  leaderboard upload, no commit.**
- `.env`/`.venv`/`outputs`/model dirs untouched; key never read/printed.

## 11. Recommendation

1. **Record the v1 (and v2) leaderboard scores first** as baselines.
2. **Run v3a selective smoke** (`--limit 50`) → validate → run the §7 log analysis;
   inspect the override rate and examples. Selective adds only **~11** verifier
   calls on the full set, targeting genuinely uncertain answers.
3. Only if v3a looks sound, run **v3b broad smoke** (every reranked long-context
   gets a second opinion, ~102 calls) and compare.
4. Run a **full** v3a/v3b into a **new** file, validate, diff vs v1/v2.
5. **Submit only after v1/v2 scores are recorded** and the override behavior looks
   trustworthy; keep v1/v2 as safe fallbacks. No correctness is claimed without the
   leaderboard.

## 12. Git status (uncommitted)

```
?? configs/verifier_selective.yaml
?? docs/AUDIT_PHASE_2L5_VERIFIER_EXPERIMENT_PREFLIGHT.md
```

Only a new config override and this audit were added; no code/output changed. All
**uncommitted**, for user review.
