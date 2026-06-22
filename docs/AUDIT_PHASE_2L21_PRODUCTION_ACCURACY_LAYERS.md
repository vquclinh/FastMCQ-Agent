# Audit — Phase 2L.21: Production Accuracy Layers for the Hidden Test

**Date:** 2026-06-22  **Branch:** `main`  **Status:** uncommitted (for review)

## Summary

Added generalized production layers aimed at the ~2000-question hidden/private test:
route-aware prompts, formula hint injection (log-only), option-aware evidence packing,
a single JSON repair retry, resume/checkpoint for long runs, and a conservative
formula-bank expansion. All no-API, qid-free, and tested. **No final prediction was
generated; `outputs/pred.csv` was not created or overwritten.**

## Files changed

**New**
- `src/production_prompts.py` — route-aware MCQ prompts (calc/long_context/
  short_knowledge/law_admin/ambiguous/default) + repair prompt + `answer_needs_repair`.
- `src/option_evidence.py` — option-aware, deterministic, no-API evidence pack.
- `src/production_inference.py` — direct-prompt inference path (prompts + option
  evidence + hints + one JSON repair retry) over an injected client.
- `tests/test_production_layers.py` — 23 tests for A–E.

**Modified**
- `src/formula_bank_solver.py` — `detect_formula_hints` (Part B) + 5 new rules
  (capacitor series/parallel, mean/median/mode, break-even quantity, binary/decimal,
  cache AMAT).
- `scripts/run_production_pipeline.py` — resume/checkpoint (`completed_qids_from_log`,
  `atomic_write_predictions`, `--resume-from-log/--skip-existing/--checkpoint-every`),
  per-sample loop, optional `--direct-prompt` path, repair/route/option-evidence flags.
- `tests/test_formula_bank_solver.py` — +8 tests for the new rules.

## Prompt / layer architecture

Two base paths, selected by the runner:
1. **Graph solver (default):** the mature `openrouter_graph` solver (own routing,
   reranking, repair, verifier) → base answer.
2. **Direct-prompt path (`--direct-prompt`):** `production_inference.predict_one_direct`
   builds a **route-specific** prompt (calc asks for extracted values/formula/mapping;
   long_context prioritizes provided evidence; short_knowledge compares all options;
   law_admin answers and does not refuse; ambiguous reasons from first principles, no
   vote language), optionally injects the option-aware evidence pack + non-binding
   formula hints, calls the client, parses strict JSON, and does **one** repair retry
   if the answer is missing/invalid.

Both paths then pass through the **safe deterministic override layer**
(`production_policy.decide`: calc → concept → formula bank). Policy unchanged:
deterministic safe rule > base LLM; risky detections are log-only.

## Formula hint policy (Part B)

`detect_formula_hints(sample)` returns `{detected_family, risk_level, hint,
safe_to_override}`. A SAFE deterministic match is reported `safe_to_override=True`
(the override still applies via the policy). Keyword-only medium/high-risk families
(capacitor/inductor series-parallel, ideal gas, Bayes, quadratic roots, subnet hosts,
GDP identity, normal forms, DB keys) are `safe_to_override=False` — **hint only**,
attached to the prompt/log, never used as an answer.

## Option-aware retrieval design (Part C)

For long_context, score chunks against `stem + EACH option` separately, keep each
option's top chunk(s), union + dedup in reading order within a char budget → one
compact pack. Deterministic (tie-break by index). Lexical (dependency-free); a neural
reranker, if wired, is unaffected. It only improves CONTEXT — never selects an answer.
Logs: `evidence_selected_by_option`, `top_option_evidence_scores`, `evidence_pack_size`.

## JSON repair retry design (Part D)

`answer_needs_repair(answer, choices)` is True when the parsed answer is missing or
not one of the sample's labels. The direct path then issues exactly **one** compact
repair call whose allowed labels come from the sample's choices; logs `retry_count`
and `repair_status ∈ {not_needed, repaired, repair_failed}`. No self-consistency, no
multi-sampling. Falls back to `A` only if repair also fails.

## Resume / checkpoint design (Part E)

- `completed_qids_from_log(log)` → qids with a non-empty `final_answer` (append-only
  JSONL). `--resume-from-log` / `--skip-existing` filter out completed qids.
- Per-sample loop; `--checkpoint-every N` atomically writes partial predictions
  (`atomic_write_predictions` = temp file + `os.replace`) so a crash never corrupts
  the output. Final write is also atomic; resumed + newly-predicted qids are merged.
- Summary logs `completed_resumed`, `newly_predicted`, `overrides_applied`.

## Added formula coverage (Part F)

New conservative rules (each: positive + decline test, unique-match-only, qid-free):
`capacitor_series_parallel` (requires "tương đương"), `mean`/`median`/`mode` (explicit
data list + exactly one statistic; declines on tie/no-data), `break_even_quantity`
(FC/(P−VC), P>VC), `binary_decimal` (both directions), `cache_amat`
(hit+miss·penalty). Plus the 2L.20 batch (kinetic/potential energy, motion, density,
pressure, freq-period, circle/triangle area, profit, ROI, depreciation, moles,
concentration).

## Tests run and results

- `compileall -q src scripts tests`: **OK**
- `pytest -q`: **386 passed** (was 363; +23).
- **Public regression:** running the formula bank over v8_clean still yields exactly
  **1** change (the verified `pythagorean_distance` fix) — the +5 rules introduced
  **no new misfires** on the public set.
- Readiness scan (no API): 463 questions, 17 fireable safe rules, 146 calc-route
  coverage gaps (LLM-handled) — unchanged, as the new rules target the hidden test.

## Confirmations

- **No OpenRouter/API call** in this phase (direct path tested with a fake client;
  graph path not executed).
- **No final prediction generated**; no `pred_v10`; `outputs/pred.csv` not created or
  overwritten (protected-output guard remains).
- No qid hardcoding; no public-test answer table; external 3-LLM sheet not used.
- `outputs/scratch` not deleted; `outputs/*` gitignored.

## Final human-run command (manual; contacts OpenRouter)

Default graph path with resume/checkpoint for the 2000-question private run:

```bash
.venv/bin/python scripts/run_production_pipeline.py \
  --input public-test_1780368312.json \
  --output outputs/pred_production_user_run.csv \
  --preset competition_qwen35_9b \
  --log-path outputs/run_production_user_run.jsonl \
  --skip-existing --checkpoint-every 50
```
(Optional alternative base: add `--direct-prompt --json-repair-retry --route-prompts
--option-evidence` to use the route-aware direct path instead of the graph solver.)
The Docker entrypoint runs the same preset on the auto-detected `/data` input into
`/output/pred.csv`.

## git status

```
 M Dockerfile
?? scripts/run_production_pipeline.py
?? src/production_prompts.py
?? src/option_evidence.py
?? src/production_inference.py
?? src/production_policy.py
?? src/formula_bank_solver.py
?? scripts/audit_hidden_generalization_readiness.py
?? scripts/docker_entrypoint.sh
?? scripts/apply_formula_bank_to_predictions.py
?? tests/test_production_layers.py
?? tests/test_production_pipeline.py
?? tests/test_formula_bank_solver.py
?? docs/AUDIT_PHASE_2L19_*.md, docs/AUDIT_PHASE_2L20_*.md, docs/AUDIT_PHASE_2L21_*.md
```
(Plus still-uncommitted files from earlier 2L.x phases; `outputs/*` and `scratch/*`
are gitignored.)

## Risks / caveats

- The direct-prompt path is an *alternative* to the mature graph solver; it has not
  been A/B-validated against the graph on real inference and is opt-in (`--direct-prompt`).
- Formula-bank additions are conservative and decline on ambiguity; the public set
  shows no new misfires, but the hidden test may surface phrasings that mis-trigger —
  each rule requires a unique safe match, which bounds the risk.
- Net hidden-test gain is unverified until the operator runs full inference and the
  leaderboard reports.

## Recommended next step

Operator runs the manual command above (graph path, with `--skip-existing
--checkpoint-every 50` for safety on 2000 questions), validates the output, and — if
accepted — promotes it to `outputs/pred.csv` via the explicit archive-first step (as
in 2L.18). Optionally A/B the `--direct-prompt` path on a small subset first. Do not
commit until a result is accepted.
