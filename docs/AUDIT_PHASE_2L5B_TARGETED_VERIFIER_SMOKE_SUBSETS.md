# Audit — Phase 2L.5B: Targeted Verifier Smoke Subsets + Correct Validation

**Date:** 2026-06-21
**Branch:** `main` @ `f73b6b8`
**Type:** Preflight correction. Builds targeted INPUT subsets for verifier smoke
tests and the matching validation commands. **No OpenRouter API call, no
inference, no `pred.csv`/v1/v2 overwrite, no leaderboard upload, no commit.**

## 1. Repo state

Branch `main` @ `f73b6b8`. Frozen outputs present and **untouched**: `pred.csv`,
`pred_phase2k3_openrouter_full.csv`, `pred_v2_calc_rerank.csv`,
`run_v2_calc_rerank.jsonl` (both pred CSVs re-validate **PASS**).

## 2. Why `--limit 50` was insufficient

`--limit N` takes the **first N samples in file order**, which does not guarantee
coverage of the samples that actually **trigger** the verifier. The selective
policy triggers on only ~11 specific qids spread across the file (e.g.
`test_0113, test_0167, test_0222, …`); a first-50 slice could include few or none,
so the smoke would exercise little of the verifier path.

## 3. Why full-input validation is wrong for a partial smoke CSV

`validate_submission.py` checks that the submission's qids **exactly cover** the
input's qids. A 50-row smoke CSV validated against the full 463-row input is
reported **FAIL** ("missing predictions for 4xx qids") even when every row is
valid. The fix is to validate the smoke CSV against a **subset input JSON**
containing exactly the smoke qids. (Verified: a 21-row CSV validates **PASS**
against the 21-row subset input.)

## 4. Files created / modified

### Created
- `scripts/create_verifier_smoke_subset.py` — selects trigger qids (via the real
  `should_run_verifier`) + control qids from a prior run log; writes a subset JSON
  in the public-input format. **Test-input selection only** — no answers, no
  ground truth, no qid-keyed solver logic.
- `outputs/input_v3a_verifier_selective_smoke.json` (git-ignored experiment artifact)
- `outputs/input_v3b_verifier_broad_smoke.json` (git-ignored experiment artifact)
- `docs/AUDIT_PHASE_2L5B_TARGETED_VERIFIER_SMOKE_SUBSETS.md` — this audit.

No code/config/solver behavior changed; no prediction CSV written.

## 5. Subset generation method

The generator reads the full input + the v2 run log (`run_v2_calc_rerank.jsonl`),
applies the **actual** `should_run_verifier` under the chosen policy, and selects:
- **trigger qids** (prioritising partial-parse / low-confidence first), then
- **control qids** spread across non-triggering routes (for contrast).
Selected qids → full sample objects → subset JSON. No answer/correctness signal is
used; selecting qids for a *test input* is not answer hardcoding.

## 6. Subset statistics

**v3a selective** (`outputs/input_v3a_verifier_selective_smoke.json`): **21**
samples = **11 triggers** (all `partial_parse+low_confidence`) + **10 controls**.
Routes: long_context 12, ambiguous 3, calculation 3, short_knowledge 3. (Contains
all 11 selective-trigger qids, so the smoke fully exercises the selective path.)

**v3b broad** (`outputs/input_v3b_verifier_broad_smoke.json`): **60** samples =
**50 triggers** (39 reranked_long_context, 9 partial+reranked, 2 partial) + **10
controls**. Routes: long_context 48, ambiguous 3, calculation 3, short_knowledge 3,
law_admin 3.

## 7. Exact targeted SMOKE commands (run manually)

### v3a selective targeted smoke
```bash
.venv/bin/python run.py \
  --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --config configs/verifier_selective.yaml \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input outputs/input_v3a_verifier_selective_smoke.json \
  --output outputs/pred_v3a_verifier_selective_smoke.csv \
  --save-raw --log-path outputs/run_v3a_verifier_selective_smoke.jsonl
```

### v3b broad targeted smoke (default config = rerank-trigger ON)
```bash
.venv/bin/python run.py \
  --solver openrouter_graph --openrouter-model qwen/qwen3.5-9b \
  --openrouter-temperature 0 --openrouter-max-tokens 1024 \
  --calculation-solver --evidence-reranker --mcq-verifier \
  --input outputs/input_v3b_verifier_broad_smoke.json \
  --output outputs/pred_v3b_verifier_broad_smoke.csv \
  --save-raw --log-path outputs/run_v3b_verifier_broad_smoke.jsonl
```

## 8. Correct SMOKE validation commands (validate against the SUBSET input)

```bash
.venv/bin/python scripts/validate_submission.py \
  --input outputs/input_v3a_verifier_selective_smoke.json \
  --submission outputs/pred_v3a_verifier_selective_smoke.csv

.venv/bin/python scripts/validate_submission.py \
  --input outputs/input_v3b_verifier_broad_smoke.json \
  --submission outputs/pred_v3b_verifier_broad_smoke.csv
```

## 9. Smoke comparison vs v2 (restricted to subset qids)

```bash
.venv/bin/python - <<'PY'
import csv
load = lambda p: {r["qid"]: r["answer"] for r in csv.DictReader(open(p, newline="", encoding="utf-8"))}
smoke = load("outputs/pred_v3a_verifier_selective_smoke.csv")   # or v3b
v1, v2 = load("outputs/pred.csv"), load("outputs/pred_v2_calc_rerank.csv")
for name, base in (("v1", v1), ("v2", v2)):
    diff = [(q, base.get(q), smoke[q]) for q in smoke if base.get(q) != smoke[q]]
    print(f"vs {name}: {len(diff)} changed on the {len(smoke)} smoke qids -> {diff[:15]}")
PY
```

## 10. Verifier log-analysis command (smoke)

```bash
.venv/bin/python - <<'PY'
import json, collections
rows = [json.loads(x) for x in open("outputs/run_v3a_verifier_selective_smoke.jsonl") if x.strip()]
rows = [r for r in rows if not r.get("_summary")]
trig = [r for r in rows if r.get("verifier_triggered")]
ovr = [r for r in trig if r.get("verifier_override_applied")]
print("rows:", len(rows), "| triggered:", len(trig), "| overrides:", len(ovr),
      "| parse_fail:", sum(1 for r in trig if r.get("verifier_parse_source") in (None, "none")),
      "| errors:", sum(1 for r in trig if r.get("verifier_error")))
print("route dist:", dict(collections.Counter(r.get("route") for r in rows)))
print("trigger reasons:", dict(collections.Counter(r.get("verifier_trigger_reason") for r in trig)))
print("override examples (qid, route, orig->new, conf, reason):")
for r in ovr[:15]:
    print("  ", r["qid"], r.get("route"), r.get("verifier_original_answer"), "->",
          r.get("verifier_answer"), round(r.get("verifier_confidence") or 0, 2),
          r.get("verifier_trigger_reason"))
PY
```

## 11. Validation results

- `compileall -q src tests scripts` → OK.
- `pytest -q` → **198 passed**.
- `pred.csv` and `pred_v2_calc_rerank.csv` → **PASS** (unchanged).
- **Subset-validation proof:** a fabricated 21-row all-`A` CSV validated against
  `input_v3a_verifier_selective_smoke.json` → **PASS** (the full input would FAIL
  with missing qids). Confirms §3.

## 12. No-hardcoding clarification

`create_verifier_smoke_subset.py` selects qids from a run log purely by
verifier-trigger signals and route — **never** by answer value or correctness, and
it writes only an input subset (no predictions). This is legitimate test-input
selection, not answer hardcoding; no qid-keyed solver logic was added.

## 13. Confirmations

- **No OpenRouter API call, no inference, no `pred.csv`/v1/v2 overwrite, no
  leaderboard upload, no commit.**
- `.env`/`.venv`/model dirs untouched; key never read/printed. (Subset inputs live
  under git-ignored `outputs/`.)

## 14. Recommendation

1. Record the **v1/v2 leaderboard scores** first.
2. **Run the v3a selective targeted smoke** (§7) → validate against the subset
   (§8) → run the §10 log analysis. Inspect the **override examples** (qid, orig→
   new, confidence, reason): are the overrides sensible? what's the override rate?
3. Only if v3a overrides look trustworthy, run the **v3b broad targeted smoke** and
   compare (every reranked long-context gets a second opinion).
4. Then a **full** v3a/v3b run into a **new** file (validate vs full input, diff vs
   v1/v2), and submit only after baselines are recorded. No correctness is claimed
   without the leaderboard.

## 15. Git status (uncommitted)

```
?? configs/verifier_selective.yaml
?? docs/AUDIT_PHASE_2L5_VERIFIER_EXPERIMENT_PREFLIGHT.md
?? docs/AUDIT_PHASE_2L5B_TARGETED_VERIFIER_SMOKE_SUBSETS.md
?? scripts/create_verifier_smoke_subset.py
```

(`outputs/input_v3a_*` and `input_v3b_*` are git-ignored experiment artifacts.)
All changes **uncommitted**, for user review.
