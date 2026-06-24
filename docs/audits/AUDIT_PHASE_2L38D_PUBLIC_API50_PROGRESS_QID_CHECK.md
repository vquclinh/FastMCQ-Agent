# Audit — Phase 2L.38D: `public_api50` Progress / Current-QID Check (read-only)

**Date:** 2026-06-24  **Branch:** `main`  **Status:** read-only diagnostic on a LIVE run
(process untouched, no API called, no files modified except this audit).

## Question

Can we determine from the current `run.log` which qid / question the live
`run_public_api50.sh public-test_1780368312.json` run is processing?

## Commands run (read-only)

```bash
RUN_DIR="scratch/runs/public_api50_20260624_005107"
ls -la "$RUN_DIR" "$RUN_DIR/work"
grep -c "\[fastmcq\] openrouter ok" "$RUN_DIR/run.log"
find "$RUN_DIR" -type f \( -name "*.jsonl" -o -name "*.json" -o -name "*.csv" \) -printf "%T@ %p\n" | sort -nr
grep -RIn "openrouter ok" src scripts
sed -n '215,230p' src/openrouter_client.py
grep -RIn "print(|log(" src/dynamic_base_predictor.py src/v12b_dynamic_layer.py src/v13_dynamic_layer.py src/fastmcq_system.py src/system_candidate_selector.py
grep -RIn "resume" src/{dynamic_base_predictor,v12b_dynamic_layer,v13_dynamic_layer,fastmcq_system}.py
grep -RIn "random|shuffle|sort" src/v12b_dynamic_layer.py src/v13_dynamic_layer.py
# + an OFFLINE (no-API, no-write) reconstruction of phase boundaries (see below)
```

## Can we know the exact current qid from `run.log` ALONE? — NO

The only per-call log line is emitted by `src/openrouter_client.py:222`:
```
log(f"openrouter ok: model={...} id={...} usage={usage}")
```
It contains **only model id, generation id, and token/cost usage** — **no qid, no layer, no
index**. The dynamic layers (`dynamic_base_predictor`, `v12b_dynamic_layer`, `v13_dynamic_layer`,
`fastmcq_system`, `system_candidate_selector`) emit **no progress/qid log lines** at all. So
`run.log` by itself cannot identify the current qid.

## But the call order IS deterministic → reconstructable offline

Determinism findings (Task 3):
- **Base predictor** calls the model for **only the UNRESOLVED qids** (those `solve_formula_bank_sample`
  does not solve), **in input order** — not all qids.
- **V12B targets**: deterministic — `targets.sort(key=lambda t: (-t.priority_score, t.qid))`;
  priority uses only deterministic features. Permutations use **fixed seeds** (no shuffle).
- **V13 targets**: deterministic — same sort; layer assignment from question/route.
- **No qid shuffle anywhere.**
- **`--resume` is accepted but UNUSED** — there is **no cache/resume state file** containing qids.
  The only qid-bearing files (`work/v12b_dynamic_records.jsonl`, `work/v13_dynamic_records.jsonl`)
  are written **at the end of each layer**, so they don't exist mid-run.

Because target priority scoring is identical for the live "dynamic_api" base source and an
offline "dynamic_fallback" base source (both weak + low-confidence), an **offline no-API
reconstruction reproduces the live call order exactly**:

```
total qids                 : 463
formula_bank solved (det.) : 18    -> base API calls = 445   (calls #1..445, input order)
V12B targets (cap 50)      : 50    -> V12B API calls = 300   (calls #446..745, 6 perms/qid)
V13  targets (cap 50)      : 50    -> V13  API calls = 137   (calls #746..882, 1/layer)
total deterministic calls  : 882
```

## Current API call count + phase inference

- Snapshot A: `openrouter ok` count = **621** → window **V12B** [446..745]; reconstructed to
  **V12B target #30/50, qid=`test_0064`, permutation 2/6** (priority 9.5).
- Snapshot B (seconds later): count = **704** → still **V12B** [446..745]; `work/` still empty.

So the live run is currently in the **V12B option-permutation phase** (base finished at call
445). This phase is inferred from the **deterministic reconstruction + live call count**, not
from `run.log` content. The exact qid is therefore an **inference** (strong, given determinism),
not a value readable from the log.

## Is `work/` still empty? When do the JSONL files appear?

`work/` is **still empty** (0 entries). Per the layer code:
- `work/v12b_dynamic_records.jsonl` is written at the **end of the V12B layer** (~after call
  #745).
- `work/v13_dynamic_records.jsonl` is written at the **end of the V13 layer** (~after call
  #882, only if ≥1 API result).
- The final `scratch/runs/public_api50_20260624_005107/pred.csv` is written last, by
  `run_fastmcq_system`.

## Discovered logging limitations

1. Per-call log has model/usage only — no qid/layer/index.
2. Layers print nothing during execution → no in-flight progress in `run.log`.
3. Intermediate JSONL is written only at layer completion (not streamed), so no mid-run qid trace.
4. `--resume` is a no-op (no state file), so there is no qid checkpoint to read.

## Recommended future logging changes (apply AFTER the live run finishes)

Add lightweight progress lines (stdout/log) inside the layers — purely additive, no behavior
change:
- `dynamic_base_predictor.predict_base_answers`: `[BASE] i/N qid=<qid> source=<...>` per sample.
- `v12b_dynamic_layer.run_v12b_layer`: `[V12B] i/N qid=<qid> permutation=j/k` per call.
- `v13_dynamic_layer.run_v13_layer`: `[V13] i/N qid=<qid> layer=<layer>` per call.
Optionally pass a `qid`/`tag` through `SelectiveAPIClient.chat` → `openrouter_client.log` so the
existing `openrouter ok` line carries the qid. Also consider streaming each record to the JSONL
as it is produced (append mode) so progress is inspectable mid-run, and implementing real
`--resume` (skip qids already in the JSONL). **Do not implement during the live run.**

## Confirmations

- **No API calls** by this diagnostic — only `ls/grep/find/sed/tail/wc` and one offline
  no-API, no-write Python reconstruction (imports deterministic modules; reads the public
  dataset; prints counts; writes nothing).
- **Running process untouched** — not stopped/killed/restarted/attached/modified.
- **No files modified** except this audit; no source/config/output/scratch/run files changed.
- `scratch/runs/` is gitignored (the live run is invisible to git).

## Git status

`git status --short`: no tracked modifications; only this new audit file is untracked.
Nothing committed.
